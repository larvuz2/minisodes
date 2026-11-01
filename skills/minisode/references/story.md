# Write the story

The concept and the trailer give you a world and people. The episode needs one want, one obstacle, one reversal
and one question to end on. Write the sheet first (`format.md`), then the beats with times, then the script.

## From concept to sheet

1. **Find the pressure.** Who wants what tonight, and why can't they just have it? A minisode is one scene of a
   bigger story, cut where the question is loudest.
2. **Pick the hook from the middle.** Write the whole beat list, then move its most loaded image or line to the
   first second. The hook is a promise the payoff keeps (in a way the viewer did not expect).
3. **Make the twist a fact, not a mood.** New information, a new person, a new place: something you can film
   and say in one line ("I was supposed to marry her").
4. **Make the choice active and costly.** The hero does something on screen; the cost shows on a face.
5. **End on a question the viewer feels.** One of the five cliffhangers, as an exact last frame.
6. **Track loops.** Close the hook's question; open a bigger one. Write both in `sheet.loops`.

## Genre engines

The format is the same; the engine that makes each beat land changes.

| Genre | Hook | Pressure | Twist | Cliff | Timing notes |
|---|---|---|---|---|---|
| Drama | a secret said aloud, a status shock | the secret costs someone | the secret was something else | new fact | let looks land: 1-2 s holds on faces after big lines |
| Comedy | an absurd image or a line nobody should say | escalation in threes (each worse) | the reversal of the premise | loaded look or callback button | setup → pause (0.3-0.6 s) → punchline → reaction shot; cut on the laugh, not after |
| Romantic comedy | chemistry under a lie | the lie is about to be found out | the other one has a lie too | the almost-kiss, or a line that changes everything | play the near-miss: eye contact, a held breath, interruption |
| Thriller | a clock, mid-crisis | the clock gets shorter | the ally is the threat | impossible choice or arrival | shorter shots as the clock runs, hard sound hits on reveals |
| Horror | one wrong detail in a normal frame | the wrong thing moves closer | it was already inside | arrival | silence before the sting, keep the threat behind the hero in depth |
| Mystery | a clue only the viewer sees | the clue contradicts the story | someone knew the whole time | new fact | plant the clue in frame, pay it off in a close-up |
| Sci-fi / fantasy | the impossible thing, already happening | its rule costs something | the rule was a lie | impossible choice | explain nothing; show one rule in action |

Comedy deserves its own care: the rule of three (two normal beats, the third breaks), the pause before the
punchline is planned as a shot (`silence`), the reaction shot is part of the joke, and a "button" (a tiny last
line or look) after the laugh. Dramatic silence is welcome in any genre when it is the loaded moment; empty air
is not.

## Beats in seconds

Use the table in `format.md`. For durations between the columns, keep the hook at 0-5 s, put the twist at
about 45 % and the cliff in the last 5-10 s, and split the rest so no beat runs past 20 s. Give each beat a
`tension` (0-1) that follows the pressure loop: hook 0.8, anchor 0.35-0.45, pressure 0.55-0.65, twist 0.85-0.9,
choice 0.7-0.75, payoff 0.4-0.5, cliff 0.95-1.0. Never two beats under 0.5 in a row.

## Dialogue

- **8 words a line, one idea.** Read it aloud in 2-3 s. If a look or a prop can say it, cut it.
- **Speech rate.** About 2.5 words per second for drama, up to 3.2 for fast comedy; `plan_check.py` flags
  shots above 3 words per second. A 60 s episode carries 45-90 spoken words.
- **Subtext over text.** People rarely say what they want; they say what protects it. The recap line is the
  exception: it states the stakes plainly for the newcomer.
- **Names early.** Say the hero's name (or the antagonist's) in the first 15 s so captions anchor who is who.
- **Write how it is said** (`how`): "through a frozen smile, low and fast". It becomes direction in the prompt.
- **Language.** The episode's language is the language of every line and of the voices. Keep proper nouns
  pronounceable; spell numbers as words.

## Characters

At most three with lines. Give each one a silhouette you can read at thumbnail size (a copper bob, a charcoal
suit, a veil), one want, one manner ("smiles with her mouth before her eyes") and a voice direction. Extras are
soft-focus background and never speak. Write them into `cast` with look, wardrobe, manner and voice; the same
words go into the sheet prompts, so keep them identical everywhere.

## Places

At most two. Each place has one light (a key direction and color, its practicals) and one geography (where the
door is, where the table is). Write the description into `locations` and build its blockout before any image.
