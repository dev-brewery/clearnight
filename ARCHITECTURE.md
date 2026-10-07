# clearnight: Architecture

Produced by the architect role from `PROJECTGUIDELINES.md`. If code and this file disagree, `PROJECTGUIDELINES.md` wins; then this file; then code.

---

## 1. Principles

1. **The post is the deliverable.** Every design choice favors demoable, offline-testable, screenshot-friendly output on the critical path (see `IMPLEMENTATIONPLAN.md`).
2. **Deterministic core, generative skin.** All numbers (times, altitudes, score) come from pure computation. The LLM only wordsmiths computed facts, and its output is verified against them.
3. **Offline first.** The whole app and test suite run without network from committed fixtures. Network is an enhancement, never a requirement.
4. **Privacy by structure.** Local config is gitignored from commit #1; the committed example uses Black Mesa State Park, OK (36.85 N, −102.88 W, America/Chicago).
5. **Small modules, one job each** (file map, §2).

Stdlib-first: `tomllib` (config), `urllib` (HTTP), `zoneinfo` (timezones), `unittest` (tests), `json`/`html` (data/render). The only pinned runtime dependency is `skyfield` (brings `numpy`). Python 3.12.

---

## 2. Final file map

```
clearnight/
├── PROJECTGUIDELINES.md        owner-maintained source of truth
├── ARCHITECTURE.md             this file
├── TASKS.md                    ordered build tasks
├── IMPLEMENTATIONPLAN.md       calendar phases and gates
├── AGENTS.md                   agent router: roles, activation, delegation protocol
├── JOURNAL.md                  orchestrator journal: decisions, outcomes, open items
├── README.md                   install, configure, run, screenshot
├── LICENSE                     MIT
├── pyproject.toml              metadata, pinned skyfield, entry point
├── config.example.toml         Black Mesa demo site + both sensor adapters
├── .gitignore                  config.local.toml, cache/, out/, *.bsp
├── clearnight/
│   ├── __init__.py
│   ├── __main__.py             CLI: plan | log | fetch; global --offline
│   ├── config.py               load/merge/validate TOML config
│   ├── models.py               all dataclasses (see §4)
│   ├── cache.py                disk cache with per-key max-age
│   ├── sky.py                  dark windows, Moon, radiant altitudes (skyfield)
│   ├── iss.py                  TLE fetch/cache + visible pass prediction
│   ├── meteors.py              shower table load + per-night events
│   ├── forecast.py             Open-Meteo client, sliced to dark windows
│   ├── conditions.py           dew risk, pressure trend, forecast-vs-actual
│   ├── score.py                pure scoring (§5)
│   ├── brief.py                LLM prompt build + OpenAI-compatible call
│   ├── verify.py               claim extraction, checking, retry/fallback
│   ├── render.py               HTML plan (red-on-black) + text summary
│   ├── fieldlog.py             JSONL append/read + match to predictions
│   ├── fixtures/               committed demo fixtures + manifest.json
│   │   ├── manifest.json       reference_date, site, generation info
│   │   ├── forecast.json       Open-Meteo reply for demo site, fixture week
│   │   ├── tle.txt             ISS TLE lines
│   │   ├── sky.json            recorded dark windows/moon/radiants, fixture week
│   │   └── sensor.csv          climate readings (Open-Meteo observations, demo site; §7)
│   └── sensor/
│       ├── __init__.py         Reading, SensorAdapter protocol, factory
│       ├── csv_adapter.py      read_recent(hours) from CSV
│       └── http_json.py        GET URL, map fields via config
├── data/
│   └── meteor_showers_2026.json   IMO-derived; source URL recorded inside
├── .pi/
│   └── skills/                    agent-role charters (repo wiring; not packaged)
│       ├── architect/SKILL.md         architect charter: owns ARCHITECTURE.md + TASKS.md
│       ├── builder/SKILL.md           builder charter: writes all code, tests, commits
│       └── orchestrator/SKILL.md      orchestrator charter: briefs, verifies, journals
├── tests/
│   ├── fixtures/               canned LLM replies, edge-case inputs
│   └── test_*.py               one per module
└── out/                        generated plans (gitignored)
```

