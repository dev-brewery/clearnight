# clearnight: Project Guidelines

A stargazing planner that tells you which nights in the coming week are worth going outside for, and what to look at when you get there. It combines weather forecasts, a local climate sensor, and the sky itself (Moon, twilight, meteor showers, ISS passes) into a ranked list of nights, then has a local open-weight model write a short plain-language brief for the best ones.

This file is the single source of truth for the project. Read it fully before planning or writing code. If anything in the codebase disagrees with this file, this file wins until Michael changes it.

---

## 1. The challenge

**DEV Hacktoberfest Open-Source AI Challenge, Week 1: "Touch Grass"**
https://dev.to/challenges/hacktoberfest-week1-2026-10-05

- **Prompt:** "Build something with open-weight models or open-source AI that gets people off the screen and into the world."
- **Deadline:** Saturday, October 11, 2026, 11:59 PM PDT (October 12, 06:59 UTC).
- **Winners announced:** week of October 12.
- **Submission:** a published DEV post using the challenge template, with sections:
  1. What I built and how it gets people outdoors
  2. Demo (screenshots or video)
  3. Code
  4. How I built it with open-source AI
  5. Why open innovation matters for this project
  6. (Optional) agent session via DevRelay
- **Required tags:** `devchallenge`, `hf26challenge`
- **Judging, in order of weight:** writing quality (heaviest), relevance to prompt and theme, creativity, technical execution, partner technology (optional).
- **Bonus:** projects tested outdoors, with the results documented, get extra credit.
- **Optional partner category worth considering:** Best Use of TabPFN (Prior Labs tabular foundation model, $200). See Stretch S2.

### What went wrong last time, and the rule that prevents it

The previous entry (homestead-stories, Weekend Challenge "Build for a Friend") was fully built and the post was fully drafted, but **the post was never published and the deadline passed.** The code was fine. The submission did not happen.

Therefore:

- **The published DEV post is the deliverable.** The code exists to support the post. A working app with no published post scores zero.
- The post draft starts on day one and grows alongside the code, not after it.
- Publishing has a hard internal deadline well ahead of the real one (see section 8). Nothing, including an unfinished feature, delays publishing past that point. Unfinished features are cut, or listed as open items in the post.

---

## 2. Who builds what

| Role | Who | Responsibilities |
|---|---|---|
| Owner | Michael | Decisions, the real sensor and location, outdoor testing, final approval, clicking Publish |
| Architect | GLM-5.3 (thinking high) via pi on z.ai (fed this file) | Produces `ARCHITECTURE.md` and `TASKS.md` (section 9) |
| Builder | pi coding agent + GLM-5.3-flash (thinking low) on z.ai | Writes all code, tests, and commits, one small task at a time |
| Orchestrator / journal | pi coding agent + GLM-5.3 (thinking max) on z.ai | Turns `TASKS.md` into task briefs, launches the builder, verifies acceptance, records outcomes. Never writes application code and never runs git in this repo |

Role wiring (Michael, Oct 7, 2026): `AGENTS.md` is the router; role charters live in `.pi/skills/{architect,builder,orchestrator}/SKILL.md`. Claude Code wrote the initial proposition only; orchestration belongs to pi, and the orchestrator owns build success or failure. All agent-role models run direct against the z.ai provider.

The in-app model calls a configurable OpenAI-compatible HTTP endpoint with an **optional API key** (any key lives only in `config.local.toml`, which is gitignored). Michael's instance runs locally on llm-box (EPYC, 2x Tesla P40) through llama.cpp, default `http://llmbox.internal:8080/v1`; any hosted OpenAI-compatible endpoint works through config alone.

---

## 3. What the app does

### Core loop

1. **Where and when.** Read the observing site (lat, lon, elevation, timezone) from local config, and a horizon of N nights (default 7).
2. **Darkness window.** For each night, compute the astronomical dark window (Sun below -18 degrees), plus Moon rise, set, illumination, and altitude across that window.
3. **Weather.** Fetch an hourly forecast for the site: total, low, mid, and high cloud cover, relative humidity, dew point, visibility, and wind. Keep only the hours inside each night's window.
4. **Local sensor.** Read recent readings from the local climate sensor (temperature, humidity, pressure, and dew point, either reported or computed). Use them to:
   - estimate dew risk on optics from the temperature to dew point spread, projected into the night;
   - report the pressure trend over the last 3 to 6 hours (falling or rising) as a clearing or worsening signal;
   - show forecast against actual for the current conditions, so the user can see how far to trust tonight's forecast.
