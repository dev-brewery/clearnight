# clearnight — Orchestrator Journal

Append-only record of orchestrator decisions, task outcomes, and open items.
Newest entries last. Maintained by the orchestrator role only.

---

## 2026-10-07 — Session 1 (wiring + recovery)

**Context:** Architect docs were produced, then an unauthorized drift toward code was
stopped by the owner; docs were deleted and later restored verbatim. Relationship
rules were established and installed globally (`~/.pi/agent/APPEND_SYSTEM.md`).

**Owner determinations (Michael, this session):**
- Wiring structure **A**: `AGENTS.md` router + `.pi/skills/{architect,builder,orchestrator}/SKILL.md`.
- **Orchestrator = pi (GLM-5.3, thinking max).** Claude Code wrote the initial
  proposition only. Orchestrator owns build success/failure outright.
- **Architect and Builder = GLM-5.3-flash.**
- Executed in `PROJECTGUIDELINES.md` §2 (roles table + wiring note; llm-box paragraph
  now scoped to the in-app model) and `TASKS.md` (builder/sign-off model references).

**Created:** `AGENTS.md`, `.pi/skills/orchestrator/SKILL.md`,
`.pi/skills/architect/SKILL.md`, `.pi/skills/builder/SKILL.md`, this journal.

**Open determinations (owner, unmoved):**
1. Where GLM-5.3 / GLM-5.3-flash run (provider vs llm-box) — affects commit sign-off
   email and whether §2's llm-box note needs further edits.
2. In-app brief model stays Qwen-on-llm-box per guidelines unless redirected.
3. Guidelines §10: sensor hardware/exposure, observing site, repo name — needed before
   the Thu Oct 9 online run; not blocking T01–T15.
4. `AGENTS.md`/`.pi/` not yet in `ARCHITECTURE.md` §2 file map — fold in on next
   architect pass.

**Next:** first build brief (T01) only on owner's go.

---

## 2026-10-07 — Session 1 addendum (model matrix finalized)

**Owner determinations (Michael):**
- Architect: GLM-5.3, thinking **high** (upgraded from GLM-5.3-flash).
- Builder: GLM-5.3-flash, thinking **low** (now defined).
- All three agent-role models run direct against the **z.ai** provider (`zai/glm-5.3`,
  `zai/glm-5.3-flash` confirmed in pi's catalog, both thinking-capable, 1M context).

**Executed:** model lines in all three `.pi/skills/*/SKILL.md` charters; `AGENTS.md`
roles table + activation commands; `PROJECTGUIDELINES.md` §2 rows + wiring note.

**Resolved:** former open item 1 (model hosting) — models run on z.ai, not llm-box.
Commit sign-off stays `Signed-off-by: GLM-5.3-flash (via pi)`; llm-box remains scoped
to the in-app model only.

**Open (renumbered):** 1) in-app brief model stays Qwen-on-llm-box unless redirected;
2) §10 sensor/site/repo-name before the Thu Oct 9 online run; 3) architect to fold
agent-wiring files into the `ARCHITECTURE.md` file map on its next pass.

**Next:** first build brief (T01) only on owner's go.

---

## 2026-10-07 — Decision queue (owner responses, recorded one at a time)

**D1 — Climate sensor (guidelines §10.1). ANSWERED.**
Production: **Home Assistant entity over HTTP** → `http_json` adapter, config-only,
lives in `config.local.toml`, never committed. No third adapter needed.
Deliverable/demo: **`csv` adapter**, with the CSV derived from a public keyless
weather API for the demo site (interpreted: Open-Meteo observation data recorded into
`clearnight/fixtures/sensor.csv` via the T06 `--record-fixtures` maintainer flow —
execution detail for the architect to fold into T06, not a new task).
Consequence: no hardware dependency anywhere in the build. §10.1 closed.

**D2 — Observing site (guidelines §10.2). ANSWERED.**
**A: home backyard — and per Michael, very dark.** Site goes in `config.local.toml`
only, never committed. HA sensor readings are directly representative of the observing
site — the strongest version of the local-sensor story (dew spread + pressure trend are
ground truth, no representativeness caveat, no forecast-fallback needed for Thursday).
Draconids field test (D3) happens at home: zero logistics. A very dark backyard also
strengthens the "touch grass" narrative for the post. §10.2 closed.

