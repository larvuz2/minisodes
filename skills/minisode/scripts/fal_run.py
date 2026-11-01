#!/usr/bin/env python3
"""Run one fal model under a hard budget, download what it returns, and log the call.

Every generation of the episode goes through this script (or through shoot.py, which uses it), so one ledger
holds every call with its price. Before a call runs, its cost is estimated from the price table below; if
spent + reserved + estimate would pass the budget, the call is refused (exit code 3) and nothing is spent.
After the call, the final cost replaces the estimate (real video length, real reference tokens).

Usage:
  python3 fal_run.py fal-ai/nano-banana-pro/edit -o assets/characters --name nora_sheet \\
      --arg prompt="character sheet ..." --arg aspect_ratio=16:9 --file image_urls=study/f_012.jpg
  python3 fal_run.py elevenlabs/tts/eleven-v4 -o assets/voices --name nora \\
      --arg text="[quietly] You said you'd never come." --arg voice=Sarah --arg stability=0.35
  python3 fal_run.py elevenlabs/music/v2.5 -o music --name score --json composition_plan=music/plan.json
  python3 fal_run.py minimax/h3-max/reference-to-video --estimate --arg duration=13 --arg resolution=768P
  python3 fal_run.py --ledger                      # spend per endpoint, remaining budget

--arg key=value   JSON value if it parses (numbers, true, lists), else a string. Repeat for each field.
--file key=path   uploads a local file (cached by content hash in uploads.json) or passes a URL through;
                  repeat a list key to build a list (image_urls, reference_image_urls, ...).
--json key=path   loads a JSON file as the value (composition_plan, reference_conditions, inputs).
--price USD       your estimate for an endpoint missing from the price table (otherwise it is refused).

Ledger: ledger.json in the current directory, or MINISODE_LEDGER. Budget: --budget, MINISODE_BUDGET, or the
ledger's budget_usd (default 5). Needs FAL_KEY and `pip install fal-client` (not for --estimate/--ledger).
"""
import argparse
import contextlib
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.request

DEFAULT_BUDGET = 5.0
LIST_KEYS = ('image_urls', 'reference_image_urls', 'reference_video_urls', 'reference_audio_urls', 'keyterms')
MEDIA_EXT = ('.mp3', '.wav', '.m4a', '.aac', '.ogg', '.mp4', '.mov', '.webm')

# USD, checked against fal's pricing API (api.fal.ai/v1/models/pricing) in November 2026.
H3_PER_SECOND = {'480P': 0.05, '768P': 0.08, '1080P': 0.16}
H3_FREE_REF_TOKENS = 4096
H3_PER_1K_REF_TOKENS = 0.02
REF_TOKENS = {'image': 1024, 'audio_s': 80, 'video_s': 512}   # image and audio from fal's docs; video is a guess
PER_IMAGE = {'fal-ai/nano-banana-pro': 0.15, 'fal-ai/nano-banana-pro/edit': 0.15}
PER_1K_CHARS = {'elevenlabs/tts/eleven-v4': 0.08, 'elevenlabs/tts/eleven-v4-turbo': 0.05,
                'fal-ai/elevenlabs/tts/eleven-v3': 0.10, 'fal-ai/elevenlabs/text-to-dialogue/eleven-v3': 0.10}
PER_MINUTE = {'elevenlabs/music/v2.5': 0.60, 'fal-ai/elevenlabs/speech-to-text/scribe-v2': 0.008,
              'fal-ai/elevenlabs/voice-changer': 0.30, 'fal-ai/elevenlabs/audio-isolation': 0.10}
PER_CALL = {'google/lyria-3.5': 0.10, 'fal-ai/minimax/voice-design': 3.00, 'fal-ai/birefnet/v2': 0.01,
            'fal-ai/bria/background/remove': 0.02}
PER_SECOND = {'fal-ai/elevenlabs/sound-effects/v2': 0.002}


# ---------------------------------------------------------------- pricing

