# clearnight: Build Tasks

Ordered, small, testable tasks for the builder (pi + GLM-5.3-flash). Rules from `PROJECTGUIDELINES.md` §7 apply to every task:

- One task, one commit. Tests written in the same task as the code. Network always mocked in tests.
- Commit format: one-line summary, short body, then `Signed-off-by: GLM-5.3-flash (via pi)`.
- Never commit real coordinates, personal URLs, or secrets. Demo site only: Black Mesa State Park, OK (36.85 N, −102.88 W).
- Blocked? Stop and report. Don't paper over.

Each task advances the listed acceptance criteria (IDs in `PROJECTGUIDELINES.md` §6). Dependencies are implicit in the ordering; never start a task whose predecessor's acceptance test fails. Target: `plan --offline` (A1) fully works by end of **T15**, Wednesday.

| Phase (IMPLEMENTATIONPLAN.md) | Tasks |
|---|---|
| 1 Skeleton | T01–T06 |
| 2 Sky | T07 |
| 3 Events | T08–T09 |
| 4 Weather/sensor | T10–T12 |
| 5 Scoring | T13 |
| 6 Online + field | T14–T17 |
| 7 AI brief | T18–T19 |
| 8 Render/log/docs | T20–T21 |
| 9 QA/post | T22 |
| 11 Stretch | S1–S4 |

---

### T01 — Repo scaffold
- **Goal:** initialize the project exactly per the file map (§2 ARCHITECTURE.md).
- **Files:** `pyproject.toml` (pkg metadata, pinned `skyfield`, `clearnight` entry point), `.gitignore` (**must include `config.local.toml`, `cache/`, `out/`, `*.bsp`**), `LICENSE` (MIT), `clearnight/__init__.py`, `clearnight/sensor/__init__.py`, `tests/__init__.py`. Run `git init`, first commit.
- **Acceptance:** `pip install -e .` succeeds; `python -m unittest discover -s tests` runs (0 tests, OK); `git check-ignore config.local.toml cache out x.bsp` all ignored.
- **ACs:** A10 (start), A11.

### T02 — Dataclasses
- **Goal:** all frozen dataclasses from ARCHITECTURE.md §4 in one module.
- **Files:** `clearnight/models.py`, `tests/test_models.py`.
- **Acceptance:** every dataclass constructs, is frozen (mutation raises), and rejects wrong types on required fields; tests pass.
- **ACs:** foundation for A3.

### T03 — Config loading
- **Goal:** TOML config load/merge/validate with example file.
- **Files:** `clearnight/config.py`, `config.example.toml` (Black Mesa site, `nights = 7`, `cache_dir`, `out_dir`, sensor examples for both adapters, llm `base_url = "<from .env / config.local.toml - never committed>"`, `model`, `timeout_s`, commented `api_key` note pointing to `config.local.toml`), `tests/test_config.py`.
- **Acceptance:** example config loads and validates; a local TOML overrides site; invalid lat/lon/adapter kind raise `ConfigError` with clear messages; no test reads `config.local.toml`.
- **ACs:** A2, A11.

### T04 — Disk cache
- **Goal:** age-aware cache keyed by filename.
- **Files:** `clearnight/cache.py`, `tests/test_cache.py`.
- **Acceptance:** put/get roundtrip; `fresh()` true within max-age, false after (mtime backdated); missing key returns None. All via temp dirs.
- **ACs:** A1, A2.

### T05 — CLI skeleton
- **Goal:** entry point with all subcommands as runnable stubs.
- **Files:** `clearnight/__main__.py`, `tests/test_cli.py`.
- **Acceptance:** `python -m clearnight plan --offline` exits 0 printing a placeholder plan; `log`/`fetch` stubs print their intent; `--config` and `--nights` flags parse. Test invokes via `subprocess` from a temp cwd.
- **ACs:** A1 (partial).

### T06 — Demo fixtures and epoch pinning
- **Goal:** committed offline dataset for the demo week.
- **Files:** `clearnight/fixtures/` (`manifest.json` with `reference_date = 2026-10-06`, site, generated-by note; `forecast.json`, `tle.txt`, `sky.json`, `sensor.csv`), plus a `--record-fixtures` mode on `fetch` that populates them from live calls (maintainer-only; run once by Michael/builder with network).
- **Note (D1):** `sensor.csv` is derived from a public keyless weather API — Open-Meteo observation data for the demo site — recorded via `fetch --record-fixtures`. It is site-derived synthetic data, not a private sensor export, so it is safe to commit.
- **Acceptance:** offline "today" resolves to `reference_date` when `--offline`; each fixture parses with its module's loader (added in T07–T12); `fetch --record-fixtures` regenerates all four files. Committed files contain only Black Mesa data; `sensor.csv` holds only Open-Meteo-derived observations.
- **ACs:** A1, A10, A11.

