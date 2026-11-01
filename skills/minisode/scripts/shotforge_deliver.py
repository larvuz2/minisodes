#!/usr/bin/env python3
"""Talk back to ShotForge while a minisode is made: progress notes, previews, the finished episode, or a failure.

ShotForge's Minisodes tab starts a Claude Code session with a request holding the episode id, the delivery URL
and a one-time delivery token. This script reports on the page: a short note with the current stage and the
money spent so far (read from the ledger), preview files (cast sheets, locations, voices, takes, the pace map)
shown while the work goes on, and the final upload of the episode with its clean master, poster and report.

Usage:
  python3 shotforge_deliver.py note "Writing the story" --stage story
  python3 shotforge_deliver.py preview cast assets/cast/nora_sheet.png assets/cast/theo_sheet.png
  python3 shotforge_deliver.py preview take takes/s01_t2.mp4 --label "Hook, take 2"
  python3 shotforge_deliver.py deliver out/ --entry final.mp4 --clean final_clean.mp4 --poster poster.jpg \\
      --report report.md --note "60 s, 21 shots, 7.80 USD"
  python3 shotforge_deliver.py fail "The budget ran out before the last sequence was usable"

Guided mode (the user approves the cast, the story and the locations in ShotForge; each phase is its own run):
  python3 shotforge_deliver.py checkpoint cast --items checkpoint/cast.json --state-dir .
  python3 shotforge_deliver.py checkpoint story --summary checkpoint/story.json --state-dir .
  python3 shotforge_deliver.py restore <state_url> [<state_url> ...] -d .     # at the start of the next phase

  checkpoint uploads every item's image and audio, packs the work folder (without takes, out, review, env.sh,
  node_modules) into state parts of 45 MB at most, sends it all, and sets the episode to "waiting for your
  approval". items.json: {"items": [{"id", "group", "label", "image", "audio", "description"}]}.
  summary.json (story): {"title", "logline", "beats": [{"id", "time", "text", "lines": []}], "cliffhanger"}.
  restore downloads the parts, joins them and unpacks them safely. It needs no token.

Stages: story, cast, locations, voices, shoot, edit, music, deliver. Preview kinds: cast, location, voice,
keyframe, take, pace, music. --episode, --url, --token default to SHOTFORGE_EPISODE, SHOTFORGE_URL,
SHOTFORGE_TOKEN; the spend comes from MINISODE_LEDGER (or ./ledger.json) unless --spent is given.
Large images are sent as 1600 px JPEGs. Standard library only (ffmpeg for the image shrink).
"""
import argparse
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

TYPES = {'.mp4': 'video/mp4', '.mov': 'video/quicktime', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
         '.m4a': 'audio/mp4', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
         '.svg': 'image/svg+xml', '.json': 'application/json', '.md': 'text/markdown; charset=utf-8',
         '.txt': 'text/plain; charset=utf-8', '.ass': 'text/plain; charset=utf-8', '.glb': 'model/gltf-binary'}
STAGES = ('story', 'cast', 'locations', 'voices', 'shoot', 'edit', 'music', 'deliver')
KINDS = ('cast', 'location', 'voice', 'keyframe', 'take', 'pace', 'music')
BATCH = 50
SHRINK_BYTES = 1_500_000
CHECKPOINTS = ('cast', 'story', 'locations')
STATE_SKIP = {'takes', 'out', 'review', 'node_modules', 'pace', 'pace_plan', 'trailer.mp4', 'env.sh',
              'package.json', 'package-lock.json', 'checkpoint'}
STATE_PART = 45_000_000


def post(url, body, attempts=3):
    data = json.dumps(body).encode()
    for i in range(attempts):
        req = urllib.request.Request(url, data=data, method='POST', headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.loads(res.read() or b'{}')
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors='replace')[:400]
            if e.code < 500 or i == attempts - 1:
                sys.exit(f'ShotForge answered {e.code}: {detail}')
        except urllib.error.URLError as e:
            if i == attempts - 1:
                sys.exit(f'Could not reach ShotForge: {e.reason}')
        time.sleep(2 * (i + 1))


def put(url, path, content_type, attempts=3):
    with open(path, 'rb') as f:
        data = f.read()
    for i in range(attempts):
        req = urllib.request.Request(url, data=data, method='PUT',
                                     headers={'Content-Type': content_type, 'x-upsert': 'true'})
        try:
            with urllib.request.urlopen(req, timeout=600) as res:
                res.read()
                return
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors='replace')[:300]
            if e.code < 500 or i == attempts - 1:
                sys.exit(f'Upload of {path} failed ({e.code}): {detail}')
        except urllib.error.URLError as e:
            if i == attempts - 1:
                sys.exit(f'Upload of {path} failed: {e.reason}')
        time.sleep(2 * (i + 1))