The one change from the guidelines' proposed map: demo fixtures live in `clearnight/fixtures/` (package data) so `plan --offline` works from a fresh clone without importing from `tests/`. `tests/fixtures/` keeps test-only material (canned LLM responses, malformed inputs). Agent-wiring files (`AGENTS.md`, `JOURNAL.md`, `.pi/skills/`) are tracked in the map per guidelines §5: they steer how the repo gets built, not what ships in the package.

---

## 3. Data flow

```
config (config.local.toml > config.example.toml)
   │  Site(lat, lon, elev, tz), SensorConfig, LLMConfig, nights
   ▼
sky.py ──(cache: de421.bsp)──► DarkWindow[] + MoonInfo[] + radiant altitudes
   │
   ├─► forecast.py ──(cache: Open-Meteo, 1 h)──► HourWeather[] sliced per window
   ├─► sensor/*.py ──(csv fixture | http_json)──► Reading[] ─► conditions.py
   │                                                (dew spread, pressure trend,
   │                                                 forecast-vs-actual)
   ├─► meteors.py ──(data/meteor_showers_2026.json)──► ShowerEvent[]
   └─► iss.py ──(cache: CelesTrak TLE, 24 h)──► ISSPass[]
   │
   ▼
models.Night (assembled in __main__.plan)
   ▼
score.py (pure) ──► NightScore(total, per-factor breakdown)
   ▼
rank, take top 3 ──► brief.py ──► LLM on llm-box ──► verify.py
   │                                          (retry ≤2, else labeled template)
   ▼
fieldlog.py (past entries ↔ predictions) ──► render.py ──► out/plan.html + stdout text
```

Times are UTC internally; rendered in the site timezone via `zoneinfo`.

---

## 4. Module contracts

Types in `models.py`; only notation shown here. All public functions are pure or cache/IO-boundary only.

