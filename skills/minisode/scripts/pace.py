#!/usr/bin/env python3
"""Measure the pace of the cut (or of the plan) against the rules that keep a viewer from scrolling.

Lays the edit out on a timeline and measures it: shot lengths (average, median, spread, cuts per 10 s),
when the hook text and the first line land, speech rate and coverage, dead air, the gaps between changes
(any cut, line, sound or music event) and between re-hooks (a new beat, a reveal, an arrival, a hit), where
the midpoint turn falls, how the episode ends, and with --render the loudness and energy of the master. Writes
pace.json and pace.svg (beats, the target pressure curve, shots, dialogue, music, effects, markers, energy) and
prints pass/fail checks. --music-plan writes ElevenLabs Music composition plans for the cues, cut to this edit.

Usage:
  python3 pace.py edit.json -o pace/
  python3 pace.py edit.json -o pace/ --render out/final.mp4
  python3 pace.py --plan episode.json -o pace/            # the planned timeline, before anything is shot
  python3 pace.py edit.json --music-plan music/           # music/cue_A.json ... for fal_run.py

Standard library only (and ffmpeg for --render).
"""
import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble  # noqa: E402

# the pressure loop of the format guide, as (share of runtime, tension)
TARGET = [(0, 0.75), (0.03, 0.8), (0.12, 0.35), (0.3, 0.55), (0.5, 0.88), (0.68, 0.7), (0.86, 0.38), (1.0, 0.97)]
ASL = {'comedy': (1.8, 3.2), 'thriller': (1.5, 3.0), 'horror': (1.5, 3.5), 'action': (1.2, 2.5)}
REHOOK = {'twist', 'reveal', 'arrival', 'turn', 'cliff', 'new-place', 'new-person', 'new-fact', 'hit'}


def words_n(s):
    return len(re.findall(r"[\w'’-]+", s or ''))


def from_plan(ep):
    """Pseudo-clips from the plan: every shot placed through its sequence slot."""
    clips = []
    cast = {c['id']: c.get('name', c['id']) for c in ep.get('cast', [])}
    for s in ep.get('sequences', []):
        a, b = s.get('slot', [0, s.get('duration', 0)])
        for k, sh in enumerate(s.get('shots', []), 1):
            t0, t1 = sh['t']
            if t0 >= b - a:
                continue
            beat = next((x['id'] for x in ep.get('beats', []) if x['start'] <= a + t0 < x['end']), '')
            clips.append({'start': a + t0, 'dur': min(t1, b - a) - t0, 'shot': f'{s["id"]}.{k}', 'beat': beat,
                          'take': s['id'], 'who': sh.get('who', []),
                          'lines': [{'who': cast.get(x['who'], x['who']), 'text': x['text']} for x in sh.get('lines', [])]})
    return clips


def shot_of(ep, ref):
    if not ep or not ref or '.' not in ref:
        return {}
    sid, k = ref.split('.')
    s = next((x for x in ep.get('sequences', []) if x['id'] == sid), None)
    return s['shots'][int(k) - 1] if s and int(k) <= len(s.get('shots', [])) else {}


def speech_spans(clips, words, ep):
    """Dialogue on the timeline: transcribed words when there are any, else the planned lines."""
    spans = []
    if words:
        cur = None
        for w in words:
            if cur and w['start'] - cur[1] <= 0.6:
                cur[1] = w['end']
                cur[2] += 1
            else:
                if cur:
                    spans.append(cur)
                cur = [w['start'], w['end'], 1]
        if cur:
            spans.append(cur)
        return [{'start': a, 'end': b, 'words': n} for a, b, n in spans], 'transcript'
    for c in clips:
        lines = c.get('lines') if 'lines' in c else shot_of(ep, c.get('shot')).get('lines', [])
        t = c['start'] + 0.25
        for ln in lines:
            n = words_n(ln['text'])
            d = n / 2.6 + 0.2
            spans.append({'start': t, 'end': min(t + d, c['start'] + c['dur'] + 0.4), 'words': n, 'text': ln['text']})
            t += d + 0.25
    return spans, 'planned lines'


