# The shot list and the prompt

The episode is filmed in sequences: one video generation of 10-15 s (MiniMax H3 Max reference-to-video, 15 s at
most) holding 2-5 shots with hard cuts, like a finished scene. Continuity inside a generation is strong (same
light, same people, same room), so a sequence covers one place and one stretch of the story. The edit then cuts
the sequences together and trims the handles.

## Sequences

- **Slot and handle.** Each sequence lands in a `slot` of the episode timeline (`[0, 12]`, `[12, 24]`...). Ask
  for about 1 s more than the slot (`duration: 13` for a 12 s slot): the model sometimes starts late or runs
  long, and the edit needs room. A 60 s episode is 4-6 sequences; 120 s is 8-10.
- **Break at the turns.** A sequence ends where the story turns or the place changes; a twist line is often the
  first shot of a sequence, so it gets a clean start.
- **Shots inside.** 2-5 shots of 1.5-5 s each. Vertical micro-drama averages 2-3.5 s a shot; nothing over 6 s
  unless it is a planned hold. `t` is in sequence seconds and the shots cover `[0, duration]` with no gap.
- **Continuity across sequences.** Same `look`, same location plates, same sheets, hero at @Image 1. When a scene
  continues across two sequences, open the second on the last kept frame of the first (`start_image: "chain"`,
  `shoot.py --start chain`) or on a keyframe.

## A shot

```json
{"t": [4.0, 8.0], "frame": "MCU-2S", "angle": "eye level", "lens": "50 mm", "move": "static, slight drift",
 "who": ["nora", "theo"], "action": "Nora turns to Theo with a bright fake smile that never reaches her eyes.",
 "lines": [{"who": "nora", "text": "She married my fiancé. Tonight, you're mine.", "how": "through a frozen smile"}],
 "sound": "glasses clink", "silence": "", "overlay": "", "transition": ""}
```

- **frame**: ECU (eyes, lips, a hand), CU (face), MCU (head and shoulders), MS (waist up), MWS (knees up), WS
  (full body in the room), EWS, OTS (over the shoulder), POV, INSERT (a detail), 2S / MCU-2S (two people).
- **angle**: eye level (neutral), slightly low (power, intimacy), low (dominance, threat), high (weakness,
  surveillance), overhead, dutch (avoid unless the story breaks).
- **lens**: 24-35 mm (place, energy, distortion near faces), 50 mm (natural), 85-135 mm (portrait, compression,
  isolation). Keep one lens family per episode.
- **move**: static, slow push-in (realization, tension), pull-out (isolation, reveal), dolly / truck (follow),
  arc (a turning point, a kiss), crane up / down, handheld (panic, intimacy), whip pan (comedy, shock), rack
  focus (shift attention between two faces). One move per shot, motivated by the story.
- **action**: what the audience sees, concrete and physical: hands, eyes, objects. Write the acting as behavior
  ("her smile cracks at the corners; she goes pale"), not as emotion labels.
- **lines**: who, the exact words (8 or fewer), and `how`. A shot without lines can carry `silence` (a planned
  dramatic pause: "a held beat, only the room murmur").
- **sound**: the sync sounds the picture needs (a glass on the table, a door). No music, ever.
- **overlay**: the hook text, for the edit (it is not in the prompt).
- **camera** (cinematic preset): A, B or C from `cinematography.coverage`; the shot inherits that camera's frame,
  angle, lens and move unless it sets its own. **signature**: true on the few shots that show the essence.
  Both in `cinematic.md`.

## Coverage that cuts

- **Dialogue**: alternate singles (CU / MCU) with an occasional two-shot or OTS to re-establish geography. Keep
  the 180-degree line: if Nora looks screen-right at Theo in one shot, Theo looks screen-left at her in the
  next. Eyelines meet.
- **Reaction shots** are where vertical drama lives: the listener's face after the line lands. Plan them.
- **Inserts** (a hand, a ring, a glass) give the edit cut points and push the story without words.
- **Cut on action** (a turn, a stand, a glass set down) so cuts feel invisible; cut on a look to change scene.
- **Screen direction**: a person leaving frame right enters the next shot from the left.

## Light

One `look.lighting` for the whole episode: the key (direction and color), fill, rim, practicals. Repeat it in
every prompt (prompt.py does), and give a sequence its own `light` only when the story moves the light (a door
opens, the power cuts). Write light physically ("warm tungsten string lights as the key from above-left, cool
blue night through the glass as rim"), never "beautiful lighting".

## The prompt (built by `prompt.py`)

```
No music. No subtitles, captions or on-screen text.
<aspect> <genre> micro-drama, <duration> seconds, <place>, <time>, <n> shots cut together like a finished scene.

REFERENCES
@Image 1 is Nora's character sheet (full body on the left, face close-ups on the right): keep ...
@Image 2 is ...                     @Audio 1 is Nora's voice: Nora speaks only in this voice ...

LOOK
[TONE LOCK, identical in every shot: <look.lock>.] <style>. Lighting: ... Camera: ... Grade: ... Texture: ...
[Tone references, for light and mood only: ...] [Grade every shot against @Image 6.] <vertical safe zone>

[CINEMATOGRAPHY: essence, rules, coverage cameras A, B, C (cinematic preset)]

SHOTS
0-2.2 s: EXTREME CLOSE-UP, eye level, 85 mm, slow push-in.
Nora's eyes over the rim of a champagne flute... Theo (@Image 2) leans in... Theo (voice: @Audio 2) says, a low
amused whisper: "Smile. Your ex is watching."
2.2-4 s: Hard cut. INSERT CLOSE-UP, her point of view, 85 mm, static. ...

MUST
- Theo's signet ring stays on his right hand.

SOUND
Native audio with lip-synced English dialogue: only the lines written above, each spoken once, by the character
named, in that character's voice. Ambience: ... No music, no score, no soundtrack, no singing, no humming.

AVOID
<look.avoid>, text, subtitles, logos, watermarks, extra people talking, faces or hands that morph.
```

- References are @-tagged by modality and order: @Image 1..9, @Video 1..3, @Audio 1..3 (12 files at most; audio
  and video clips 2-15 s each and 15 s per type). The REFERENCES block binds each tag; the first mention of each
  person in SHOTS carries their tag; each line names the voice. The @ tells the model a reference is meant; the
  words after it are the model's own names for its inputs (`TAG_STYLES` in `prompt.py` for other models).
- When the plan has a look frame (`look.reference`), it is attached to every sequence after its own images and
  LOOK says to grade against it (`cinematic.md`).
- `prompt_expansion_mode` is `disabled`: the prompt is sent as written.
- Keep prompts under ~5,500 characters (the cinematic blocks add about 1,000); cut adjectives before shots.
- `MUST` is for fixes after a review (`sequence.must`), short and concrete.
- Check every prompt with `python3 scripts/prompt.py episode.json` (warnings exit 1) and `shoot.py --dry-run`.

## Video models

`video_model` in the plan picks the adapter in `shoot.py` (`ADAPTERS`). Only `minimax/h3-max/reference-to-video`
today (480P 0.05, 768P 0.08, 1080P 0.16 USD per second; reference tokens over 4,096 at 0.02 USD per 1,000). To add
a model: write an adapter that maps the built sequence (prompt, reference files, first and last frame, duration,
resolution, aspect) to that model's arguments, add its price to `fal_run.py`, and test with `--dry-run`.
