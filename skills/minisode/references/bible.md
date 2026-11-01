# The bible: cast, places, keyframes, voices

Consistency is built before the first shot. The video model keeps a person or a room the same only when it is
shown the same references, bound to the same names, every time. Everything here is declared in `episode.json`
under `assets`, each with a `make` recipe, and built with `make.py` (priced, logged, in dependency order).

## Study the trailer first

`study_video.py trailer.mp4 -o study/` gives frames every 0.5 s, a timed contact sheet, the palette and the cuts.
Write down, from named frames: each character's clearest frame (face, then full body), each place's widest frame,
the light (key direction, color temperature, practicals), the lens feel (wide and close or long and compressed),
the grade (warm or cool, contrast, blacks) and the texture (grain, halation). These become `look`, `cast` and
`locations`. When the trailer and the concept disagree, the trailer wins: the user approved it.

## Character sheets (`kind: character_sheet`)

One 16:9 sheet per character, generated with `fal-ai/nano-banana-pro/edit` from 1-3 trailer frames of that
person (or `fal-ai/nano-banana-pro` from the description alone if the person is not in the trailer):

- **Left half:** full-body turnaround at one scale, feet visible, relaxed A-pose: front, three-quarter, side
  profile, back.
- **Right half, large:** a 3x2 grid of big head-and-shoulders close-ups of the same face, sharp eyes: neutral,
  and the five expressions the episode needs (anger, shock, a smile, tears, a smirk...). These close-ups are what
  keep the face stable in close shots, so they are big.
- **Bottom of the right half:** close-ups of the outfit fabric, the signature accessory, the shoes.
- Plain light-gray background, even soft studio light, photoreal skin, no text, labels or borders.
- 2K resolution. One sheet per character; regenerate until the face matches the trailer frame, side by side.

If a take shows sheet artifacts (split screens, grids, a gray studio background bleeding in), give that
character a separate face close-up (`kind: face`, 1:1, 2x2 grid of large faces) and a front full-body image
instead of the sheet, and say in the prompt which is which.

## Location plates (`kind: location`)

Built from the gray blockout (`blockout.md`), so the geography is fixed before the look: `nano-banana-pro/edit`
with the empty clay render of a camera (`<cam>_empty.png`) as image 1 and a trailer frame of the place as image 2:
"Render image 1 as a finished photoreal set in the look of image 2... Keep the exact camera, perspective, layout
and the size and position of every piece of furniture. No people." One plate per main camera direction (usually
two: toward the action and the reverse). Build the second plate from the first (`@first_plate`) so materials
match. These plates are the H3 image references for the room ("Image 3 is the reception, view toward Nora's
table") and the backgrounds of keyframes.

## Keyframes (`kind: keyframe`)

A first frame for a sequence whose opening composition matters (always the hook): `nano-banana-pro/edit` with
the blockout render with mannequins (layout and poses), the plate (look) and the sheets of the people in frame:
"Image 1 is the shot layout: keep its camera, lens and composition exactly. Replace the violet mannequin with
Nora from image 3..." 9:16 for a vertical episode (the video canvas follows the first frame). The sequence's
`start_image` points at it; H3 opens exactly on it while the references keep identity.

Use keyframes where they pay: the hook, a reveal, an exact cliff frame (`end_image`). In a small budget, only the
hook.

## Props (`kind: prop`)

Only props the story turns on (a ring, a letter, a phone screen): one clean product-style image on gray, then
referenced in the sequences where they matter. Most props live in the location plate.

## Voices (`kind: voice`)

Each speaking character gets a 3-5 s voice sample, made once, used as an audio reference in every sequence where
they speak ("Audio 1 is Nora's voice"). Three voices must fit the model's 15 s of audio references, so keep each
under 5 s.

- `elevenlabs/tts/eleven-v4` (latest, most expressive; about 0.08 USD per 1,000 characters). Pick a library
  voice per character (Aria, Roger, Sarah, Laura, Charlie, George, Callum, River, Liam, Charlotte, Alice,
  Matilda, Will, Jessica, Eric, Chris, Brian, Daniel, Lily, Bill...) that fits age, accent and manner; never the
  same voice for two characters. `stability` 0.3-0.45 for emotion; audio tags in the text set delivery:
  `[whispering]`, `[dryly]`, `[sighs]`, `[laughs]`, `[angry]`.
- The sample is a characteristic line in the character's register, not a line from the episode, with a little
  emotion (the model copies timbre and rhythm, so a flat sample gives flat acting).
- Write the voice into `cast[].voice` (model, voice, stability, direction, sample) so retakes and later episodes
  use the same voice.
- A designed voice (`fal-ai/minimax/voice-design`, about 3 USD a voice) only when no library voice fits and the
  budget allows.
- When a take gets the words and the lip-sync right but the voice drifts, fix it in post as a last resort:
  isolate the dialogue (`fal-ai/elevenlabs/audio-isolation`), convert it with the character's voice
  (`fal-ai/elevenlabs/voice-changer`, about 0.30 USD a minute), and lay room tone back under it.

## The asset recipe

```json
"nora_sheet": {"type": "image", "kind": "character_sheet", "of": "nora", "file": "assets/cast/nora_sheet.png",
  "make": {"endpoint": "fal-ai/nano-banana-pro/edit", "files": {"image_urls": ["study/f_009.jpg"]},
           "args": {"aspect_ratio": "16:9", "resolution": "2K", "prompt": "Character reference sheet of ..."}}}
```

`files` values are paths relative to the plan, URLs, or `@asset_id` (another asset's file, built first).
`python3 scripts/make.py episode.json --estimate` prices everything missing; `make.py episode.json <ids>` builds;
`--force` rebuilds and keeps the old file as `name.v1.png`. Look at each result before building what uses it.

## Costs (November 2026)

| Asset | Endpoint | USD |
|---|---|---|
| Sheet, plate, keyframe | `fal-ai/nano-banana-pro(/edit)` | 0.15 each (4K doubles) |
| Voice sample | `elevenlabs/tts/eleven-v4` | about 0.005 |
| Designed voice | `fal-ai/minimax/voice-design` | 3.00 |
| Trailer study, blockout | local | 0 |

A 3-character, 1-location episode: 3 sheets + 2 plates + 1-2 keyframes + 3 voices, about 1 USD.
