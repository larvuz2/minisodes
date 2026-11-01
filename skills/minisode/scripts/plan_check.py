#!/usr/bin/env python3
"""Check an episode plan before anything is generated: format rules, timing math, references, budget.

Reads episode.json and reports errors (fix before shooting), warnings (decide), and a budget table that
prices the whole episode at each resolution and says which one fits with a retake reserve.

Checks, from the micro-drama format guide and the video model's limits:
  story   episode sheet complete; hook formula; recap <= 12 words; hook text <= 8 words; lines <= 8 words
  beats   cover 0..duration with no gap; hook ends by 5 s; twist starts between 35 % and 60 %; cliff <= 10 s;
          a new beat at least every 20 s; never two flat beats in a row; the cliff is the tension peak
  shots   contiguous; camera fully specified; dialogue <= 3 words per second; a face in the first frame;
          a cut at least every 6 s; wide shots under 30 % of a vertical episode
  refs    <= 9 images, 3 audio, 3 video, 12 in total; audio and video 2-15 s each, 15 s per type
  budget  assets + shots + music at 480P / 768P / 1080P against budget_usd, with >= 25 % kept for retakes

Usage:
  python3 plan_check.py episode.json
  python3 plan_check.py episode.json --json

Standard library only (prompt.py and fal_run.py from this folder).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fal_run  # noqa: E402
import prompt as P  # noqa: E402

HOOKS = {'mid-crisis', 'forbidden-line', 'status-shock', 'wrong-image', 'clock', 'callback'}
CLIFFS = {'unfinished-line', 'new-fact', 'loaded-look', 'impossible-choice', 'arrival'}
WIDE = {'WS', 'EWS', 'MWS'}
RESERVE = 0.25


def words(s):
    return len(re.findall(r"[\w'’-]+", s or ''))


class Report:
    def __init__(self):
        self.items = []

    def err(self, area, msg):
        self.items.append(('error', area, msg))

    def warn(self, area, msg):
        self.items.append(('warn', area, msg))

    def ok(self, area, msg):
        self.items.append(('ok', area, msg))


def check_story(ep, r):
    sh = ep.get('sheet') or {}
    need = ['hook', 'recap', 'want', 'obstacle', 'twist', 'choice', 'cost', 'payoff', 'cliffhanger', 'loops']
    for k in need:
        if not sh.get(k):
            r.err('story', f'episode sheet is missing "{k}"')
    hook = sh.get('hook') or {}
    for k in ('image', 'line', 'text'):
        if not hook.get(k):
            r.err('story', f'hook needs an {k} (image + line + on-screen text)')
    if hook.get('formula') and hook['formula'] not in HOOKS:
        r.warn('story', f'hook formula "{hook["formula"]}" is not one of {", ".join(sorted(HOOKS))}')
    if words(hook.get('text')) > 8:
        r.warn('story', f'hook text has {words(hook.get("text"))} words; keep it under 8, readable muted')
    if words(hook.get('line')) > 8:
        r.warn('story', f'hook line has {words(hook.get("line"))} words; 8 or fewer')
    if words(sh.get('recap')) > 12:
        r.err('story', f'recap line has {words(sh.get("recap"))} words; 12 or fewer')
    cliff = sh.get('cliffhanger') or {}
    if cliff and cliff.get('type') not in CLIFFS:
        r.warn('story', f'cliffhanger type "{cliff.get("type")}" is not one of {", ".join(sorted(CLIFFS))}')
    if cliff and not cliff.get('last_frame'):
        r.err('story', 'cliffhanger needs the exact last frame')
    loops = sh.get('loops') or {}
    if not loops.get('closed') or not loops.get('opened'):
        r.err('story', 'close one loop and open one: loops.closed and loops.opened')
    for s in ep.get('sequences', []):
        for shot in s.get('shots', []):
            for ln in shot.get('lines', []):
                n = words(ln['text'])
                if n > 12:
                    r.err('story', f'{s["id"]}: "{ln["text"]}" has {n} words (8 max, cut it)')
                elif n > 8:
                    r.warn('story', f'{s["id"]}: "{ln["text"]}" has {n} words (8 max)')


def check_beats(ep, r):
    dur = ep['format']['duration_s']
    beats = sorted(ep.get('beats', []), key=lambda b: b['start'])
    if not beats:
        r.err('beats', 'no beats')
        return
    t = 0
    for b in beats:
        if abs(b['start'] - t) > 0.01:
            r.err('beats', f'gap or overlap before "{b["id"]}" at {b["start"]} s (expected {t})')
        t = b['end']
    if abs(t - dur) > 0.01:
        r.err('beats', f'beats end at {t} s, the episode lasts {dur} s')
    if beats[0]['id'] != 'hook' or beats[0]['end'] > 5:
        r.err('beats', 'the first beat is the hook and ends by 5 s')
    tw = next((b for b in beats if b['id'] == 'twist'), None)
    if not tw:
        r.err('beats', 'no twist beat (the midpoint re-hook)')
    elif not 0.35 * dur <= tw['start'] <= 0.6 * dur:
        r.warn('beats', f'twist starts at {tw["start"]} s; the midpoint re-hook belongs between '
                        f'{0.35 * dur:.0f} and {0.6 * dur:.0f} s')
    if beats[-1]['id'] != 'cliff' or beats[-1]['end'] - beats[-1]['start'] > 10:
        r.err('beats', 'the last beat is the cliffhanger, 10 s or shorter')
    starts = [b['start'] for b in beats] + [dur]
    gap = max(b - a for a, b in zip(starts, starts[1:]))
    (r.warn if gap > 20 else r.ok)('beats', f'longest stretch without a new beat: {gap:.0f} s (re-hook every 15-20 s)')
    ten = [b.get('tension', 0.5) for b in beats]
    for a, b, x, y in zip(beats, beats[1:], ten, ten[1:]):
        if x < 0.5 and y < 0.5:
            r.warn('beats', f'"{a["id"]}" and "{b["id"]}" are both quiet: never two flat beats in a row')
    if ten[-1] < max(ten):
        r.warn('beats', 'the cliffhanger is not the tension peak')


def timeline(ep):
    """Planned shots placed on the episode timeline through the sequence slots."""
    out = []
    for s in ep.get('sequences', []):
        a, b = s.get('slot', [0, s.get('duration', 0)])
        for sh in s.get('shots', []):
            t0, t1 = sh['t']
            if t0 >= b - a:
                continue
            out.append({'seq': s['id'], 'start': a + t0, 'end': a + min(t1, b - a), 'shot': sh})
    return out


def check_shots(ep, base, r):
    fmt = ep['format']
    dur = fmt['duration_s']
    slot_t = 0
    for s in ep.get('sequences', []):
        sid = s['id']
        a, b = s.get('slot', [None, None])
        if a is None:
            r.err('shots', f'{sid}: no slot (where it lands in the episode)')
            continue
        if abs(a - slot_t) > 0.01:
            r.err('shots', f'{sid}: slot starts at {a} s, expected {slot_t}')
        slot_t = b
        d = s.get('duration', 0)
        if d > 15:
            r.err('shots', f'{sid}: {d} s; one generation lasts 15 s at most')
        if d - (b - a) < 0.5:
            r.warn('shots', f'{sid}: {d - (b - a):.1f} s of handle; generate ~1 s more than the slot to trim on')
        t = 0
        for i, sh in enumerate(s.get('shots', [])):
            t0, t1 = sh['t']
            if abs(t0 - t) > 0.01:
                r.err('shots', f'{sid} shot {i + 1}: starts at {t0} s, expected {t}')
            t = t1
            miss = [k for k in ('frame', 'angle', 'lens', 'move', 'action') if not sh.get(k)]
            if miss:
                r.warn('shots', f'{sid} shot {i + 1}: no {", ".join(miss)}')
            n = sum(words(ln['text']) for ln in sh.get('lines', []))
            wps = n / max(0.1, t1 - t0)
            if wps > 3.5:
                r.err('shots', f'{sid} shot {i + 1}: {n} words in {t1 - t0:.1f} s ({wps:.1f}/s); too fast to land')
            elif wps > 3.0:
                r.warn('shots', f'{sid} shot {i + 1}: {wps:.1f} words/s; tight')
        if s.get('shots') and abs(t - d) > 0.3:
            r.err('shots', f'{sid}: shots end at {t} s, the sequence lasts {d} s')
    if abs(slot_t - dur) > 0.01:
        r.err('shots', f'sequence slots end at {slot_t} s, the episode lasts {dur} s')

    tl = timeline(ep)
    if tl:
        first = tl[0]['shot']
        if not first.get('who'):
            r.err('shots', 'no face in the first frame: the hook starts on a person or a threat')
        talk = [x for x in tl if x['shot'].get('lines') or x['shot'].get('overlay')]
        if not talk or talk[0]['start'] > 2:
            r.warn('shots', 'no line or hook text in the first 2 s')
        longest = max(tl, key=lambda x: x['end'] - x['start'])
        L = longest['end'] - longest['start']
        (r.warn if L > 6 else r.ok)('shots', f'longest planned shot {L:.1f} s ({longest["seq"]}); '
                                              f'average {sum(x["end"] - x["start"] for x in tl) / len(tl):.1f} s')
        if fmt.get('aspect_ratio') == '9:16':
            wide = sum(x['end'] - x['start'] for x in tl if x['shot'].get('frame', '').upper() in WIDE)
            if wide > 0.3 * dur:
                r.warn('shots', f'wide shots fill {wide:.0f} s of a vertical episode; faces and hands, not landscapes')

    for s in ep.get('sequences', []):
        b = P.build(ep, s['id'], base)
        for w in b['warnings']:
            r.err('refs', f'{s["id"]}: {w}')
        if not b['prompt'].startswith('No music'):
            r.err('refs', f'{s["id"]}: the prompt must open with "No music"')
    cast = {c['id']: c for c in ep.get('cast', [])}
    if len(cast) > 3:
        r.warn('story', f'{len(cast)} characters; the format holds 3')
    if len(ep.get('locations', [])) > 2:
        r.warn('story', f'{len(ep["locations"])} locations; the format holds 2')
    assets = ep.get('assets', {})
    for cid, c in cast.items():
        refs = c.get('refs', {})
        if not any(assets.get(x, {}).get('type') == 'image' for x in refs.values()):
            r.err('refs', f'{c["name"]} has no image reference')
        if not any(assets.get(x, {}).get('kind') == 'voice' for x in refs.values()):
            r.warn('refs', f'{c["name"]} has no voice reference')


def budget(ep, base, r):
    assets = ep.get('assets', {})
    fixed = 0.0
    for aid, x in assets.items():
        mk = x.get('make')
        if mk and not os.path.exists(os.path.join(base, x.get('file', ''))):
            fixed += fal_run.estimate(mk['endpoint'], mk.get('args') or {}, None, mk.get('price')) or 0.25
    music = ep.get('music') or {}
    cue_s = sum(max(3, c['to'] - c['from']) for c in music.get('cues', []))
    if music.get('model', '').startswith('elevenlabs/music'):
        fixed += cue_s / 60 * fal_run.PER_MINUTE['elevenlabs/music/v2.5']
    elif music.get('cues'):
        fixed += 0.10 * len(music['cues'])
    fixed += 0.10                                   # sound effects and transcripts
    spent = 0.0
    ledger = os.path.join(base, 'ledger.json')
    if os.path.exists(ledger):
        spent = json.load(open(ledger)).get('spent_usd', 0)
    cap = float(ep.get('budget_usd', fal_run.DEFAULT_BUDGET))
    rows = []
    for res in ('480P', '768P', '1080P'):
        shots = 0.0
        for s in ep.get('sequences', []):
            b = P.build(ep, s['id'], base)
            args = {'duration': b['duration'], 'resolution': res,
                    'reference_image_urls': b['reference_image_files'],
                    'reference_audio_urls': b['reference_audio_files'],
                    'reference_video_urls': b['reference_video_files']}
            shots += fal_run.estimate('minimax/h3-max/reference-to-video', args)
        total = spent + fixed + shots
        reserve = cap - total
        rows.append({'resolution': res, 'shots': round(shots, 2), 'assets_audio': round(fixed, 2),
                     'spent': round(spent, 2), 'total_once': round(total, 2), 'left_for_retakes': round(reserve, 2),
                     'retake_share': round(reserve / shots, 2) if shots else 0})
    fits = [x for x in rows if x['left_for_retakes'] >= RESERVE * x['shots']]
    pick = fits[-1]['resolution'] if fits else None
    planned = ep['format'].get('resolution', 'auto')
    if pick is None:
        need = rows[0]['total_once'] + RESERVE * rows[0]['shots']
        r.warn('budget', f'{cap:.2f} USD is not enough for a full episode with retakes even at 480P; '
                         f'about {need:.2f} USD needed. Cut a sequence, drop a keyframe, or raise the budget.')
    elif planned not in ('auto', pick) and planned in [x['resolution'] for x in rows]:
        mine = next(x for x in rows if x['resolution'] == planned)
        if mine['left_for_retakes'] < RESERVE * mine['shots']:
            r.warn('budget', f'{planned} leaves {mine["left_for_retakes"]:.2f} USD for retakes; {pick} fits the budget')
    else:
        r.ok('budget', f'{pick} fits {cap:.2f} USD with a retake reserve')
    return {'budget_usd': cap, 'rows': rows, 'pick': pick}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plan')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    ep, base = P.load(a.plan)
    r = Report()
    check_story(ep, r)
    check_beats(ep, r)
    check_shots(ep, base, r)
    money = budget(ep, base, r)
    errors = [x for x in r.items if x[0] == 'error']
    if a.json:
        print(json.dumps({'items': [dict(zip(('level', 'area', 'message'), x)) for x in r.items], 'budget': money},
                         indent=1))
    else:
        for level, area, msg in r.items:
            mark = {'error': 'x', 'warn': '!', 'ok': '.'}[level]
            print(f'{mark} {area:7s} {msg}')
        print(f'\nbudget {money["budget_usd"]:.2f} USD     shots   assets+audio  spent  once   left for retakes')
        for x in money['rows']:
            print(f'  {x["resolution"]:6s}               {x["shots"]:6.2f}  {x["assets_audio"]:6.2f}      '
                  f'{x["spent"]:5.2f}  {x["total_once"]:5.2f}  {x["left_for_retakes"]:6.2f} '
                  f'({x["retake_share"] * 100:.0f} % of shots)')
        print(f'  pick: {money["pick"] or "none fits"}')
        print(f'\n{len(errors)} errors, {sum(1 for x in r.items if x[0] == "warn")} warnings')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