def spent_from_ledger():
    path = os.environ.get('MINISODE_LEDGER') or 'ledger.json'
    try:
        return round(json.load(open(path)).get('spent_usd', 0), 2)
    except (OSError, ValueError):
        return None


def web_image(path, tmp):
    """Big PNG sheets go up as 1600 px JPEGs: the page only shows them."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp') or os.path.getsize(path) <= SHRINK_BYTES:
        return path
    dest = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + '.jpg')
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vf', "scale='min(1600,iw)':-2", '-q:v', '3', dest])
    return dest if r.returncode == 0 else path


def upload(a, auth, pairs):
    """pairs: [(local file, path under the episode's out/ folder)]"""
    for start in range(0, len(pairs), BATCH):
        batch = pairs[start:start + BATCH]
        answer = post(a.url, {'action': 'upload-urls', 'paths': [rel for _, rel in batch], **auth})
        urls = {u['path']: u['url'] for u in answer.get('uploads', [])}
        for p, rel in batch:
            ext = os.path.splitext(rel)[1].lower()
            put(urls[rel], p, TYPES.get(ext) or mimetypes.guess_type(rel)[0] or 'application/octet-stream')
            print(f'  {rel}  ({os.path.getsize(p) / 1e6:.1f} MB)')


def folder_files(folder):
    for d, dirs, files in os.walk(folder):
        dirs[:] = sorted(x for x in dirs if not x.startswith('.'))
        for name in sorted(files):
            if not name.startswith('.'):
                full = os.path.join(d, name)
                yield full, os.path.relpath(full, folder).replace(os.sep, '/')


def pack_state(src, tmp):
    """The work folder as a .tgz split in parts small enough for storage (the token file stays out)."""
    import tarfile
    tgz = os.path.join(tmp, 'state.tgz')
    with tarfile.open(tgz, 'w:gz') as t:
        for name in sorted(os.listdir(src)):
            if name in STATE_SKIP or name.startswith('.'):
                continue
            t.add(os.path.join(src, name), arcname=name)
    parts = []
    with open(tgz, 'rb') as f:
        while True:
            chunk = f.read(STATE_PART)
            if not chunk:
                break
            part = os.path.join(tmp, f'state.tgz.{len(parts):02d}')
            with open(part, 'wb') as out:
                out.write(chunk)
            parts.append(part)
    return parts


def restore(urls, dest):
    """Download the state parts in order, join them and unpack them, refusing any path outside dest."""
    import io
    import tarfile
    data = b''
    for u in urls:
        with urllib.request.urlopen(u, timeout=600) as res:
            data += res.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
        for m in t.getmembers():
            parts = m.name.split('/')
            if m.name.startswith('/') or '..' in parts or m.issym() or m.islnk() or m.isdev():
                sys.exit(f'unsafe entry in the state: {m.name}')
        os.makedirs(dest, exist_ok=True)
        try:
            t.extractall(dest, filter='data')
        except TypeError:                      # Python before 3.12
            t.extractall(dest)
    print(f'restored {len(data) / 1e6:.1f} MB into {dest}')


def safe_id(text):
    import re
    return re.sub(r'[^\w-]+', '_', str(text))[:60] or 'item'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('action', choices=['note', 'preview', 'deliver', 'fail', 'checkpoint', 'restore'])
    ap.add_argument('values', nargs='+', help='the note, the failure reason, "<kind> <files...>", the out folder, '
                                              'the checkpoint stage, or the state URLs to restore')
    ap.add_argument('--items', help='checkpoint: items.json')
    ap.add_argument('--summary', help='checkpoint: summary.json (story)')
    ap.add_argument('--state-dir', help='checkpoint: the work folder to save for the next phase')
    ap.add_argument('-d', '--dir', default='.', help='restore: where to unpack the state')
    ap.add_argument('--stage', choices=STAGES)
    ap.add_argument('--spent', type=float, help='USD spent so far (default: from the ledger)')
    ap.add_argument('--label', help='preview: label for a single file')
    ap.add_argument('--entry', default='final.mp4')
    ap.add_argument('--clean')
    ap.add_argument('--poster')
    ap.add_argument('--report')
    ap.add_argument('--note', default='')
    ap.add_argument('--episode', default=os.environ.get('SHOTFORGE_EPISODE'))
    ap.add_argument('--url', default=os.environ.get('SHOTFORGE_URL'))
    ap.add_argument('--token', default=os.environ.get('SHOTFORGE_TOKEN'))
    a = ap.parse_args()
    if a.action == 'restore':
        restore(a.values, a.dir)
        return
    if not (a.episode and a.url and a.token):
        sys.exit('--episode, --url and --token are required (or SHOTFORGE_EPISODE, SHOTFORGE_URL, SHOTFORGE_TOKEN)')
    auth = {'episodeId': a.episode, 'token': a.token}
    spent = a.spent if a.spent is not None else spent_from_ledger()

    if a.action in ('note', 'fail'):
        body = {'action': a.action, 'note': ' '.join(a.values)[:300], **auth}
        if a.action == 'note':
            if a.stage:
                body['stage'] = a.stage
            if spent is not None:
                body['spent_usd'] = spent
        post(a.url, body)
        print(f'{a.action} sent' + (f' (stage {a.stage})' if a.stage else '') + (f', spent {spent}' if spent else ''))
        return

    if a.action == 'preview':
        kind, files = a.values[0], a.values[1:]
        if kind not in KINDS or not files:
            sys.exit(f'preview needs a kind ({", ".join(KINDS)}) and files')
        with tempfile.TemporaryDirectory() as tmp:
            pairs = []
            for f in files:
                if not os.path.isfile(f):
                    sys.exit(f'{f} not found')
                src = web_image(f, tmp)
                pairs.append((src, f'previews/{kind}/{os.path.basename(src)}'))
            upload(a, auth, pairs)
        labels = [a.label if a.label and len(files) == 1 else
                  os.path.splitext(os.path.basename(f))[0].replace('_', ' ') for f in files]
        post(a.url, {'action': 'preview', 'items': [{'path': rel, 'kind': kind, 'label': lab}
                                                     for (_, rel), lab in zip(pairs, labels)], **auth})
        print(f'{len(pairs)} {kind} preview(s) shown')
        return

    if a.action == 'checkpoint':
        stage = a.values[0]
        if stage not in CHECKPOINTS:
            sys.exit(f'checkpoint stage must be one of {", ".join(CHECKPOINTS)}')
        items = json.load(open(a.items, encoding='utf-8')).get('items', []) if a.items else []
        summary = json.load(open(a.summary, encoding='utf-8')) if a.summary else None
        if stage == 'story' and not summary:
            sys.exit('the story checkpoint needs --summary')
        if stage != 'story' and not items:
            sys.exit(f'the {stage} checkpoint needs --items')
        state = []
        with tempfile.TemporaryDirectory() as tmp:
            pairs = []
            for it in items:
                it['id'] = safe_id(it.get('id') or it.get('label'))
                for key in ('image', 'audio'):
                    f = it.get(key)
                    if not f:
                        continue
                    if not os.path.isfile(f):
                        sys.exit(f'{f} not found')
                    src = web_image(f, tmp) if key == 'image' else f
                    rel = f'checkpoint/{stage}/{it["id"]}_{key}{os.path.splitext(src)[1].lower()}'
                    pairs.append((src, rel))
                    it[key] = rel
            if a.state_dir:
                for part in pack_state(a.state_dir, tmp):
                    rel = f'state/{os.path.basename(part)}'
                    pairs.append((part, rel))
                    state.append(rel)
            if pairs:
                upload(a, auth, pairs)
        body = {'action': 'checkpoint', 'stage': stage, 'items': items, 'summary': summary, 'state': state,
                'note': a.note or f'Your {stage} is ready for review.', **auth}
        if spent is not None:
            body['spent_usd'] = spent
        post(a.url, body)
        print(f'{stage} checkpoint sent: {len(items)} items, {len(state)} state part(s); waiting for approval')
        return

    folder = a.values[0]
    if not os.path.isfile(os.path.join(folder, a.entry)):
        sys.exit(f'{a.entry} not found in {folder}')
    files = list(folder_files(folder))
    total = sum(os.path.getsize(p) for p, _ in files)
    for p, rel in files:
        if os.path.getsize(p) > 50_000_000:
            print(f'warning: {rel} is {os.path.getsize(p) // 1_000_000} MB; storage may refuse files over 50 MB')
    print(f'uploading {len(files)} files, {total / 1e6:.1f} MB')
    upload(a, auth, files)
    body = {'action': 'deliver', 'entry': a.entry, 'note': a.note, **auth}
    for key in ('clean', 'poster', 'report'):
        if getattr(a, key):
            body[key] = getattr(a, key)
    if spent is not None:
        post(a.url, {'action': 'note', 'note': 'Uploading the episode…', 'stage': 'deliver', 'spent_usd': spent, **auth})
    answer = post(a.url, body)
    print(f'delivered: {answer.get("url")}')


if __name__ == '__main__':
    main()
