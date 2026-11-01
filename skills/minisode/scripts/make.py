#!/usr/bin/env python3
"""Generate the assets declared in the episode plan: character sheets, location plates, keyframes, voices.

Each asset in episode.json may carry a "make" recipe: {endpoint, args, files}. Files are local paths relative
to the plan, URLs, or "@asset_id" to use another asset's file (a keyframe built from a plate and two sheets).
Assets are built in dependency order, priced before they run, and logged in the ledger through fal_run.py.

Usage:
  python3 make.py episode.json --estimate           # what every missing asset will cost, nothing runs
  python3 make.py episode.json                      # build every asset whose file is missing
  python3 make.py episode.json nora_sheet kf_s01    # only these (and only if missing)
  python3 make.py episode.json theo_voice --force   # rebuild; the old file is kept as name.v1.ext

Look at every result before building what depends on it: a wrong sheet poisons every shot.
Needs FAL_KEY and fal-client unless --estimate.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fal_run  # noqa: E402


def deps(asset):
    out = []
    for v in (asset.get('make', {}).get('files') or {}).values():
        for f in (v if isinstance(v, list) else [v]):
            if isinstance(f, str) and f.startswith('@'):
                out.append(f[1:])
    return out


def order(assets, wanted):
    seen, out = set(), []

    def visit(aid, trail=()):
        if aid in seen:
            return
        if aid in trail:
            sys.exit(f'dependency loop: {" -> ".join(trail + (aid,))}')
        if aid not in assets:
            sys.exit(f'unknown asset {aid}')
        for d in deps(assets[aid]):
            visit(d, trail + (aid,))
        seen.add(aid)
        out.append(aid)

    for aid in wanted:
        visit(aid)
    return out


def keep_old(path):
    if not os.path.exists(path):
        return
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f'{stem}.v{n}{ext}'):
        n += 1
    shutil.move(path, f'{stem}.v{n}{ext}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plan')
    ap.add_argument('ids', nargs='*')
    ap.add_argument('--estimate', action='store_true')
    ap.add_argument('--force', action='store_true', help='rebuild even if the file exists')
    a = ap.parse_args()

    ep = json.load(open(a.plan, encoding='utf-8'))
    base = os.path.dirname(os.path.abspath(a.plan))
    assets = ep.get('assets', {})
    os.environ.setdefault('MINISODE_LEDGER', os.path.join(base, 'ledger.json'))
    if ep.get('budget_usd') and not os.environ.get('MINISODE_BUDGET'):
        os.environ['MINISODE_BUDGET'] = str(ep['budget_usd'])
    path_of = {aid: os.path.join(base, x['file']) for aid, x in assets.items() if x.get('file')}
    wanted = a.ids or [aid for aid, x in assets.items() if x.get('make')]
    plan = [aid for aid in order(assets, wanted)
            if assets[aid].get('make') and (a.force and aid in (a.ids or wanted) or not os.path.exists(path_of[aid]))]
    if not plan:
        print('nothing to build: every asset file exists')
        return

    total = 0.0
    for aid in plan:
        x = assets[aid]
        mk = x['make']
        args = dict(mk.get('args') or {})
        media = {}
        missing = []
        for key, val in (mk.get('files') or {}).items():
            vals = val if isinstance(val, list) else [val]
            resolved = []
            for f in vals:
                p = path_of.get(f[1:]) if f.startswith('@') else (f if f.startswith('http') else os.path.join(base, f))
                if not p.startswith('http') and not os.path.exists(p):
                    missing.append(f)
                if p.lower().endswith(fal_run.MEDIA_EXT) and os.path.exists(p):
                    media[p] = fal_run.media_seconds(p) or 5.0
                resolved.append(p)
            args[key] = resolved if isinstance(val, list) or key in fal_run.LIST_KEYS else resolved[0]
        est = fal_run.estimate(mk['endpoint'], args, media, mk.get('price'))
        total += est or 0
        line = f'{aid:22s} {mk["endpoint"]:36s} ~{est:.3f} USD' if est is not None else f'{aid}: unknown price'
        if a.estimate:
            print(line + (f'   (needs {", ".join(missing)})' if missing else ''))
            continue
        if missing:
            sys.exit(f'{aid}: input files missing: {", ".join(missing)}')
        for key, val in list(args.items()):
            if key in (mk.get('files') or {}):
                args[key] = [fal_run.upload(p) for p in val] if isinstance(val, list) else fal_run.upload(val)
                if isinstance(val, list):
                    for p, u in zip(val, args[key]):
                        if p in media:
                            media[u] = media[p]
        dest = path_of[aid]
        out_dir = os.path.dirname(dest)
        name = os.path.splitext(os.path.basename(dest))[0] + '.raw'
        print(line, flush=True)
        try:
            result, files, cost = fal_run.run(mk['endpoint'], args, out_dir, name, mk.get('price'), media=media)
        except fal_run.OverBudget as e:
            sys.exit(f'BUDGET: {e}')
        if not files:
            sys.exit(f'{aid}: the model returned no file: {json.dumps(result)[:400]}')
        if a.force:
            keep_old(dest)
        first = files[0]
        ext = os.path.splitext(first)[1]
        if ext.lower() != os.path.splitext(dest)[1].lower():
            print(f'  note: model returned {ext}, saved as {dest} anyway (rename the plan entry if it matters)')
        shutil.move(first, dest)
        for i, extra in enumerate(files[1:], 1):
            shutil.move(extra, f'{os.path.splitext(dest)[0]}.alt{i}{os.path.splitext(extra)[1]}')
        if x['type'] == 'audio':
            secs = fal_run.media_seconds(dest)
            if secs and not 2 <= secs <= 15:
                print(f'  ! {aid} lasts {secs:.1f} s; audio references must be 2-15 s (trim or rewrite the sample)')
        print(f'  -> {os.path.relpath(dest, base)}  {cost:.3f} USD')
    if a.estimate:
        print(f'{"":22s} {"total":36s} ~{total:.3f} USD')


if __name__ == '__main__':
    main()
