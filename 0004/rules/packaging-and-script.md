# 0004 packaging + script rules (growth plan Phases 4-6)

The 0004 script writer (a scheduled task or a `0004:` chat) reads this file, `0004/lessons.md` and the 0006 Demand Map **before every script**. These rules sit on top of the engine rules in `claude/0004-START-HERE.md`: never mention the graphic, the 3-second rule, and the two-host handoff.

## 0. No idea, no script
- Every video starts from an idea card in `0006/ideas.json` whose row in the **Ideas** tab of the "0006 Demand Map" sheet says **PASS**. The gate needs:
  - at least 3 subject outliers (3× their channel's median and 10k+ views) from at least 2 channels
  - a title format with lift ≥ 1.0 over at least 15 videos
- Mitchael's `0004:` ideas go through the same gate. If the gate fails, bridge the idea to the nearest subject or format that passes, say which, and continue.
- `scenes.json` must carry the idea in `meta.idea`:
  `{"id", "format", "title", "thumb_text", "promise", "proof", "plan"}`.
  `0004/pipeline/preflight.py` checks this and prints warnings before a render.

## 1. Title (Features tab evidence, 11k creator videos)
- **60 characters or fewer.** Longer titles get cut off on phones.
- **No `?` and no `!`.** Question titles lift 0.69× and `!` lifts 0.73×. Give the verdict; don't ask for one.
- A number helps (1.16×).
- One emoji is optional (1.38×, but compilation channels skew that number). Use at most one, at the end, and only when it adds meaning.
- **It must use its format's pattern**, e.g. `Prime X Was …`, `Footballers Who …`, `The Rise and Fall of …`. The Ideas tab "Title check" column flags titles that don't.
- Write 3 options per idea. The feed simulator (`0006/requests/feedsim.json`) picks between them.

## 2. Thumbnail (feed simulator finding, 6 Nov)
- **A recognisable player face is mandatory.** The pilot's text-only thumbnail ("60 GOALS 2ND." + medal) sat among 8 face-led competitors and got 0.9% CTR.
- **Text: 3 words or fewer**, and complementary to the title, never a repeat of it.
- **One focal subject plus one number or symbol.** Saturated colours: Daylight palette, pushed brighter at thumbnail size.
- **Run the feed simulator on every thumbnail and title pair before upload.** It picks the variant that stands out in a real feed.
- **Three proven templates** (thumbnail galleries in Drive `football-engine/0006/gallery/`, top outliers per format):
  - **T1, face-row data strip.** For "Footballers Who", "N Players" and "Most X" lists:
    - 4–6 cut-out player faces in a row, each with a name label and one big number, flag or trophy count underneath
    - yellow/red labels on a saturated background
    - This is the GOAT stats, Real Data 360 and Sportivion look (outliers from 50× to 1,500×). It fits our data mechanism exactly.
    - **Built** as engine thumbnail variant **D**: set `meta.thumb.row = [{who, label, value, mood}]` with 4–5 entries.
  - **T2, one face plus a verdict.** For Rise and Fall, Exposed and The Day:
    - one large face, often split bright/dark or with a red/green arrow
    - 2–3 words in caps ("GONE FOREVER", "THEY SUCK.", "EXPLOITED")
  - **T3, illustrated character.** For full stories:
    - cartoon or anime-style player art (FDOR "Neymar Jr Full Story" 3.9M views; HitoCast)
    - This is direct evidence that our anime identity can sell in the thumbnail. The art must be ours or licensed.
- **"Prime X Was …" outliers are almost all raw match-footage frames with no text.** We can't use footage, so this format's lift is partly theirs, not ours. Use T2 with a photo Mitchael supplies, and treat early results as a test.

## 3. The first 30–45 seconds: Promise → Proof → Plan
1. **Promise (first sentence, ≤ 10 s).** Restate exactly what the title and thumbnail promised, over the *same* image and number the thumbnail shows. The viewer must feel they clicked the right video.
2. **Proof (one sentence).** The channel's authority line, written once and reused with light variation: *"We rebuilt this from every match of that season: every goal, every minute."* Data depth is our edge.
3. **Plan (1–2 sentences).** Where the video goes, concretely enough that the viewer commits. Example: *"First the rise. Then the night it fell apart. And then the number nobody talks about."* 20-minute episodes open with a 15–20 s spoiler montage of the arcs.

Then deliver: open loops every 30–60 s (re-hooks), and pay off every promise made in the first 45 s.

## 4. Structure comes from the format's winners
| Format | Structure |
|---|---|
| Footballers/Players Who …, N Players …, Most/Highest … | Countdown of 8–15 items to #1. A re-hook every 2–3 items ("#3 still holds a record"). Michael's breakdown section on the top 2. |
| Prime X Was … | Thesis verdict, then 3 pieces of evidence (peak stats, a signature match, how rivals rated him), then the modern comparison, then the verdict. |
| Rise and Fall / Name – How … | Anime arcs: Rise, Peak, Fall (villain) arc, Aftermath. Michael explains *why* the fall happened. |
| The Day/Night X … | Cold open on the moment, rewind, build-up, the moment again in full, aftermath and legacy. |
| Exposed … | Claim, evidence 1–3, the strongest counter-argument, verdict. Every number needs a source link. |
| What Happened to … | Per person: who they were then (one peak stat), where they are now, and the turning point. |
| The Real Origins of … | Map structure: country by country, a family-roots fact per player, ending on the surprise. |

## 5. Length (Features tab)
- 3–8 min lifts 1.16×. 8–12 min (1.03) and 20–40 min (1.06) are neutral. **40+ min hurts (0.62).**
- Keep the locked mix (8–10 min standard + one 20-min episode), but never pad: a topic that runs out at 6 minutes ships at 6.

## 6. Repackaging
- **0005 verdict REPACKAGE** (CTR < 2% after 7 days): change the title and thumbnail in Studio.
  - Use another title option from the idea card.
  - Run the feed simulator first.
  - Log the change in the idea card's `history`.
- **0005 verdict FIX HOOK** (CTR fine, average view < 30%): the next scripts tighten Promise–Proof–Plan. The video itself stays.
