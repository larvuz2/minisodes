# ShotForge: the Minisodes tab

The brief given to the Lovable agent of the Phatty Acid app (ShotForge) to add the Minisodes tab. It mirrors
the Video to Game tab: the page films a trailer with MiniMax H3, then "Generate minisode" fires a Claude Code
routine on this repository, and the routine reports back and delivers through the same edge function.
Keep this file in sync with `skills/minisode/scripts/shotforge_deliver.py` and `prompts/shotforge-routine.md`.

## Brief

Add a new section **Minisodes** to ShotForge, built exactly like the existing Video to Game tab
(`src/pages/VideoToGame.tsx`, `src/lib/video-to-game.ts`, `supabase/functions/video-to-game/index.ts`,
`drizzle/migrations/0002_video_games.sql`, `useCanUseVideoToGame`). Reuse its patterns: the `Shell` layout, the
card styles, React Query polling, fal queue calls through `resolveLiveTvFalAccount` / `falKeyForJob`, the
optimistic claim before firing the routine, sha256 token hashing, signed upload URLs. Do not change Video to Game.
Do not implement or delete the pending plan in `.lovable/plan.md` (the "Press Enter to start" fix); leave it for
the owner.

A minisode is a 1 to 2 minute social-media micro-drama (vertical 9:16 by default). The user types a concept,
picks a genre, watches a 15 s trailer filmed with H3, then hits Create, picks the duration and settings, and
Claude Code produces the finished episode in the background (story, cast sheets, locations, voices, shots,
edit, music) and delivers an mp4.

### Access and navigation

- `src/hooks/useCanUseMinisodes.ts` with `MINISODES_ALLOWLIST = ["gus@phattyacid.studio", "paul@phattyacid.studio"]`,
  mirrored by a SQL function `public.can_use_minisodes(_user_id uuid)` with the same two emails (same shape as
  `can_use_video_to_game`). Keep both lists in sync.
- Route `/minisodes` in `src/App.tsx`, lazy page `src/pages/Minisodes.tsx`, inside `ProtectedRoute`.
- In `src/components/GlobalSidebar.tsx`, a new section labelled **Minisodes** (same label style as "Games"),
  with one item `{ to: "/minisodes", icon: Clapperboard (or Film), label: "Minisodes" }`, shown only when
  `canUseMinisodes`.

### Database: `drizzle/migrations/0003_minisodes.sql` (add it to `_journal.json` and apply it)

```sql
CREATE OR REPLACE FUNCTION public.can_use_minisodes(_user_id uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  select exists (select 1 from auth.users u where u.id = _user_id
    and lower(u.email) in ('gus@phattyacid.studio','paul@phattyacid.studio'));
$$;
REVOKE EXECUTE ON FUNCTION public.can_use_minisodes(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.can_use_minisodes(uuid) TO authenticated, service_role;

CREATE TABLE public.minisodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  concept text NOT NULL,
  genre text NOT NULL,
  aspect_ratio text NOT NULL DEFAULT '9:16',
  language text NOT NULL DEFAULT 'en',
  title text, logline text,
  trailer_prompt text,
  trailer_status text NOT NULL DEFAULT 'writing',   -- writing | submitting | generating | ready | failed
  writer_request_id text, request_id text, fal_account text,
  trailer_url text, error text,
  settings jsonb,                                   -- what "Generate minisode" sent
  build_status text,                                -- null | building | built | failed
  build_stage text,                                 -- story | cast | locations | voices | shoot | edit | music | deliver
  build_note text,
  spent_usd numeric, budget_usd numeric,
  previews jsonb NOT NULL DEFAULT '[]'::jsonb,      -- [{path, url, kind, label}]
  session_url text,
  episode_url text, clean_url text, poster_url text, report_url text,
  build_token_hash text, build_started_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX minisodes_user_created ON public.minisodes (user_id, created_at DESC);
GRANT SELECT ON public.minisodes TO authenticated; GRANT ALL ON public.minisodes TO service_role;
ALTER TABLE public.minisodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Owners read their minisodes" ON public.minisodes FOR SELECT TO authenticated USING (user_id = auth.uid());
INSERT INTO storage.buckets (id, name, public) VALUES ('minisodes', 'minisodes', true) ON CONFLICT (id) DO NOTHING;
```

