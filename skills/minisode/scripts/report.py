#!/usr/bin/env python3
"""Write the episode report: the story sheet, beats, cast, every take with its verdict, the pace checks, the
spend per endpoint, and what differs from the plan. It goes to the user with the episode (Report button).

Usage:
  python3 report.py episode.json --edit edit.json --pace pace/pace.json -o out/report.md
  python3 report.py episode.json --edit edit.json --pace pace/pace.json --notes notes.md -o out/report.md

--notes is your own short list of what differs from the plan and why (a line cut, a retake that never landed,
a voice fixed in post). Never write "identical"; say what changed. Standard library only.
"""
import argparse
import json
import os


def load(path, default=None):
    try:
        return json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return default


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plan')
    ap.add_argument('--edit')
    ap.add_argument('--pace')
    ap.add_argument('--notes')
    ap.add_argument('-o', '--out', default='out/report.md')
    a = ap.parse_args()
    ep = load(a.plan)
    base = os.path.dirname(os.path.abspath(a.plan))
    takes = load(os.path.join(base, 'review', 'takes.json'), {})
    ledger = load(os.environ.get('MINISODE_LEDGER') or os.path.join(base, 'ledger.json'), {})
    pace = load(a.pace, {}) if a.pace else {}
    fmt = ep.get('format', {})
    sh = ep.get('sheet', {})
    L = []
    w = L.append

    w(f'# {ep.get("title", "Minisode")}\n')
    w(f'> {ep.get("logline", "")}\n')
    spent = ledger.get('spent_usd', 0)
    w(f'{ep.get("genre_label") or ep.get("genre", "")} · {fmt.get("aspect_ratio")} · {fmt.get("duration_s")} s · '
      f'{ep.get("video_model")} at {fmt.get("resolution")} · {spent:.2f} of {ep.get("budget_usd", 0):.2f} USD\n')

    w('## Episode sheet\n')
    hook = sh.get('hook', {})
    rows = [('Type', sh.get('type')), ('Hook (0-5 s)', f'{hook.get("image", "")} "{hook.get("line", "")}" '
            f'· text: {hook.get("text", "")} · formula: {hook.get("formula", "")}'), ('Recap line', sh.get('recap')),
            ('Want → obstacle', f'{sh.get("want", "")} → {sh.get("obstacle", "")}'), ('Twist', sh.get('twist')),
            ('Choice + cost', f'{sh.get("choice", "")} Cost: {sh.get("cost", "")}'), ('Payoff', sh.get('payoff')),
            ('Cliffhanger', f'{sh.get("cliffhanger", {}).get("type", "")}: {sh.get("cliffhanger", {}).get("last_frame", "")}'),
            ('Loops', f'closed: {"; ".join(sh.get("loops", {}).get("closed", []))} · opened: '
                      f'{"; ".join(sh.get("loops", {}).get("opened", []))}')]
    w('| | |\n|---|---|')
    for k, v in rows:
        w(f'| {k} | {str(v or "").replace("|", "/")} |')
    w('')

    w('## Beats\n')
    w('| Beat | Time | Tension | What changes |\n|---|---|---|---|')
    for b in ep.get('beats', []):
        w(f'| {b["id"]} | {b["start"]}-{b["end"]} s | {b.get("tension", "")} | {b.get("change", "")} |')
    w('')

    w('## Cast\n')
    w('| Character | Look | Wardrobe | Voice |\n|---|---|---|---|')
    for c in ep.get('cast', []):
        v = c.get('voice', {})
        w(f'| {c["name"]} ({c.get("role", "")}) | {c.get("look", "")} | {c.get("wardrobe", "")} | '
          f'{v.get("model", "")} "{v.get("voice", "")}", {v.get("direction", "")} |')
    w('')

    w('## Sequences and takes\n')
    w('| Sequence | Slot | Takes | Kept | Usable | Notes |\n|---|---|---|---|---|---|')
    gen = use = 0.0
    for s in ep.get('sequences', []):
        ts = sorted((k, v) for k, v in takes.items() if v.get('seq') == s['id'])
        kept = [k for k, v in ts if v.get('verdict') == 'keep']
        u = sum(b - a_ for _, v in ts for a_, b in v.get('usable', []))
        g = sum(v.get('duration', 0) for _, v in ts)
        gen += g
        use += u
        notes = '; '.join(v['note'] for _, v in ts if v.get('note'))
        w(f'| {s["id"]} ({", ".join(s.get("beats", []))}) | {s.get("slot")} | {len(ts)} | {", ".join(kept) or "-"} | '
          f'{u:.1f}/{g:.1f} s | {notes} |')
    if gen:
        w(f'\nUsable before edit: {use:.1f} of {gen:.1f} s generated ({100 * use / gen:.0f} %).')
    w('')

    if pace:
        w('## Pace\n')
        w(f'{pace.get("shots")} shots, average {pace.get("asl")} s, median {pace.get("median")} s, longest '
          f'{pace.get("max")} s; cuts per 10 s {pace.get("cuts_per_10s")}; speech {pace.get("speech", {}).get("words")} '
          f'words at {pace.get("speech", {}).get("wps_speaking")} words/s while talking.\n')
        w('| Check | | Detail |\n|---|---|---|')
        for c in pace.get('checks', []):
            w(f'| {c["name"]} | {"ok" if c["ok"] else "**fix**"} | {c["detail"]} |')
        w('\nThe pace map is pace.svg next to this report.\n')

    if a.edit:
        edit = load(a.edit, {})
        if edit.get('music'):
            w('## Music and sound\n')
            for m in edit['music']:
                w(f'- Cue {m.get("cue", "")}: {m["at"]:.1f}-{m["at"] + m["out"] - m["in"]:.1f} s at {m.get("gain_db", -16)} dB')
            for s in edit.get('sfx', []):
                w(f'- {s.get("kind", "effect")} at {s["at"]:.1f} s ({os.path.basename(s["file"])})')
            w(f'- Mix: {edit.get("mix", {}).get("loudness", -14)} LUFS, music ducked '
              f'{edit.get("mix", {}).get("duck_db", 9)} dB under dialogue\n')

    w('## Spend\n')
    per = {}
    for c in ledger.get('calls', []):
        if c.get('status') == 'done':
            n, usd = per.get(c['endpoint'], (0, 0.0))
            per[c['endpoint']] = (n + 1, usd + (c.get('cost_usd') or 0))
    w('| Endpoint | Calls | USD |\n|---|---|---|')
    for ep_, (n, usd) in sorted(per.items(), key=lambda x: -x[1][1]):
        w(f'| `{ep_}` | {n} | {usd:.2f} |')
    w(f'| **total** | {sum(n for n, _ in per.values())} | **{spent:.2f}** of {ep.get("budget_usd", 0):.2f} |\n')

    w('## What differs from the plan\n')
    if a.notes and os.path.exists(a.notes):
        w(open(a.notes, encoding='utf-8').read().strip() + '\n')
    else:
        w('_No notes given._\n')
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print(a.out)


if __name__ == '__main__':
    main()
