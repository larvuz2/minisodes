#!/usr/bin/env python3
"""Cut the episode from an edit list: picture, dialogue with J/L cuts, music ducked under dialogue, sound effects,
loudness to the social target, captions and hook text inside the phone's safe zones.

edit.json (see templates/edit.json):
  clips     [{take, in, out, j, l, punch, focus, gain_db, beat, shot}]  in order; in/out in take seconds.
            j = its audio starts j s before its picture (J-cut), l = its audio runs l s past it (L-cut);
            the neighbor's audio is trimmed to make room. punch 1.1 = 10 % push-in, focus [x, y] in 0..1.
  overlays  [{text, start, end, style: "hook" | "title"}]  timeline seconds; \\n for a line break
  captions  true | false        words from review/<take>/words.json (review_take.py --transcribe)
  music     [{file, at, in, out, gain_db, fade_in, fade_out}]
  sfx       [{file, at, gain_db}]
  mix       {loudness: -14, true_peak: -1.5, duck_db: 9, dialogue_gain_db: 0}

Usage:
  python3 assemble.py edit.json -o out/            # out/final.mp4 (captions), out/final_clean.mp4, out/poster.jpg
  python3 assemble.py edit.json -o out/ --draft    # fast, low quality, for checking timing

Needs ffmpeg with libass and libx264. Standard library only.
"""
import argparse
import json
import os
import re
import subprocess
import sys

LILAC_ASS = '&H00FFA5C4'      # #C4A5FF in ASS BGR
INK_ASS = '&H00140F12'


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type:format=duration', '-of',
                          'json', path], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    return {'duration': float(d['format']['duration']), 'audio': any(s['codec_type'] == 'audio' for s in d['streams'])}


def run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'{what} failed:\n{r.stderr[-3000:]}')
    return r


def layout(edit, base):
    """Timeline positions of every clip and its audio range after J/L cuts."""
    clips = []
    t = 0.0
    for c in edit['clips']:
        c = dict(c)
        c['path'] = os.path.join(base, c['take'])
        c['dur'] = round(c['out'] - c['in'], 4)
        if c['dur'] <= 0:
            sys.exit(f'clip {c["take"]} has out <= in')
        c['start'] = t
        t += c['dur']
        clips.append(c)
    for i, c in enumerate(clips):
        nxt = clips[i + 1] if i + 1 < len(clips) else None
        prv = clips[i - 1] if i > 0 else None
        head = c.get('j', 0) - (prv.get('l', 0) if prv else 0)          # >0 starts early, <0 starts late
        tail = c.get('l', 0) - (nxt.get('j', 0) if nxt else 0)          # >0 runs late, <0 ends early
        c['a_in'] = max(0.0, c['in'] - head)
        c['a_out'] = c['out'] + tail
        c['a_at'] = c['start'] - (c['in'] - c['a_in'])
    return clips, t


def picture_graph(clips, inputs, W, H, fps):
    parts = []
    for k, c in enumerate(clips):
        i = inputs[c['path']]
        p = float(c.get('punch', 1.0))
        fx, fy = c.get('focus', [0.5, 0.5])
        chain = (f'[{i}:v]trim=start={c["in"]}:end={c["out"]},setpts=PTS-STARTPTS,fps={fps},'
                 f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}')
        if p > 1.0:
            chain += (f',scale={round(W * p / 2) * 2}:{round(H * p / 2) * 2},'
                      f'crop={W}:{H}:(iw-{W})*{fx}:(ih-{H})*{fy}')
        parts.append(chain + f',setsar=1[v{k}]')
    parts.append(''.join(f'[v{k}]' for k in range(len(clips))) + f'concat=n={len(clips)}:v=1:a=0[v]')
    return ';\n'.join(parts)


