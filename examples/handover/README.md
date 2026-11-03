# Handover (cinematic example)

A complete plan for a 60 s vertical drama in the **cinematic preset**, written with the minisode skill: two
people, one empty apartment, one camera essence, three fixed cameras. It is the worked example of
[`references/cinematic.md`](../../skills/minisode/references/cinematic.md) and a test fixture.

> On moving day, Maya returns the key to the apartment she shared with Daniel, and turns out to be the buyer he is
> waiting for.

| File | What it is |
|---|---|
| [`episode.json`](episode.json) | the plan: `preset: cinematic`, essence `empty-space`, coverage A (center), B (left), C (right), a tone lock, three tone films, a look frame, 2 characters, 1 location, 9 references, 5 sequences of 13 s with 15 shots, 2 music cues |
| [`blockout/flat.json`](blockout/flat.json) | the gray-box apartment: island, hallway door, windows, both marks, cameras A, B, C and the one high angle |
| [`blockout/plan.jpg`](blockout/plan.jpg), [`blockout/cameras.jpg`](blockout/cameras.jpg) | the top view and the four camera renders (A, B, C, A high) |

How the preset shows in the plan:

- **Essence, empty space.** Three signature shots (`"signature": true`), all wides from A with both people small:
  the hook, the held silence after the twist, and Daniel stopping in the doorway. One special angle in 60 s:
  the high shot from under the ceiling on the payoff.
- **Coverage.** Every shot names camera A, B or C and inherits its frame, angle, lens and move. Each sequence
  ends on a different camera from the one the next starts on, so the joins between generations are cuts between
  angles.
- **Conversation only.** Two people, a walk toward the camera in the first shot, a key slid across a counter;
  lines of 8 words or fewer with silences written in.
- **Tone.** `look.lock` is repeated word for word in all 5 prompts and in the plate and keyframe recipes; the tone
  films are Past Lives, Manchester by the Sea and Columbus; `look_frame` (GPT Image 2.5, built first) rides along
  as the last image of every sequence and every image recipe, tagged ("Grade every shot against @Image 6").

The beats:

| Time | Beat | What happens |
|---|---|---|
| 0-8 s | hook | Maya walks out of the hallway into the empty room. "You kept a key." |
| 8-20 s | anchor | "You never asked for it back." "The buyers come at six." The key on the island. |
| 20-30 s | pressure | "Say why you came, Maya." She looks at a pale square on the wall. "To see it empty." |
| 30-40 s | twist | "Their agent said the buyer knew the place." "I'm the six o'clock." A held wide. |
| 40-48 s | choice | "You could have just asked." He closes her hand over the key. "Then it was always yours." |
| 48-54 s | payoff | From high above: "It was never the apartment." |
| 54-60 s | cliff | In the doorway, without turning: "I know. I turned down two higher offers." Hold on her. |

Run the checks from this folder:

```bash
python3 ../../skills/minisode/scripts/plan_check.py episode.json
python3 ../../skills/minisode/scripts/prompt.py episode.json s01
python3 ../../skills/minisode/scripts/pace.py --plan episode.json -o /tmp/pace
python3 ../../skills/minisode/scripts/make.py episode.json --estimate
node ../../skills/minisode/scripts/blockout.mjs blockout/flat.json -o blockout/flat/
```

To make it for real, render the blockout, build `look_frame` and look at it, then the sheets, plates and keyframe
(`make.py episode.json`), and follow `skills/minisode/SKILL.md` from step 6. At 768P it plans to about 7.2 USD
once, 9 USD with retakes. At 5 USD it only fits at 480P with one plate (A) and no keyframe, and leaves almost
nothing for retakes; `plan_check.py` says so before anything is spent.
