# Shoot and review

## Money first

`plan_check.py` prices the episode at each resolution (shots + assets + audio) and picks the highest that keeps
a quarter of the shot money for retakes. The budget in the plan (`budget_usd`) is a hard cap shared by every
script through `ledger.json`: a call that would pass it is refused before it runs.

| 60 s episode, ~65 s filmed | 480P | 768P | 1080P |
|---|---|---|---|
| Shots once | ~3.40 | ~5.40 | ~10.70 |
| Assets + score + transcripts | ~1.0-1.5 | ~1.0-1.5 | ~1.0-1.5 |
| Budget with a 25 % retake reserve | ~5.8 | ~8.3 | ~15.5 |

Double the shot money for 120 s. **Lean mode** when the budget is tight (the 5 USD default for 60 s): 480P, one
location plate per place, a keyframe only for the hook, the score from `google/lyria-3.5` (0.10 USD a cue)
instead of ElevenLabs Music, transcripts only for takes you keep. Upscale the 480P master to 1080x1920 in
`assemble.py` (it scales every clip to the output size). Tell the user what lean mode cost them in quality.

## Shooting

1. `python3 scripts/shoot.py episode.json s01 --dry-run`: read the full prompt and the payload; fix the plan, not
   the prompt text.
2. Shoot the hook first: it decides whether the look and the cast work. Then the rest in parallel:
   `shoot.py episode.json s02 s03 s04 s05 --jobs 4`.
3. Each take is `takes/<seq>_t<N>.mp4` with a sidecar `.json` (prompt, tags, seed, cost, reference tokens).
4. Tell ShotForge as you go (`shotforge_deliver.py note "Shooting the twist" --stage shoot`) and show takes you
   keep (`preview take takes/s03_t2.mp4 --label "Twist"`).

## Review every take

```bash
python3 scripts/review_take.py takes/s02_t1.mp4 --plan episode.json --transcribe
```

It writes `review/<take>/sheet.jpg` (a frame every 0.5 s with its time), `frames/` (every 0.25 s), the cuts the
model made against the planned cuts, loudness and silences, and with `--transcribe` the words spoken
(ElevenLabs Scribe v2 with the character names as key terms, about 0.01 USD) matched to the script line by line
with timing, extra words that are not in the script, and audio events (a "music" event is a failed take: the
prompt said no music). Open the sheet, then the frames around every cut and every line. Then score:

| Score (0 broken, 1 usable with care, 2 good) | Look for |
|---|---|
| identity | each face matches its sheet in every shot; no face swap between characters; same hair, same wardrobe |
| continuity | props, hands, glasses, positions consistent across the cuts; the room matches its plate |
| lipsync | mouths move on the right lines; the right person speaks; no extra lines |
| performance | the behavior the shot asked for (the smile that cracks, the held look); timing of the beat |
| camera | shot sizes, angles and moves as planned; cuts where planned (the cut table) |
| artifacts | morphing hands, melting faces, text or logos, sheet collage leaking in, flicker |

And record:

```bash
python3 scripts/review_take.py takes/s02_t1.mp4 --verdict keep --usable 0.2-12.6 \
    --score identity=2,continuity=2,lipsync=2,performance=1,camera=2,artifacts=2 --note "hands soft at 9 s"
```

- **keep**: the sequence works; usable ranges cover its slot.
- **salvage**: parts work; the edit can use the usable ranges with other takes or inserts around them.
- **retake**: not usable; write down why.

`review_take.py --summary --plan episode.json` lists every take and the usable-footage rate (usable seconds over
generated seconds). Aim for 80 % or better; under 60 %, the plan or the references are wrong, not the luck.

## Retakes, cheapest first

1. **Same prompt, new seed**: for random failures (a hand, a blink, a wrong line once).
2. **A MUST line** in the sequence (`"must": ["Theo's ring stays on his right hand"]`): for a specific, repeated
   error. Short and concrete.
3. **Fewer shots or longer shots** in the sequence: when the model skips cuts or rushes lines.
4. **A first frame**: a keyframe (`start_image`), or `--start chain` to open on the last kept frame of the
   previous sequence: for composition and continuity.
5. **Swap a reference**: the sheet leaks (grids, gray studio) → a face close-up + a full-body front instead; a
   face drifts in close-ups → add the face close-up as a second image for that character.
6. **A camera-move video, last resort**: render the move from the blockout (`<cam>_move.mp4`), add it to the
   plan's assets as `kind: camera_move`, and shoot with `--video-ref <id>`. The prompt then says "Video 1 shows
   only the camera move: copy its path, speed and framing; ignore its gray clay look and mannequins." It costs
   reference tokens and can pull gray into the picture: check the sheet.
7. **Fix in the edit**: a punch-in to hide a soft edge, a reaction shot from another take, an L-cut to carry a
   line over a better picture. Cheaper than a retake, and often better.

Stop retaking a sequence after three takes; change the plan instead (split it, simplify the action, change the
angle). Keep the last quarter of the budget for the sequences that matter most: the hook, the twist, the cliff.

## Voices

When the voice drifts but the words and the lip-sync are right, keep the take and fix the voice in post
(`bible.md`, voices). When the wrong person speaks or lines are added, retake: post cannot fix that.
