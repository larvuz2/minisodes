#!/usr/bin/env python3
"""Build the video prompt and the reference lists for each sequence of an episode plan.

The plan (episode.json) names every reference by asset id. This script turns a sequence into what the video
model needs: an ordered list of image, audio and video references, and a prompt whose REFERENCES block binds
each one ("Image 1 is Nora's character sheet", "Audio 1 is Nora's voice"), then the look, then the shots second
by second, then the sound. "No music" is the first line of every prompt and is repeated in the sound block:
the score is added in the edit.

Usage:
  python3 prompt.py episode.json              # every sequence: prompt, references, warnings
  python3 prompt.py episode.json s01 s03      # only these
  python3 prompt.py episode.json s01 --json   # machine-readable (what shoot.py sends)

Standard library only. File paths in the plan are relative to the plan's folder.
"""
import argparse
import json
import os
import re
import sys

LIMITS = {'image': 9, 'audio': 3, 'video': 3, 'total': 12, 'audio_s': 15.0, 'video_s': 15.0, 'duration': 15.0}
FRAMES = {'ECU': 'extreme close-up', 'CU': 'close-up', 'MCU': 'medium close-up', 'MS': 'medium shot',
          'MWS': 'medium wide shot', 'WS': 'wide shot', 'EWS': 'extreme wide shot', 'OTS': 'over-the-shoulder shot',
          'POV': 'point-of-view shot', 'INSERT': 'insert close-up', '2S': 'two-shot', 'TWO-SHOT': 'two-shot',
          'MCU-2S': 'medium close two-shot'}
LANGS = {'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian', 'pt': 'Portuguese',
         'ja': 'Japanese', 'ko': 'Korean', 'zh': 'Mandarin Chinese'}
SAFE_VERTICAL = ('Vertical 9:16 frame for phones: faces and key action sit in the middle band, eyes in the upper '
                 'third, nothing important in the top 12% or the bottom 20% of the frame, or along the right edge.')


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f), os.path.dirname(os.path.abspath(path))


def media_seconds(path):
    import subprocess
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out) if out else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def by_id(items):
    return {x['id']: x for x in items or []}


def owner_name(ep, oid):
    for group in ('cast', 'locations', 'props'):
        hit = by_id(ep.get(group)).get(oid)
        if hit:
            return hit.get('name') or oid, group
    return oid, None


def describe(ep, aid, asset, n):
    """One REFERENCES line for an asset, by its kind."""
    if asset.get('bind'):
        return asset['bind'].replace('{n}', str(n))
    name, _ = owner_name(ep, asset.get('of', ''))
    kind = asset.get('kind', '')
    t = asset['type'].capitalize()
    if kind == 'character_sheet':
        return (f'{t} {n} is {name}\'s character sheet (full body on the left, face close-ups on the right): keep '
                f'{name}\'s face, hair, body, wardrobe and accessories exactly as shown.')
    if kind == 'face':
        return f'{t} {n} is {name}\'s face up close: match identity, skin, eyes, hair and expression range.'
    if kind == 'outfit':
        return f'{t} {n} shows {name}\'s outfit and accessories up close: same garments, colors and details.'
    if kind == 'location':
        view = f' (view: {asset["view"]})' if asset.get('view') else ''
        return f'{t} {n} is {name}{view}: keep its layout, furniture, materials, colors and light.'
    if kind == 'prop':
        return f'{t} {n} is the {name}: keep its shape, color, size and material.'
    if kind == 'voice':
        return f'{t} {n} is {name}\'s voice: {name} speaks only in this voice (timbre, accent, rhythm).'
    if kind == 'camera_move':
        return (f'{t} {n} shows only the camera move: copy its path, speed and framing; ignore its gray clay look '
                f'and mannequins.')
    if kind == 'motion':
        return f'{t} {n} shows {asset.get("label", "the movement")}: copy the movement and timing, not the look.'
    return f'{t} {n} is {asset.get("label") or name}.'


def fmt_t(x):
    return f'{x:.1f}'.rstrip('0').rstrip('.') if x != int(x) else str(int(x))


def render_line(ep, line, voice_tag):
    who = by_id(ep.get('cast')).get(line['who'], {}).get('name', line['who'])
    how = f', {line["how"]}' if line.get('how') else ''
    voice = f' (voice: {voice_tag})' if voice_tag else ''
    return f'{who}{voice} says{how}: "{line["text"]}"'