### Edge function `supabase/functions/minisodes/index.ts` (`[functions.minisodes] verify_jwt = false`)

One POST endpoint dispatching on `body.action`, like `video-to-game`. Build-side actions first (no login, token
checked), then page actions (Bearer JWT, then `admin.rpc("can_use_minisodes", { _user_id })`).

Page actions:

- `list` → `{ episodes }`: the user's last 24 rows (strip `writer_request_id`, `request_id`, `fal_account`,
  `build_token_hash`, `user_id`). Advance each row like video-to-game's `advance()`:
  - `writing`: poll the writer request; when it completes, parse its JSON output `{title, logline, prompt}`,
    save them, submit the trailer to `https://queue.fal.run/minimax/h3-max/text-to-video` with
    `{ prompt, duration: 15, resolution: "768P", aspect_ratio: row.aspect_ratio, prompt_expansion_mode: "disabled" }`,
    store `request_id`, set `generating`. If the writer fails or returns bad JSON, use the fallback template below.
  - `generating`: poll H3; when done copy the video to `minisodes/<id>/trailer.mp4` (same `persistVideo` logic),
    set `ready` + `trailer_url`.
  - fail builds older than 12 h (`expireBuild`).
- `trailer` `{ concept (max 1500), genre, aspect_ratio ("9:16" | "16:9"), language }` → insert a row with
  `trailer_status: 'writing'`, submit the writer to the fal queue `openrouter/router` with
  `{ model: "anthropic/claude-opus-5.5", system_prompt: TRAILER_SYSTEM, prompt: <concept, genre, aspect, language>, max_tokens: 8000, reasoning: true }`
  (`reasoning: true` is mandatory: without it fal answers "Reasoning is mandatory for this endpoint and cannot be
  disabled." and every trailer falls back to the template)
  (the same way Movie Maker's story director calls it), store `writer_request_id`, return `{ episode }`.
  Max 4 rows filming at once per user (429), like video-to-game.
- `retrailer` `{ id, prompt? }` → re-film the trailer with the edited prompt (or the same one) straight to H3.
  With `rewrite: true` and an optional `direction` (500 chars), it re-runs the writer for the row first (adding
  "Director's notes for the trailer: <direction>" to the writer prompt), then films. Prompts are capped at 4,000
  characters.
- `create` `{ id, settings, again? }` → requires `trailer_status === 'ready'`; same guards and optimistic claim as
  video-to-game's `build`; reads `CLAUDE_MINISODE_ROUTINE_FIRE_URL` and `CLAUDE_MINISODE_ROUTINE_TOKEN` (503
  "Claude Code isn't connected to Minisodes yet" when missing; same FIRE_URL regex); new 64-hex deliver token,
  store its sha256; set `build_status: 'building'`, `build_stage: 'story'`, `build_note: 'Starting a Claude Code session…'`,
  `budget_usd: settings.budget_usd`, `spent_usd: 0`, clear previews and result URLs. Fire with
  `{ text: JSON.stringify(request, null, 2) }` and the same headers as video-to-game, where:

```ts
const request = {
  shotforge_request: "build-minisode",
  episode_id: row.id,
  concept: row.concept, genre: row.genre, language: row.language,
  title: row.title, logline: row.logline,
  trailer_url: row.trailer_url, trailer_prompt: row.trailer_prompt,
  trailer_model: { endpoint: "minimax/h3-max/text-to-video", duration: 15, resolution: "768P", aspect_ratio: row.aspect_ratio },
  settings: {           // validated server-side
    duration_s,         // 60..120, default 60
    aspect_ratio,       // "9:16" (default) | "16:9"
    video_model,        // only "minimax/h3-max/reference-to-video" for now
    resolution,         // "auto" (default) | "480P" | "768P" | "1080P"
    budget_usd,         // 1..100, default 5: a hard cap on all fal spend for the episode
    language,           // "en" default
    captions,           // true default
    notes,              // optional director notes, max 1000 chars
  },
  deliver_url: `${Deno.env.get("SUPABASE_URL")}/functions/v1/minisodes`,
  deliver_token: deliverToken,
};
```

  Save `claude_code_session_url` as `session_url`, then note "Claude is writing the story…".

Build-side actions, body `{ action, episodeId, token, ... }`, token checked against `build_token_hash` (401
"Unknown episode or token"):

- `note` `{ note, stage?, spent_usd? }` → `build_note` (max 300 chars), `build_stage` when it is one of
  story | cast | locations | voices | shoot | edit | music | deliver, `spent_usd` when numeric. `{ ok: true }`.
- `upload-urls` `{ paths: string[] }` (1–100, same GAME_PATH regex) → signed upload URLs (upsert) for
  `minisodes/<id>/out/<path>`; returns `{ uploads: [{ path, url }] }`.
- `preview` `{ items: [{ path, kind, label }] }` → `kind` in cast | location | voice | keyframe | take | pace | music;
  each path must already be uploaded under `<id>/out/`; append `{ path, url: publicUrl, kind, label }` to `previews`
  (replace an item with the same path; keep at most 60). `{ ok: true }`.
- `deliver` `{ entry = "final.mp4", clean?, poster?, report?, note? }` → entry must end with .mp4 and exist under
  `<id>/out/`; set `build_status: 'built'`, `build_stage: 'deliver'`, `episode_url`, and `clean_url`, `poster_url`,
  `report_url` when given and present; `build_note` = note or "Your minisode is ready." Returns `{ ok: true, url }`.
- `fail` `{ note }` → `build_status: 'failed'`, `build_note` = note or "Claude could not finish the minisode."

TRAILER_SYSTEM (use verbatim):

```text
You are a trailer director and editor. You write the prompt for a 15-second teaser trailer of a minisode, a 1 to
2 minute episode for social media. MiniMax H3 Max films your prompt in one text-to-video generation with native
sound, and the result becomes the look document for the whole episode: every later shot will match its
characters, places, light and style. Return JSON only, with no markdown fences:
{"title": "...", "logline": "...", "prompt": "..."}

Write the prompt in English. Spoken lines are in the requested spoken language.

Build the prompt as a real trailer, in this order:

1. RULES, the first line, exactly: "No title cards, no subtitles, no captions, no on-screen text, no logos."
2. STYLE, one sentence: the format (vertical 9:16 or widescreen 16:9), the medium and the look. Take the medium
   from the concept. If it says cartoon, animated, anime, claymation, stop-motion, puppet, or the hero is not
   human (an animal, an object, a food), make it a stylized animated feature-film look: describe shapes,
   materials, color and light, and never name a studio or a franchise. Otherwise photoreal live action with a
   cinematic 35 mm look.
3. CHARACTERS: at most 3, each described once, precisely enough to draw: name, species or age, body shape,
   colors, wardrobe, one signature prop, one personality tell. Use exactly the same words if they reappear.
4. SHOTS: 6 to 8 shots with time codes that cover 0-15 s with no gap. Each shot starts with its transition
   keyword (COLD OPEN, SMASH CUT, HARD CUT, MATCH CUT, WHIP PAN, CRASH ZOOM, SPEED RAMP), then shot size, angle,
   lens or camera move, then the action as visible behavior. Follow the trailer arc:
   - 0-2 s COLD OPEN: the most loaded moment of the story, mid-action, a face in the first frame, and the hook
     line by 1.5 s.
   - 2-5 s WORLD AND WANT: who the hero is and what they want, in one strong image.
   - 5-9 s COMPLICATION: the other character and the conflict in a quick exchange, then a rapid montage of two
     or three one-second shots that escalate.
   - 9-12 s THE TURN: the biggest image of the story, the money shot, on a beat drop or an impact.
   - 12-15 s BUTTON: a held reaction or a last line that leaves a question, then a hard cut to black on a
     sound sting. No title card.
5. DIALOGUE: two or three lines in total, 8 words or fewer each, in quotes, with who says it and how,
   lip-synced.
6. SOUND: native audio with the dialogue and the ambience of the place, plus trailer sound design: whooshes on
   the cuts, a low riser, impact hits and one final sting, and a sparse trailer score that drops out right
   before the last line.

Genre engine: drama = a secret, pressure, a face that breaks; comedy = an absurd image, escalation in threes, a
pause before the punchline, a reaction shot as the button; romantic comedy = chemistry, the almost-kiss, the
wrong-moment interruption; thriller = a clock and a threat behind the hero; horror = one wrong detail in a normal
frame, silence before the sting; mystery = a clue only the viewer sees; sci-fi and fantasy = one impossible rule
shown in action. If the concept's tone and the chosen genre disagree, keep the concept's world and play it in
the chosen genre.

Staging: in a vertical frame, faces and hands, not landscapes; eyes in the upper third; nothing important in
the bottom fifth or along the right edge. In a widescreen frame, compose for 16:9. One or two places. The same
light in every shot, physically plausible. Original characters only: no real people, brands, studios or
existing franchises.

Keep the prompt under 3,000 characters. The title (1 to 3 words) and the logline (one sentence: who wants what,
and what is in the way) are for the app only and never appear in the video.
```

Fallback when the writer fails (the trailer is still a real trailer: cut keywords, time codes, story, genre beats,
the medium the concept asks for, dialogue in the chosen language):

```ts
const ANIMATED = /\b(cartoon|animated|animation|anime|claymation|clay|stop[- ]motion|puppet|3d animated|2d animated)\b/i;
const GENRE_MONTAGE: Record<string, string> = {
  drama: "a secret surfaces, a hand trembles, a face starts to break",
  comedy: "three escalating mishaps, each worse than the last, a beat of silence before the punchline",
  romcom: "a near-kiss, an interruption at the worst moment, a look held too long",
  thriller: "a clock running down, a threat closing in behind the hero, a door that will not open",
  horror: "one wrong detail in a normal room, it moves closer, silence before the sting",
  mystery: "a clue only the viewer sees, a lie, a glance that gives someone away",
  scifi: "one impossible rule shown in action, its cost, the hero choosing anyway",
  fantasy: "one impossible rule shown in action, its cost, the hero choosing anyway",
};
function fallbackPrompt(concept: string, genre: string, aspect: string, language = "en") {
  const vertical = aspect === "9:16";
  const style = ANIMATED.test(concept)
    ? "stylized animated feature-film look, soft rounded 3D shapes, tactile materials, saturated but harmonious colors, warm key light from the left in every shot"
    : "photoreal live action, cinematic 35 mm film look, shallow depth of field, natural skin texture, warm key light from the left in every shot";
  const frame = vertical
    ? "Vertical 9:16, faces and hands, eyes in the upper third, nothing important in the bottom fifth"
    : "Widescreen 16:9";
  const label = (GENRES[genre] ?? genre).toLowerCase();
  const lang = LANGUAGES[language] ?? "English";
  return [
    "No title cards, no subtitles, no captions, no on-screen text, no logos.",
    `STYLE: ${frame}, ${style}. A ${label} teaser trailer, 15 seconds, 7 shots.`,
    `STORY: ${concept.trim()}`,
    "SHOTS:",
    "0-2 s COLD OPEN: extreme close-up, crash zoom in, mid-action on the hero at the most loaded moment of this story; by 1.5 s the hero says one short line, 8 words or fewer, that raises a question.",
    "2-5 s HARD CUT: medium shot, low angle, slow push-in: the hero in their world doing what they love, showing what they want.",
    "5-7 s WHIP PAN: two-shot: the other main character confronts the hero; a short, sharp reply line.",
    `7-9 s SMASH CUT: a montage of two one-second close-ups: ${GENRE_MONTAGE[genre] ?? GENRE_MONTAGE.drama}.`,
    "9-12 s SPEED RAMP: wide shot, the biggest image of this story, slow motion into an impact on the beat drop.",
    "12-15 s HARD CUT: a held close-up reaction of the hero; silence; a last whispered line that leaves the question open; hard cut to black on a sound sting.",
    `DIALOGUE: three lines in total, 8 words or fewer each, lip-synced, in ${lang}.`,
    "SOUND: native audio with the dialogue and the ambience, whooshes on every cut, a low riser, impact hits, a sparse trailer score that drops out before the last line, one final sting.",
  ].join("\n").slice(0, MAX_PROMPT);
}
```

When the writer fails, `error` says so ("Claude's trailer writer failed (<reason>); this trailer used the basic
template.") and the page offers **Rewrite with Claude**.

### Client: `src/lib/minisodes.ts` and `src/pages/Minisodes.tsx`

- `listEpisodes`, `makeTrailer(concept, genre, aspect_ratio, language)`, `refilmTrailer(id, prompt?)`,
  `createMinisode(id, settings, again?)` through `invoke("minisodes", { action, ... })`. Poll `list` every 5 s
  while a trailer is writing or filming, every 15 s while an episode is building.
- Same skeleton as Video to Game (pill "Minisodes", h1 "Make a *minisode*"):
  1. **Composer**: concept textarea (1500 chars) with three example chips; a **Genre** select (Drama, Comedy,
     Romantic comedy, Thriller, Horror, Mystery, Sci-fi, Fantasy); a **Format** toggle Vertical 9:16 (default) /
     Landscape 16:9; a **Language** select (English default, Spanish, French, Portuguese); button
     **Make trailer**.
  2. **Trailer card**: a black stage with the right aspect (9:16 stage is narrow and tall, centered,
     `max-h-[75vh]`); states "Claude is writing the trailer…" then "Filming the trailer…" with the elapsed clock,
     then the video with controls. Under it the title, logline and the trailer prompt in a collapsible,
     editable box with **Refilm trailer** and **Rewrite with Claude** (with an optional "Direction for the
     trailer"). When `error` says the basic template was used, show it in amber with that button.
  3. **Create**: button **Create minisode** opens a settings panel: Duration slider 60–120 s, step 15, default
     60; Format (prefilled from the trailer); **Video model** dropdown with one option "MiniMax H3 Max ·
     reference to video" (designed to receive more models later); Resolution (Auto default, 480P, 768P, 1080P);
     **Budget** in USD (default 5, 1–100) with a live estimate under it; Captions switch (on); Director notes
     (optional). Button **Generate minisode**.
     Live estimate (show the math): video seconds = duration × 1.1; price per second 480P 0.05, 768P 0.08,
     1080P 0.16; assets 1.20; audio 0.10 + 0.60 × duration / 60; retakes reserve 25 % of video. Auto picks the
     highest resolution whose total fits the budget. If even 480P does not fit, say so in amber ("about $X needed
     for a full episode at 480P") but still allow it.
  4. **Build strip**: a stage tracker Story → Cast → Locations → Voices → Shoot → Edit → Music → Delivered
     from `build_stage`; the `build_note`; spent vs budget as a thin bar (`spent_usd` / `budget_usd`); elapsed
     time; "Claude Code session" link; **Build again** when failed or built.
  5. **Previews**: a horizontal strip of `previews` grouped by kind (images as thumbnails with a lightbox, takes and
     voices as small players).
  6. **Result**: when built, the episode in the stage (vertical), buttons Download (with captions), Download clean,
     Report (open `report_url`).
  7. **Your minisodes** grid of past rows (poster or trailer thumb, title, status).

### Secrets the owner adds

`CLAUDE_MINISODE_ROUTINE_FIRE_URL` and `CLAUDE_MINISODE_ROUTINE_TOKEN`: the API trigger of a Claude Code routine on
`larvuz2/minisodes` (see `prompts/shotforge-routine.md`). Until they are set, Create shows the 503 message.

## Update 2: three modes, guided approvals, the gallery

The second brief given to the Lovable agent. It extends the contract above; `skills/minisode/scripts/shotforge_deliver.py checkpoint` and `restore` are its run side.

Redesign the Minisodes page and add three ways to make an episode: trailer then autopilot (what exists), straight to autopilot with no trailer, and a guided mode where the user approves the cast, then the story, then the locations before Claude films. Keep everything that works today (trailer writer, Rewrite with Claude, the build actions note/upload-urls/preview/deliver/fail, the routine fire). Do not touch Video to Game or other pages. Do not start any paid fal generation or fire the routine while testing; use mocks.

### How guided mode works (the important part)

A Claude Code run cannot wait hours for a click, so a guided episode is made in phases, each phase its own fire of the same routine:

- Phase `cast`: Claude drafts the story, makes each character's sheet and voice sample, uploads them plus its saved work folder ("state"), calls the new build action `checkpoint`, and the run ends. The episode is now `awaiting_approval`.
- The user approves, or comments on specific characters. A comment fires phase `cast` again with `revision: true` and the comments; approving fires phase `story`.
- Phase `story` → checkpoint with a story summary the user can edit, comment on, or approve.
- Phase `locations` → checkpoint with 3+ views per place.
- After the last approval, phase `finish` makes the rest and delivers.

Every fire after the first sends signed URLs of the saved state so the run can restore it.

### Database: `drizzle/migrations/0004_minisodes_guided.sql` (add to `_journal.json` and apply)

```sql
ALTER TABLE public.minisodes
  ADD COLUMN with_trailer boolean NOT NULL DEFAULT true,
  ADD COLUMN guided boolean NOT NULL DEFAULT false,
  ADD COLUMN phase text,                                      -- last phase fired: full | cast | story | locations | finish
  ADD COLUMN approval_stage text,                             -- cast | story | locations while waiting for the user
  ADD COLUMN checkpoint jsonb,                                -- {stage, items, summary, note, at}
  ADD COLUMN approvals jsonb NOT NULL DEFAULT '{}'::jsonb,    -- {cast: {approved_at, rounds}, story: {...}, locations: {...}}
  ADD COLUMN state_paths jsonb NOT NULL DEFAULT '[]'::jsonb,  -- storage paths (under <id>/out/) of the saved work folder parts, in order
  ADD COLUMN fires integer NOT NULL DEFAULT 0;
CREATE INDEX minisodes_built_created ON public.minisodes (build_status, created_at DESC);
```

New values (text columns, no constraints): `trailer_status = 'skipped'` when there is no trailer; `build_status = 'awaiting_approval'`.

### Edge function `supabase/functions/minisodes/index.ts`

1. **`start`** (page) `{ concept, genre, aspect_ratio, language, with_trailer, guided, settings }`:
   - Validate `settings` with `cleanSettings` and store `settings`, `with_trailer` and `guided` on the new row.
   - `with_trailer: true` → exactly today's `trailer` flow.
   - `with_trailer: false` → insert the row with `trailer_status: 'skipped'`, then fire at once with phase `guided ? 'cast' : 'full'`.
   - Keep `trailer` as an alias of `start` with `with_trailer: true`.
   - If the routine secrets are missing, return the same 503. The row stays, and the page offers **Start** again from the workspace.
2. **`create`** `{ id, settings, again? }`:
   - Allowed when `trailer_status` is `'ready'` or `'skipped'`.
   - Phase is `row.guided ? 'cast' : 'full'`.
   - `again: true` also resets `approvals`, `checkpoint`, `approval_stage` and `state_paths`.
3. **One shared `fire(row, { phase, revision = false, feedback = null, comment = null, story_edits = null })`** used by start, create and approve:
   - Mint a new 64-hex deliver token and store its sha256; `fires += 1`.
   - Set:
     - `phase`;
     - `build_status: 'building'`;
     - `approval_stage: null`;
     - `build_stage` (`cast` → `cast`, `story` → `story`, `locations` → `locations`, `finish` → `shoot`, `full` → `story`);
     - `build_note` ("Claude is drawing the cast…", "Claude is writing the story…", "Claude is building the locations…", "Thanks for the approvals. Claude is filming…", or today's note for `full`).
   - Reset `spent_usd`, `previews`, the result URLs and `build_started_at` only on the first fire of a build: phase `full`, or phase `cast` with `revision` false and no approvals yet.
   - Payload = today's request plus:
     - `mode: { with_trailer, guided }`;
     - `phase`, `revision`, `feedback`, `comment`, `story_edits`;
     - `approved: { cast: bool, story: bool, locations: bool }`;
     - `state_urls`: `state_paths` signed for 7 days, in order, or `null` when empty;
     - `trailer_url` and `trailer_prompt` are `null` when skipped.
   - Same optimistic claim, headers, error handling and `session_url` saving as today.
4. **`checkpoint`** (build action, token-checked like the others) `{ stage: 'cast'|'story'|'locations', items: [], summary?, state: [], note?, spent_usd? }`:
   - Validate:
     - `items`: at most 40. Each item:
       - `id` matching `^[\w-]{1,60}$`;
       - `group` (80 chars), `label` (120) and `description` (600);
       - optional `image` and `audio`: GAME_PATH paths that are uploaded under `<id>/out/`.
     - `summary` (required for story, under 20 KB): `{ title, logline, beats: [{ id, time, text, lines: [] }] (at most 12), cliffhanger }`.
     - `state`: 1 to 20 uploaded paths.
   - Set:
     - `build_status: 'awaiting_approval'`, `approval_stage: stage`, `build_stage: stage`;
     - `checkpoint: { stage, items, summary, note, at }`;
     - `state_paths: state`;
     - `build_note`: the note, or "Your <stage> is ready for review.";
     - `spent_usd` when numeric.
   - Return `{ ok: true }`.
5. **`approve`** (page) `{ id, stage, decision: 'approve'|'revise', feedback?: { [item_id]: string }, comment?: string, story_edits? }`:
   - Requires `build_status === 'awaiting_approval'` and `approval_stage === stage`.
   - Size limits: feedback values 1000 chars, at most 40 keys; comment 1000; `story_edits` under 20 KB, same shape as `summary`.
   - `revise`: needs at least one non-empty feedback value or comment, or `story_edits` for the story stage. Do `approvals[stage].rounds += 1`, then `fire(phase: stage, revision: true, …)`.
   - `approve`: set `approvals[stage] = { approved_at, rounds }`. The next phase is `cast → story`, `story → locations`, `locations → finish`. Pass `story_edits` along when the user edited the story and approved in one go.
6. **`list`** (page): the user's rows that are not built, plus built rows from the last 24 hours, newest first, 30 at most, advanced as today. Sign `checkpoint.items[].image` and `audio` into `image_url`/`audio_url` (7 days).
7. **`gallery`** (page) `{ cursor?, genre?, q?, limit? (default 18, max 36) }`:
   - Built episodes of every allowlisted user (a shared studio library), newest first.
   - Keyset pagination on `(created_at, id)`.
   - Optional genre filter, and `q` matched with ilike on title, logline and concept.
   - Returns `{ episodes: [{ id, title, logline, concept, genre, aspect_ratio, duration_s: settings.duration_s, poster_url, episode_url, clean_url, report_url, trailer_url, created_at, guided, with_trailer }], next_cursor }`, URLs signed.
   - Without a cursor, it also returns `genres: [{ genre, count }]` for the built episodes.

### Page: `src/pages/Minisodes.tsx` (home) and `src/pages/MinisodeWorkspace.tsx` (`/minisodes/:id`)

The look is a dark, cinematic streaming home. Use the existing theme tokens and shadcn components; build small components (`EpisodeCard`, `GalleryRow`, `ModePicker`, `Stepper`, `CastApproval`, `StoryApproval`, `LocationsApproval`, `PlayerDialog`). Make it work well on desktop and on a phone.

#### Home `/minisodes`

1. **Composer** at the top, a wide glass card over a soft blurred backdrop of the newest poster:
   - A big textarea "Describe your minisode…" (1,500 chars) with three example chips.
   - A control row: Genre, Format (9:16 / 16:9 segmented), Language, Duration (60–120 s, step 15), and Budget with the live estimate as a popover.
   - **Two checkboxes**, each with a one-line description:
     - ☑ **Create a trailer first**: "Watch a 15-second teaser before anything else (about $1.20)." On by default.
     - ☐ **Guided: approve cast, story and locations**: "Claude stops for your OK at each step before filming." Off by default.
   - Under the checkboxes, one line describing the chosen path:
     - "Trailer → you watch it → Claude makes the episode";
     - "Claude starts now and makes everything";
     - "Trailer → you approve the cast → the story → the locations → Claude films and finishes";
     - "Claude makes the cast → you approve → story → locations → Claude films and finishes".
   - A collapsible **More settings**: the video model dropdown, resolution, captions, director notes.
   - The primary button reads **Make trailer** when the trailer box is ticked, otherwise **Start minisode**. It calls `start`, then opens the workspace.
2. **Needs your approval**: a row shown only when non-empty, with amber "Cast ready for review" / "Story ready" / "Locations ready" badges.
3. **In progress**: a row with the stage label and a thin progress bar; trailers that are writing or filming show here too.
4. **The gallery**, Netflix style, the biggest part of the page:
   - Big 9:16 poster cards: about 240 px wide on desktop, 2 per row on a phone. Each card has:
     - title, genre chip, duration badge;
     - on hover, a muted autoplay of the episode and the logline.
   - Rows: "New episodes" first, then one row per genre with episodes (from `genres`), each with horizontal scroll, arrow buttons and **See all**.
   - **See all** and the search field open a grid with infinite scroll (`gallery` with cursor).
   - Clicking a card opens the **PlayerDialog**:
     - a tall vertical player (max 85vh);
     - title, logline, genre, duration and date;
     - Download, Download clean, Report, and Open workspace.
   - An elegant empty state when nothing is finished yet.
   - Lazy-load rows as they scroll into view; this must stay fast with thousands of episodes.

#### Workspace `/minisodes/:id`

1. A header with the title (or the concept), genre, and mode badges (Trailer, Guided, Autopilot).
2. The **Stepper**, horizontal on desktop and vertical on a phone:
   - Steps: Trailer (only when `with_trailer`) → Cast → Story → Locations → Filming → Edit → Music → Done.
   - Each step shows an icon and a short label:
     - ✓ done: "Characters approved", "Story approved", "Locations approved";
     - ● Claude working (spinner);
     - ⏳ waiting for you (amber: "Your turn");
     - ○ upcoming.
   - Filming shows "Filming 3 of 5" when the build note carries it.
   - In autopilot, Cast, Story and Locations are marked done automatically from `build_stage`, with no approval badge.
3. The panel for the current step:
   - **Trailer**: today's trailer card (player, prompt, Refilm, Rewrite with Claude, Create minisode with settings).
   - **Cast approval** (`approval_stage: 'cast'`):
     - A grid of character cards: a big sheet image (lightbox with zoom), name, description, and a voice player.
     - Each card has **Looks right ✓** (a toggle) and **Change…**, which opens a textarea "What should change? e.g. shorter hair, warmer voice".
     - A sticky footer shows "2 of 3 approved", plus an optional general comment.
     - If any card has a note, the main button is **Regenerate 1 character with your notes** (revise). When every card is approved, it is **Approve cast & continue**.
   - **Story approval**:
     - Editable title and logline.
     - The beats as a vertical timeline: a time chip, editable text, and key lines as quotes. The cliffhanger is editable too.
     - **Rewrite with Claude** needs a "What should change?" comment.
     - **Approve story & continue** sends `story_edits` when anything was edited.
   - **Locations approval**:
     - One section per place: big views in a grid or carousel (lightbox), each with its description.
     - Each view has **Looks right ✓** and **Change…**. Use a placeholder hint like "the walls warmer, brass instead of chrome, more plants".
     - A general comment per place, sent as a feedback entry with the key `place:<group>`.
     - The footer offers **Regenerate N views with your notes** or **Approve locations & start filming**.
   - **While Claude works on a step**: skeleton cards with "Claude is drawing the cast… usually 5–15 minutes", plus the Claude Code session link.
   - **After the last approval**: a warm full-width panel:
     - "That's it. You can leave now. I'll keep working and finish your episode in the background. Thanks for the approvals."
     - Below it: the expected time (about 1–2 hours), the remaining stepper, spent vs budget, and the previews strip.
   - **Done**: the episode player, the downloads and the report.
4. **Polling**:
   - every 5 s while a trailer is writing or filming, or a step is running;
   - every 20 s while waiting for approval;
   - never for the gallery.

### Test (no paid jobs, no real fire)

- Mock fal and the fire, and walk one guided episode through every step:
  - start without a trailer;
  - a fake cast checkpoint (2 items with images);
  - revise one item;
  - approve;
  - a story checkpoint, edited and approved;
  - a locations checkpoint, approved;
  - finish;
  - deliver.

  Check each fire payload (phase, revision, feedback, story_edits, state_urls).
- Check that a checkpoint with a path that was not uploaded is refused.
- Check that approve is refused when the stage does not match.
- Check that the gallery paginates.
- Take screenshots of the home and of each approval panel with seeded fake rows, then delete every test row and test file.
