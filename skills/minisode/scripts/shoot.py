#!/usr/bin/env python3
"""Film sequences of the episode with the video model: one call per take, priced and logged in the ledger.

Builds the prompt and the ordered references with prompt.py, uploads the files once (cached), sends the
request through fal_run.py under the episode budget, and saves takes/<seq>_t<N>.mp4 with a sidecar .json
(prompt, reference map, seed, cost). Takes of different sequences can run in parallel; the ledger lock keeps
them inside the budget.

Usage:
  python3 shoot.py episode.json s01 --dry-run          # prompt, payload, price; nothing is sent
  python3 shoot.py episode.json s01                    # one take of s01
  python3 shoot.py episode.json s01 s02 s03 --jobs 3   # three sequences at once
  python3 shoot.py episode.json s04 --takes 2          # two takes of s04 (different seeds)
  python3 shoot.py episode.json s02 --start chain      # open on the last kept frame of the previous sequence
  python3 shoot.py episode.json s03 --video-ref cam_push_s03   # last resort: a blockout camera move as Video 1

--start/--end take an asset id, a file, "chain" (start only) or "none", and override the plan.
The first-frame image fixes composition and continuity; references keep identity. Needs FAL_KEY unless --dry-run.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fal_run  # noqa: E402
import prompt as P  # noqa: E402


def h3_args(b, up):
    """minimax/h3-max/reference-to-video. Add an adapter per model; the plan's video_model picks it."""
    args = {'prompt': b['prompt'], 'prompt_expansion_mode': 'disabled', 'duration': b['duration'],
            'resolution': b['resolution'], 'aspect_ratio': b['aspect_ratio']}
    for key, files in (('reference_image_urls', b['reference_image_files']),
                       ('reference_audio_urls', b['reference_audio_files']),
                       ('reference_video_urls', b['reference_video_files'])):
        if files:
            args[key] = [up(f) for f in files]
    if b.get('start_image'):
        args['image_url'] = up(b['start_image'])
    if b.get('end_image'):
        args['end_image_url'] = up(b['end_image'])
    if b.get('seed') is not None:
        args['seed'] = b['seed']
    return args


ADAPTERS = {'minimax/h3-max/reference-to-video': h3_args}


def kept_takes(base):
    path = os.path.join(base, 'review', 'takes.json')
    return json.load(open(path)) if os.path.exists(path) else {}


def chain_frame(ep, base, seq_id):
    """The last usable frame of the kept take of the sequence before seq_id, saved as a PNG."""
    ids = [s['id'] for s in ep['sequences']]
    i = ids.index(seq_id)
    if i == 0:
        return None, 'chain: first sequence has nothing before it'
    prev = ids[i - 1]
    kept = [(k, v) for k, v in kept_takes(base).items() if v.get('seq') == prev and v.get('verdict') == 'keep']
    if not kept:
        return None, f'chain: no kept take of {prev} yet (review it with review_take.py --verdict keep)'
    take, info = kept[-1]
    t_out = (info.get('usable') or [[0, None]])[-1][1]
    src = os.path.join(base, 'takes', take + '.mp4')
    dest = os.path.join(base, 'takes', f'{prev}_end.png')
    seek = ['-ss', str(max(0, t_out - 0.05))] if t_out else ['-sseof', '-0.1']
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *seek, '-i', src, '-frames:v', '1', dest], check=True)
    return dest, None


def next_take(base, seq_id, k):
    nums = [int(m.group(1)) for f in glob.glob(os.path.join(base, 'takes', f'{seq_id}_t*.mp4'))
            if (m := re.search(r'_t(\d+)\.mp4$', f))]
    start = max(nums, default=0) + 1
    return list(range(start, start + k))


def frame_override(ep, base, value):
    if value in (None, ''):
        return None
    if value == 'none':
        return ''
    a = ep.get('assets', {}).get(value)
    return os.path.join(base, a['file']) if a else value


