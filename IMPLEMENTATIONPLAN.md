# clearnight: Implementation Plan

## Progress tracker

Orchestrator-maintained. Updated at every task acceptance; committed with the next
builder commit (predictable cadence: brief → build → verify → accept → journal +
tracker → next brief). Only the builder commits.

| Item | What | Status | Commit |
|---|---|---|---|
| WO1 | Architect: §5 v2 rewrite, T13/T15/T06 updates, file map fold-in | ✅ accepted — arithmetic independently verified | pre-git |
| T01 | Repo scaffold, git init, first commit (16 files) | ✅ accepted — exit-5 deviation ruled closed | `0a3f9d8` |
| T02 | `models.py` — 11 frozen dataclasses incl. `NightScore.verdict` | ✅ accepted — 23 tests | `658a84e` |
| T03 | `config.py` + example TOML (D4 api_key pattern) | ✅ accepted — 39 tests total | `e0182b9` |
| T04 | `cache.py` + tzdata Windows marker | ✅ accepted — 47 tests total | `3d5e362` |
| T05 | CLI skeleton (`plan`/`log`/`fetch`, `--offline`) | ✅ accepted — 54 tests, exit codes verified live | `94c6191` |
| T04a | De-flake cache timing tests (flake caught post-accept) | ✅ accepted — 5× green runs | `9dd449d` |
| T06 | Demo fixtures + epoch pinning (ref date corrected → 2026-10-07) | ✅ accepted — 60 tests; live fixtures verified | `6ee7e5a` |
| T07 | Sky engine (skyfield: dark windows, Moon, radiants) + sky.json | ✅ accepted — 72 tests; Oct 9 illum 0.26%, 9.58 h dark | `8d2be02` |
| T08 | Meteor showers + `data/meteor_showers_2026.json` | ✅ accepted — 84 tests; Draconids boundary verified live | `4fe5d43` |
| T09 | ISS TLE cache + visible-pass prediction + fixture recording | ✅ accepted — 98 tests; 1 real pass (Oct 13, dawn, 19.7°) | `d3ff041` |
| T10 | Open-Meteo forecast client + window slicing | ✅ accepted — 112 tests; live slice check (Oct 9 window: 0% cloud) | `c3701b6` |
| T11 | Sensor adapters (csv + http_json) + factory | ✅ accepted — 124 tests; A8 config-switch asserted | `0d79e87` |
| T12 | Conditions (dew risk, pressure trend, forecast-vs-actual) | ✅ accepted — 138 tests; live assess check | `2102d3b` |
| T13 | Pure scoring (ratified D5 v2) + verdict bands — **A5 gate** | ✅ accepted — 157 tests; live week preview: 96 PRIME → 15 STAY IN BED | `ba20985` |
| T14 | Assemble nights + offline plan — **A1 gate** | ✅ accepted — 165 tests; live plan verified (Oct 8: 100 PRIME) | `58da4a1` |
| T15 | HTML render (red-on-black) + text summary polish | ✅ accepted — 176 tests; self-contained page verified | `b2fb089` |
| T16 | Online path (live fetch/sensor/TLE through cache) — **A2 core** | ✅ accepted — live smoke verified; cache-through proven | `f5c4bea` |
| T17 | Field log (`log` command + plan integration) — **A9** | ✅ accepted — 190 tests; FIELD LOG block verified end-to-end | `9c8775e` |
| — | **Post draft started** (POST_DRAFT.md — sections 1, 4, 5 drafted from real build facts) | ✅ Wed milestone | rides next commit |
| T11b | http_json auth headers + HA-format regression tests | ✅ accepted — 194 tests; header + `_dewy` chain verified in-process | `4ad848f` |
| — | `out/verify_sensor_endpoint.py` local tool (token via env) | ✅ live: degrade path exit 1 vs real endpoint | local (gitignored) |
| T18 | Brief generation (prompt build + LLM call) | ✅ accepted — 204 tests (`691883b`); empty-nights guard T18a (`7893a9a`) | `691883b` |
| T19 | Verifier + retry/fallback — **A6/A7 gate** | ✅ accepted — 224 tests; extractor verified live | `9cbbaf3` |
| T20 (+a–d) | Verified brief wired into plan — **A2 complete** | ✅ accepted — 243 tests; **LIVE VERIFIED BRIEF from local Qwen** | `07a12c3`…`ca9beb2` |
| T21 | README + screenshots | 🔵 next | — |
| T22 | QA sweep: accuracy check (A4), audits (A11/A12), fresh-clone A1 | ⚪ queued | — |

