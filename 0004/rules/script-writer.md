# 0004 script writer (step 4): the daily 14:00 Lagos job

A scheduled session (or a `0004:` chat) follows this file top to bottom. Its output is one committed
`0004/videos/<idea-id>/scenes.json`. The pipeline does the rest on its own:
`0004-intake.yml` (photo slots in Drive + Telegram list) → Mitchael fills slots → `0004-render.yml` renders at 21:00 Lagos → Drive + Telegram.

## 0. Setup
- Clone `Mitchaelbasil/football-engine` (gh is authenticated). Work on `main`.
- Read, in this order:
  1. this file
  2. `0004/rules/packaging-and-script.md`
  3. Project docs `claude/0004-START-HERE.md` (engine and scene schema) and `claude/0004-READ-FIRST-growth-rules.md`
  4. `0004/videos/villains-opening/scenes.json`, the reference script: structure, beats, actions, photo slots, meta
- **One video in flight.** If any `0004/videos/*` folder (not `_`-prefixed) has an idea whose card status in `0006/ideas.json` is
  `scripted` but not `rendered`/`uploaded`, stop and send a Telegram line saying what is waiting.

## 1. Pick the idea
- Use the newest Demand Map export (Drive `football-engine/0006/`, the text export) **Ideas** tab and `0006/ideas.json`.
- Only cards whose gate says PASS. Rank by format lift × subject outliers. Skip any card that has a `status`.
- Prefer a different format from the last video (variety tests more formats; 0005 verdicts will say which to double down on).
- If 0005's double-down queue (the "Verdicts" tab) names a topic, that beats the ranking.

## 2. Research (facts are the product)
- WebSearch for every number, date, fee and quote. Two sources for anything surprising.
- Every claim goes into `meta.sources` as `"<what it backs>: <url>"`. `describe.py` prints them in the description.
- No number from memory. If a fact can't be sourced, cut the line.

## 3. Write `scenes.json`
- Folder name = idea id. Copy the shape of villains-opening.
- **meta**
  - `title`: the card's first title option, after a lint against the title rules
  - `idea`: {id, format, title, thumb_text, promise, proof, plan}
  - `thumb`: use `row` (variant D) for lists; use `big`/`top`/`kicker` plus `faces` for single-player formats
  - `sources`
- **Opening:** Promise → Proof → Plan within 45 s. Structure per format: packaging rules §4.
- **Two hosts:** Bella (H) tells the story. Michael (P) does the breakdown, 15–25 % of the runtime, and handles the top entries.
- **Photo slots:** 1 per entry/section, numbered from 1, each with a concrete `desc` (player, shirt, season, moment) and a `cap`. Never more than 14.
- **Length:** what the topic supports. Lists of 8–15 items: 6–9 min. Never pad.
- **Shorts:** two, built from the two strongest standalone moments.

## 4. Validate before committing
```
python 0004/pipeline/preflight.py 0004/videos/<id>   # 0 warnings
python 0004/pipeline/build.py 0004/videos/<id>       # fake-voice plan must pass (no "plan issue" lines)
```
- If the plan fails, vary the `do` words at the reported scene. Don't use `--allow-invalid`.

## 5. Commit
- `git add 0004/videos/<id>`.
- Set the card's `status` in `0006/ideas.json` to `"scripted <date>"`.
- Commit message: `0004 script: <title>`. Push.
- The push triggers intake: Drive slots, Telegram list, render clock (before 15:00 → 21:00 Lagos the same day).
- Telegram (shared/telegram.py) one line: title, length estimate, slot count.
