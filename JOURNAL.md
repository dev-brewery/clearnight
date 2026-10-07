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
