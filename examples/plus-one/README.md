# Plus One (example)

A complete plan for a 60 s vertical romantic comedy, written with the minisode skill. It is the worked example of
every file an episode needs before and after the camera rolls, and the fixture the repository tests run on.

> At the wedding of the friend who stole her fiancé, Nora's hired date turns out to be the bride's jilted ex, and
> he did not pick Nora by chance.

| File | What it is |
|---|---|
| [`episode.json`](episode.json) | the plan: episode sheet, 7 beats, look, 3 characters, 1 location, 9 references with their recipes, 5 sequences of 13 s with 21 shots, 3 music cues |
| [`trailer.txt`](trailer.txt) | the trailer prompt the user approved (the look document) |
| [`blockout/glasshouse.json`](blockout/glasshouse.json) | the gray-box reception: tables, chairs, string lights, actor marks, 6 cameras |
| [`blockout/plan.jpg`](blockout/plan.jpg), [`blockout/cameras.jpg`](blockout/cameras.jpg) | the top view and four camera renders (wide, reverse, over the shoulder, close-up) |
| [`edit.json`](edit.json) | the cut: 21 clips with a J-cut, an L-cut and two punch-ins, hook text, 3 music cues, 3 effects, story markers |
| [`pace.svg`](pace.svg) | the pace map of the cut against the target pressure curve |

The story beats:

| Time | Beat | What happens |
|---|---|---|
| 0-4 s | hook | "Smile. Your ex is watching." Hook text: SHE HIRED HIM FOR ONE NIGHT. |
| 4-12 s | anchor | "She married my fiancé. Tonight, you're mine." (the recap line) |
| 12-24 s | pressure | The bride arrives, sees the hired date: "Theo?" "Hi, Celeste." A held beat. |
| 24-36 s | twist | "You swore you'd never come back." "I was supposed to marry her." |
| 36-47 s | choice | Nora kisses Theo in front of the bride. |
| 47-55 s | payoff | The bride walks away. "Did she cry?" "Not yet." "Then you're not done." |
| 55-60 s | cliff | "I didn't answer your ad by accident." Held look, hard cut. |

Run the checks from this folder:

```bash
python3 ../../skills/minisode/scripts/plan_check.py episode.json
python3 ../../skills/minisode/scripts/prompt.py episode.json s01
python3 ../../skills/minisode/scripts/pace.py --plan episode.json -o /tmp/pace
python3 ../../skills/minisode/scripts/make.py episode.json --estimate
python3 ../../skills/minisode/scripts/shoot.py episode.json s01 s02 --dry-run
node ../../skills/minisode/scripts/blockout.mjs blockout/glasshouse.json -o blockout/glasshouse/
```

To make it for real, generate the trailer from `trailer.txt` with `minimax/h3-max/text-to-video` (15 s, 9:16),
study it into `study/` and point the sheet recipes at the frames where each person is clearest, then follow
`skills/minisode/SKILL.md` from step 4. At 768P it plans to about 7 USD once, 9 USD with retakes.
