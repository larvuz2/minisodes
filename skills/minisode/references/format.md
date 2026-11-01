# The format: one episode, one pressure loop

From the Phatty Acid micro-drama format guide, adapted from its 2:30 target to the 60-120 s minisode. The
guide's rules do not change with length; the timings scale, except the hook, which stays 5 s at any length.

## The shape

Tension rises fast, dips while the viewer learns the stakes, climbs to a reversal near the middle, eases after
the hero acts, and spikes again on the last frame. Release is allowed; flat is not.

| Beat | Job | Writer rule | 60 s | 90 s | 120 s | (2:30 guide) |
|---|---|---|---|---|---|---|
| Hook | Start mid-action, a face or threat in frame 1 | No setup, no establishing shot. One image + one line that raises a question | 0-4 | 0-5 | 0-5 | 0:00-0:05 |
| Anchor | Who wants what, right now; where we are | One recap line so a new viewer can enter. State the stakes | 4-12 | 5-15 | 5-16 | 0:05-0:20 |
| Pressure | An obstacle hits; new information lands | Someone says or does the thing that makes the plan impossible | 12-24 | 15-38 | 16-45 | 0:20-0:55 |
| Twist | Reversal near the middle; power flips | Re-hook the viewer about to scroll: a new fact, person or place | 24-36 | 38-55 | 45-72 | 0:55-1:30 |
| Choice | The hero acts; it costs something | An active decision, not a reaction. Show the cost on the face | 36-47 | 55-72 | 72-95 | 1:30-2:05 |
| Payoff | Answer the hook question, differently than expected | Close one question, pay off a connected one. A real mini-reward | 47-55 | 72-84 | 95-110 | 2:05-2:22 |
| Cliff | Cut on the loaded moment | An unfinished line, a new fact or a held look. Never explain it | 55-60 | 84-90 | 110-120 | 2:22-2:30 |

The twist starts between 35 % and 60 % of the runtime. The cliff is 10 s or shorter and is the tension peak.
`plan_check.py` enforces these; `pace.py` draws the target curve under your cut.

## The first five seconds

The hook is not an intro: it is the most interesting moment of the episode, shown first, with a question
attached.

- **0.0 s, already moving.** Face or action in frame 1. No fade-in, no logo.
- **0.5 s, text hook lands.** A big on-screen line (under 8 words), readable muted, upper third.
- **1.5 s, first line + sound hit.** Short, loaded, 8 words or fewer.
- **3.0 s, the question forms.** A second element appears; the viewer asks why.
- **5.0 s, stakes are clear.** Who wants what, and what is the clock.

Six hook formulas (`sheet.hook.formula`):

| Formula | What | Example shape |
|---|---|---|
| mid-crisis | Open on the worst moment, explain later | Hand on the door, the alarm already ringing |
| forbidden-line | Someone says what nobody should say | "You were never supposed to wake up." |
| status-shock | A person exposed, crowned or cast out | The room goes silent, then looks at her |
| wrong-image | One impossible detail in a normal frame | Snow falling inside the house |
| clock | Tell the viewer what is about to break | "The gates close at dawn." |
| callback | Open on the last episode's last frame, then flip it | Same look, opposite meaning |

Avoid: title cards, slow establishing shots, characters introducing themselves, "previously on" montages,
starting calm "to build", key information only in the score.

## Eight rules that make vertical work

1. **Re-hook every 15-20 s**: new information, a new place, a new sound or a reversal. If 20 s pass and nothing
   changes, cut or twist. Under that, something should change every 3-5 s (a cut, a line, a sound).
2. **One want per episode.** Every beat pushes for it or against it.
3. **Short lines.** About 8 words, one idea per line. If a look, an action or a prop can say it, cut the line.
4. **Works muted.** The story reads from picture + captions; sound adds, never carries alone.
5. **Vertical staging.** Faces and hands, not landscapes. One or two characters per frame. Depth: foreground,
   hero, threat behind.
6. **Every episode is episode 1.** One recap line in the first 20 s; a new viewer can enter anywhere.
7. **Close one loop, open one.** Answer the hook question; plant a bigger one. Track open loops in the sheet.
8. **Respect the safe zones.** Faces and key text away from the top band (about 12 %), the bottom band (about
   20 %: captions, handle, buttons) and the right rail (like, share).

## Five ways to end

| Type (`cliffhanger.type`) | Shape | Craft |
|---|---|---|
| unfinished-line | "I'm not—" | Cut mid-word |
| new-fact | "He's not her brother." | One sentence, hard cut |
| loaded-look | Hold the face 2 s | Silence is the cut |
| impossible-choice | Two doors, one clock | Show both options |
| arrival | The door opens; someone is there | Reveal, don't explain |

## The episode sheet (one per episode, in `episode.json` → `sheet`)

| Field | Content |
|---|---|
| type | spine (moves the plot), heart (deepens a relationship) or spike (set piece or big reveal) |
| hook | image + line + on-screen text, and the formula |
| recap | 12 words or fewer |
| want → obstacle | one want, one thing in the way |
| twist | what flips: a new fact, person or place |
| choice + cost | what the hero does, what it costs |
| payoff | how the hook question is answered |
| cliffhanger | the type and the exact last frame |
| loops | closed in this episode, opened for the next |
| limits | 2 locations, 3 characters at most |

Before production (`plan_check.py` and `pace.py --plan` check each one): the hook works in 5 s; the recap line
is present; a change every 20 s; the hook is answered and a new loop is opened; it reads with sound off.

## Series

In a season, small peaks every episode and a bigger turn at the end of each chapter; never two quiet episodes in
a row. A new episode opens with a callback to the last frame of the previous one (`series.previous_last_frame`).
Pick the number of episodes from what the story needs; do not pad.