### T07 — Sky engine
- **Goal:** dark windows, Moon info, radiant altitudes via skyfield.
- **Files:** `clearnight/sky.py`, `tests/test_sky.py` (asserts against values recorded in `sky.json` fixture).
- **Acceptance:** for the demo week: Black Mesa dark windows ~1:40 h long bracket around local midnight SDT-equivalent (exact values from fixture); Oct 9 Moon illumination < 2% (Draconids precondition, D3); empty window at high-latitude site returns empty list; Moon never-up-in-window yields `up_fraction 0`, rise/set `None`. Uses cached `de421.bsp`; offline test path reads `sky.json`.
- **ACs:** A3, A4 (basis).

### T08 — Meteor showers
- **Goal:** bundled IMO-derived table and per-night events.
- **Files:** `data/meteor_showers_2026.json` (each record: name, peak UTC, active start/end, ZHR, radiant RA/Dec, parent; file header records IMO calendar source URL), `clearnight/meteors.py`, `tests/test_meteors.py`.
- **Acceptance:** Draconids present with peak Oct 8–9 UTC window; `events_for_night` marks Oct 9 (America/Chicago) as peak night; radiant-up hours computed for the demo site; out-of-season shower never returned; malformed JSON raises a clear error.
- **ACs:** A3, A5 (bonus basis).

### T09 — ISS passes
- **Goal:** TLE cache + visible-pass prediction.
- **Files:** `clearnight/iss.py`, `tests/test_iss.py` (TLE from fixture).
- **Acceptance:** passes filtered to observer-dark + ISS-sunlit + max_alt > 10°; each result has start/max/end times, max_alt, 8-point directions; fresh-cache path and 24 h-stale path both tested (mtime manipulation); matches `sky.json`-recorded pass set for the demo week.
- **ACs:** A3, A4 (basis).

### T10 — Forecast client
- **Goal:** Open-Meteo hourly fetch, validation, window slicing.
- **Files:** `clearnight/forecast.py`, `tests/test_forecast.py`.
- **Acceptance:** builds the exact URL with pinned variable list (ARCHITECTURE §4 types); parses fixture reply into `HourWeather` (missing fields → None); slices to a window inclusively; 15 s timeout; cache-hit path skips network (mocked urlopen asserts no call when fresh); offline+no-cache falls back to fixture.
- **ACs:** A2, A3.

### T11 — Sensor adapters
- **Goal:** adapter interface, CSV and HTTP-JSON implementations, factory.
- **Files:** `clearnight/sensor/__init__.py` (protocol + `make_adapter`), `clearnight/sensor/csv_adapter.py`, `clearnight/sensor/http_json.py`, `tests/test_sensor.py`.
- **Acceptance:** CSV adapter reads `fixtures/sensor.csv` within `hours`; malformed rows skipped with warning; http_json maps configured fields, 10 s timeout, error → empty list (never crash); switching adapters is config-only (test constructs via `make_adapter` from two TOML snippets) — A8.
- **ACs:** A8.

### T12 — Conditions
- **Goal:** dew risk, pressure trend, forecast-vs-actual.
- **Files:** `clearnight/conditions.py`, `tests/test_conditions.py`.
- **Acceptance:** spread ≥ 8 → "low", 3–8 → "moderate", < 3 → "high"; 3 h trend from ≥ 2 pressure readings classifies rising/falling/flat with hPa delta; forecast-vs-actual string compares latest reading to current forecast hour; empty readings → "unknown" states, no crash.
- **ACs:** A3.

### T13 — Scoring
- **Goal:** pure, deterministic scoring with full breakdown.
- **Files:** `clearnight/score.py`, `tests/test_score.py`.
- **Acceptance:** the four ARCHITECTURE §5 worked examples produce 100 / 83 / 81 / 8 exactly; **overcast cap**: mean cloud 86% with §5's cap-binding variant scores 15 with reason `"overcast"`, while 84% scores 66 uncapped — the cap must bind even when event bonuses push past it; **wind cliff**: wind 15 km/h ⇒ wind_term 1.0, 20 km/h ⇒ 0.5, 25 km/h ⇒ 0.0; verdict bands: 85→PRIME, 84→WORTH IT, 70→WORTH IT, 69→Marginal, 50→Marginal, 49→Poor, 35→Poor, 34→STAY IN BED; dew spread 6→1 °C lowers the score; adding a peak shower with radiant-up raises it (A5); empty-window and no-weather rules return 0 with reasons; `rank` sorts descending with earlier-date tiebreak.
- **ACs:** A5.

### T14 — Assemble nights + offline plan (A1 complete)
- **Goal:** wire modules into `plan --offline` end to end on fixtures.
- **Files:** `clearnight/__main__.py` (plan pipeline), `tests/test_plan_offline.py`.
- **Acceptance:** from a clean checkout with example config: `python -m clearnight plan --offline` writes `out/plan.html` and prints a text summary without network (socket blocked in test) and without LLM; nights ranked by score; each night shows window, Moon, cloud summary, dew risk, score + breakdown, showers (peak marked), ISS passes — A3 fields all present; brief is the labeled template — A7 offline case.
- **ACs:** A1, A3, A7 (offline half).