**Phase 1 gate (skeleton, Wed AM): ✅ COMPLETE** (T01–T06 + T04a). Phase 2 (sky core):
✅ T07 accepted. Phase 3 (events): ✅ COMPLETE (T08–T09). Phase 4 (weather/sensor)
in flight: T10–T12. ✅ COMPLETE. Phase 5 (scoring) in flight: T13. ✅ COMPLETE (A5). Phase 6 milestone: T14 ✅ COMPLETE — **A1 PASSED**
(`py -m clearnight plan --offline` runs end-to-end from committed fixtures; Oct 8
ranks 100 PRIME, Oct 9 85 PRIME with Draconids PEAK at 0% cloud; overcast cap
fired on the weekend). Radiant-up hours recorded into sky.json. Template brief
labeled per A7. Ruling: 103-char label line exceeds 80 cols - wording wins,
wrap to two lines in T15. Next: T15 render. T15 ✅ (`b2fb089`). T16 ✅ (`f5c4bea`) —
Thursday gate secured. T17 in flight (A9). **Flags:** tzdata exception pending
owner ratification (JOURNAL, T03 entry). Delegation briefs live in `out/brief-*.md` **Owner-required, non-delegable:**
Thu Oct 9 field test (D3); Sat Oct 11 publish click (D1).

---

This file sequences the build into calendar-bound phases so that every MUST item (D1–D4, A1–A12) is complete by **EOD Friday, Oct 10**, leaving Saturday for final review and publishing only. It does not replace `PROJECTGUIDELINES.md` (source of truth), `ARCHITECTURE.md` (design), or `TASKS.md` (builder tasks). It is the orchestration layer: what must be true at the end of each day, and what gets cut if it isn't.

**The two immovable anchors:**

1. **Thu Oct 9, before dusk** — `plan` runs end-to-end online, because the Draconids field test happens that night (D3). This is the critical path; everything before it exists to make this possible.
2. **Fri Oct 10, EOD** — all MUST items pass, post draft is complete. Sat Oct 11 is read-and-publish only (noon final read, 6:00 PM CT publish, hard stop).

---

## Phase overview

| # | Phase | When | Aspect | Exit criteria (gate) |
|---|---|---|---|---|
| 0 | Decisions & Architecture | Tue Oct 7, night | Planning | `ARCHITECTURE.md` + `TASKS.md` written; sensor type, site, repo name confirmed by Michael |
| 1 | Skeleton & Offline Spine | Wed Oct 8, AM | Repo / infra | Repo initialized; `plan --offline` stub produces fixture-driven output skeleton |
| 2 | Sky Engine | Wed Oct 8, midday | Astronomy core | Dark windows + Moon data correct for demo site; unit tested from fixtures |
| 3 | Sky Events | Wed Oct 8, PM | Astronomy core | Meteor showers + ISS passes per night, cached TLE, tested offline |
| 4 | Weather & Sensor | Wed Oct 8, late PM | Data layer | Open-Meteo client, both sensor adapters, conditions module; all mocked in tests |
| 5 | Scoring & First Brief | Wed Oct 8, EOD | Ranking + writing start | Pure score function with unit tests (A5); post draft started |
| 6 | Online End-to-End & Field Test | Thu Oct 9 | Integration + evidence | `plan` online for Michael's site (A2, A3); **Draconids field test that night; log it** |
| 7 | Grounded AI Brief | Fri Oct 10, AM | Open-source AI core | Brief + verifier + retry + labeled fallback (A6, A7) |
| 8 | Render, Log, Docs | Fri Oct 10, midday | Output + evidence | HTML plan, text summary, field log in plan (A9), README + screenshots (D2) |
| 9 | QA Freeze & Post Complete | Fri Oct 10, PM (stretch cutoff 8 PM) | Quality + submission | Full offline suite green (A10); accuracy cross-check recorded (A4); privacy audit (A11); post draft complete |
| 10 | Publish | Sat Oct 11 | Submission | Post published by 6:00 PM CT (D1); repo public and linked (D2) |
| 11 | Stretch (conditional) | Fri Oct 10 only, before 8 PM | Enhancement | S-items only if every gate above passed on time |