**D3 — Repo name (guidelines §10.3). ANSWERED.**
**Confirmed: `dev-brewery/clearnight`.** Availability verified before confirmation:
repo 404 (free), org exists, no duplicate under `brewer-michael`. Name is settled —
no renames after T01. §10.3 closed.

**D4 — In-app brief model. ANSWERED.**
**The app accepts any HTTP endpoint and an optional API key** (owner, Oct 7): LLM config
carries `base_url`, `model`, `api_key` (optional), `timeout_s`; key lives only in
`config.local.toml`. Default endpoint remains owner-configured (llm-box/Qwen);
example config demonstrates the pattern. Strengthens the D4-post "swappable model"
argument: local llama.cpp keyless or any hosted OpenAI-compatible provider, config-only.
Executed: `PROJECTGUIDELINES.md` (§2 endpoint paragraph, §3 in-app bullet, §4 keyless
constraint amended to data-sources-only with the LLM endpoint as the configurable
exception), `ARCHITECTURE.md` (LLMCfg fields, §6 auth-header behavior), `TASKS.md`
(T03 config example, T18 header test). Journal open item 1 closed.

**D5 — Scoring weights. INTENT ANSWERED; numeric translation presented for ratification.**
Owner's words: less concerned about dew; a clear full-Moon night is still glorious;
light breeze is fine but stronger wind would be miserable. Translation proposed to
owner: weights cloud 0.45 / moon 0.15 / transparency 0.15 / dew 0.05 / wind 0.20;
moon term floored at 0.15 so clear moonlit nights stay high; wind curve reshaped to
clamp01((28−w)/13) — unpenalized ≤15 km/h, zeroed ≥28 km/h. Worked examples become
99→~100, 71→~83, 8→~13; A5 orderings preserved. On ratification, architect updates
ARCHITECTURE.md §5 + A5 test examples.

**D5 addendum — owner calibration.** "Overcast, full moon, damp, wind is 100% a night
I stay in bed." Translation v2 presented: wind curve steepened to clamp01((25−w)/10)
(≤15 km/h unpenalized, zeroed ≥25 km/h — 25 km/h appears in the owner's stay-in-bed
example); NEW hard cap — mean cloud ≥85% in the window caps total at 15 (overcast =
stay in bed regardless of other niceties); verdict bands added to the render so scores
read as decisions: ≥85 Prime / 70–84 Worth it / 50–69 Marginal / 35–49 Poor / <35
Stay in bed. Examples: 100 Prime · 83 & 81 Worth it · 8 Stay in bed. Awaiting
ratification.

**D5 RATIFIED (v2, final).** Weights cloud 0.45 / moon 0.15 / transparency 0.15 /
dew 0.05 / wind 0.20; moon_term = 0.15 + 0.85·(1 − illum·up_frac); wind_term =
clamp01((25−w)/10); overcast cap: mean cloud ≥85% ⇒ total ≤15 with reason "overcast";
verdict bands ≥85 PRIME / 70–84 WORTH IT / 50–69 Marginal / 35–49 Poor / <35 STAY
IN BED rendered beside every score; bonuses unchanged. §10/queue closed for D5.

**Architect work order #1 (from D1+D5, next architect session):** rewrite
`ARCHITECTURE.md` §5 to the ratified formula with exact recomputed worked examples
+ verdict-band display spec; update `TASKS.md` T13 acceptance (new examples + two
new test cases: overcast cap, wind cliff at 25 km/h); fold D1 into T06 (sensor.csv
fixture derived from public keyless weather API); fold `AGENTS.md` + `.pi/skills/`
into the §2 file map.

**D6 — Offline fixture strategy. ANSWERED: A, fixture epoch (as designed).**
Committed fixtures cover the fixed demo week (Oct 6–12, 2026, Black Mesa); `--offline`
pins today to the reference date; demo + A1/A10 bit-for-bit reproducible; Draconids
evidence night sits inside the week; `de421.bsp` stays gitignored with recorded
`sky.json` as the offline sky source; new offline weeks via maintainer
`fetch --record-fixtures`. No change needed — architecture stands as written.

**D7 — Verifier strictness. PRESENTED (final queue item).**

