# Score and sound

The takes carry dialogue and ambience (the prompts forbid music). The score is composed after the picture is
locked, so it can turn exactly where the story turns, and the mix is measured to the platforms' loudness.

## The score: 2-3 cues, one voice

- **Spot it from the cut.** Music enters on the hook (after the first line has landed or under it, quiet), drops
  out before the biggest silence, re-enters at the twist, swells on the choice, and the last cue holds or cuts
  dead on the final frame. Silence is a cue too: a planned drop-out before a reveal makes the reveal hit.
- **Write the cues** in `episode.json` → `music.cues` (`from`, `to` on the locked timeline, `intent`) and the
  shared `styles` and `avoid` lists. Same styles for every cue keeps them one score.
- **Plan them on the cut:** `python3 scripts/pace.py edit.json --music-plan music/` writes
  `music/cue_<id>.json`, an ElevenLabs Music composition plan per cue: chunks split at the beats and story markers
  inside the cue (each 3 s or longer), durations in milliseconds that add up to the cue's length, the shared
  styles on the first chunk, intensity words that follow the story's tension, and the avoid list on every chunk.
- **Generate**, with one seed for every cue:
  `python3 scripts/fal_run.py elevenlabs/music/v2.5 -o music --name cue_A --json composition_plan=music/cue_A.json --arg seed=7`
  (0.60 USD per minute of music). Listen through the numbers: `ffmpeg -i music/cue_A.mp3 -af ebur128` for level,
  and check the length matches the plan.
- **Lean mode:** `google/lyria-3.5` (0.10 USD a generation) with a prompt that names the genre, instruments, tempo,
  the duration and time-coded sections ("0-8 s: sparse pizzicato; 8-20 s: building..."). Less exact timing; trim
  in the edit.
- Under dialogue, music stays restrained: no vocals, no busy melody in the voice range (300 Hz-3 kHz), no big
  drums. The swell belongs to the moments without words.

## Effects: few, on purpose

`fal-ai/elevenlabs/sound-effects/v2` (0.002 USD a second): `--arg text="..." --arg duration_seconds=1.2`.

| Moment | Effect | Level |
|---|---|---|
| The cut after the hook line | a short whoosh or a soft hit | -12 dB |
| The twist line | a low sub hit or a reversed swell into it | -9 dB |
| Into the cliffhanger | a riser of 1.5-2.5 s, cut dead on the last frame | -14 dB |
| Comedy beats | a stinger, a record scratch, a tiny "boop" on the reaction (sparingly) | -10 dB |
| Room continuity | a room-tone loop (`loop: true`) at about -30 dB under the whole scene, to glue takes whose ambience differs | -30 dB |

Three to six effects a minute; never on top of a line; `kind: hit` on an effect makes `pace.py` count it as a
re-hook.

## The mix (`edit.json` → `mix`, done by `assemble.py`)

- Dialogue bus from the takes, with 12-20 ms fades at every cut (no clicks) and the J/L overlaps.
- Music at -16 to -20 dB, ducked a further 6-10 dB (`duck_db`) whenever someone speaks (sidechain compression
  keyed by the dialogue).
- Effects at their own levels, a limiter at the end.
- Loudness normalized in two passes to -14 LUFS integrated, -1.5 dBTP true peak: the level the social platforms
  normalize to, so the episode is neither turned down nor quieter than the next video.
- The master is AAC 192 kbps at 48 kHz in an H.264 mp4 with fast start.

After the master: `python3 scripts/pace.py edit.json -o pace/ --render out/final.mp4` reads the loudness and
draws the energy curve under the beats; the energy should rise into the twist and the cliff.