5. **Sky events.** For each night, collect:
   - active meteor showers (from a bundled data file), with peak date, ZHR, radiant, and whether the radiant is up during the dark window;
   - visible ISS passes: start, max-altitude, and end times, max altitude, and direction, only for passes where the ISS is sunlit and the observer is in darkness;
   - optional: bright planets above 15 degrees during the window.
6. **Score.** Give each night a deterministic 0 to 100 score from cloud cover in the dark window, Moon interference, transparency (humidity and visibility), dew risk, and wind, plus a bonus for events. The scoring function is pure, documented, and unit tested. **The LLM never computes the score.**
7. **Brief.** The local open-weight model writes a short brief for the top nights: when to go out, which way to face, and what to expect. Every time, number, and named event in the brief must come from the computed data (section 4).
8. **Output.** A one-page HTML plan (printable and readable on a phone in the dark, with red-on-black styling) and a plain-text summary for the terminal.
9. **Field log.** A command to record what actually happened on a night: went out yes or no, how clear it was, meteors counted, whether the ISS was seen, and notes. The plan shows past predictions next to logged outcomes. This produces the outdoor-testing evidence the post needs.

### Where open-source AI is at the core

- **In-app:** a configurable open-weight model (default Qwen on llm-box; any OpenAI-compatible HTTP endpoint, optional API key) turns scored nights into a human brief. A verifier checks every time, date, number, and event name in the brief against the computed night data. A brief that fails goes back to the model with its problems listed, up to a retry limit. If it still fails, the app falls back to a template brief, which is clearly labeled as such. This is the same grounding pattern as homestead-stories, applied to sky data.
- **Open data and tools:** keyless open weather data, public orbital elements, and open-source astronomy libraries. No accounts, no API keys, and no location data sent anywhere except the forecast request.
- **Built by open-weight AI:** the builder model writes and commits all of the code (section 2).

---

## 4. Data sources and constraints

| Need | Source | Notes |
|---|---|---|
| Hourly forecast | Open-Meteo forecast API (no key) | `cloud_cover`, `cloud_cover_low/mid/high`, `relative_humidity_2m`, `dew_point_2m`, `visibility`, `wind_speed_10m`, `temperature_2m`. Optional second source: NWS `api.weather.gov` gridpoint `skyCover` (US only, needs a User-Agent header). |
| Sun, Moon, twilight, ISS geometry | `skyfield` (MIT) with a bundled or cached JPL ephemeris (`de421.bsp`) | All geometry is computed locally. |
| ISS orbital elements | CelesTrak GP data for NORAD 25544 (no key) | Cache to disk, refresh when older than 24 h, and work offline from cache. |
| Meteor showers | `data/meteor_showers_2026.json`, built from the IMO 2026 Meteor Shower Calendar | Peak (UTC), active range, ZHR, radiant RA/Dec, parent body. Record the source URL inside the file. |
| Local climate sensor | Adapter (see below) | Exact hardware is **TBD by Michael**. |

**Sensor adapter.** Define one small interface: `read_recent(hours) -> list[Reading]`, where `Reading` has a timestamp plus optional temperature, humidity, pressure, and dew point. Ship two implementations:
1. `csv`: reads a local CSV file. This is used for tests and the demo, and any sensor that can append to a file works with it.
2. `http_json`: GETs a configurable URL and maps fields through config. This covers Home Assistant's REST API, ESPHome, and most hobby stations.

The real sensor is wired in through config only, with no code changes. If Michael's sensor needs a third adapter, it is added as its own task.

**Hard constraints:**
- Python 3.12. Dependencies are limited to `skyfield` (which brings `numpy`) and anything required for Stretch S2. Use the standard library for HTTP (`urllib`), HTML, and CLI. Pin versions in `pyproject.toml`.
- **Michael's home coordinates and sensor URL never enter the repo.** They live in `config.local.toml`, which is gitignored. The committed `config.example.toml` and every demo or screenshot use a public dark-sky site instead: Black Mesa State Park, Oklahoma (approximately 36.85 N, -102.88 W).
- Every network call has a timeout and a cached or fixture fallback. **The whole test suite runs offline** from fixtures in `tests/fixtures/`.
- Data sources are keyless: no accounts, no telemetry. The LLM endpoint is the one configurable exception — it may carry an API key, stored only in gitignored `config.local.toml`; the offline path (template brief) never needs one.
- Times are stored in UTC and displayed in the site's local timezone.