---

## Phase details

### Phase 0 — Decisions & Architecture (Tue Oct 7, night)

The architect model reads `PROJECTGUIDELINES.md` in full and produces:

- `ARCHITECTURE.md`: final file map, data flow, module signatures, exact scoring formula with a worked example, brief prompt outline, verifier claim-extraction rules, caching/offline strategy, risks with mitigations.
- `TASKS.md`: ordered tasks T01…, each ~15 min of builder time, ending in passing tests, tagged with the AC IDs they advance. T01 creates `pyproject.toml`, `.gitignore` (must include `config.local.toml` from the very first commit — A11), `LICENSE`, skeleton, and runs `git init`.

**Blocking decisions needed from Michael before Wednesday starts:**

1. Sensor hardware and how it exposes readings (decides whether `http_json` covers it or a third adapter task is needed).
2. Observing site (home vs. darker site — goes in `config.local.toml` only).
3. Repo name confirmation (`dev-brewery/clearnight`).

**Gate:** both docs exist in the repo; the three open questions are answered. No application code is written in this phase.

### Phase 1 — Skeleton & Offline Spine (Wed Oct 8, AM)

- Package skeleton per the file map; `config.py` loading `config.example.toml` (Black Mesa demo site) with `config.local.toml` override; `models.py` dataclasses; `cache.py` disk cache with max-age.
- `__main__.py` with `plan` / `log` / `fetch` / `--offline` entry points wired to stubs.
- Fixtures directory started (`tests/fixtures/`).

**Gate:** `python -m clearnight plan --offline` runs and prints a placeholder plan from fixtures, no network, no LLM. A1 is on track to be the earliest working acceptance item, as required.

### Phase 2 — Sky Engine (Wed Oct 8, midday)

- `sky.py` with skyfield + bundled/cached `de421.bsp`: astronomical dark window (Sun < −18°), Moon rise/set/illumination/altitude across each window, for the N-night horizon from config.
- Unit tests from fixtures; times stored UTC, displayed in site-local timezone.

**Gate:** dark windows and Moon numbers for the demo site look sane and are tested offline.

### Phase 3 — Sky Events (Wed Oct 8, PM)

- `meteors.py`: `data/meteor_showers_2026.json` from the IMO calendar (source URL recorded in the file); active/peak/radiant-up logic per night. Verify the Draconids peak (Oct 9, ~1% Moon) is present and correct — Phase 6 depends on it.
- `iss.py`: CelesTrak GP/TLE fetch with 24 h cache refresh and offline fallback; visible-pass prediction (sunlit ISS, dark observer) with times, max altitude, direction.

**Gate:** event lists per night render into the offline plan; TLE cache works offline.

### Phase 4 — Weather & Sensor (Wed Oct 8, late PM)

- `forecast.py`: Open-Meteo hourly client (`urllib`, timeout, cached/fixture fallback), sliced to each night's dark window.
- `sensor/`: adapter interface `read_recent(hours)`, `csv` adapter (fixture-tested) and `http_json` adapter (config-mapped fields).
- `conditions.py`: dew-risk estimate from temp/dew-point spread, 3–6 h pressure trend, forecast-vs-actual view.

**Gate:** all network calls mocked in tests; sensor switchable by config alone (A8).

### Phase 5 — Scoring & Post Draft Start (Wed Oct 8, EOD)

- `score.py`: pure, deterministic 0–100 score from cloud cover, Moon interference, transparency, dew risk, wind, event bonus; per-factor breakdown. Unit tests must cover the A5 orderings: clear moonless > clear full-Moon > cloudy; dew risk lowers; meteor peak raises. **No LLM anywhere near the score.**
- **Post draft started tonight** (sections 1 and 4 of the template: what I built, how I built it with open-source AI). The post grows alongside the code from here — this is the lesson from homestead-stories.

**Gate:** A5 tests green; `draft.md` for the post exists in the writing tool of choice with real content.

### Phase 6 — Online End-to-End & Field Test (Thu Oct 9)