**D7 ANSWERED: A, ratified as specified.** Times ±1 min of computed events; numbers
±1 of computed values; names/directions whitelisted to computed facts; ≤2 retries with
allowed values fed back; then the labeled template brief. Grounding guarantee is
absolute — the post's AI story stands on it (A6). No doc changes; architecture §6
stands as written.

---

## 2026-10-07 — Decision queue CLOSED

All seven owner determinations recorded. D1 sensor (HA production / csv-from-public-
API deliverable), D2 site (dark backyard), D3 repo (dev-brewery/clearnight, verified
free), D4 in-app LLM (any endpoint + optional API key — docs executed), D5 scoring
(v2 ratified — architect work order queued), D6 offline (fixture epoch — stands),
D7 verifier (strict — stands). No determinations remain open.

**Next (each on owner's go):** 1) Architect session (`zai/glm-5.3:high` +
`/skill:architect`) executes work order #1 from this journal. 2) Builder session
(`zai/glm-5.3-flash:low` + `/skill:builder`) takes the T01 brief. Timeline anchors
unchanged: online run before dusk Thu Oct 9; MUSTs done Fri; publish Sat 6 PM CT.

---

## 2026-10-07 — Owner determination: hands-off delegation

Owner: "I'm not going to be involved in this process. The onus is on you to structure
the pi architecture so that you successfully manage delegation... you'll be invoking
pi in non-interactive mode with the p flag."
Executed: delegation protocol codified in `AGENTS.md` + orchestrator charter
(`pi -p -a --model … --skill … --name …`; stdout captured; orchestrator verifies each
result against acceptance criteria and journals it). Orchestrator now proceeds
autonomously through architect work order #1 and the T01+ build briefs.
Owner-required, non-delegable, stay flagged: Thu Oct 9 field test (D3), Sat Oct 11
Publish click (D1).
Operational note (orchestrator-level, reversible): builder git identity will be set
repo-local as `GLM-5.3-flash (via pi) <glm-5.3-flash@pi.local>` — A12 requires the
model name in authorship + sign-off; the email token is operational only.

---

## 2026-10-07 — Delegation mechanism validated; architect WO1 executed & accepted

**Mechanism:** three smoke tests. (1) `-a` + auto-discovery → child loaded the WRONG
charter (skills are progressive-disclosure; model chooses what to read).
(2) `--no-skills --skill` → charter not reliably delivered. (3) `@file` attachment →
deterministic correct charter. **Final pattern:**
`pi -p -a --no-skills --model <m> --name <n> @.pi/skills/<role>/SKILL.md "<brief>"`
— codified in AGENTS.md + orchestrator charter. Environment: `python` is 3.7.4,
`py` resolves 3.12.10 (builder must use `py`), git 2.22, pip 25.0.1.

**Architect WO1 — ACCEPTED.** Session `architect-WO1` (zai/glm-5.3:high). ARCHITECTURE.md
§5 rewritten to ratified D5 v2 (weights 0.45/0.15/0.15/0.05/0.20, moon floor, wind
cliff 25, overcast cap, verdict bands) with four worked examples + arithmetic;
T13/T15/T06 acceptances updated (overcast-cap and wind-cliff test cases, verdict-band
rendering, sensor.csv provenance); file map now includes AGENTS.md / JOURNAL.md /
.pi/skills. Consequential amendments accepted: NightScore.verdict, pure
verdict_label(), verifier whitelist for band words. Orchestrator independently
recomputed all four examples (100 PRIME / 83 / 81 WORTH IT / 8 STAY IN BED) and the
cap-binding pair (86%→15, 84%→66) — verified against the ratified spec.

**Next:** builder T01 brief (delegated, pattern above).

---

## 2026-10-07 — Builder T01 executed & accepted (first commit `0a3f9d8`)

Session `builder-T01` (zai/glm-5.3-flash:low). Scaffold committed: pyproject
(skyfield==1.49.0 pinned, entry point, >=3.12), .gitignore (config.local.toml,
cache/, out/, *.bsp — all four verified by orchestrator via check-ignore -v), MIT
LICENSE, package/tests skeleton, stub README. All 16 repo files in the initial
commit; working tree clean; author + sign-off per A12. Orchestrator independently
verified commit, ignores, pip install, clean status.