def tag_first(text, name, tag):
    """Put the reference tag on the first natural mention of a name, never inside quoted dialogue.

    Prefers a plain mention ("Nora turns"), then the speaker of a line ("Nora (voice: Audio 1) says"),
    then a possessive ("Nora's eyes")."""
    parts = re.split(r'("[^"]*")', text)          # odd indexes are quoted dialogue
    n = re.escape(name)
    tries = [(rf"\b{n}\b(?!'s)(?! \()", f'{name} ({tag})'),
             (rf'\b{n} \(voice: ', f'{name} ({tag}, voice: '),
             (rf"\b{n}'s\b", f"{name}'s ({tag})")]
    for pattern, repl in tries:
        for i in range(0, len(parts), 2):
            new, k = re.subn(pattern, repl, parts[i], count=1)
            if k:
                parts[i] = new
                return ''.join(parts), True
    return text, False


def build(ep, seq_id, base='.'):
    """Everything the video model needs for one sequence, plus warnings."""
    seqs = by_id(ep.get('sequences'))
    if seq_id not in seqs:
        raise SystemExit(f'no sequence {seq_id}')
    seq = seqs[seq_id]
    assets = ep.get('assets', {})
    look = ep.get('look', {})
    fmt = ep.get('format', {})
    cast = by_id(ep.get('cast'))
    warn = []

    refs = {'image': [], 'audio': [], 'video': []}
    for aid in seq.get('refs', []) + seq.get('video_refs', []):
        a = assets.get(aid)
        if not a:
            warn.append(f'unknown asset {aid}')
            continue
        refs[a['type']].append(aid)
    tags = {}
    lines = []
    for kind in ('image', 'video', 'audio'):
        for i, aid in enumerate(refs[kind], 1):
            tags[aid] = f'{kind.capitalize()} {i}'
            lines.append(describe(ep, aid, assets[aid], i))

    # who has which reference, so names can carry their tag on first mention
    person_tags, voice_tag = {}, {}
    for aid, tag in tags.items():
        a = assets[aid]
        if a.get('of') in cast:
            if a['type'] == 'image':
                person_tags.setdefault(a['of'], []).append(tag)
            elif a.get('kind') == 'voice':
                voice_tag[a['of']] = tag

    shots_txt = []
    speakers = set()
    for i, sh in enumerate(seq.get('shots', [])):
        t0, t1 = sh['t']
        frame = FRAMES.get(sh.get('frame', '').upper(), sh.get('frame', ''))
        camera = ', '.join(x for x in (frame.upper(), sh.get('angle'), sh.get('lens'), sh.get('move')) if x)
        cut = '' if i == 0 else (sh.get('transition') or 'Hard cut') + '. '
        body = [sh.get('action', '').strip()]
        for ln in sh.get('lines', []):
            speakers.add(ln['who'])
            body.append(render_line(ep, ln, voice_tag.get(ln['who'])))
        if sh.get('silence'):
            body.append(f'Silence: {sh["silence"]}.')
        if sh.get('sound'):
            body.append(f'Sound: {sh["sound"]}.')
        shots_txt.append(f'{fmt_t(t0)}-{fmt_t(t1)} s: {cut}{camera}.\n' + ' '.join(b for b in body if b))
    shots = '\n'.join(shots_txt)
    for cid, ts in person_tags.items():
        name = cast[cid].get('name', cid)
        tag = ts[0] if len(ts) == 1 else ', '.join(ts[:-1]) + ' and ' + ts[-1]
        shots, ok = tag_first(shots, name, tag)
        if not ok:
            warn.append(f'{name} has a reference image but is never named in the shots')

    lang = LANGS.get(fmt.get('language', 'en'), fmt.get('language', 'English'))
    aspect = fmt.get('aspect_ratio', '9:16')
    duration = float(seq.get('duration', 10))
    n_shots = len(seq.get('shots', []))
    head = ['No music. No subtitles, captions or on-screen text.',
            f'{aspect} {ep.get("genre_label") or ep.get("genre", "drama")} micro-drama, {fmt_t(duration)} seconds, '
            f'{seq.get("place") or owner_name(ep, seq.get("location", ""))[0]}, {seq.get("time", "")}'.rstrip(', ')
            + f', {n_shots} shot{"s" if n_shots != 1 else ""} cut together like a finished scene.']
    look_bits = [look.get('style'), 'Lighting: ' + (seq.get('light') or look.get('lighting', '')),
                 'Camera: ' + look.get('camera', ''), 'Grade: ' + look.get('grade', ''),
                 'Texture: ' + look.get('texture', '')]
    look_txt = ' '.join(b.rstrip('.') + '.' for b in look_bits if b and not b.endswith(': '))
    if aspect == '9:16':
        look_txt += ' ' + SAFE_VERTICAL
    ambience = seq.get('ambience') or look.get('ambience') or 'natural room tone'
    if speakers:
        sound = (f'Native audio with lip-synced {lang} dialogue: only the lines written above, each spoken once, '
                 f'by the character named, in that character\'s voice. Ambience: {ambience}. '
                 'No music, no score, no soundtrack, no singing, no humming.')
    else:
        sound = f'Native audio, no dialogue. Ambience: {ambience}. No music, no score, no soundtrack.'
    avoid = ', '.join(x for x in [look.get('avoid'), 'text, subtitles, logos, watermarks',
                                   'extra people talking', 'faces or hands that morph'] if x)
    must = seq.get('must') or []              # fixes written after reviewing a take ("Theo's ring stays on his right hand")
    must_txt = 'MUST\n' + '\n'.join(f'- {m.rstrip(".")}.' for m in must) if must else ''
    prompt = '\n\n'.join(['\n'.join(head), 'REFERENCES\n' + '\n'.join(lines) if lines else '',
                          'LOOK\n' + look_txt, 'SHOTS\n' + shots, must_txt, 'SOUND\n' + sound,
                          'AVOID\n' + avoid.capitalize() + '.'])
    prompt = re.sub(r'\n{3,}', '\n\n', prompt).strip()

    # limits of the model and of the format
    total = sum(len(v) for v in refs.values())
    for kind in ('image', 'audio', 'video'):
        if len(refs[kind]) > LIMITS[kind]:
            warn.append(f'{len(refs[kind])} {kind} references (max {LIMITS[kind]})')
    if total > LIMITS['total']:
        warn.append(f'{total} references (max {LIMITS["total"]})')
    for kind in ('audio', 'video'):
        secs = 0.0
        for aid in refs[kind]:
            f = os.path.join(base, assets[aid].get('file', ''))
            s = assets[aid].get('seconds') or (media_seconds(f) if os.path.exists(f) else None) or 5.0
            if not 2 <= s <= 15:
                warn.append(f'{aid} is {s:.1f} s; {kind} references must be 2-15 s')
            secs += s
        if secs > LIMITS[f'{kind}_s']:
            warn.append(f'{kind} references add up to {secs:.1f} s (max 15)')
    if not 0.92 <= duration <= LIMITS['duration']:
        warn.append(f'duration {duration} s outside 0.92-15')
    for sp in speakers:
        if sp not in voice_tag:
            warn.append(f'{cast.get(sp, {}).get("name", sp)} speaks but has no voice reference in this sequence')
    in_shots = {w for sh in seq.get('shots', []) for w in sh.get('who', [])}
    for cid in in_shots:
        if cid not in person_tags:
            warn.append(f'{cast.get(cid, {}).get("name", cid)} is on screen but has no image reference')
    if len(prompt) > 4500:
        warn.append(f'prompt is {len(prompt)} characters; keep it under ~4500')
    if seq.get('shots') and abs(seq['shots'][-1]['t'][1] - duration) > 0.3:
        warn.append(f'shots end at {seq["shots"][-1]["t"][1]} s but the sequence lasts {duration} s')

    def files(kind):
        return [os.path.join(base, assets[a]['file']) for a in refs[kind]]

    def frame_file(key):
        v = seq.get(key)
        if not v or v == 'chain':
            return v
        return os.path.join(base, assets[v]['file']) if v in assets else v

    return {'id': seq_id, 'prompt': prompt, 'tags': tags, 'refs': refs,
            'reference_image_files': files('image'), 'reference_audio_files': files('audio'),
            'reference_video_files': files('video'), 'start_image': frame_file('start_image'),
            'end_image': frame_file('end_image'), 'duration': duration, 'aspect_ratio': aspect,
            'resolution': seq.get('resolution') or fmt.get('resolution', '768P'), 'seed': seq.get('seed'),
            'warnings': warn}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('plan')
    ap.add_argument('sequences', nargs='*')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    ep, base = load(a.plan)
    ids = a.sequences or [s['id'] for s in ep.get('sequences', [])]
    out = [build(ep, i, base) for i in ids]
    if a.json:
        print(json.dumps(out if len(out) > 1 else out[0], indent=1))
        return
    bad = 0
    for b in out:
        print(f'===== {b["id"]}  {b["duration"]} s  {b["resolution"]}  {len(b["prompt"])} chars')
        print('  '.join(f'{t} = {aid}' for aid, t in b['tags'].items()))
        if b['start_image']:
            print(f'first frame: {b["start_image"]}')
        print()
        print(b['prompt'])
        for w in b['warnings']:
            print(f'  ! {w}')
        bad += bool(b['warnings'])
        print()
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