---

## 5. Proposed file map

This is a starting point. The architect may change it, but must replace this section's contents in `ARCHITECTURE.md` with the final map, and every file must still have one stated job.

```
clearnight/
├── PROJECTGUIDELINES.md        this file (owner-maintained)
├── ARCHITECTURE.md             architect output: modules, data flow, interfaces, scoring formula
├── TASKS.md                    architect output: ordered, small, testable build tasks
├── README.md                   install, configure, run, screenshot
├── LICENSE                     MIT
├── pyproject.toml              metadata, pinned deps, `clearnight` entry point
├── config.example.toml         public demo site + sensor adapter examples
├── .gitignore                  includes config.local.toml, cache/, out/, *.bsp
├── clearnight/
│   ├── __init__.py
│   ├── __main__.py             CLI: `plan`, `log`, `fetch`, `--offline`
│   ├── config.py               load example/local TOML, validate site + sensor + llm settings
│   ├── models.py               dataclasses: Site, Night, HourWeather, Reading, Event, NightScore
│   ├── cache.py                disk cache with max-age for forecast, TLE, ephemeris
│   ├── sky.py                  dark window, Moon rise/set/illum/alt (skyfield)
│   ├── iss.py                  TLE fetch + visible pass prediction
│   ├── meteors.py              load shower table, active/peak/radiant-up per night
│   ├── forecast.py             Open-Meteo client (+ optional NWS), slice to dark window
│   ├── sensor/
│   │   ├── __init__.py         Reading + adapter interface + factory from config
│   │   ├── csv_adapter.py
│   │   └── http_json.py
│   ├── conditions.py           dew risk, pressure trend, forecast-vs-actual
│   ├── score.py                pure scoring function + per-factor breakdown
│   ├── brief.py                LLM prompt build + call (OpenAI-compatible)
│   ├── verify.py               check brief claims against Night data; retry loop
│   ├── render.py               HTML plan (red night-mode) + text summary
│   └── fieldlog.py             append/read field log (JSONL), match to predictions
├── data/
│   └── meteor_showers_2026.json
├── tests/
│   ├── fixtures/               forecast JSON, TLE text, sensor CSV, canned LLM replies
│   └── test_*.py               one per module
└── out/                        generated plans (gitignored)
```

---

## 6. Deliverable acceptance criteria

The project is **done** when all MUST items pass. Each one should be checkable by running a command or reading a file.

### Submission (MUST, highest priority)
- **D1.** A DEV post is **published** (not draft) on Michael's account (`dev.to/devbrewery`) before **Sat Oct 11, 6:00 PM CT**, with tags `devchallenge` and `hf26challenge` and every template section from section 1.
- **D2.** The post links the public GitHub repo (`dev-brewery/clearnight`) and includes at least one screenshot of a generated plan.
- **D3.** The post documents at least one real night outdoors: the plan's prediction for that night next to the field log entry. The target night is the Draconids peak, Oct 9 (Moon about 1% lit), with any other clear night as a fallback. If every night is clouded out, the post says so honestly and shows the planner correctly predicting the clouds.
- **D4.** The post explains why open innovation matters here (local model, private location and sensor data, keyless open data, swappable model).

### App (MUST)
- **A1.** `python -m clearnight plan --offline` runs from a fresh clone using only committed fixtures and the example config, and writes `out/plan.html` plus a text summary. No network access and no LLM are required; the template brief is used.
- **A2.** `python -m clearnight plan` (online) fetches the forecast and TLE, reads the configured sensor, calls the local LLM, and produces a plan for the next 7 nights, ranked by score.
- **A3.** Each night in the plan shows: the dark window (local time), Moon phase, illumination, and rise/set, the cloud cover summary for the window, dew risk, the score with a per-factor breakdown, active meteor showers (marking a peak night), and visible ISS passes with times, max altitude, and direction.
- **A4.** Sun, Moon, and ISS numbers match an independent reference (for example, timeanddate.com or Heavens-Above for the demo site) within ±5 minutes for event times and ±5 degrees for altitude, on at least one checked night. The check is recorded in `tests/` or the post.
- **A5.** The scoring function is pure and deterministic, and has unit tests that cover: clear moonless night > clear full-Moon night > cloudy night; dew risk lowering the score; and a meteor peak raising the score.
- **A6.** The verifier rejects a brief that states any time, number, or event not present in that night's data, and accepts one that only cites real data. Tests use canned LLM replies, one passing and one failing.
- **A7.** If the LLM is unreachable or keeps failing verification, the plan still renders with a labeled template brief and no crash.
- **A8.** Sensor readings come in through the adapter interface. The CSV adapter works from a fixture, and switching to `http_json` is a config change only.
- **A9.** `python -m clearnight log --date YYYY-MM-DD ...` appends a field log entry, and the next plan shows past predictions next to logged outcomes.
- **A10.** The full test suite passes offline: `python -m unittest` (or `pytest`, if the architect chooses it).
- **A11.** No home coordinates, sensor URLs, or secrets exist anywhere in the git history. `config.local.toml` is gitignored from the first commit.
- **A12.** Every commit in the repo is authored by the builder model, with a sign-off line naming the model.