**Orchestrator ruling (exit-5 deviation):** Python 3.12 `unittest discover` exits 5
when zero tests exist — real behavior, honestly flagged by the builder. Ruling:
acceptance means 'suite runs green'; from T02 onward real tests exist and exit 0 is
required. No placeholder test; T01 stands as-is.

**Next:** T02 (models.py dataclasses + tests).

---

## 2026-10-07 — Builder T02 executed & accepted (commit `658a84e`)

All 11 frozen dataclasses per ARCHITECTURE §4 incl. NightScore.verdict; 23 tests
(frozen/type/naive-UTC/optional-None) — orchestrator re-ran suite (OK, exit 0) and
spot-checked NightScore immutability + verdict field live. Builder correctly excluded
orchestrator's uncommitted JOURNAL.md edits. Convention from T03: builder commits
include JOURNAL.md so the repo carries the log.

**Next:** T03 (config loading), then T04 (cache), T05 (CLI skeleton).

---

## 2026-10-07 — Builder T03 executed & accepted (commit `e0182b9`); tzdata ruling

Config module + example TOML per ARCHITECTURE §4 incl. D4 (optional api_key,
commented, config.local.toml-only note). 39 tests total green; orchestrator re-ran
suite, spot-checked Black Mesa values + api_key guidance. JOURNAL.md now rides task
commits (convention set).

**ORCHESTRATOR RULING — tzdata exception (FLAGGED FOR OWNER RATIFICATION):** Windows
has no system tz database; stdlib zoneinfo requires the `tzdata` package. Builder
surfaced it correctly without scope-creeping pyproject. Ruling: add
`tzdata; platform_system == "Windows"` to pyproject in T04 — zero impact on
Linux/macOS/CI, stdlib-endorsed data-only package. Tension with guidelines §4
("dependencies limited to skyfield") acknowledged: recorded here as an interim
exception under delegation authority; guidelines text left untouched pending owner
ratification (removal = one-line revert if rejected).

**Next:** T04 (disk cache) + tzdata marker.

---

## 2026-10-07 — Owner directive: progress tracker + commit cadence

Owner: "As the orchestrator it is of paramount importance that you update the
progress tracker as you go and ensure commits are done in a predictable cadence."
Executed: progress tracker added at the top of IMPLEMENTATIONPLAN.md (per-task status,
commits, flags, phase-gate position); cadence codified in orchestrator charter and
AGENTS.md — tracker + journal updated at every acceptance, riding the next builder
commit (builder remains the only committer, A12).

## 2026-10-07 — Builder T04 executed & accepted (commit `3d5e362`)

Cache per ARCHITECTURE §4: traversal-guarded keys, mtime staleness, None = never
expires. 47 tests green; tzdata marker added per ruling with journal-cited comment.
Orchestrator verified live (guard '../evil','a/b',''; roundtrip). Builder self-corrected
a test expectation against spec (good charter behavior).

**Next:** T05 (CLI skeleton), then T06 (fixtures). Phase 1 gate: T05–T06.

---

## 2026-10-07 — Builder T05 executed & accepted (commit `94c6191`); T04 flake found

CLI skeleton: plan (offline/config/nights, placeholder output), log/fetch stubs,
main()->int. 54 tests. Orchestrator verified live (plan --offline exit 0 + output,
log stub, --nights 99 exit 2 — orchestrator's first recheck piped through tail and
misread exit 0; recheck without pipe confirmed 2). Tracker/journal/AGENTS rode the
commit as designed.

**Flake caught at 18:15 UTC:** `test_cache.test_fresh_within_age` failed post-accept
(passed at commit) — wall-clock race in the test, not a code defect. Micro-brief T04a
issued: deterministic mtimes via os.utime, suite run ×5. Standing lesson recorded:
timing tests must pin mtimes, never race the clock.

**T06 correction (orchestrator):** TASKS.md fixture reference_date 2026-10-06 is one
day off — today is Tue 2026-10-07, so demo week = Oct 7–13 (covers Draconids Oct 9).
Manifest reference_date := 2026-10-07. sky.json recording deferred to T07 (needs
sky.py); T06 records manifest/forecast/TLE/sensor + epoch pinning.

**Next:** T04a (de-flake), then T06.

---

## 2026-10-07 — Builder T04a executed & accepted (commit `9dd449d`)