def render_audio(path, step=0.5):
    err = subprocess.run(['ffmpeg', '-v', 'info', '-i', path, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    tail = err[err.rfind('Summary:'):]
    get = lambda k: float((re.search(rf'{k}:\s+(-?[\d.]+)', tail) or [0, 'nan'])[1])
    loud = {'lufs': get('I'), 'lra': get('LRA'), 'true_peak': get('Peak')}
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    n = int(8000 * step)
    rms = []
    for i in range(0, len(raw) // 2 - n, n):
        chunk = memoryview(raw)[i * 2:(i + n) * 2].cast('h')
        e = math.sqrt(sum(x * x for x in chunk) / n) / 32768
        rms.append([round(i / 8000, 2), round(20 * math.log10(e) if e > 1e-6 else -90, 1)])
    return loud, rms


def target_at(x):
    for (a, ta), (b, tb) in zip(TARGET, TARGET[1:]):
        if a <= x <= b:
            u = (x - a) / (b - a)
            u = u * u * (3 - 2 * u)
            return ta + (tb - ta) * u
    return TARGET[-1][1]


def analyze(clips, total, edit, ep, words, render):
    durs = [c['dur'] for c in clips]
    cuts = [round(c['start'], 2) for c in clips[1:]]
    spans, speech_src = speech_spans(clips, words, ep)
    music = edit.get('music', [])
    sfx = edit.get('sfx', [])
    overlays = edit.get('overlays', [])
    markers = edit.get('markers', [])
    beats_tl = []
    for c in clips:
        if c.get('beat') and (not beats_tl or beats_tl[-1]['id'] != c['beat']):
            beats_tl.append({'id': c['beat'], 'start': c['start']})
    for i, b in enumerate(beats_tl):
        b['end'] = beats_tl[i + 1]['start'] if i + 1 < len(beats_tl) else total
        b['tension'] = next((x.get('tension', 0.5) for x in (ep or {}).get('beats', []) if x['id'] == b['id']), 0.5)

    changes = sorted(set(cuts + [round(s['start'], 2) for s in spans] + [s['at'] for s in sfx]
                         + [m['at'] for m in music] + [m['at'] + m['out'] - m['in'] for m in music]
                         + [o['start'] for o in overlays]))
    rehooks = sorted(set([b['start'] for b in beats_tl[1:]] + [m['t'] for m in markers if m.get('type') in REHOOK]
                         + [s['at'] for s in sfx if s.get('kind') == 'hit']))

    def max_gap(events):
        pts = [0.0] + [e for e in events if 0 < e < total] + [total]
        g = max(((b - a), a, b) for a, b in zip(pts, pts[1:]))
        return round(g[0], 2), [round(g[1], 2), round(g[2], 2)]

    # quiet: no speech, no music, no effect
    busy = [(s['start'], s['end']) for s in spans] + [(m['at'], m['at'] + m['out'] - m['in']) for m in music] \
        + [(s['at'], s['at'] + 1.0) for s in sfx]
    busy.sort()
    quiet, t = [], 0.0
    for a, b in busy:
        if a > t:
            quiet.append((t, a))
        t = max(t, b)
    if t < total:
        quiet.append((t, total))
    longest_quiet = max(quiet, key=lambda q: q[1] - q[0]) if quiet else (0, 0)
    intended = any(m.get('type') == 'silence' and m['t'] <= longest_quiet[0] + 1 and m.get('until', m['t'] + 4) >=
                   longest_quiet[1] - 1 for m in markers)
    speak_time = sum(s['end'] - s['start'] for s in spans)
    nwords = sum(s['words'] for s in spans)
    per10 = [sum(1 for c in cuts if k <= c < k + 10) for k in range(0, int(math.ceil(total)), 10)]
    first_line = spans[0]['start'] if spans else None
    hook = next((o for o in overlays if o.get('style', 'hook') == 'hook'), None)
    twist = next((m['t'] for m in markers if m.get('type') in ('twist', 'reveal')), None) \
        or next((b['start'] for b in beats_tl if b['id'] == 'twist'), None)
    recap = ((ep or {}).get('sheet') or {}).get('recap', '')
    recap_at = None
    if recap:
        for c in clips:
            lines = c.get('lines') if 'lines' in c else shot_of(ep, c.get('shot')).get('lines', [])
            if any(recap.lower()[:20] in ln['text'].lower() for ln in lines):
                recap_at = round(c['start'], 2)
                break
    genre = (ep or {}).get('genre', 'drama')
    lo, hi = ASL.get(genre, (2.0, 3.5))
    first_who = clips[0].get('who') if 'who' in clips[0] else shot_of(ep, clips[0].get('shot')).get('who')
    end_music = [m for m in music if abs(m['at'] + m['out'] - m['in'] - total) < 0.3]

    res = {
        'duration': round(total, 2), 'shots': len(clips), 'asl': round(total / len(clips), 2),
        'median': round(statistics.median(durs), 2), 'min': round(min(durs), 2), 'max': round(max(durs), 2),
        'stdev': round(statistics.pstdev(durs), 2), 'cuts_per_10s': per10, 'cuts': cuts,
        'first_line_at': first_line and round(first_line, 2), 'hook_text': hook and [hook['start'], hook['end']],
        'recap_at': recap_at, 'twist_at': twist,
        'speech': {'source': speech_src, 'words': nwords, 'wps_overall': round(nwords / total, 2),
                   'wps_speaking': round(nwords / speak_time, 2) if speak_time else 0,
                   'coverage': round(speak_time / total, 2),
                   'longest_quiet': [round(longest_quiet[0], 2), round(longest_quiet[1], 2)],
                   'quiet_intended': intended},
        'max_change_gap': max_gap(changes), 'max_rehook_gap': max_gap(rehooks), 'rehooks': rehooks,
        'beats': beats_tl, 'spans': spans,
    }
    if render:
        res['loudness'], res['rms'] = render_audio(render)

    def chk(name, ok, detail):
        res.setdefault('checks', []).append({'name': name, 'ok': bool(ok), 'detail': detail})

    chk('Face or threat in frame 1', bool(first_who), f'first shot shows {first_who or "nobody"}')
    chk('Hook text lands by 0.6 s', hook and hook['start'] <= 0.6, f'hook text {res["hook_text"]}')
    chk('First line by 2 s', first_line is not None and first_line <= 2.0, f'first line at {res["first_line_at"]} s')
    chk('Recap line in the first 20 s', recap_at is not None and recap_at <= 20, f'recap at {recap_at} s')
    chk('A re-hook every 20 s', res['max_rehook_gap'][0] <= 20,
        f'longest stretch without one {res["max_rehook_gap"][0]} s at {res["max_rehook_gap"][1]}')
    chk('Something changes every 5 s', res['max_change_gap'][0] <= 5,
        f'longest stretch with no cut, line, sound or music event {res["max_change_gap"][0]} s at {res["max_change_gap"][1]}')
    chk(f'Average shot {lo}-{hi} s ({genre})', lo <= res['asl'] <= hi, f'average {res["asl"]} s, median {res["median"]} s')
    chk('No shot over 6 s', res['max'] <= 6, f'longest {res["max"]} s')
    chk('Midpoint turn between 35 % and 60 %', twist is not None and 0.35 * total <= twist <= 0.6 * total,
        f'turn at {twist} s of {total:.0f}')
    q = res['speech']['longest_quiet']
    chk('No dead air over 3 s (unless a planned silence)', (q[1] - q[0]) <= 3 or intended,
        f'quiet {q[0]}-{q[1]} s' + (' (planned silence)' if intended else ''))
    chk('Speech 2.0-3.6 words/s while talking', 2.0 <= res['speech']['wps_speaking'] <= 3.6 or not nwords,
        f'{res["speech"]["wps_speaking"]} words/s, talking {res["speech"]["coverage"] * 100:.0f} % of the time')
    chk('Ends on the loaded moment (last shot <= 4 s, no long fade)',
        durs[-1] <= 4 and all(m.get('fade_out', 0.4) <= 0.2 for m in end_music), f'last shot {durs[-1]:.1f} s')
    chk('Reads with sound off (captions + hook text)', edit.get('captions', True) and hook is not None,
        'captions ' + ('on' if edit.get('captions', True) else 'off'))
    if render:
        L = res['loudness']
        chk('Loudness -14 LUFS +-1, true peak <= -1 dBTP', abs(L['lufs'] + 14) <= 1 and L['true_peak'] <= -1.0,
            f'{L["lufs"]} LUFS, {L["true_peak"]} dBTP, LRA {L["lra"]}')
    return res


def svg(res, edit, path):
    W, T = 1400, res['duration']
    x = lambda t: 60 + (W - 90) * t / T
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="560" font-family="Inter,Helvetica,Arial,sans-serif" '
           'font-size="12"><rect width="100%" height="100%" fill="#0e0d12"/>']
    txt = lambda X, Y, s, c='#bdb7cc', a='start', sz=12: out.append(
        f'<text x="{X:.1f}" y="{Y}" fill="{c}" font-size="{sz}" text-anchor="{a}">{s}</text>')
    txt(20, 24, f'Pace map · {T:.1f} s · {res["shots"]} shots · average {res["asl"]} s · '
                f'{res["speech"]["words"]} words ({res["speech"]["source"]})', '#ffffff', sz=14)
    for k in range(0, int(T) + 1, 5):
        out.append(f'<line x1="{x(k):.1f}" y1="40" x2="{x(k):.1f}" y2="530" stroke="#26232f"/>')
        txt(x(k), 548, f'{k}s', '#6f6a7d', 'middle', 11)
    # beats and tension
    txt(8, 62, 'beats', '#6f6a7d', sz=11)
    for b in res['beats']:
        out.append(f'<rect x="{x(b["start"]):.1f}" y="48" width="{x(b["end"]) - x(b["start"]) - 2:.1f}" height="22" rx="3" '
                   f'fill="#c4a5ff" fill-opacity="{0.15 + 0.7 * b["tension"]:.2f}"/>')
        txt(x(b['start']) + 5, 63, b['id'], '#0e0d12' if b['tension'] > 0.6 else '#e9e3ff', sz=11)
    top, h = 85, 110
    txt(8, top + 12, 'tension', '#6f6a7d', sz=11)
    pts = ' '.join(f'{x(T * i / 100):.1f},{top + h - h * target_at(i / 100):.1f}' for i in range(101))
    out.append(f'<polyline points="{pts}" fill="none" stroke="#6f6a7d" stroke-dasharray="5 4" stroke-width="2"/>')
    step = ' '.join(f'{x(b["start"]):.1f},{top + h - h * b["tension"]:.1f} {x(b["end"]):.1f},{top + h - h * b["tension"]:.1f}'
                    for b in res['beats'])
    out.append(f'<polyline points="{step}" fill="none" stroke="#c4a5ff" stroke-width="2.5"/>')
    txt(W - 30, top + 12, 'dashed: target pressure loop · lilac: this cut', '#6f6a7d', 'end', 11)
    # shots
    y = 215
    txt(8, y + 16, 'shots', '#6f6a7d', sz=11)
    t = 0.0
    for i, d in enumerate([b - a for a, b in zip([0] + res['cuts'], res['cuts'] + [T])]):
        c = '#3a3546' if i % 2 else '#4a4458'
        if d > 6:
            c = '#a33b3b'
        out.append(f'<rect x="{x(t):.1f}" y="{y}" width="{max(1, x(t + d) - x(t) - 1):.1f}" height="26" fill="{c}"/>')
        if x(t + d) - x(t) > 22:
            txt(x(t) + (x(t + d) - x(t)) / 2, y + 17, f'{d:.1f}', '#e9e3ff', 'middle', 10)
        t += d
    # dialogue
    y = 258
    txt(8, y + 11, 'dialogue', '#6f6a7d', sz=11)
    for s in res['spans']:
        out.append(f'<rect x="{x(s["start"]):.1f}" y="{y}" width="{max(2, x(s["end"]) - x(s["start"])):.1f}" height="14" '
                   'rx="2" fill="#f2f0f7"/>')
    q = res['speech']['longest_quiet']
    out.append(f'<rect x="{x(q[0]):.1f}" y="{y - 2}" width="{x(q[1]) - x(q[0]):.1f}" height="18" fill="none" '
               f'stroke="{"#6f6a7d" if res["speech"]["quiet_intended"] else "#e0a030"}" stroke-dasharray="3 3"/>')
    # music, effects, overlays, markers
    y = 290
    txt(8, y + 11, 'music', '#6f6a7d', sz=11)
    for m in edit.get('music', []):
        a, b = m['at'], m['at'] + m['out'] - m['in']
        out.append(f'<rect x="{x(a):.1f}" y="{y}" width="{x(b) - x(a):.1f}" height="14" rx="2" fill="#7c5cc4"/>')
        txt(x(a) + 4, y + 11, f'cue {m.get("cue", "")}', '#ffffff', sz=10)
    y = 318
    txt(8, y + 11, 'fx / text', '#6f6a7d', sz=11)
    for s in edit.get('sfx', []):
        out.append(f'<path d="M{x(s["at"]):.1f},{y} l6,12 l-12,0 z" fill="#e0a030"/>')
    for o in edit.get('overlays', []):
        out.append(f'<rect x="{x(o["start"]):.1f}" y="{y + 16}" width="{x(o["end"]) - x(o["start"]):.1f}" height="6" fill="#facc15"/>')
    for m in edit.get('markers', []):
        out.append(f'<line x1="{x(m["t"]):.1f}" y1="44" x2="{x(m["t"]):.1f}" y2="350" stroke="#ff7a90" stroke-dasharray="2 3"/>')
        txt(x(m['t']) + 3, 360, m.get('type', ''), '#ff7a90', sz=10)
    # energy of the master
    if res.get('rms'):
        top, h = 380, 140
        txt(8, top + 12, 'energy', '#6f6a7d', sz=11)
        pts = ' '.join(f'{x(t):.1f},{top + h - h * max(0, min(1, (db + 60) / 60)):.1f}' for t, db in res['rms'] if t <= T)
        out.append(f'<polyline points="{pts}" fill="none" stroke="#7fd1c7" stroke-width="1.5"/>')
        L = res['loudness']
        txt(W - 30, top + 12, f'{L["lufs"]} LUFS · peak {L["true_peak"]} dBTP · LRA {L["lra"]}', '#7fd1c7', 'end', 11)
    out.append('</svg>')
    with open(path, 'w') as f:
        f.write('\n'.join(out))


def music_plans(res, edit, ep, out_dir):
    music = (ep or {}).get('music') or {}
    os.makedirs(out_dir, exist_ok=True)
    # story tension is not music volume: under dialogue the score stays restrained, it blooms on reveals
    words = lambda t: ('sparse, quiet, low register' if t < 0.45 else 'light pulse, slowly building' if t < 0.7
                       else 'tense, held, rising underneath the dialogue')
    at_marker = {m['t']: m.get('type') for m in edit.get('markers', [])}
    color = {'reveal': 'emotional swell, the melody blooms', 'twist': 'a low hit, then suspended tension',
             'cliff': 'suspended, unresolved, no cadence', 'arrival': 'a sly new figure enters',
             'turn': 'pulls back to a single line'}
    for cue in music.get('cues', []):
        a, b = cue['from'], cue['to']
        cuts = sorted({a, b} | {x['start'] for x in res['beats'] if a < x['start'] < b}
                      | {m['t'] for m in edit.get('markers', []) if a < m['t'] < b and m.get('type') != 'silence'})
        segs = [[p, q] for p, q in zip(cuts, cuts[1:])]
        merged = []
        for s in segs:                       # each chunk lasts at least 3 s
            if merged and (s[1] - s[0] < 3 or merged[-1][1] - merged[-1][0] < 3):
                merged[-1][1] = s[1]
            else:
                merged.append(s)
        chunks = []
        for i, (p, q) in enumerate(merged):
            beat = next((x for x in res['beats'] if x['start'] <= p + 0.01 < x['end']), {'id': 'scene', 'tension': 0.5})
            styles = (list(music.get('styles', [])) if i == 0 else []) + [words(beat['tension'])]
            mark = at_marker.get(round(p, 2)) or at_marker.get(p)
            if mark in color:
                styles.append(color[mark])
            if i == 0:
                styles.append(cue['intent'])
            tag = {'twist': 'hit', 'cliff': 'hold'}.get(mark, mark)
            name = beat['id'].capitalize() + (f' - {tag}' if mark in color else '')
            chunks.append({'text': f'[{name}]', 'duration_ms': int(round((q - p) * 1000)),
                           'positive_styles': styles, 'negative_styles': list(music.get('avoid', []))})
        path = os.path.join(out_dir, f'cue_{cue["id"]}.json')
        with open(path, 'w') as f:
            json.dump({'chunks': chunks}, f, indent=1)
        print(f'{path}: {b - a:.1f} s in {len(chunks)} chunks -> python3 fal_run.py elevenlabs/music/v2.5 -o {out_dir} '
              f'--name cue_{cue["id"]} --json composition_plan={path} --arg seed=7')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('edit', nargs='?')
    ap.add_argument('--plan', help='analyze the planned timeline of this episode.json instead of an edit')
    ap.add_argument('-o', '--out', default='pace')
    ap.add_argument('--render', help='the rendered master, for loudness and energy')
    ap.add_argument('--music-plan', metavar='DIR', help='write composition plans for the music cues to DIR')
    a = ap.parse_args()

    if a.plan:
        ep = json.load(open(a.plan, encoding='utf-8'))
        clips = from_plan(ep)
        total = clips[-1]['start'] + clips[-1]['dur']
        silences = [{'t': c['start'], 'until': c['start'] + c['dur'], 'type': 'silence'} for c in clips
                    if shot_of(ep, c['shot']).get('silence')]
        edit = {'overlays': [{'text': ep['sheet']['hook']['text'], 'start': 0.2, 'end': 2.5, 'style': 'hook'}]
                if ep.get('sheet', {}).get('hook', {}).get('text') else [],
                'music': [{'cue': c['id'], 'at': c['from'], 'in': 0, 'out': c['to'] - c['from'],
                           'fade_out': 0.03 if abs(c['to'] - total) < 0.3 else 0.6}
                          for c in (ep.get('music') or {}).get('cues', [])],
                'markers': [{'t': b['start'], 'type': b['id'] if b['id'] in REHOOK else 'beat'} for b in ep['beats'][1:]]
                + silences}
        words = []
    else:
        if not a.edit:
            ap.error('give edit.json or --plan episode.json')
        edit = json.load(open(a.edit, encoding='utf-8'))
        base = os.path.dirname(os.path.abspath(a.edit))
        ep = json.load(open(os.path.join(base, edit['plan']), encoding='utf-8')) if edit.get('plan') else None
        clips, total = assemble.layout(edit, base)
        words = assemble.words_for(clips, base)
    res = analyze(clips, total, edit, ep, words, a.render)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'pace.json'), 'w') as f:
        json.dump(res, f, indent=1)
    svg(res, edit, os.path.join(a.out, 'pace.svg'))
    for c in res['checks']:
        print(f'{"ok  " if c["ok"] else "FIX "} {c["name"]:52s} {c["detail"]}')
    print(f'cuts per 10 s {res["cuts_per_10s"]}; shots {res["shots"]}, average {res["asl"]} s, '
          f'median {res["median"]} s, spread {res["stdev"]} s')
    print(f'{os.path.join(a.out, "pace.json")}  {os.path.join(a.out, "pace.svg")}')
    if a.music_plan:
        music_plans(res, edit, ep, a.music_plan)
    sys.exit(0 if all(c['ok'] for c in res['checks']) else 1)


if __name__ == '__main__':
    main()
