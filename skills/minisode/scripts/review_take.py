#!/usr/bin/env python3
"""Review a take so you can judge it without watching it: frames, cuts against the plan, sound, words.

You cannot watch video, so this turns a take into evidence: a contact sheet with time stamps, the cuts the
model made against the cuts the plan asked for, loudness and silences, and (with --transcribe) what was
actually said against the script, line by line, with timing. Then you record a verdict and the usable ranges;
review/takes.json keeps them for shoot.py (chaining), the edit and the usable-footage rate.

Usage:
  python3 review_take.py takes/s01_t1.mp4 --plan episode.json                 # evidence, free
  python3 review_take.py takes/s01_t1.mp4 --plan episode.json --transcribe    # + words (Scribe v2, ~0.01 USD)
  python3 review_take.py takes/s01_t1.mp4 --verdict keep --usable 0.2-6.1,6.4-12.8 \\
      --score identity=2,continuity=2,lipsync=2,performance=1,camera=2,artifacts=2 --note "Theo's ring flips hand at 9 s"
  python3 review_take.py --summary --plan episode.json                         # every take, usable rate

Scores are 0 (broken), 1 (usable with care), 2 (good). Verdicts: keep, salvage (parts are usable), retake.
Needs ffmpeg/ffprobe; --transcribe needs FAL_KEY and fal-client.
"""
import argparse
import difflib
import json
import math
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RUBRIC = ('identity', 'continuity', 'lipsync', 'performance', 'camera', 'artifacts')


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                          'stream=codec_type,width,height,r_frame_rate:format=duration', '-of', 'json', path],
                         capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    v = next(s for s in d['streams'] if s['codec_type'] == 'video')
    num, den = v['r_frame_rate'].split('/')
    return {'duration': round(float(d['format']['duration']), 3), 'width': v['width'], 'height': v['height'],
            'fps': round(int(num) / int(den), 3), 'audio': any(s['codec_type'] == 'audio' for s in d['streams'])}


def sheet(path, out, info, every=0.5, with_frames=True):
    cols = 6
    n = max(1, math.ceil(info['duration'] / every))
    rows = math.ceil(n / cols)
    w = 270 if info['height'] > info['width'] else 400
    # label each frame with its source time before resampling, so the stamp is the real time in the take
    stamp = "%{eif\\:t\\:d}.%{eif\\:mod(t*10\\,10)\\:d} s"
    vf = (f"scale={w}:-2,drawtext=font=DejaVu Sans:text='{stamp}':x=6:y=6:fontsize={w // 11}:fontcolor=white:"
          f"box=1:boxcolor=black@0.6:boxborderw=4,fps=1/{every},tile={cols}x{rows}:padding=4:color=white")
    dest = os.path.join(out, 'sheet.jpg')
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vf', vf, '-frames:v', '1', '-q:v', '3', dest],
                       capture_output=True, text=True)
    if r.returncode:   # drawtext without fontconfig: no time stamps, frames still in order (0.5 s apart)
        vf = f'fps=1/{every},scale={w}:-2,tile={cols}x{rows}:padding=4:color=white'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vf', vf, '-frames:v', '1', '-q:v', '3', dest],
                       check=True)
    if not with_frames:
        return dest
    fdir = os.path.join(out, 'frames')
    os.makedirs(fdir, exist_ok=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vf', f'fps=4,scale=540:-2', '-q:v', '3',
                    os.path.join(fdir, 'f_%03d.jpg')], check=True)
    return dest