```python
# config.py
class ConfigError(Exception): ...
def load_config(path: str | None = None) -> Config
  # merges config.local.toml over config.example.toml; validates ranges;
  # Config: site: Site, sensor: SensorCfg, llm: LLMCfg, nights: int = 7,
  #         cache_dir: Path = "cache", out_dir: Path = "out"
  # LLMCfg: base_url, model, api_key (optional; config.local.toml only), timeout_s

# models.py  (all frozen dataclasses, UTC datetimes)
Site(name, lat, lon, elevation_m, tz_name)
HourWeather(time_utc, cloud_total_pct, cloud_low_pct, cloud_mid_pct, cloud_high_pct,
            rh_pct, dew_point_c, temperature_c, visibility_m, wind_kmh)   # None-able
DarkWindow(start_utc, end_utc)                    # Sun < -18°
MoonInfo(phase_name, illumination_frac, rise_utc, set_utc, up_fraction, max_alt_deg)
ShowerEvent(name, peak_utc, active_start, active_end, zhr, radiant_ra_deg,
            radiant_dec_deg, parent_body, radiant_up_hours, is_peak_night)
ISSPass(start_utc, max_utc, end_utc, max_alt_deg, start_dir, max_dir, end_dir)  # dirs: 8-point compass
Conditions(dew_spread_c, dew_risk: Literal["low","moderate","high"],
           pressure_trend: Literal["rising","falling","flat","unknown"], trend_hpa_3h,
           forecast_vs_actual: str | None)
Night(date_local, dark: DarkWindow, moon: MoonInfo, weather: list[HourWeather],
      conditions: Conditions, showers: list[ShowerEvent], iss_passes: list[ISSPass],
      score: NightScore | None)
NightScore(total, verdict: Literal["PRIME","WORTH IT","Marginal","Poor","STAY IN BED"],
           cloud_term, moon_term, transparency_term, dew_term, wind_term,
           base, meteor_bonus, iss_bonus, event_bonus, reasons: list[str])
Reading(timestamp_utc, temperature_c, humidity_pct, pressure_hpa, dew_point_c)  # all but timestamp None-able
FieldLogEntry(date_local, went_out: bool, clearness: int /*0-5*/, meteors_counted,
              iss_seen: bool, notes: str, recorded_utc)

# cache.py
class Cache:
    def __init__(self, root: Path): ...
    def path(self, key: str) -> Path
    def get(self, key: str, max_age_s: int | None) -> bytes | None      # None ⇒ stale/absent
    def put(self, key: str, data: bytes) -> None
    def fresh(self, key: str, max_age_s: int) -> bool

# sky.py
def load_ephemeris(cache: Cache, offline: bool) -> Ephemeris        # de421.bsp, download-once
def dark_windows(site: Site, start_date: date, nights: int, eph: Ephemeris) -> list[DarkWindow]
def moon_info(site: Site, window: DarkWindow, eph: Ephemeris) -> MoonInfo
def radiant_up_hours(site: Site, window: DarkWindow, ra_deg: float, dec_deg: float, eph: Ephemeris) -> float

# meteors.py
def load_showers(path: Path = data/meteor_showers_2026.json) -> list[ShowerEvent]  # without per-night fields
def events_for_night(showers, night_date: date) -> list[ShowerEvent]               # fills radiant_up_hours, is_peak_night

# iss.py
def load_tle(cache: Cache, offline: bool) -> list[str]             # 3-line groups; 24 h cache; fixture fallback
def visible_passes(site: Site, windows: list[DarkWindow], tle: list[str]) -> list[ISSPass]
  # keep only passes: observer in darkness, ISS sunlit, max_alt > 10°

# forecast.py
def fetch_hourly(site: Site, start: datetime, hours: int, cache: Cache, offline: bool) -> list[HourWeather]
def slice_to_window(weather: list[HourWeather], window: DarkWindow) -> list[HourWeather]

# sensor/
class SensorAdapter(Protocol):
    def read_recent(self, hours: int = 6) -> list[Reading]: ...
def make_adapter(cfg: SensorCfg) -> SensorAdapter                  # kind: "csv" | "http_json"
class CSVAdapter(SensorAdapter):   __init__(path: Path)
class HttpJsonAdapter(SensorAdapter): __init__(url, field_map: dict, timeout_s=10)

# conditions.py
def assess(readings: list[Reading], window_weather: list[HourWeather]) -> Conditions
def dew_risk_label(spread_c: float) -> str        # >=8 low, 3-8 moderate, <3 high

# score.py   (PURE — no IO, no LLM)
def score_night(window: DarkWindow, moon: MoonInfo, weather: list[HourWeather],
                dew_spread_c: float, showers: list[ShowerEvent],
                iss_passes: list[ISSPass]) -> NightScore
def verdict_label(total: int) -> str              # verdict bands (§5); sets NightScore.verdict
def rank(nights: list[Night]) -> list[Night]      # descending total, tie ⇒ earlier date

# brief.py
def build_prompt(nights: list[Night]) -> list[dict]                 # messages for the API
def generate_brief(nights: list[Night], llm: LLMCfg, timeout_s=30) -> BriefResult
  # BriefResult(text, source: "llm" | "template", attempts: int, violations: list[str])

# verify.py
def extract_claims(text: str) -> Claims                            # times, numbers+units, names, directions, day-words
def check_claims(claims: Claims, nights: list[Night]) -> list[str] # human-readable violations
def verified_brief(nights, llm, max_retries=2) -> BriefResult      # retry loop + labeled template fallback

# render.py
def render_html(plan: Plan) -> str        # red-on-black, one page, print + phone CSS
def render_text(plan: Plan) -> str        # terminal summary
  # every night's score renders with its verdict band beside it (§5), in both outputs
  # Plan: site, generated_utc, nights (ranked), brief: BriefResult, log_matches: list[(Night, FieldLogEntry|None)]

# fieldlog.py
def append_entry(out_dir: Path, entry: FieldLogEntry) -> None      # out/fieldlog.jsonl
def read_entries(out_dir: Path) -> list[FieldLogEntry]
def match_to_nights(nights: list[Night], entries: list[FieldLogEntry]) -> list[tuple[Night, FieldLogEntry | None]]

# __main__.py
# python -m clearnight plan [--offline] [--config PATH] [--nights N]
# python -m clearnight log --date YYYY-MM-DD [--went-out] [--clearness 0-5]
#                         [--meteors N] [--iss-seen] [--notes TEXT]
# python -m clearnight fetch            # refresh cache (forecast+TLE+bsp), print status
```

---

## 5. Scoring formula (exact)

`score_night` is pure and deterministic. All means are arithmetic over dark-window hours with non-`None` values. `clamp01(x) = min(1, max(0, x))`.