- **Before dusk:** wire the real config; run `python -m clearnight plan` online for Michael's site (A2). Full night display per A3: dark window (local time), Moon phase/illum/rise/set, cloud summary, dew risk, score + breakdown, showers with peak marked, ISS passes with times/alt/direction. Fix whatever breaks — this run is the rehearsal for the night.
- Pull `fieldlog.py` (basic append) forward into today if the schedule allows, so the night can be logged immediately; otherwise record observations in notes and log them Friday morning — do not let the evidence evaporate.
- **That night: Michael goes out with the printed plan** (Draconids peak, ~1% Moon). Note: actual conditions vs. prediction, meteors counted, ISS seen, anything the plan got wrong.

**Gate:** online plan produced for the real site; field observations captured in some durable form. If clouded out: capture the plan predicting clouds — that is the honest fallback D3 allows.

### Phase 7 — Grounded AI Brief (Fri Oct 10, AM)

- `brief.py`: prompt built strictly from computed Night data; call to the local Qwen endpoint on llm-box (`http://llmbox.internal:8080/v1`, OpenAI-compatible) with timeout.
- `verify.py`: extract every time, number, and named event from the brief; check each against that night's computed data; retry loop with problems listed; labeled template brief as final fallback. Tests with canned replies: one passes, one fails (A6); unreachable-LLM case renders fine (A7).

**Gate:** A6 and A7 tests green; a real brief from llm-box survives verification or falls back cleanly.

### Phase 8 — Render, Log, Docs (Fri Oct 10, midday)

- `render.py`: one-page red-on-black HTML plan (phone-in-the-dark readable, printable) + terminal text summary.
- Field log wired into the plan: Thursday's entry appears next to its prediction (A9, and the D3 evidence).
- `README.md`: install, configure, run, screenshot. Capture screenshots for the post (D2), including the field-log comparison.

**Gate:** `out/plan.html` for Michael's site contains the Thursday prediction next to the logged outcome; screenshots captured.

### Phase 9 — QA Freeze & Post Complete (Fri Oct 10, PM)

- Full suite offline: `python -m unittest` green (A10).
- Accuracy cross-check (A4): Sun/Moon/ISS for the demo site vs. timeanddate.com / Heavens-Above, ±5 min / ±5°, recorded in `tests/` or the post.
- Privacy audit (A11): no home coordinates, sensor URLs, or secrets anywhere in code, fixtures, history. Verify `.gitignore` covered `config.local.toml` from commit #1.
- Commit audit (A12): every commit authored by the builder with the sign-off line.
- **Post draft complete**: all template sections, tags `devchallenge` + `hf26challenge`, repo link, screenshots, field-test section, open-innovation section (D1–D4 content).
- Stretch work stops at **8:00 PM CT**. Anything unfinished after that is cut or listed as an open item in the post — it does not delay Saturday.

**Gate (EOD Friday definition of done):** every MUST item D1–D4-content-ready and A1–A12 passes; the only remaining action is publish.

### Phase 10 — Publish (Sat Oct 11)

- Noon: final read of the post; Michael approves.
- **6:00 PM CT: Michael clicks Publish. Hard stop. Feature freeze.** The 11:59 PM PDT deadline is buffer, never the plan.

### Phase 11 — Stretch (conditional)

Only if all MUST gates passed on time, and never after Fri 8 PM CT, in priority order:

- **S1** NWS `skyCover` second source with agreement display.
- **S2** TabPFN clear-sky classifier alongside (never replacing) the deterministic score — only if convincing, since it gates the partner-category entry.
- **S3** bright planets > 15° in window.
- **S4** `.ics` export of top nights and ISS passes.

---

## Aspect coverage matrix

| Aspect | ACs | Phases |
|---|---|---|
| Submission / DEV post | D1–D4 | 5 (start), 6 (evidence), 8 (screenshots), 9 (complete), 10 (publish) |
| Sky & events computation | A3, A4 | 2, 3, 9 |
| Weather & local sensor | A3, A8 | 4, 6 |
| Scoring | A5 | 5 |
| Open-weight AI brief + verifier | A6, A7 | 7 |
| Output & field log | A1, A9 | 1, 6, 8 |
| Offline operation | A1, A10 | 1–5, 9 |
| Privacy & provenance | A11, A12 | 1, 9 |
| Enhancements | S1–S4 | 11 |

## If behind schedule

Cut in this order (from section 8 of the guidelines): S-items → NWS second source → forecast-vs-actual view → ISS direction detail. **Never cut:** the post, the field test, A1, A6, A7. A working app with no published post scores zero.
