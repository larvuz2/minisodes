# The cinematic preset

Use it when the plan says `"preset": "cinematic"` (ShotForge sends `settings.preset`, or "cinematic" in the
notes), or when the user asks for a film look, a short film, "less TikTok". The social preset is built to stop
the scroll; this one is built to hold a look. Same skill, same scripts, same budget and "No music." rule; what
changes is the story's pressure, the camera's grammar, and how hard the look is locked.

A worked example: `examples/handover/` at the repository root (two people, one empty apartment, essence
empty space, cameras A, B and C).

## What changes

| | social | cinematic |
|---|---|---|
| Story | the pressure loop: hook text, recap line, re-hook every 20 s | the same beats, quieter: the hook can be a picture, no hook text, no recap line, a new beat every 30 s at most |
| Scenes | up to 3 people, 2 places, any action | **conversations**: 2 people, 1 place, talking, listening, a walk toward the camera |
| Lines | 8 words or fewer | 12 or fewer; pauses written in as `silence` |
| Shots | 2-3.5 s average, a cut every 5 s, nothing over 6 s | 3.5-8 s average, something changes every 12 s, nothing over 12 s |
| Camera | whatever sells the beat | **one essence**, three fixed coverage cameras, angles rationed |
| Look | `look` written the same in every prompt | plus a **tone lock** repeated word for word, 1-3 **tone films**, and a **look frame** attached to every image and video generation |

`plan_check.py` and `pace.py` read the preset and switch their numbers; `plan_check.py` adds the `cine` checks
below.

## 1. Pick one essence

The essence is the one idea the camera keeps coming back to, the way a director's style is recognizable in any
frame. Pick one per episode from what the story is about, write it in `cinematography.essence` with a sentence
in `statement` that says why, and 2-4 `rules` that make it concrete. Everything else is plain coverage: the
essence is strong because it is rare.

| Essence | The idea | Signature shot | Tone films (light and mood) |
|---|---|---|---|
| `empty-space` | what is missing: people small in bare rooms, half the frame left empty | a wide from A with both people small, floor and wall around them | Past Lives (2023, Shabier Kirchner), Columbus (2017, Elisha Christian), Ida (2013, Łukasz Żal, Ryszard Lenczewski) |
| `high-angle` | being watched, trapped, judged: the camera looks down | a high angle from the ceiling or a stairwell onto one person | Sicario (2015, Roger Deakins), Parasite (2019, Hong Kyung-pyo), Zodiac (2007, Harris Savides) |
| `silence` | acting and emotion: reactions longer than lines, pauses before answers | a held close-up of the listener after a line, 6-10 s | Manchester by the Sea (2016, Jody Lee Lipes), Portrait of a Lady on Fire (2019, Claire Mathon), Drive My Car (2021, Hidetoshi Shinomiya) |
| `frames-within-frames` | separation: people seen through doorways, windows, mirrors | a single framed by a door or window edge | Carol (2015, Edward Lachman), Paris, Texas (1984, Robby Müller) |
| `symmetry` | order and control: centered, one-point perspective | a dead-center frame with the vanishing point behind the face | Moonrise Kingdom (2012, Robert Yeoman), The Shining (1980, John Alcott) |
| `long-lens` | observation: compressed, from a distance, through glass | a long-lens single through a window or across a street | Tinker Tailor Soldier Spy (2011, Hoyte van Hoytema), Lost in Translation (2003, Lance Acord) |
| `low-angle` | power and threat: the camera looks up | a low angle on the one who holds the power, ceiling in frame | No Country for Old Men (2007, Roger Deakins), Moonlight (2016, James Laxton) |
| `backs-and-doorways` | what is not said: backs to camera, exits, the empty door | a person leaving through a door, held after they are gone | The Godfather (1972, Gordon Willis), Aftersun (2022, Gregory Oke) |

The films are for light, color and mood only: never their characters, scenes or likenesses. Write them into
`look.tone_refs` with the cinematographer and one line of what to take from each:

```json
"tone_refs": [
  {"film": "Past Lives", "year": 2023, "dp": "Shabier Kirchner", "take": "patient conversations, people small against architecture, soft natural light"}
]
```

## 2. Ration the angles

- **Signature shots** (`"signature": true` on the shot): the essence in its purest form. At most one per 10 s;
  three in a 60 s episode is plenty. Put them on the hook, the turn and the last beat.
