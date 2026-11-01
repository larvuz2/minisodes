#!/usr/bin/env python3
"""Turn the trailer (or any clip) into things you can look at: frames, a timed contact sheet, palette, cuts.

The trailer the user approved is the look document of the episode: its people become the cast sheets, its
rooms become the locations, its light and grade become the look. Open the sheet first, then the frames, and
write down which frame shows each character and each place best (study.json lists every frame with its time).

Usage:
  python3 study_video.py trailer.mp4 -o study/
  python3 study_video.py trailer.mp4 -o study/ --every 0.25 --colors 12

Needs ffmpeg and ffprobe. Standard library only.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from review_take import cuts, probe, sheet  # noqa: E402


def frames(path, out, every, info):
    w = 720 if info['height'] > info['width'] else 1280
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vf', f'fps=1/{every},scale={w}:-2', '-q:v', '2',
                    os.path.join(out, 'f_%03d.jpg')], check=True)
    names = sorted(f for f in os.listdir(out) if f.startswith('f_') and f.endswith('.jpg'))
    return [{'t': round(i * every, 2), 'file': n} for i, n in enumerate(names)]


def palette(path, k):
    """Dominant colors from 24 small frames, 4 bits per channel, with their share of the picture."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vf', 'fps=2,scale=48:-2', '-frames:v', '24',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    bins, sums = Counter(), {}
    for i in range(0, len(raw) - 2, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        key = (r >> 4, g >> 4, b >> 4)
        bins[key] += 1
        s = sums.setdefault(key, [0, 0, 0])
        s[0] += r
        s[1] += g
        s[2] += b
    total = sum(bins.values()) or 1
    return [{'hex': '#%02x%02x%02x' % tuple(v // n for v in sums[key]), 'share': round(n / total, 3)}
            for key, n in bins.most_common(k)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video')
    ap.add_argument('-o', '--out', default='study')
    ap.add_argument('--every', type=float, default=0.5, help='seconds between saved frames')
    ap.add_argument('--colors', type=int, default=10)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    info = probe(a.video)
    fr = frames(a.video, a.out, a.every, info)
    sheet_path = sheet(a.video, a.out, info, every=max(0.5, info['duration'] / 30), with_frames=False)
    info.update(palette=palette(a.video, a.colors), cuts=cuts(a.video), frames=fr,
                sheet=os.path.basename(sheet_path))
    with open(os.path.join(a.out, 'study.json'), 'w') as f:
        json.dump(info, f, indent=1)
    print(f"{info['width']}x{info['height']} {info['fps']} fps {info['duration']} s, {len(fr)} frames, "
          f"cuts at {info['cuts']}, palette {' '.join(c['hex'] for c in info['palette'])}")
    print(f'open {sheet_path} first, then the frames (f_NNN.jpg, times in study.json)')


if __name__ == '__main__':
    main()