def audio_graph(edit, clips, inputs, total, base, has_audio):
    parts, dlg, mus, sfx = [], [], [], []
    fmt = 'aformat=sample_rates=48000:channel_layouts=stereo'
    dg = edit.get('mix', {}).get('dialogue_gain_db', 0)
    for k, c in enumerate(clips):
        if not has_audio[c['path']]:
            continue
        d = c['a_out'] - c['a_in']
        parts.append(f'[{inputs[c["path"]]}:a]atrim=start={c["a_in"]}:end={c["a_out"]},asetpts=PTS-STARTPTS,{fmt},'
                     f'volume={c.get("gain_db", 0) + dg}dB,afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.02):.3f}:d=0.02,'
                     f'adelay={int(max(0, c["a_at"]) * 1000)}:all=1[d{k}]')
        dlg.append(f'[d{k}]')
    for k, m in enumerate(edit.get('music', [])):
        i = inputs[os.path.join(base, m['file'])]
        d = m['out'] - m['in']
        parts.append(f'[{i}:a]atrim=start={m["in"]}:end={m["out"]},asetpts=PTS-STARTPTS,{fmt},volume={m.get("gain_db", -16)}dB,'
                     f'afade=t=in:d={m.get("fade_in", 0.05)},afade=t=out:st={max(0, d - m.get("fade_out", 0.4)):.3f}:'
                     f'd={m.get("fade_out", 0.4)},adelay={int(m["at"] * 1000)}:all=1[m{k}]')
        mus.append(f'[m{k}]')
    for k, s in enumerate(edit.get('sfx', [])):
        i = inputs[os.path.join(base, s['file'])]
        parts.append(f'[{i}:a]{fmt},volume={s.get("gain_db", -8)}dB,adelay={int(s["at"] * 1000)}:all=1[s{k}]')
        sfx.append(f'[s{k}]')

    def bus(names, label):
        if not names:
            parts.append(f'anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[{label}]')
        else:
            parts.append(''.join(names) + f'amix=inputs={len(names)}:normalize=0:duration=longest,'
                         f'apad=whole_dur={total:.3f},atrim=0:{total:.3f}[{label}]')

    bus(dlg, 'dlg')
    bus(mus, 'mus')
    bus(sfx, 'sfx')
    duck = edit.get('mix', {}).get('duck_db', 9)
    ratio = max(1.5, 10 ** (duck / 20))
    parts.append('[dlg]asplit=2[dlg1][dlgk]')
    parts.append(f'[mus][dlgk]sidechaincompress=threshold=0.025:ratio={ratio:.1f}:attack=15:release=350[musd]')
    parts.append('[dlg1][musd][sfx]amix=inputs=3:normalize=0,alimiter=limit=0.97:level=false[mix]')
    return ';\n'.join(parts)


def words_for(clips, base):
    """Spoken words placed on the timeline through each clip's audio range."""
    out = []
    for c in clips:
        name = os.path.splitext(os.path.basename(c['take']))[0]
        path = os.path.join(base, 'review', name, 'words.json')
        if not os.path.exists(path):
            continue
        for w in json.load(open(path)).get('words', []):
            if w.get('type', 'word') != 'word' or w['start'] < c['a_in'] or w['end'] > c['a_out'] + 0.05:
                continue
            out.append({'text': w['text'].strip(), 'start': c['a_at'] + (w['start'] - c['a_in']),
                        'end': c['a_at'] + (w['end'] - c['a_in'])})
    return sorted(out, key=lambda w: w['start'])


def ts(t):
    t = max(0.0, t)
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'