def media_seconds(path_or_url):
    """Duration of a local or remote media file, or None."""
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                              path_or_url], capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out) if out else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def h3_ref_tokens(args, media=None):
    media = media or {}
    n = len(args.get('reference_image_urls') or [])
    audio_s = sum(media.get(u, 5.0) for u in args.get('reference_audio_urls') or [])
    video_s = sum(media.get(u, 5.0) for u in args.get('reference_video_urls') or [])
    for c in args.get('reference_conditions') or []:
        if c.get('type') == 'image':
            n += 1
        elif c.get('type') == 'audio':
            audio_s += media.get(c.get('url'), 5.0)
        elif c.get('type') == 'video':
            video_s += media.get(c.get('url'), 5.0)
    return int(n * REF_TOKENS['image'] + audio_s * REF_TOKENS['audio_s'] + video_s * REF_TOKENS['video_s'])


def estimate(endpoint, args, media=None, price=None):
    """Estimated USD for one call, or None when the endpoint is unknown and no --price was given."""
    if price is not None:
        return float(price)
    if endpoint.startswith('minimax/h3-max/'):
        res = args.get('resolution', '768P')
        secs = float(args.get('duration', 5)) + 0.5            # the output can run ~0.7 s long
        tokens = h3_ref_tokens(args, media)
        extra = max(0, tokens - H3_FREE_REF_TOKENS) / 1000 * H3_PER_1K_REF_TOKENS
        return round(secs * H3_PER_SECOND.get(res, 0.08) + extra, 4)
    if endpoint in PER_IMAGE:
        mult = 2 if args.get('resolution') == '4K' else 1
        return PER_IMAGE[endpoint] * int(args.get('num_images', 1)) * mult
    if endpoint in PER_1K_CHARS:
        text = args.get('text') or ' '.join(b.get('text', '') for b in args.get('inputs') or [])
        return round(max(len(text), 1) / 1000 * PER_1K_CHARS[endpoint], 4)
    if endpoint in PER_MINUTE:
        if endpoint.startswith('elevenlabs/music'):
            plan = args.get('composition_plan') or {}
            ms = sum(c.get('duration_ms', 0) for c in plan.get('chunks', [])) or args.get('music_length_ms') or 60000
            return round(ms / 60000 * PER_MINUTE[endpoint], 4)
        src = args.get('audio_url') or args.get('video_url')
        secs = (media or {}).get(src) or 120.0
        return round(secs / 60 * PER_MINUTE[endpoint], 4)
    if endpoint in PER_CALL:
        return PER_CALL[endpoint]
    if endpoint in PER_SECOND:
        return round(float(args.get('duration_seconds') or 5) * PER_SECOND[endpoint], 4)
    return None


def final_cost(endpoint, args, result, est, out_files):
    """Replace the estimate with what the call really produced, when we can tell."""
    if endpoint.startswith('minimax/h3-max/') and isinstance(result, dict):
        res = args.get('resolution', '768P')
        vid = next((f for f in out_files if f.endswith('.mp4')), None)
        secs = media_seconds(vid) if vid else None
        secs = secs or float(args.get('duration', 5))
        tokens = result.get('reference_tokens') or h3_ref_tokens(args)
        extra = max(0, tokens - H3_FREE_REF_TOKENS) / 1000 * H3_PER_1K_REF_TOKENS
        return round(secs * H3_PER_SECOND.get(res, 0.08) + extra, 4)
    return est


# ---------------------------------------------------------------- ledger

class OverBudget(Exception):
    """The call would take spend past the budget; nothing was spent."""

def ledger_path():
    return os.environ.get('MINISODE_LEDGER') or os.path.abspath('ledger.json')


@contextlib.contextmanager
def locked_ledger(path=None, budget=None):
    """Read-modify-write the ledger under an exclusive lock, so parallel shots cannot overspend."""
    path = path or ledger_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    lock = open(path + '.lock', 'w')
    try:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        except ImportError:
            pass
        data = json.load(open(path)) if os.path.exists(path) else {'budget_usd': DEFAULT_BUDGET, 'calls': []}
        if budget is not None:
            data['budget_usd'] = float(budget)
        elif os.environ.get('MINISODE_BUDGET'):
            data['budget_usd'] = float(os.environ['MINISODE_BUDGET'])
        yield data
        data['spent_usd'] = round(sum(c.get('cost_usd') or 0 for c in data['calls'] if c.get('status') == 'done'), 4)
        data['reserved_usd'] = round(sum(c.get('estimate_usd') or 0 for c in data['calls']
                                         if c.get('status') == 'running'), 4)
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    finally:
        lock.close()