### T15 — HTML render
- **Goal:** red-on-black one-page plan, phone- and print-friendly.
- **Files:** `clearnight/render.py`, `tests/test_render.py`.
- **Acceptance:** HTML is a single self-contained file (inline CSS, no external requests); body colors dark background / #ff3b30-spectrum text; all A3 fields per night; every score rendered with its verdict band beside it (PRIME / WORTH IT / Marginal / Poor / STAY IN BED) in both HTML and text (§5); template-brief label rendered when `source == "template"`; text summary ≤ 80 cols; HTML escapes all data-driven strings.
- **ACs:** A1 (polish), A3, A7.

### T16 — Online path
- **Goal:** real forecast/TLE/sensor/ephemeris with cache-through and fallbacks.
- **Files:** `clearnight/__main__.py`, `clearnight/forecast.py`/`iss.py`/`sky.py` wiring (no behavior changes offline), `tests/test_online_wiring.py` (mocked urlopen).
- **Acceptance:** `python -m clearnight plan` (no `--offline`) populates `cache/`, then a second run within max-age performs no network calls for forecast/TLE; any single source failing falls back per ARCHITECTURE §7 and still renders with a footer note; site comes from `config.local.toml` when present.
- **ACs:** A2, A3.

### T17 — Field log
- **Goal:** record outcomes, show them beside predictions.
- **Files:** `clearnight/fieldlog.py`, `clearnight/__main__.py` (`log` subcommand), `tests/test_fieldlog.py`.
- **Acceptance:** `python -m clearnight log --date 2026-10-09 --went-out --clearness 4 --meteors 7 --iss-seen --notes "..."` appends one JSONL line to `out/fieldlog.jsonl`; next plan shows that entry next to the Oct 9 prediction; duplicate date appends (latest wins on match); unknown flags rejected.
- **ACs:** A9, D3 (evidence).

### T18 — Brief generation
- **Goal:** prompt build + OpenAI-compatible call to llm-box.
- **Files:** `clearnight/brief.py`, `tests/test_brief.py` (canned replies, mocked urlopen).
- **Acceptance:** prompt contains only computed values for the top-3 nights (snapshot test on fixture nights); request JSON has temperature 0.2, max_tokens 400, timeout from config; `Authorization: Bearer` header present when a key is configured, absent when not; one transport retry; unreachable endpoint returns template `BriefResult(source="template")` without raising.
- **ACs:** A7, A6 (basis).

### T19 — Verifier and retry loop
- **Goal:** claim extraction, checking, retries, labeled fallback.
- **Files:** `clearnight/verify.py`, `tests/test_verify.py`.
- **Acceptance:** clean canned brief → 0 violations; brief with an invented time and a wrong percentage → both flagged with messages naming allowed values; wrong shower name and bad compass direction flagged; "tomorrow" day-word checked against plan date; retry loop re-prompts ≤ 2 times including violation list; exhausting retries → labeled template (A6, A7).
- **ACs:** A6, A7.

### T20 — Wire brief + plan integration
- **Goal:** real LLM brief in the online plan, verified.
- **Files:** `clearnight/__main__.py`, `tests/test_plan_integration.py`.
- **Acceptance:** online plan for top-3 nights calls brief→verify and renders the surviving text with `source: llm`; forced-verify-failure test renders the labeled template; offline plan never attempts the LLM.
- **ACs:** A2, A6, A7.

### T21 — README and screenshots
- **Goal:** user-facing docs and post assets.
- **Files:** `README.md` (install, configure both sensor kinds, run online/offline, screenshot), screenshots of offline plan HTML + field-log comparison into `docs/` (generated from demo fixtures only).
- **Acceptance:** a fresh-clone user can follow README to reproduce A1 in ≤ 5 commands; screenshots show no local data; README states privacy model and data sources.
- **ACs:** D2, A11.

### T22 — QA sweep, audits, accuracy check
- **Goal:** prove the MUST bar before Friday freeze.
- **Files:** `tests/test_accuracy.py`, any fix commits.
- **Acceptance:** full suite green offline; A4 cross-check fixture (Black Mesa, Draconids night: Sun set/astronomical twilight, Moon rise/set/illum, one ISS pass vs. timeanddate.com / Heavens-Above, ±5 min / ±5°) passes and the check method is documented; `git log --all` + history grep shows zero home coordinates / sensor URLs / secrets and every commit carries the sign-off line (A11, A12); `plan --offline` re-verified from a pristine clone in a temp dir.
- **ACs:** A4, A10, A11, A12, D1-readiness.

---

## Stretch tasks (only after T22 passes, never after Fri Oct 10, 8:00 PM CT)

- **S1** NWS `api.weather.gov` gridpoint `skyCover` second source + agreement display in plan and HTML. Files: `clearnight/forecast.py`, `render.py`, tests.
- **S2** TabPFN clear-sky classifier: features = forecast cloud layers/humidity + pressure trend + sensor spread; labels from Open-Meteo historical or field log; probability shown **alongside** the deterministic score. Adds pinned `tabpfn` dependency. Only if it works convincingly.
- **S3** Bright planets > 15° in dark window (skyfield, same ephemeris): name, rise/set, max alt per night.
- **S4** `.ics` export of top nights + ISS passes (`out/plan.ics`).