def ass_file(edit, words, W, H, path):
    vertical = H > W
    cap_size, hook_size = (int(H * 0.034), int(H * 0.04)) if vertical else (int(H * 0.05), int(H * 0.06))
    cap_mv = int(H * 0.27) if vertical else int(H * 0.08)        # above the bottom UI band
    hook_mv = int(H * 0.13) if vertical else int(H * 0.07)       # below the top UI band
    side_l, side_r = (int(W * 0.08), int(W * 0.15)) if vertical else (int(W * 0.1), int(W * 0.1))  # right rail
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Inter,{cap_size},{LILAC_ASS},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{max(3, cap_size // 14)},1,2,{side_l},{side_r},{cap_mv},1
Style: Hook,Inter,{hook_size},{INK_ASS},&H00FFFFFF,{LILAC_ASS},&H00000000,-1,0,0,0,100,100,0,0,3,{max(8, hook_size // 4)},0,8,{side_l},{side_r},{hook_mv},1
Style: Title,Inter,{hook_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,5,{side_l},{side_r},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for o in edit.get('overlays', []):
        style = {'hook': 'Hook', 'title': 'Title'}.get(o.get('style', 'hook'), 'Hook')
        ev.append(f'Dialogue: 1,{ts(o["start"])},{ts(o["end"])},{style},,0,0,0,,{o["text"].upper().replace(chr(10), "\\N")}')
    if edit.get('captions', True) and words:
        chunks, cur = [], []
        for w in words:
            if cur and (len(cur) >= 3 or w['start'] - cur[-1]['end'] > 0.35 or w['end'] - cur[0]['start'] > 1.4
                        or re.search(r'[.?!,;:—-]$', cur[-1]['text'])):
                chunks.append(cur)
                cur = []
            cur.append(w)
        if cur:
            chunks.append(cur)
        for i, ch in enumerate(chunks):
            # hold a beat after the last word, but never overlap the next caption (libass would stack them)
            end = ch[-1]['end'] + 0.15
            if i + 1 < len(chunks):
                end = min(end, chunks[i + 1][0]['start'] - 0.01)
            # karaoke: each word stays highlighted until the next one starts, so the color follows the voice
            ks = [(ch[k + 1]['start'] if k + 1 < len(ch) else w['end']) - w['start'] for k, w in enumerate(ch)]
            txt = ''.join('{\\k%d}%s ' % (max(1, round(k * 100)), w['text'].upper()) for k, w in zip(ks, ch))
            ev.append(f'Dialogue: 0,{ts(ch[0]["start"])},{ts(end)},Caption,,0,0,0,,{txt.strip()}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(head + '\n'.join(ev) + '\n')
    return len(ev)


def loudnorm(src, dest, target, tp):
    r = run(['ffmpeg', '-hide_banner', '-i', src, '-af', f'loudnorm=I={target}:TP={tp}:LRA=11:print_format=json',
             '-f', 'null', '-'], 'loudness measure')
    m = json.loads(r.stderr[r.stderr.rfind('{'):r.stderr.rfind('}') + 1])
    af = (f'loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m["input_i"]}:measured_TP={m["input_tp"]}:'
          f'measured_LRA={m["input_lra"]}:measured_thresh={m["input_thresh"]}:offset={m["target_offset"]}:linear=true')
    run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-af', af, '-ar', '48000', dest], 'loudness apply')
    return float(m['input_i'])


def cut_sheet(video, clips, out):
    """The last frame before and the first frame after every cut, side by side, one row per cut."""
    tmp = os.path.join(os.path.dirname(out), '.work', 'cuts')
    os.makedirs(tmp, exist_ok=True)
    rows = []
    for k, c in enumerate(clips[1:], 1):
        pair = []
        for side, t in (('a', c['start'] - 0.06), ('b', c['start'] + 0.06)):
            f = os.path.join(tmp, f'{k:02d}{side}.jpg')
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{max(0, t):.3f}', '-i', video, '-frames:v', '1',
                            '-vf', 'scale=-2:360', f], check=True)
            pair.append(f)
        rows.append(pair)
    if not rows:
        return None
    ins = sum((['-i', f] for pair in rows for f in pair), [])
    n = len(rows)
    cols = 4                                    # two cuts per row: before|after  before|after
    graph = ''.join(f'[{i}]' for i in range(2 * n)) + f'xstack=inputs={2 * n}:layout=' + '|'.join(
        f'{"+".join(["w0"] * (i % cols)) or 0}_{"+".join(["h0"] * (i // cols)) or 0}' for i in range(2 * n)) + ':fill=white'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *ins, '-filter_complex', graph, '-frames:v', '1', '-q:v', '3', out],
                   check=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('edit')
    ap.add_argument('-o', '--out', default='out')
    ap.add_argument('--draft', action='store_true', help='fast encode for timing checks')
    a = ap.parse_args()

    edit = json.load(open(a.edit, encoding='utf-8'))
    base = os.path.dirname(os.path.abspath(a.edit))
    os.makedirs(a.out, exist_ok=True)
    work = os.path.join(a.out, '.work')
    os.makedirs(work, exist_ok=True)
    W, H = map(int, edit.get('size', '1080x1920').split('x'))
    fps = edit.get('fps', 30)
    clips, total = layout(edit, base)

    files = []
    for c in clips:
        if c['path'] not in files:
            files.append(c['path'])
    for m in edit.get('music', []) + edit.get('sfx', []):
        p = os.path.join(base, m['file'])
        if p not in files:
            files.append(p)
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        sys.exit(f'missing files: {missing}')
    inputs = {f: i for i, f in enumerate(files)}
    info = {f: probe(f) for f in files}
    for c in clips:
        if c['out'] > info[c['path']]['duration'] + 0.05:
            sys.exit(f'{c["take"]}: out {c["out"]} past the end ({info[c["path"]]["duration"]:.2f} s)')
    in_args = sum((['-i', f] for f in files), [])
    q = ['-preset', 'veryfast', '-crf', '26'] if a.draft else ['-preset', 'slow', '-crf', '16']

    # 1. picture
    script = os.path.join(work, 'picture.txt')
    open(script, 'w').write(picture_graph(clips, inputs, W, H, fps))
    picture = os.path.join(work, 'picture.mp4')
    run(['ffmpeg', '-v', 'error', '-y', *in_args, '-filter_complex_script', script, '-map', '[v]', '-c:v', 'libx264',
         *q, '-pix_fmt', 'yuv420p', picture], 'picture')

    # 2. sound: dialogue bus, music ducked under it, effects, then loudness
    script = os.path.join(work, 'audio.txt')
    open(script, 'w').write(audio_graph(edit, clips, inputs, total, base, {f: info[f]['audio'] for f in files}))
    mix = os.path.join(work, 'mix.wav')
    run(['ffmpeg', '-v', 'error', '-y', *in_args, '-filter_complex_script', script, '-map', '[mix]', '-ar', '48000', mix],
        'audio mix')
    mixcfg = edit.get('mix', {})
    norm = os.path.join(work, 'mix_norm.wav')
    before = loudnorm(mix, norm, mixcfg.get('loudness', -14), mixcfg.get('true_peak', -1.5))

    # 3. clean master, then the social master with captions and hook text
    clean = os.path.join(a.out, 'final_clean.mp4')
    run(['ffmpeg', '-v', 'error', '-y', '-i', picture, '-i', norm, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', clean], 'clean master')
    ass = os.path.join(a.out, 'captions.ass')
    n_ev = ass_file(edit, words_for(clips, base), W, H, ass)
    final = os.path.join(a.out, 'final.mp4')
    if n_ev:
        esc = ass.replace('\\', '/').replace(':', '\\:').replace("'", "\\'")
        run(['ffmpeg', '-v', 'error', '-y', '-i', clean, '-vf', f"subtitles='{esc}'", '-c:v', 'libx264', *q,
             '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', final], 'captions burn')
    else:
        run(['ffmpeg', '-v', 'error', '-y', '-i', clean, '-c', 'copy', final], 'copy')
    poster_t = edit.get('poster_t', next((o['start'] + 0.4 for o in edit.get('overlays', [])
                                           if o.get('style', 'hook') == 'hook'), 0.5))
    run(['ffmpeg', '-v', 'error', '-y', '-ss', str(poster_t), '-i', final, '-frames:v', '1', '-q:v', '2',
         os.path.join(a.out, 'poster.jpg')], 'poster')
    cuts_jpg = cut_sheet(clean, clips, os.path.join(a.out, '.work', 'cuts.jpg'))
    durs = [c['dur'] for c in clips]
    print(f'{final}: {total:.2f} s, {len(clips)} shots, average {total / len(clips):.2f} s, '
          f'longest {max(durs):.2f} s; mix {before:.1f} -> {mixcfg.get("loudness", -14)} LUFS; '
          f'{n_ev} caption/overlay events')
    print(f'{clean}\n{os.path.join(a.out, "poster.jpg")}\n{ass}')
    if cuts_jpg:
        print(f'{cuts_jpg}: before | after every cut, two cuts per row; look at every pair')


if __name__ == '__main__':
    main()