- **Special angles** (an `angle` that differs from the shot's coverage camera and is not eye level): at most one
  per 30 s. Use one where the story turns, never twice in a row.
- **Moves**: locked off by default; one very slow push-in per sequence at most, on a turn. Never whip pans,
  crash zooms, handheld shake, orbits, rolls, drones: they break the stitch between generations and the calm of
  the look (`plan_check.py` refuses them).
- Everything else is eye level, from the coverage cameras.

## 3. Coverage: cameras A, B and C

Every sequence is a separate generation that must cut against the next one invisibly. So the camera positions
are fixed for the whole episode, like a real set, and every shot names one of them:

```json
"cinematography": {
  "essence": "empty-space",
  "statement": "...",
  "rules": ["Every wide leaves at least half of the frame empty", "..."],
  "coverage": {
    "A": {"side": "center", "frame": "WS",  "angle": "eye level", "lens": "35 mm", "move": "locked off", "desc": "on the room's axis at chest height, ..."},
    "B": {"side": "left",   "frame": "MCU", "angle": "eye level", "lens": "50 mm", "move": "locked off", "desc": "behind Maya's right shoulder, onto Daniel, ..."},
    "C": {"side": "right",  "frame": "MCU", "angle": "eye level", "lens": "50 mm", "move": "locked off", "desc": "behind Daniel's left shoulder, onto Maya, ..."}
  }
}
```

A shot then needs only `"camera": "B"` plus what differs (`frame`, `angle`, `lens`, `move`); `prompt.py` fills
the rest from coverage and writes `CAMERA B (left side), MEDIUM CLOSE-UP, eye level, 50 mm, locked off.`, and
the CINEMATOGRAPHY block describes all three positions in every prompt, so every generation sees the same set.

- **A, center**: the master. The whole space, both people, the essence. Starts the episode and ends it.
- **B, left** and **C, right**: the two singles of the conversation, over the shoulder, both on the same side of
  the line between the two people (the 180-degree rule): B sees the person on the right, C the person on the
  left. Put all three cameras in the blockout (`blockout.md`) and check them on `plan.png`.
- **The seams**: the last shot of a sequence and the first shot of the next use different cameras, so the join
  between two generations is a cut between angles, not a jump. `plan_check.py` warns when they match.
- **Walk toward the camera**: a person walks toward A (or between B and C) and stops on a mark. It is the one
  movement that stitches perfectly: it reads the same from every angle. Name the mark in the blockout.
- **The scene**: two people talking across a table, a counter, a car, a bench; or walking toward the camera
  side by side. No fights, chases, crowds, dancing or busy hands; the drama is in the faces.

## 4. Lock the tone

Three things carry the same light into every generation:

1. **The tone lock** (`look.lock`): 15-40 precise words for the light direction and quality, color temperature,
   palette, contrast, grain and mood. `prompt.py` writes it word for word at the top of LOOK in every sequence
   ("TONE LOCK, identical in every shot: ..."), and `make.py` adds it to every plate and keyframe recipe. Write
   it once and never paraphrase it.
2. **The tone films** (`look.tone_refs`): named in every prompt as "for light and mood only".
3. **The look frame** (`look.reference`): one image asset of `kind: "look"`, the episode's light in a single
   frame, built first.
   - From the trailer: the best trailer frame through `fal-ai/nano-banana-pro/edit` or
     `openai/gpt-image-2.5/flare/edit`, "same light, palette and grain; remove the people".
   - Without a trailer: text to image (`openai/gpt-image-2.5/flare/text-to-image` with `image_size:
     "portrait_16_9"` and `quality: "high"`, or `fal-ai/nano-banana-pro`), the lock words in the prompt.
   - No people in it, or only from behind and out of focus, so no face leaks into the cast.
   - Look at it before anything else is built; it is the most expensive mistake to fix later.

   `prompt.py` attaches the look frame to every sequence after its own images and binds it: "@Image 6 is the
   look reference frame: every shot matches its light ... Take nothing else from it", and LOOK ends with "Grade
   every shot against @Image 6". `make.py` attaches it as the last input image of every image recipe (switching
   text-to-image endpoints to their edit endpoint) with a note of what to take from it: only the medium, color
   and grain for character sheets, which keep their plain studio light; the light, palette and grain for plates
   and keyframes. A recipe opts out with `"look": false`. It counts toward the 9 images of a sequence.

## 5. Tags

Every reference is named with an @ tag in every prompt: `@Image 1`, `@Audio 2`, `@Video 1`. The REFERENCES
block binds each tag to what it is, the first mention of each person carries their image tag ("Maya (@Image
1)"), each line names its voice ("Maya (voice: @Audio 1) says ..."), and LOOK points at the look frame. The word
after the @ is the model's own name for the input (H3 numbers images, videos and audios in the order sent);
another video model gets its pattern in `TAG_STYLES` in `prompt.py`. Image recipes use the same habit: "@image 3
is the look reference".

## 6. Story, edit and sound

- Beats keep their names (`hook` ... `cliff`); the hook may end by 8 s and the cliff may last 12 s. A cinematic
  hook is a picture that holds and a line said quietly; the cliffhanger is usually a look after a new fact.
- Write pauses as `silence` on the shot ("the room holds it"); `pace.py` accepts planned silences of any length.
- Edit on looks and breaths, not on lines: L-cuts into the listener, hold the reaction. Captions stay on for
  phones; no hook text.
- Music is sparse: 1-2 cues that enter late (on the turn) and stop dead on the last frame; never under the
  first lines. The video prompts still say "No music."

## 7. Checks

`python3 scripts/plan_check.py episode.json` adds:

- errors: no essence, no coverage, a shot without a coverage camera, a forbidden move, no tone lock, no look
  frame or one that is not an image of kind `look`;
- warnings: no tone films or more than 3, coverage without a center, left and right camera, an unused camera,
  no signature shot or more than one per 10 s, more than one special angle per 30 s, more than 2 people in a
  shot, busy action, an average shot outside 3.5-8 s, too many words for a `silence` episode, the same camera on
  both sides of a seam.

`python3 scripts/pace.py --plan episode.json -o pace_plan/` uses the cinematic numbers: average shot 3.5-8 s, a
change every 12 s, a re-hook every 30 s, no shot over 12 s, no dead air over 8 s unless planned, speech 1.6-3.4
words per second, the last shot 8 s or shorter.