Cache timing tests rewritten deterministically (pinned mtimes via os.utime, no
wall-clock races); full suite 5× consecutive green, identical counts. Orchestrator
re-ran twice to confirm. Convention added: long delegation briefs are written to
`out/brief-<task>.md` (gitignored) and passed as @file — avoids shell quoting
fragility (one transient exit-127 on an inline brief triggered this).

**Next:** T06 with orchestrator corrections (reference_date 2026-10-07; sky.json
deferred to T07; live recording run included).

---

## 2026-10-07 — Builder T06 executed & accepted (commit `6ee7e5a`) — PHASE 1 GATE COMPLETE

Fixtures committed: manifest (ref 2026-10-07, sky_json deferred), forecast.json
(11 hourly vars, Oct 6–14, equal lengths), tle.txt (ISS ZARYA 3-liner), sensor.csv
(43 rows, exact header). fetch --record-fixtures live-ran exit 0. resolve_today
offline pinning verified live by orchestrator. 60 tests green. Deviation (self-caught,
accepted): first test draft used bare functions; rewritten to unittest.TestCase.

**Next:** T07 sky engine + sky.json recording. Phase 2 begins.

---

## 2026-10-07 — Builder T07 executed & accepted (commit `8d2be02`) — Phase 2 core done

sky.py per ARCHITECTURE §4 (bsp cached + gitignored; SkyUnavailable offline guard;
sampling helpers take altitude callbacks for offline tests). sky.json recorded live:
7 nights; orchestrator verified Oct 9 window 01:50–11:25 UTC (9.58 h — plausible
for 36.85°N early Oct) and Moon 0.26% New, never up, max_alt −18° — D3 Draconids
precondition met with margin. 72 tests green offline. Builder kept recording script
in gitignored out/ (flagged, accepted). Tromsø midsummer case auto-skips without bsp.

**Checkpoint (orchestrator):** 9 accepted items today (WO1, T01–T07, T04a), one
commit each, A12 sign-offs verified every time, suite 0 → 72 tests, tree clean at
every acceptance. Next: T08 meteors, T09 ISS, then scoring (T13) and the offline
plan (T14 = A1).

---

## 2026-10-07 (late) — Owner directive: deliver by EOD Friday; T08 accepted

Owner: "You will work this until you deliver the deliverable per my criteria by EOD
Friday." Orchestrator continues the loop autonomously through T22 + post draft;
owner-required dates unchanged (Thu field test, Sat publish).

**Builder T08 executed & accepted (commit `4fe5d43`).** 12-shower IMO table +
meteors.py; 84 tests. Orchestrator verified Draconids record and the ±1-day peak
boundary live (Oct 8/9/10 True; Oct 7 False; Oct 11 inactive). Deviations accepted:
radiant_up_hours defaults 0.0 per models (architect wins over brief); year-wrap
covered synthetically. Convention confirmed: orchestrator artifacts ride the NEXT
task commit (one-commit lag by design).

**Next:** T09 ISS passes.

---

## 2026-10-07 (late) — Builder T09 executed & accepted (commit `d3ff041`) — Phase 3 complete

iss.py: TLE 24 h cache with fresh→stale→fixture fallback chain (provenance carried);
30 s sampling; cylindrical shadow test cross-checked against skyfield is_sunlit;
8-point directions; window clamp + dedup. Demo-week recording: exactly ONE visible
pass (Oct 13, 11:21–11:25 UTC dawn, 19.7°, S→SE→E) — sparse but real; builder
cross-checked no samples were over-filtered. Online plans use fresh TLE (T16), so
Thursday's real plan may differ. 98 tests green. Phase 3 (events) COMPLETE.

**Next:** Phase 4 — T10 forecast, T11 sensors, T12 conditions; then T13 scoring.

---

## 2026-10-07 (late) — Builder T10 executed & accepted (commit `c3701b6`)

Forecast client per ARCHITECTURE §4: pinned 9-var URL, 15 s timeout, 1 h cache,
fresh→stale→fixture chain with range clipping. 112 tests. Orchestrator live check:
48 fixture hours fetched offline; Oct 9 dark window sliced to 10 h with MEAN CLOUD
0.0% — the demo fixture records a perfectly clear Draconids night. A8-relevant A11
note: fixture is demo-site data only.

**Next:** T11 sensor adapters, T12 conditions.
