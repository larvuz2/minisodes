# AGENTS.md

Guidance for coding agents working on this repository. To use the skill rather than develop it, see the README.

## Layout

```text
skills/minisode/               the skill (this is what gets installed)
  SKILL.md                     entry point: workflow, hard rules, reference routing
  references/                  format, story, bible, blockout, shots, shoot-and-review, edit, sound
  scripts/                     Python (standard library; fal-client only through fal_run.py) + blockout.mjs (Node)
  templates/                   episode.json, layout.json, edit.json
examples/plus-one/             a complete 60 s plan, blockout and edit list (the test fixture)
prompts/                       ShotForge routine prompt, the Minisodes tab brief (the app's contract)
docs/                          the micro-drama format guide
tests/check_repo.py            static checks + the example's plan, prompt and pace checks
.claude-plugin/                Claude Code plugin + marketplace manifests
```

## Commands

```bash
python3 tests/check_repo.py
```

## Rules

- Python 3.9+, standard library, ffmpeg/ffprobe on PATH; `fal-client` is imported only inside `fal_run.py`. Every
  script has a docstring with usage lines and `--help`. Every fal call goes through `fal_run.run` so the ledger
  sees it.
- `episode.json` is the single source of truth for an episode; scripts read it, never a second copy of the story.
- The delivery contract (`shotforge_deliver.py`) must match the `minisodes` edge function described in
  `prompts/shotforge-minisodes-tab.md`. Change both together.
- Prices live in `fal_run.py` (check them against fal's pricing API when a model changes).
- No absolute home paths, secrets or API keys in committed files; no generated media in the repo except the small
  example previews. Keep the repository under 10 MB. Code comments in English.