```
cloud_term = (100 − mean(cloud_total_pct)) / 100
moon_term  = 0.15 + 0.85 × (1 − illumination_frac × up_fraction)
                                                          # up_fraction: share of window hours Moon alt > 0°
                                                          # 0.15 floor: a clear full-Moon night is still glorious
hum_term   = clamp01((85 − mean(rh_pct)) / 45)            # rh ≤ 40 ⇒ 1, rh ≥ 85 ⇒ 0
vis_term   = clamp01((mean(visibility_m) − 5000) / 19000) # vis ≥ 24 km ⇒ 1, ≤ 5 km ⇒ 0
trans_term = hum_term × vis_term
dew_term   = clamp01((dew_spread_c − 2) / 8)              # spread ≤ 2 °C ⇒ 0, ≥ 10 °C ⇒ 1
wind_term  = clamp01((25 − mean(wind_kmh)) / 10)          # ≤ 15 km/h ⇒ 1 (breeze is free), ≥ 25 km/h ⇒ 0

base = 100 × (0.45·cloud + 0.15·moon + 0.15·trans + 0.05·dew + 0.20·wind)

meteor_bonus = 6  if any shower peaks within ±1 day of the night AND radiant_up_hours ≥ 2
             else 2  if any active shower has radiant_up_hours ≥ 2
             else 0                                       # max over showers, not sum
iss_bonus    = min(4, 2 × count(iss_passes with max_alt ≥ 45°))
event_bonus  = min(10, meteor_bonus + iss_bonus)

total = round(clamp01(base/100 + event_bonus/100) × 100)  # i.e. clamp(base + event_bonus, 0, 100)

# HARD CAP — overcast: mean(cloud_total_pct) ≥ 85 ⇒ total = min(total, 15)
# and reason "overcast" is recorded. Overcast is a stay-in-bed night regardless
# of Moon, dew, wind, or events.
```

Weights, curves, cap, and bands are **owner-ratified (journal D5, Oct 7 2026)**, translating stated intent into numbers: dew matters least (0.05 — "less concerned about dew"); the Moon dings but never kills (0.15 weight with a 0.15 floor — "a clear full-Moon night is still glorious"); wind is the second dealbreaker after cloud (0.20, zeroed at 25 km/h — "light breeze fine, stronger wind miserable"); and overcast caps everything ("overcast, full Moon, damp, wind is 100% a night I stay in bed").

**Verdict bands** — a pure function of the final `total` (after event bonus, rounding, and cap), stored on `NightScore.verdict` and rendered beside every score by `render.py` (§4):

| total | verdict |
|---|---|
| ≥ 85 | PRIME |
| 70–84 | WORTH IT |
| 50–69 | Marginal |
| 35–49 | Poor |
| < 35 | STAY IN BED |

`dew_spread_c` input is chosen by the caller (keeps `score.py` pure): the sensor-projected spread from `conditions.assess()` when readings exist, else the forecast spread (mean temperature − mean dew point over the window).

**Empty / missing data rules (deterministic):**
- No astronomical darkness (empty window, e.g. summer at high latitude): `total = 0`, reason `"no astronomical darkness"`.
- No weather hours at all: `total = 0`, reason `"no forecast data"`.
- Some hours missing a variable: mean over the non-`None` values; if all `None` for a term's inputs, that term uses 0 and a reason is recorded.
- The overcast cap is evaluated on the same mean as `cloud_term`; if cloud is entirely missing the cap cannot fire (the all-`None` rule above already zeroes the term and records a reason).
- `verdict` is a pure function of the final `total` (after bonus, rounding, and cap). Totals of 0 from the missing-data rules land in STAY IN BED; the recorded reason explains why.

**Worked examples** (verifiable in `tests/test_score.py`):

*Example A — Draconids night, clear, near-new Moon:* mean cloud 5%, illumination 0.01, up_fraction 0.5, mean rh 45%, mean vis 24,000 m, spread 6 °C, mean wind 8 km/h; peak shower radiant-up, one ISS pass ≥ 45°.
cloud 0.95 · moon 0.15 + 0.85×(1−0.005) = 0.99575 · hum 40/45 = 0.888889 · vis 1.0 ⇒ trans 0.888889 · dew 0.5 · wind clamp01((25−8)/10) = 1.0
base = 100×(0.4275 + 0.1493625 + 0.1333333 + 0.025 + 0.200) = **93.52**; event = min(10, 6+2) = 8 ⇒ total = round(clamp(93.52+8, 0, 100)) = **100 — PRIME**