def committed(data):
    return sum((c.get('cost_usd') if c.get('status') == 'done' else c.get('estimate_usd')) or 0
               for c in data['calls'] if c.get('status') in ('done', 'running'))


def reserve(endpoint, name, est, args, budget=None):
    """Book the estimate before the call. Returns the call id; raises OverBudget if it does not fit."""
    with locked_ledger(budget=budget) as data:
        left = data['budget_usd'] - committed(data)
        if est > left + 1e-9:
            raise OverBudget(f'{endpoint} needs ~{est:.2f} USD, only {left:.2f} of {data["budget_usd"]:.2f} left; '
                             'not run')
        cid = f'{len(data["calls"]) + 1:04d}'
        data['calls'].append({'id': cid, 'status': 'running', 'endpoint': endpoint, 'name': name,
                              'started': time.strftime('%Y-%m-%dT%H:%M:%S'), 'estimate_usd': round(est, 4),
                              'prompt': args.get('prompt') or args.get('text'),
                              'arguments': {k: v for k, v in args.items() if k not in ('prompt', 'text')}})
        return cid


def settle(cid, status, cost=None, **extra):
    with locked_ledger() as data:
        for c in data['calls']:
            if c['id'] == cid:
                c['status'] = status
                c['cost_usd'] = round(cost if cost is not None else (c['estimate_usd'] if status == 'done' else 0), 4)
                c.update(extra)


def print_ledger():
    path = ledger_path()
    if not os.path.exists(path):
        print(f'no ledger at {path}')
        return
    data = json.load(open(path))
    per = {}
    for c in data['calls']:
        if c.get('status') == 'done':
            n, usd = per.get(c['endpoint'], (0, 0.0))
            per[c['endpoint']] = (n + 1, usd + (c.get('cost_usd') or 0))
    for ep, (n, usd) in sorted(per.items(), key=lambda x: -x[1][1]):
        print(f'{usd:8.3f} USD  {n:3d} calls  {ep}')
    spent = sum(u for _, u in per.values())
    print(f'{spent:8.3f} USD spent of {data["budget_usd"]:.2f}, {data["budget_usd"] - spent:.2f} left '
          f'({sum(1 for c in data["calls"] if c.get("status") == "failed")} failed calls, not billed here)')


# ---------------------------------------------------------------- fal

def parse_value(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def upload(path, cache_path=None):
    """Upload a local file to the fal CDN once; later calls reuse the URL (cache keyed by content hash)."""
    if path.startswith(('http://', 'https://', 'data:')):
        return path
    cache_path = cache_path or os.path.join(os.path.dirname(ledger_path()), 'uploads.json')
    digest = hashlib.sha1(open(path, 'rb').read()).hexdigest()
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    hit = cache.get(digest)
    if hit and time.time() - hit['t'] < 5 * 86400:
        return hit['url']
    import fal_client  # pip install fal-client
    url = fal_client.upload_file(path)
    cache[digest] = {'url': url, 'file': path, 't': time.time()}
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=1)
    return url


def urls_in(obj):
    """Every downloadable file URL in a fal result, with the key path it came from."""
    out = []
    if isinstance(obj, dict):
        if isinstance(obj.get('url'), str) and obj['url'].startswith('http'):
            out.append(('', obj['url'], obj.get('file_name') or obj.get('content_type')))
        for k, v in obj.items():
            if k != 'url':
                out += [(f'{k}.{p}'.strip('.'), u, n) for p, u, n in urls_in(v)]
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += [(f'{i}.{p}'.strip('.'), u, n) for p, u, n in urls_in(v)]
    return out


def ext_for(url, hint):
    ext = os.path.splitext(url.split('?')[0])[1]
    if ext and len(ext) <= 5:
        return ext
    return mimetypes.guess_extension(hint or '') or '.bin'