### Stretch (only after all MUST items pass, and never after Fri Oct 10, 8:00 PM CT)
- **S1.** NWS `skyCover` as a second forecast source; the plan shows agreement or disagreement between sources.
- **S2.** TabPFN "will it actually be clear" classifier: trained on tabular features (forecast cloud layers, humidity, pressure trend, sensor spread) against observed outcomes (Open-Meteo historical data or field log). Its probability is shown alongside the deterministic score, not in place of it. Entering the TabPFN partner category is only worth doing if this works convincingly.
- **S3.** Bright planets above 15 degrees in the dark window.
- **S4.** A `.ics` export of the top nights and ISS passes.

---

## 7. Engineering rules for the builder

- One task, one commit. Each task in `TASKS.md` should fit in roughly 15 minutes of builder time and end with passing tests.
- Write the tests in the same task as the code. Network calls are always mocked in tests.
- Never put real coordinates, URLs from `config.local.toml`, or personal data in code, tests, fixtures, or commit messages.
- Keep modules small, with one job each, as stated in the file map.
- Commit message: a one-line summary, a short body, then `Signed-off-by: <model name> (via pi) <qwen@llm-box.local>`.
- If a task can't be completed, stop and say so in the reply. Don't paper over it.

---

## 8. Timeline (Central Time)

| When | Milestone |
|---|---|
| Tue Oct 7, night | Guidelines done; architect produces `ARCHITECTURE.md` and `TASKS.md`; Michael confirms the sensor type |
| Wed Oct 8 | Skeleton, config, sky, meteors, ISS, forecast, sensor adapters, and scoring built and tested. **Post draft started** (what I built, why) |
| Thu Oct 9, before dusk | `plan` runs end to end online for Michael's site. **Draconids night: Michael goes out with the plan and logs the result** |
| Fri Oct 10 | Brief + verifier, HTML render, field log, README, screenshots. Post draft complete. Stretch work stops at 8 PM |
| Sat Oct 11, noon | Final read of the post; Michael's approval |
| **Sat Oct 11, 6:00 PM CT** | **Post published. Hard stop. Feature freeze.** |
| Sat Oct 11, 11:59 PM PDT | Official deadline (buffer only, never the plan) |

If the build is behind schedule, cut scope in this order: S-items, then the NWS source, then the forecast-vs-actual view, then ISS direction detail. Never cut the post, the field test, or A1/A6/A7.

---

## 9. What the architect must produce

Read this whole file, then write two files in the repo root:

1. **`ARCHITECTURE.md`** containing:
   - the final file map;
   - the data flow from config to plan;
   - the public function signatures and dataclasses for each module;
   - the exact scoring formula, with weights and a worked example;
   - the brief prompt outline and the verifier's claim-extraction rules;
   - the caching and offline strategy;
   - the risks, with a mitigation for each.
2. **`TASKS.md`** containing ordered build tasks, each with an ID (`T01`...), the goal, the files touched, the acceptance test, and the AC IDs it advances (`A1`...). The first task creates `pyproject.toml`, `.gitignore` (including `config.local.toml`), `LICENSE`, and the package skeleton, and runs `git init`. Order the tasks so that `plan --offline` (A1) works as early as possible, then add features to it incrementally.

Do not write application code in the architecture step.

---

## 10. Open questions for Michael

1. **Sensor:** what hardware is it, and how does it expose readings (Home Assistant entity, ESPHome, MQTT, a file, something else)? This decides whether `http_json` covers it.
2. **Observing site:** home backyard, or a darker site nearby? Either way, it goes in `config.local.toml` only.
3. **Repo name:** is `clearnight` under `dev-brewery` OK? It must not duplicate anything on `brewer-michael`.