def cuts(path):
    """Hard cuts: frames whose scene score spikes far above the frames around them.

    A fixed threshold misses cuts between two similar shots (same room, same light) and fires on fast motion;
    a spike against the local median catches the first and ignores the second."""
    err = subprocess.run(['ffmpeg', '-v', 'info', '-i', path, '-vf', "select='gte(scene,0)',metadata=print",
                          '-an', '-f', 'null', '-'], capture_output=True, text=True).stderr
    t = [float(x) for x in re.findall(r'pts_time:([\d.]+)', err)]
    s = [float(x) for x in re.findall(r'lavfi\.scene_score=([\d.]+)', err)]
    out = []
    for i, (ti, si) in enumerate(zip(t, s)):
        around = sorted(s[max(0, i - 12):i] + s[i + 1:i + 13]) or [0]
        local = around[len(around) // 2]
        peak = si >= max(s[max(0, i - 3):i + 4])
        if peak and (si >= 0.35 or si >= max(0.08, 3 * local + 0.05)):
            out.append(round(ti, 2))
    return out


def loudness(path):
    err = subprocess.run(['ffmpeg', '-v', 'info', '-i', path, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    tail = err[err.rfind('Summary:'):]
    get = lambda k: (re.search(rf'{k}:\s+(-?[\d.]+)', tail) or [None, None])[1]
    sil = subprocess.run(['ffmpeg', '-v', 'info', '-i', path, '-vn', '-af', 'silencedetect=n=-38dB:d=0.4', '-f',
                          'null', '-'], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r'silence_start: (-?[\d.]+)', sil)]
    ends = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', sil)]
    return {'lufs': float(get('I') or 'nan'), 'lra': float(get('LRA') or 'nan'), 'true_peak': float(get('Peak') or 'nan'),
            'silences': [[round(max(0, a), 2), round(b, 2)] for a, b in zip(starts, ends)]}


def transcribe(path, out, keyterms):
    import fal_run
    audio = os.path.join(out, 'audio.mp3')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vn', '-ac', '1', '-b:a', '96k', audio], check=True)
    args = {'audio_url': fal_run.upload(audio), 'diarize': True, 'tag_audio_events': True}
    if keyterms:
        args['keyterms'] = keyterms[:100]
    media = {args['audio_url']: fal_run.media_seconds(audio) or 15}
    result, _, cost = fal_run.run('fal-ai/elevenlabs/speech-to-text/scribe-v2', args, out, 'scribe', media=media)
    words = [{'text': w.get('text', ''), 'start': w.get('start'), 'end': w.get('end'),
              'speaker': w.get('speaker_id'), 'type': w.get('type', 'word')}
             for w in result.get('words', []) if w.get('start') is not None]
    with open(os.path.join(out, 'words.json'), 'w') as f:
        json.dump({'text': result.get('text'), 'words': words, 'cost_usd': cost}, f, indent=1)
    return words


def norm(s):
    return re.sub(r"[^\w' ]+", ' ', s.lower()).split()


def match_lines(planned, words):
    """Best matching span of spoken words for each planned line: similarity and timing."""
    spoken = [w for w in words if w['type'] == 'word']
    toks = [norm(w['text'])[0] if norm(w['text']) else '' for w in spoken]
    used = set()
    out = []
    for p in planned:
        target = norm(p['text'])
        best = (0.0, None, None)
        n = len(target)
        for i in range(len(toks)):
            for L in (n - 1, n, n + 1):
                if L <= 0 or i + L > len(toks):
                    continue
                r = difflib.SequenceMatcher(None, target, toks[i:i + L]).ratio()
                if r > best[0]:
                    best = (r, i, i + L)
        r, i, j = best
        row = {'who': p['who'], 'line': p['text'], 'planned_at': p['at'], 'similarity': round(r, 2)}
        if i is not None and r >= 0.5:
            row.update(said=' '.join(w['text'] for w in spoken[i:j]), start=spoken[i]['start'], end=spoken[j - 1]['end'],
                       offset=round(spoken[i]['start'] - p['at'], 2), speaker=spoken[i]['speaker'])
            used.update(range(i, j))
        out.append(row)
    extra = [w['text'] for k, w in enumerate(spoken) if k not in used]
    events = [w['text'] for w in words if w['type'] != 'word']
    return out, extra, events


def planned_for(plan_path, seq_id):
    ep = json.load(open(plan_path, encoding='utf-8'))
    seq = next((s for s in ep.get('sequences', []) if s['id'] == seq_id), None)
    cast = {c['id']: c.get('name', c['id']) for c in ep.get('cast', [])}
    if not seq:
        return ep, None, [], []
    planned_cuts = [sh['t'][0] for sh in seq.get('shots', [])[1:]]
    lines = []
    for sh in seq.get('shots', []):
        for k, ln in enumerate(sh.get('lines', [])):
            lines.append({'who': cast.get(ln['who'], ln['who']), 'text': ln['text'], 'at': sh['t'][0] + 0.3 + k * 1.2})
    return ep, seq, planned_cuts, lines


def registry_path(take):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(take))), 'review', 'takes.json')


