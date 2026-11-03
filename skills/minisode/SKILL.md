---
name: minisode
description: >-
  Makes a minisode: a finished 1 to 2 minute vertical (or landscape) micro-drama, comedy or romance for social
  media, from a concept and an approved trailer. Writes the episode to the micro-drama format (hook in 5 s,
  re-hook every 15-20 s, midpoint turn, cliffhanger), plans it second by second like a director and
  cinematographer, gray-boxes the locations, generates character sheets, location plates, keyframes and voices
  with fal, films 10-15 s sequences with MiniMax H3 Max reference-to-video under a hard budget, reviews every
  take, cuts it with a measured pacing pass, scores it, mixes it to -14 LUFS with captions and hook text, and
  delivers it to ShotForge. Two presets: social (the scroll-stopping micro-drama) and cinematic (quiet
  conversations, one camera essence, fixed coverage, a locked tone and look frame). Use when asked to make a
  minisode, mini episode, micro-drama, vertical short drama, cinematic short, episodic short or "a 1-minute
  episode" from an idea or trailer. Not for single clips, music videos or ads.
metadata:
  tags: [video, micro-drama, vertical-video, fal, minimax-h3, elevenlabs, editing, storytelling]
  category: creative
---

# Minisode

A minisode is a pressure loop you can watch on a phone: it hooks in five seconds, something changes every few
seconds, it turns at the middle, and it ends on a question. Your job is the whole crew: writer, director,
cinematographer, production designer, casting, sound, editor, composer. The video model is the camera and the
actors; it does what the prompt and the references say, and nothing you leave out. So the work happens before
the camera rolls (story, plan, references), and after (review, edit, mix), and both are measured, not felt.

You cannot watch video. Every judgment goes through pictures and numbers: contact sheets, frames, the cut
table, transcripts, the pace map. "Looks good" without one of those is not a check.

## Workflow

Work in one folder per episode (`work/<episode_id>/`); every path in the plan is relative to `episode.json`.
Each script prints its usage with `--help`. Scripts are in `scripts/` next to this file.

1. **Study the trailer.** `python3 scripts/study_video.py trailer.mp4 -o study/`. Open `study/sheet.jpg`, then
   frames. Note which frame shows each character and each place best, the light direction, the palette, the
   lens feel. The trailer is the look the user approved: the episode must look like it. `references/bible.md`.
2. **Write the story** into `episode.json` (start from `templates/episode.json`): logline, the episode sheet,
   beats timed to the duration, and the script with lines of 8 words or fewer. `references/format.md` (the
   rules), `references/story.md` (genre engines, dialogue, the beat math for 60-120 s).
3. **Plan the shoot**: sequences of 10-15 s that each land in a slot of the timeline plus about 1 s of handle,
   and inside each sequence the shots second by second: size, angle, lens, move, action, lines, sound.
   `python3 scripts/plan_check.py episode.json` until it shows zero errors and picks a resolution that fits the
   budget; `python3 scripts/pace.py --plan episode.json -o pace_plan/` until every check passes.
   `references/shots.md`.
4. **Block out the locations** in gray: one layout per place with furniture, actor marks and every camera of
   the shot list. `node scripts/blockout.mjs blockout/<place>.json -o blockout/<place>/`. Open `plan.png` and
   the `_labels.png` renders; fix the layout until each camera frames what its shots need.
   `references/blockout.md`.
5. **Build the references** declared in the plan's `assets` (each with a `make` recipe):
   `python3 scripts/make.py episode.json --estimate`, then build in order and look at every result before what
   depends on it: character sheets from trailer frames, location plates from the blockout renders and the
   trailer, keyframes from blockout + plate + sheets, voice samples with Eleven v4. `references/bible.md`.
6. **Shoot.** `python3 scripts/shoot.py episode.json s01 --dry-run` and read the whole prompt. Then shoot,
   several sequences at once (`--jobs 3`). Review every take: `python3 scripts/review_take.py takes/s01_t1.mp4
   --plan episode.json --transcribe`, look at the sheet and the frames, record a verdict with usable ranges and
   scores. Retake with a fix written into the sequence's `must` list, a new seed, a first frame, a chained
   frame, and only as a last resort a gray camera-move video. `references/shoot-and-review.md`.
7. **Edit.** Write `edit.json` from the kept ranges (`templates/edit.json`). `python3 scripts/pace.py edit.json
   -o pace/` and fix every failed check; `python3 scripts/assemble.py edit.json -o out/ --draft`; look at frames
   around every cut. `references/edit.md`.
8. **Score and sound.** `python3 scripts/pace.py edit.json --music-plan music/` writes composition plans cut to
   the locked edit; generate the 2-3 cues with one model and one style list; add a few effects; assemble the
   master: `python3 scripts/assemble.py edit.json -o out/`, then `pace.py edit.json -o pace/ --render
   out/final.mp4` for loudness and energy. `references/sound.md`.
9. **Deliver.** `python3 scripts/report.py episode.json --edit edit.json --pace pace/pace.json --notes notes.md
   -o out/report.md`, copy `pace/pace.svg` to `out/`, and send it (ShotForge: `prompts/shotforge-routine.md`).

Every fal call goes through `fal_run.py`, `make.py`, `shoot.py` or `review_take.py`, which share one ledger
(`ledger.json`) and refuse any call that would pass the budget. `python3 scripts/fal_run.py --ledger` shows the
spend. Scripts need Python 3.9+, ffmpeg with libass, `pip install fal-client` with `FAL_KEY`, and for the
blockout Node 18+ with playwright and Chromium (`npm i three@0.160.0` to serve Three.js locally).