*Example B — clear, full Moon (up 0.8 of the window):* same weather as A, illumination 1.0, up_fraction 0.8, no events. moon = 0.15 + 0.85×(1−0.8) = 0.32.
base = 100×(0.4275 + 0.048 + 0.1333333 + 0.025 + 0.200) = **83.38** ⇒ **total 83 — WORTH IT**

*Example C — clear, full Moon up all night:* as B but up_fraction 1.0. moon = 0.15 + 0.85×(1−1.0) = 0.15.
base = 100×(0.4275 + 0.0225 + 0.1333333 + 0.025 + 0.200) = **80.83** ⇒ **total 81 — WORTH IT**

*Example D — overcast, full Moon, damp, windy:* mean cloud 90%, illumination 1.0 up all night, rh 70%, vis 10,000 m, spread 1 °C, wind 25 km/h, no events.
cloud 0.10 · moon 0.15 · hum 15/45 = 0.333333 · vis 5/19 = 0.263158 ⇒ trans 0.087719 · dew 0 · wind 0
base = 100×(0.045 + 0.0225 + 0.0131579 + 0 + 0) = **8.07** ⇒ total 8, then cap: min(8, 15) = 8 with reason "overcast" ⇒ **total 8 — STAY IN BED**

*Cap-binding variant (for tests):* Example B's weather with mean cloud 86% plus peak + ISS (event 8): base = 100×(0.45×0.14 + 0.1493625 + 0.1333333 + 0.025 + 0.200) = 57.07 ⇒ 57.07+8 = 65 ⇒ **capped to 15, reason "overcast"**. The same night at mean cloud 84% (cloud_term 0.16) gives base 57.97 ⇒ 65.97 ⇒ **66, uncapped**.

Ordering A (100) > B (83) > C (81) > D (8) satisfies A5's clear-moonless > clear-full-Moon > cloudy requirement with wide margins; the moon floor keeps both full-Moon nights firmly WORTH IT, and the cap puts every overcast night in bed.

---

## 6. Brief generation and verification

### Prompt outline (brief.py)

- **system:** "You write short stargazing briefs. Use ONLY facts present in the provided data. Every time, number, direction, and event name must come from the data, pre-rounded as given. Never invent or estimate. ≤120 words. Structure: when to go out, which way to face, what to look for."
- **user:** compact JSON for the top 3 nights: local date and day-of-week, dark window start/end (local, 12-hour), Moon facts (phase name, illumination %, rise/set, up share), weather aggregates (mean cloud %, humidity %, wind, visibility), dew risk label, score with factor breakdown and verdict band, meteor showers (name, ZHR, peak flag, radiant-up hours), ISS passes (times, max altitude, directions), and the site name.
- Call: `POST {llm.base_url}/chat/completions` (any OpenAI-compatible endpoint; `Authorization: Bearer <api_key>` sent only when a key is configured — local llama.cpp stays keyless), `temperature 0.2`, `max_tokens 400`, `timeout 30 s`, one retry on transport error.

### Claim extraction and checking (verify.py)

Extract from the brief text:
- **Times:** every `H:MM` / `HH:MM` (optional am/pm). Each must match, to ±1 minute, one of: any night's window start/end, Moon rise/set, ISS pass start/max/end, shower peak — in site-local time. 12/24-hour and minute-rounding are normalized before comparison.
- **Numbers with units:** percentages must equal a computed value for that night (cloud, humidity, illumination, score) within ±1; degrees within ±1 of a computed altitude; km/h and °C within ±1 of given aggregates; meteor counts must be the quoted ZHR (never a promise of visible counts — a violation message steers the model away from predicting counts).
- **Named events:** must be an active shower name from the data, `"ISS"` / `"International Space Station"`, the computed Moon phase name, the site name, or the computed verdict band word (`PRIME` / `WORTH IT` / `Marginal` / `Poor` / `STAY IN BED`).
- **Directions:** 8-point compass words must match a direction attached to an ISS pass in the data; "up"/"overhead" allowed only if some pass has max_alt ≥ 60°.
- **Day words:** "tonight/today" ⇒ plan date; "tomorrow" ⇒ +1; explicit weekdays must match.

