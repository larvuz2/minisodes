# Edit: the pacing pass

The edit decides whether a viewer stays. It is measured: every cut has a reason (Murch's order: emotion, story,
rhythm, then eye-trace and space), and every minute is checked against numbers from the format and from how
attention behaves.

## What the numbers are based on

- **The first seconds decide.** Short-form feeds let a viewer leave at any moment, and most leaving happens at the
  very start. Hence a face or threat in frame 1, hook text by 0.6 s, the first line by 2 s, stakes by 5 s.
- **Change keeps attention.** Viewers re-orient at every change of picture or sound. Plan a small change (a cut,
  a line, a sound) every 3-5 s and a re-hook (a new fact, person, place or a reversal) every 15-20 s
  (`format.md`).
- **Shot length.** Hollywood average shot length fell from about 10 s in the 1930s to about 4 s by the 2010s
  (Cutting et al., *Quicker, faster, darker: changes in Hollywood film over 75 years*, 2011); dialogue-driven vertical drama runs shorter,
  about 2-3.5 s. Lengths in a well-cut scene vary: most shots short, a few long holds (a skewed, roughly lognormal
  spread), and the variation itself follows slower rhythms rather than noise (Cutting, DeLong and Nothelfer,
  *Attention and the evolution of Hollywood film*, 2010). Do not cut on a metronome: cluster fast cuts in the
  pressure and the twist, hold the faces that matter.
- **Rule of six** (Walter Murch, *In the Blink of an Eye*): a cut is good if it serves emotion (51 %), then story
  (23 %), rhythm (10 %), eye-trace (7 %), the 2D plane (5 %) and 3D space (4 %). Give up the lower ones first.
- **Eye-trace.** On a phone the eye lives in the upper-middle of the frame. Cut between shots whose point of
  interest sits in the same place (the speaker's eyes), and the cut costs no attention; make the eye jump only on
  purpose (a reveal).
- **Cut at the end of a thought** (Murch's blink): when a line lands or a look completes, not in the middle of it,
  except for the unfinished-line cliffhanger.

## The edit list (`edit.json`, see `templates/edit.json`)

```json
{"take": "takes/s01_t2.mp4", "in": 4.0, "out": 8.0, "beat": "anchor", "shot": "s01.3", "j": 0, "l": 0,
 "punch": 1.0, "focus": [0.5, 0.4], "gain_db": 0}
```

- `in`/`out` are seconds in the take, inside a usable range from the review. Clips play in order; the timeline is
  the sum of their lengths, so the episode lasts exactly what the cut says.
- `beat` and `shot` tie the clip to the plan: `pace.py` draws beats and reads planned lines through them.
- `j` (J-cut): this clip's sound starts `j` seconds under the previous picture: the next line or sound pulls the
  viewer into the cut (anticipation). `l` (L-cut): this clip's sound runs `l` seconds over the next picture: cut
  to the listener while the speaker finishes (the reaction is the point). 0.2-0.6 s each. The neighbor's sound is
  trimmed automatically.
- `punch` 1.05-1.2 crops in for emphasis or to cut inside one take (a "punch-in"), centered on `focus` [x, y]. At
  480P keep it at 1.1 or under, or the picture goes soft.
- `overlays`: the hook text (`style: hook`, the lilac box in the upper third, 0.25 to about 2.5 s). Uppercase, 8
  words or fewer, split in two lines with `\n`.
- `captions: true` burns the spoken words from the take transcripts (2-3 words per caption, at most 1.4 s,
  uppercase, the current word highlighted), above the bottom UI band and clear of the right rail.
- `markers`: the story events the pace check counts as re-hooks (`arrival`, `twist`, `reveal`, `turn`, `cliff`,
  `new-fact`...) and planned silences (`silence` with `until`), which are not dead air.

## The passes

1. **Assembly.** Every sequence's kept range in order, trimmed to its slot. `pace.py edit.json -o pace/`.
2. **Rough cut.** Cut the dead air: a pause over 0.4 s between lines goes unless it is a planned beat; heads
   where nothing happens yet go; the model's slow starts go. Re-check pace.
3. **Fine cut.** Reaction shots after the big lines; J-cuts into reveals; L-cuts out of lines that land on someone
   else; punch-ins on the realization; the comedy pause before the punchline (0.3-0.6 s) and the cut to the
   reaction on the laugh.
4. **Lock.** Every `pace.py` check passes or has a written reason in `notes.md`. Render a draft:
   `assemble.py edit.json -o out/ --draft`, and look at `out/.work/cuts.jpg` (the frames before and after every
   cut): a face that jumps, a hand that changes, an eyeline that flips is a cut to move or cover.
5. **Score and mix** (`sound.md`), then the master and `pace.py --render out/final.mp4`.

## The checks (`pace.py`)

| Check | Threshold |
|---|---|
| Face or threat in frame 1 | the first shot has someone in it |
| Hook text lands | by 0.6 s |
| First line | by 2 s |
| Recap line | in the first 20 s |
| A re-hook every 20 s | longest gap between beats, story markers or hits |
| Something changes every 5 s | longest gap with no cut, line, effect or music event |
| Average shot | 2.0-3.5 s (comedy 1.8-3.2, thriller 1.5-3.0) |
| No shot over 6 s | unless a planned hold (then say so in the notes) |
| Midpoint turn | between 35 % and 60 % |
| No dead air over 3 s | unless marked as a planned silence |
| Speech pace | 2.0-3.6 words per second while talking |
| Ends on the loaded moment | last shot 4 s or shorter, no fade longer than 0.2 s |
| Reads with sound off | captions on and hook text present |
| Loudness (with --render) | -14 LUFS +-1, true peak -1 dBTP or lower |

`pace.svg` draws it all on one timeline: beats by tension, the target pressure curve against your cut, every
shot with its length (red over 6 s), dialogue, music cues, effects, hook text, markers, and the master's energy.
Send it with the episode.
