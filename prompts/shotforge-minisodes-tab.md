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