**Retry/fallback:** on violations, re-prompt with the violation list and the exact allowed values, up to 2 retries. If still failing or the LLM is unreachable: template brief assembled from the computed data, labeled `"Template brief (LLM output unavailable or failed verification; all values are computed, not generated)."` The plan renders either way (A7).

---

## 7. Caching and offline strategy

| Artifact | Cache key | Max age | Offline fallback |
|---|---|---|---|
| Forecast (Open-Meteo) | `forecast_{lat}_{lon}_{yyyymmdd}.json` | 1 h | `clearnight/fixtures/forecast.json` |
| ISS TLE (CelesTrak 25544) | `celestrak_iss.txt` | 24 h | `clearnight/fixtures/tle.txt` |
| Ephemeris `de421.bsp` | `de421.bsp` | never expires | recorded `clearnight/fixtures/sky.json` |
| Sensor (http_json) | not cached | — | `clearnight/fixtures/sensor.csv` via CSV adapter |
| LLM brief | not cached | — | template brief (labeled) |

- `cache/` sits in the repo root, gitignored. Every network call has a timeout (forecast 15 s, TLE 15 s, bsp 120 s, sensor 10 s, LLM 30 s) and falls back exactly as above.
- **Fixture epoch:** `clearnight/fixtures/manifest.json` records `reference_date` (the Tuesday of the demo week) and the demo site. In `--offline` mode the planner's "today" is pinned to `reference_date`, so the demo week (Tue Oct 6 – Mon Oct 12, 2026, America/Chicago) always has valid fixture data and reproducible output. Online mode uses the real clock.
- Fixtures are (re)generated by the maintainer via `python -m clearnight fetch --record-fixtures` (not needed by end users); committed so a fresh clone passes A1/A10 with zero network. `sensor.csv` is recorded from keyless Open-Meteo observation data for the demo site (D1), so no private sensor readings are ever committed.
- `fetch` subcommand refreshes forecast + TLE + bsp and prints cache status; `plan` always prefers fresh cache over network when within max age.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Ephemeris unavailable offline (17 MB, gitignored) | Recorded `sky.json` fixture powers `--offline`; online path downloads bsp once into `cache/` |
| LLM hallucinates or endpoint down | Verify-then-retry (≤2) with explicit allowed values; labeled template fallback (A6/A7) |
| Open-Meteo schema/param drift | Exact param list pinned in `forecast.py`; response validated field-by-field; cached/fixture fallback; unit tests assert on fixture shape |
| Stale TLE (>24 h offline) | Pass quality degrades gracefully; plan footer states TLE age |
| Sensor wiring | Resolved (D1, Oct 7): production = Home Assistant entity over `http_json`, config-only in `config.local.toml`; deliverable/demo = `csv` fixture derived from Open-Meteo observations; a third adapter would be its own task only if hardware changes |
| DST / timezone bugs | UTC internally, `zoneinfo` only at render; unit test across the Nov 1 US DST boundary and at UTC-date edges |
| Schedule slip threatens the post | Phase gates in `IMPLEMENTATIONPLAN.md`; cut order fixed; post drafting starts Wed regardless of code state |
| Privacy leak of coordinates/URLs | `config.local.toml` gitignored in commit #1; example config uses Black Mesa; audit task greps history before publish |
| Draconids clouded out Thu night | D3 fallback documented: show the planner correctly predicting clouds; any other clear night works as evidence |

---

## 9. Test strategy

- `python -m unittest discover -s tests` — fully offline, no LLM, no network, deterministic (fixture epoch).
- One `test_*.py` per module, written in the same task as the module. Network is always mocked or bypassed via fixtures.
- Score tests encode §5's four worked examples exactly, plus dew-risk, peak-bonus, overcast-cap and wind-cliff cases, and verdict-band boundaries (A5).
- Brief/verify tests use canned replies: one clean pass, one with an invented time and a wrong percentage (A6), one transport failure (A7).
- Accuracy cross-check (A4): `tests/test_accuracy.py` asserts recorded Sun/Moon/ISS values for Black Mesa on the Draconids night against reference numbers captured from timeanddate.com / Heavens-Above and stored as a fixture, ±5 min / ±5°.
- CLI test runs `plan --offline` end-to-end from the example config into a temp `out/` and asserts on the HTML/text (A1).