def shoot_one(ep, base, seq_id, n, opts):
    b = P.build(ep, seq_id, base)
    if opts.video_ref:
        ep2 = json.loads(json.dumps(ep))
        for s in ep2['sequences']:
            if s['id'] == seq_id:
                s['video_refs'] = s.get('video_refs', []) + opts.video_ref
        b = P.build(ep2, seq_id, base)
    for key, val in (('start_image', opts.start), ('end_image', opts.end)):
        if val is not None:
            b[key] = frame_override(ep, base, val)
    if b.get('start_image') == 'chain':
        b['start_image'], why = chain_frame(ep, base, seq_id) if not opts.dry_run else ('<last frame of previous kept take>', None)
        if why:
            b['warnings'].append(why)
    if opts.resolution:
        b['resolution'] = opts.resolution
    if opts.seed is not None:
        b['seed'] = opts.seed + n
    model = ep.get('video_model', 'minimax/h3-max/reference-to-video')
    if model not in ADAPTERS:
        raise SystemExit(f'no adapter for {model}; add one to ADAPTERS in shoot.py')
    name = f'{seq_id}_t{n}'
    media = {}
    for f in b['reference_audio_files'] + b['reference_video_files']:
        if os.path.exists(f):
            media[f] = fal_run.media_seconds(f) or 5.0
    if opts.dry_run:
        args = ADAPTERS[model](b, lambda f: f)
        est = fal_run.estimate(model, args, media)
        return name, {'prompt': b['prompt'], 'args': {k: v for k, v in args.items() if k != 'prompt'},
                      'tags': b['tags'], 'estimate_usd': est, 'warnings': b['warnings']}
    missing = [f for f in b['reference_image_files'] + b['reference_audio_files'] + b['reference_video_files']
               + [b.get('start_image') or '', b.get('end_image') or ''] if f and not os.path.exists(f)]
    if missing:
        raise SystemExit(f'{name}: missing files {missing}; build them with make.py first')
    uploaded = {}

    def up(f):
        uploaded[f] = fal_run.upload(f)
        return uploaded[f]

    args = ADAPTERS[model](b, up)
    for f, secs in list(media.items()):
        if f in uploaded:
            media[uploaded[f]] = secs
    result, files, cost = fal_run.run(model, args, os.path.join(base, 'takes'), name, media=media)
    video = next((f for f in files if f.endswith('.mp4')), None)
    side = {'seq': seq_id, 'take': n, 'model': model, 'file': video and os.path.relpath(video, base),
            'seed': result.get('seed'), 'cost_usd': cost, 'tags': b['tags'], 'prompt': b['prompt'],
            'start_image': b.get('start_image') and os.path.relpath(b['start_image'], base),
            'args': {k: v for k, v in args.items() if k != 'prompt'}, 'warnings': b['warnings'],
            'reference_tokens': result.get('reference_tokens')}
    with open(os.path.join(base, 'takes', name + '.json'), 'w') as f:
        json.dump(side, f, indent=1)
    return name, side


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plan')
    ap.add_argument('sequences', nargs='+')
    ap.add_argument('--takes', type=int, default=1, help='takes per sequence')
    ap.add_argument('--jobs', type=int, default=1, help='calls in flight at once')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--start', help='asset id, file, "chain" or "none"')
    ap.add_argument('--end', help='asset id, file or "none"')
    ap.add_argument('--video-ref', action='append', default=[], metavar='ASSET_ID')
    ap.add_argument('--resolution', choices=['480P', '768P', '1080P'])
    ap.add_argument('--seed', type=int, help='base seed; take N uses seed + N')
    a = ap.parse_args()

    ep, base = P.load(a.plan)
    os.environ.setdefault('MINISODE_LEDGER', os.path.join(base, 'ledger.json'))
    if ep.get('budget_usd') and not os.environ.get('MINISODE_BUDGET'):
        os.environ['MINISODE_BUDGET'] = str(ep['budget_usd'])
    os.makedirs(os.path.join(base, 'takes'), exist_ok=True)
    jobs = [(s, n) for s in a.sequences for n in (next_take(base, s, a.takes) if not a.dry_run else [0])]
    failed = 0
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        futs = {pool.submit(shoot_one, ep, base, s, n, a): (s, n) for s, n in jobs}
        for fut in cf.as_completed(futs):
            s, n = futs[fut]
            try:
                name, side = fut.result()
            except fal_run.OverBudget as e:
                print(f'{s}: BUDGET: {e}', file=sys.stderr)
                failed += 1
                continue
            except (Exception, SystemExit) as e:  # noqa: BLE001 - report every failed take, keep the others
                print(f'{s}: failed: {e}', file=sys.stderr)
                failed += 1
                continue
            if a.dry_run:
                print(f'===== {s}: ~{side["estimate_usd"]:.3f} USD')
                print(json.dumps(side['args'], indent=1))
                print(side['prompt'])
            else:
                print(f'{name}: {side["file"]}  {side["cost_usd"]:.3f} USD  seed {side["seed"]}')
            for w in side['warnings']:
                print(f'  ! {w}')
    sys.exit(3 if failed else 0)


if __name__ == '__main__':
    main()
