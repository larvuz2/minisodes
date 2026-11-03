# AGENTS.md

Guidance for coding agents working on this repository. To use the skill rather than develop it, see the README.

## Layout

```text
skills/minisode/               the skill (this is what gets installed)
  SKILL.md                     entry point: workflow, hard rules, reference routing
  references/                  format, story, bible, blockout, shots, shoot-and-review, edit, sound, cinematic
  scripts/                     Python (standard library; fal-client only through fal_run.py) + blockout.mjs (Node)
  templates/                   episode.json, layout.json, edit.json
examples/plus-one/             a complete 60 s social plan, blockout and edit list (a test fixture)
examples/handover/             a complete 60 s cinematic plan and blockout (a test fixture)
prompts/                       ShotForge routine setup and run steps, the Minisodes tab brief (the app's contract)
docs/                          the micro-drama format guide
tests/check_repo.py            static checks + both examples' plan, prompt, pace and estimate checks
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
- Presets (`social`, `cinematic`) change numbers in `plan_check.py` (`PRESETS`) and `pace.py` (`PACE`); keep
  them in step with `references/format.md` and `references/cinematic.md`.
- No absolute home paths, secrets or API keys in committed files; no generated media in the repo except the small
  example previews. Keep the repository under 10 MB. Code comments in English.