## Modes

- **Autopilot** (with or without a trailer): one run does steps 1 to 9. Without a trailer, step 1 becomes
  "decide the look from the concept" (`references/bible.md`, without a trailer).
- **Guided**: the user approves the cast, then the story, then the locations, and each approval is a new run.
  A run ends at its checkpoint (`shotforge_deliver.py checkpoint <stage> --items|--summary --state-dir .`), and
  the next one starts with `shotforge_deliver.py restore`. Comments come back as `feedback` per item: rebuild only
  what was commented. Whatever the user approved is locked for the rest of the episode. The ShotForge saved prompt
  (`prompts/shotforge-routine.md` at the repository root) spells out each phase.

## Presets

The plan's `preset` decides the grammar; ShotForge sends it as `settings.preset`.

- **social** (the default): the micro-drama pressure loop below, built to stop the scroll.
- **cinematic**: a short film scene that holds a look. Conversations between two people in one place (or a walk
  toward the camera), one camera essence (empty space, high angles, silence...), three fixed coverage cameras
  A (center), B (left), C (right) used by every shot, angles rationed, a tone lock repeated word for word in
  every prompt, 1-3 tone films, and a look frame attached to every image and video generation. Hook text, recap
  line and the 6 s shot cap do not apply; shots run 3.5-8 s. Read `references/cinematic.md` before writing the
  story, and plan from `examples/handover/`.

## Hard rules

- **Story before pixels.** Nothing is generated until the episode sheet is complete and `plan_check.py` shows
  zero errors. A beautiful take of a flat scene is waste.
- **No music in any video prompt.** "No music." is the first line of every prompt and the sound block repeats
  it: the score is composed after the edit is locked, to its cuts. No subtitles or on-screen text either; the
  captions and the hook text are added in the edit.
- **The format is the contract**: a face or a threat in frame 1, hook text and the first line in 2 s, the stakes
  by 5 s, a recap line in the first 20 s, a re-hook every 15-20 s, the turn near the middle, the cliffhanger as
  the tension peak and the last frame, lines of 8 words or fewer, 3 characters and 2 locations at most. The
  cinematic preset keeps the beats and relaxes the clock (`references/cinematic.md`).
- **References are bound, not hoped for.** Everyone on screen has an image reference and everyone who speaks a
  voice reference, in the same sequence. Every reference has an @ tag in the prompt and the prompt says what it
  is ("@Image 1 is Nora's character sheet", "Nora (voice: @Audio 1) says"), so the model knows which file to
  take. Keep the hero at @Image 1 in every sequence. Never more than 9 images, 3 audio, 3 video, 12 files.
- **Consistent light, lens and staging.** One key direction and color per location for the whole episode, the
  same lens family, eyelines and screen direction kept across cuts (180-degree rule), the same wardrobe. When
  the plan has a tone lock (`look.lock`) and a look frame (`look.reference`), they go into every generation.
- **The budget is a hard cap.** Plan the resolution with `plan_check.py`, keep a quarter of the shot money for
  retakes, never call fal outside the ledger. When the money runs out, finish the best cut of what you have
  and say so; never leave the user with nothing.
- **Judge from evidence.** Every take gets a sheet, a cut table and a verdict with usable ranges; every edit a
  pace map; every master a loudness reading. Look at the frames around every cut before delivering.
- **Vertical is its own grammar.** Faces and hands, not landscapes; one or two people per frame; depth from
  foreground, hero, threat behind; eyes in the upper third; nothing important in the top 12 %, the bottom 20 %
  or the right rail where the app's buttons sit.
- **Original only.** No real people, brands, existing characters or franchises; no likeness of a real person.
  Tone films are named for light and mood only.

## Reference routing

| File | Read when |
|---|---|
| `references/format.md` | always first: the pressure loop, hooks, cliffhangers, the eight vertical rules, the episode sheet |
| `references/story.md` | writing: genre engines (drama, comedy, romcom, thriller, horror), beats for 60-120 s, dialogue |
| `references/bible.md` | the trailer study, cast sheets, location plates, keyframes, voices, the asset recipes |
| `references/blockout.md` | gray-boxing a location: layout format, cameras and lenses, using the renders |
| `references/shots.md` | the shot list and the prompt: sequences, timecoded shots, camera and light language, tags |
| `references/shoot-and-review.md` | filming: budget, takes, the review rubric, retake tactics, the last-resort video reference |
| `references/edit.md` | cutting: the edit list, pace numbers, J/L cuts, punch-ins, captions, the checks |
| `references/sound.md` | the score cut to the edit, effects, ducking, loudness |
| `references/cinematic.md` | the cinematic preset: essences, rationed angles, coverage A/B/C, tone lock, look frame, @ tags |

Templates: `templates/episode.json` (the plan), `templates/layout.json` (a blockout), `templates/edit.json`
(the cut). Complete worked examples at the repository root: `examples/plus-one/` (social) and
`examples/handover/` (cinematic).

## Output expectations

- The episode: `out/final.mp4` (captions and hook text), `out/final_clean.mp4`, `out/poster.jpg`,
  `out/report.md`, `out/pace.svg`.
- Say what was checked and how: which takes were kept and why, the usable-footage rate, the pace checks, the
  loudness reading.
- The fal spend per endpoint and the total against the budget.
- An honest list of what differs from the plan (a line the model never said right, a cut that jumps, a voice
  that drifts). Never "perfect".