def run(endpoint, args, out='.', name=None, price=None, budget=None, media=None):
    """Estimate, reserve, call, download, settle. Returns (result, files, cost)."""
    est = estimate(endpoint, args, media, price)
    if est is None:
        sys.exit(f'{endpoint} has no price in the table; pass --price USD with your estimate')
    name = name or endpoint.replace('/', '_') + time.strftime('_%H%M%S')
    cid = reserve(endpoint, name, est, args, budget)
    import fal_client  # pip install fal-client
    t0 = time.time()
    try:
        handle = fal_client.submit(endpoint, arguments=args)
        result = handle.get()
    except Exception as e:  # noqa: BLE001 - any failure must release the reservation
        settle(cid, 'failed', 0, error=str(e)[:500], seconds=round(time.time() - t0, 1))
        raise
    os.makedirs(out, exist_ok=True)
    files = []
    found = urls_in(result)
    for i, (key, url, hint) in enumerate(found):
        dest = os.path.join(out, name + ('' if len(found) == 1 else f'_{i}') + ext_for(url, hint))
        urllib.request.urlretrieve(url, dest)
        files.append(dest)
    with open(os.path.join(out, name + '.result.json'), 'w') as f:
        json.dump(result, f, indent=1)
    cost = final_cost(endpoint, args, result, est, files)
    settle(cid, 'done', cost, request_id=getattr(handle, 'request_id', None), files=files,
           seconds=round(time.time() - t0, 1), seed=result.get('seed') if isinstance(result, dict) else None)
    return result, files, cost


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('endpoint', nargs='?')
    ap.add_argument('-o', '--out', default='.')
    ap.add_argument('--name', help='base name of the saved files (default: endpoint + time)')
    ap.add_argument('--arg', action='append', default=[], metavar='KEY=VALUE')
    ap.add_argument('--file', action='append', default=[], metavar='KEY=PATH')
    ap.add_argument('--json', action='append', default=[], metavar='KEY=PATH')
    ap.add_argument('--price', type=float, help='estimated USD for an endpoint missing from the price table')
    ap.add_argument('--budget', type=float, help='set the budget in USD (stored in the ledger)')
    ap.add_argument('--estimate', action='store_true', help='print the estimated cost and exit')
    ap.add_argument('--ledger', action='store_true', help='print spend per endpoint and exit')
    a = ap.parse_args()

    if a.ledger:
        print_ledger()
        return
    if not a.endpoint:
        ap.error('endpoint is required')
    args, media = {}, {}
    for kv in a.arg:
        k, v = kv.split('=', 1)
        args[k] = parse_value(v)
    for kv in a.json:
        k, p = kv.split('=', 1)
        args[k] = json.load(open(p))
    for kv in a.file:
        k, p = kv.split('=', 1)
        local_media = not p.startswith(('http://', 'https://', 'data:')) and p.lower().endswith(MEDIA_EXT)
        secs = (media_seconds(p) or 5.0) if local_media else None
        url = p if a.estimate else upload(p)
        if secs:
            media[url] = secs                   # audio/video length prices H3 reference tokens and per-minute models
        if k in args or k in LIST_KEYS:
            args.setdefault(k, [])
            args[k] = (args[k] if isinstance(args[k], list) else [args[k]]) + [url]
        else:
            args[k] = url

    if a.estimate:
        est = estimate(a.endpoint, args, media, a.price)
        print('unknown endpoint: pass --price' if est is None else f'{est:.3f} USD')
        return
    if not os.environ.get('FAL_KEY'):
        sys.exit('FAL_KEY is not set')
    try:
        result, files, cost = run(a.endpoint, args, a.out, a.name, a.price, a.budget, media)
    except OverBudget as e:
        sys.stderr.write(f'BUDGET: {e}\n')
        sys.exit(3)
    for f in files:
        print(f)
    if not files:
        print(json.dumps(result, indent=1)[:2000])
    print(f'cost {cost:.3f} USD', file=sys.stderr)


if __name__ == '__main__':
    main()