def record(take, a):
    path = registry_path(take)
    reg = json.load(open(path)) if os.path.exists(path) else {}
    name = os.path.splitext(os.path.basename(take))[0]
    m = re.match(r'(.+)_t(\d+)$', name)
    entry = reg.get(name, {'seq': m.group(1) if m else name, 'take': int(m.group(2)) if m else 0})
    entry['verdict'] = a.verdict
    if a.usable:
        entry['usable'] = [[float(x) for x in r.split('-')] for r in a.usable.split(',')]
    if a.score:
        entry['scores'] = {k: int(v) for k, v in (kv.split('=') for kv in a.score.split(','))}
        bad = [k for k in entry['scores'] if k not in RUBRIC]
        if bad:
            sys.exit(f'unknown score keys {bad}; use {", ".join(RUBRIC)}')
    if a.note:
        entry['note'] = a.note
    entry['duration'] = probe(take)['duration']
    entry['t'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    reg[name] = entry
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(reg, f, indent=1)
    print(f'{name}: {a.verdict}' + (f', usable {entry.get("usable")}' if entry.get('usable') else ''))


def summary(plan_path):
    base = os.path.dirname(os.path.abspath(plan_path))
    path = os.path.join(base, 'review', 'takes.json')
    reg = json.load(open(path)) if os.path.exists(path) else {}
    ep = json.load(open(plan_path, encoding='utf-8'))
    gen = usable = 0.0
    for s in ep.get('sequences', []):
        takes = sorted((k, v) for k, v in reg.items() if v.get('seq') == s['id'])
        kept = [k for k, v in takes if v.get('verdict') == 'keep']
        status = 'KEEP ' + kept[-1] if kept else ('salvage' if any(v['verdict'] == 'salvage' for _, v in takes)
                                                  else 'needs a take')
        print(f'{s["id"]}  slot {s.get("slot")}  takes {len(takes)}  {status}')
        for k, v in takes:
            u = sum(b - a for a, b in v.get('usable', []))
            gen += v.get('duration', 0)
            usable += u
            sc = ' '.join(f'{x[:4]}={v["scores"][x]}' for x in RUBRIC if x in v.get('scores', {}))
            print(f'   {k:10s} {v["verdict"]:8s} usable {u:5.1f}/{v.get("duration", 0):5.1f} s  {sc}  {v.get("note", "")}')
    if gen:
        print(f'usable before edit: {usable:.1f} of {gen:.1f} s generated = {100 * usable / gen:.0f} %')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('take', nargs='?')
    ap.add_argument('--plan')
    ap.add_argument('--transcribe', action='store_true')
    ap.add_argument('--verdict', choices=['keep', 'salvage', 'retake'])
    ap.add_argument('--usable', help='usable ranges in take seconds: 0.2-6.1,6.4-12.8')
    ap.add_argument('--score', help='identity=2,continuity=2,lipsync=1,performance=2,camera=2,artifacts=1')
    ap.add_argument('--note')
    ap.add_argument('--summary', action='store_true')
    a = ap.parse_args()

    if a.summary:
        if not a.plan:
            ap.error('--summary needs --plan')
        summary(a.plan)
        return
    if not a.take:
        ap.error('take is required')
    if a.verdict:
        record(a.take, a)
        return

    name = os.path.splitext(os.path.basename(a.take))[0]
    episode_dir = os.path.dirname(os.path.dirname(os.path.abspath(a.take)))     # takes/<take>.mp4 -> episode folder
    os.environ.setdefault('MINISODE_LEDGER', os.path.join(episode_dir, 'ledger.json'))   # transcripts bill the episode
    if a.plan and not os.environ.get('MINISODE_BUDGET'):
        budget = json.load(open(a.plan, encoding='utf-8')).get('budget_usd')
        if budget:
            os.environ['MINISODE_BUDGET'] = str(budget)
    out = os.path.join(episode_dir, 'review', name)
    os.makedirs(out, exist_ok=True)
    info = probe(a.take)
    rep = {'take': name, **info, 'sheet': os.path.relpath(sheet(a.take, out, info), os.getcwd())}
    rep['cuts'] = cuts(a.take)
    seq_id = re.sub(r'_t\d+$', '', name)
    ep, seq, planned_cuts, lines = planned_for(a.plan, seq_id) if a.plan else (None, None, [], [])
    if seq:
        rep['planned_cuts'] = planned_cuts
        near = lambda p: min(rep['cuts'], key=lambda c: abs(c - p)) if rep['cuts'] else None
        rep['cut_match'] = [{'planned': p, 'found': near(p) if near(p) is not None and abs(near(p) - p) <= 1.0 else None}
                            for p in planned_cuts]
        rep['extra_cuts'] = [c for c in rep['cuts'] if all(abs(c - p) > 0.8 for p in planned_cuts)]
        if abs(info['duration'] - seq.get('duration', info['duration'])) > 1.0:
            rep.setdefault('flags', []).append(f'lasts {info["duration"]} s, planned {seq["duration"]} s')
    if info['audio']:
        rep['audio'] = loudness(a.take)
    else:
        rep.setdefault('flags', []).append('no audio stream: the dialogue must be rebuilt or the take redone')
    if a.transcribe and info['audio']:
        names = [c.get('name') for c in (ep or {}).get('cast', []) if c.get('name')]
        words = transcribe(a.take, out, names)
        rep['lines'], rep['extra_speech'], rep['audio_events'] = match_lines(lines, words)
        if any('music' in e.lower() for e in rep['audio_events']):
            rep.setdefault('flags', []).append('music detected in the take: the prompt says no music')
    with open(os.path.join(out, 'report.json'), 'w') as f:
        json.dump(rep, f, indent=1)

    print(f'{name}: {info["width"]}x{info["height"]} {info["fps"]} fps {info["duration"]} s, audio {info["audio"]}')
    print(f'  sheet  {rep["sheet"]}   frames every 0.25 s in {os.path.relpath(os.path.join(out, "frames"), os.getcwd())}')
    print(f'  cuts   found {rep["cuts"]}' + (f'   planned {planned_cuts}' if seq else ''))
    for m in rep.get('cut_match', []):
        drift = 'MISSING (the model did not cut here)' if m['found'] is None else f'{m["found"] - m["planned"]:+.2f} s'
        print(f'         planned {m["planned"]:5.2f} -> found {m["found"]}  {drift}')
    if rep.get('extra_cuts'):
        print(f'         unplanned cuts at {rep["extra_cuts"]}')
    if rep.get('audio'):
        au = rep['audio']
        print(f'  sound  {au["lufs"]} LUFS, peak {au["true_peak"]} dBTP, silences {au["silences"]}')
    for ln in rep.get('lines', []):
        said = ln.get('said', '(not found)')
        print(f'  line   {ln["who"]}: "{ln["line"]}"  ->  "{said}"  sim {ln["similarity"]}'
              + (f'  at {ln["start"]:.1f} s ({ln["offset"]:+.1f})' if 'start' in ln else ''))
    if rep.get('extra_speech'):
        print(f'  extra  words not in the script: {" ".join(rep["extra_speech"])[:200]}')
    for fl in rep.get('flags', []):
        print(f'  ! {fl}')
    print('  now look at the sheet and the frames, then record: --verdict keep|salvage|retake --usable a-b,... '
          f'--score {",".join(k + "=?" for k in RUBRIC)}')


if __name__ == '__main__':
    main()
