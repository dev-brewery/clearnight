# POST DRAFT — clearnight (DEV Hacktoberfest Week 1: "Touch Grass")

Status: DRAFT — started Wed Oct 8 per timeline. Sections 2, 3, 5, 6 fill in as
evidence lands (screenshots after the field test; code section at freeze).
Required tags: `devchallenge`, `hf26challenge`. Publish: Sat Oct 11, 6:00 PM CT,
dev.to/devbrewery. NOTHING delays publishing past that point.

---

## 1. What I built and how it gets people outdoors

clearnight is a stargazing planner that answers one question for the week ahead:
**which nights are actually worth going outside for — and what will be up there
when you are?**

It fuses three kinds of data into a ranked list of nights:

- **The sky** — astronomical darkness windows (Sun below −18°), Moon phase,
  illumination, rise/set and altitude through each window, active meteor showers
  with radiant-up hours, and visible ISS passes (sunlit station, dark observer,
  max altitude, direction of travel). All geometry computed locally with
  skyfield and a cached JPL ephemeris.
- **The weather** — keyless Open-Meteo hourly forecasts sliced to each night's
  dark window: cloud layers, humidity, visibility, dew point, wind.
- **A sensor-shaped local feed** — the app reads whatever serves current site
  conditions over HTTP: a real backyard instrument, or, as in our instance, a
  Home Assistant template sensor emulating one from met.no conditions for the
  site. It feeds the dew-risk estimate and a pressure trend, and a
  source-agreement view (current conditions vs the forecast) so you can see how
  far to trust tonight's forecast. Ground truth in this system is the field log
  — the human record of what the sky actually did.

Each night gets a deterministic 0–100 score with a per-factor breakdown and a
plain verdict — PRIME, WORTH IT, Marginal, or STAY IN BED — and the plan renders
as a red-on-black single page you can read on a phone in the dark without ruining
your night vision.

It gets people outdoors by removing every excuse: it tells you the exact window,
the exact things to look for, and it is honest when the answer is "stay in bed."
And it holds itself accountable — a built-in field log records what actually
happened, and the next plan shows its own past predictions next to your outcomes.

## 2. Demo

[SCREENSHOTS - docs/plan-offline.png: the full offline plan, red-on-black, seven
ranked nights with verdicts, the Draconids PEAK marking, the overcast-capped
weekend at STAY IN BED, and the labeled template brief. docs/fieldlog-comparison.png:
a night's prediction rendered beside its field-log entry. Both regenerate from a
fresh clone: `py -m clearnight plan --offline`. The live verified brief from the
local model (receipt below) goes here too.]

Verifier receipt for the post: the first live attempts FAILED verification and the
plan said so - the model corrupted the dark-window times; the retry loop fed the
violations back; the surviving brief cites only computed values: "Go out at Black
Mesa State Park (demo) on 2026-10-08 from 8:55 pm to 6:25 am. Face E, S, or SE.
Look for Draconids, ZHR 10, and Orionids, ZHR 20. New Moon, 2% illumination...
Score 100, PRIME." - footer: brief: llm-verified (2 LLM call(s), 17 claims checked).

Accuracy receipt: computed dark windows match timeanddate.com for the demo site
within 1 minute; the Oct 9 New Moon (1.0% at lunar noon, never above the horizon
all night) confirmed against the independent reference; locked in the test suite
(tests/test_accuracy.py).

## 3. Code

Public repo: `github.com/dev-brewery/clearnight` (MIT). Python 3.12, one pinned
runtime dependency (skyfield) plus a Windows-only tzdata marker, stdlib for
everything else - no API keys for any data source, no accounts, no telemetry.
`python -m clearnight plan --offline` reproduces the demo plan from committed
fixtures with zero network (proven from a fresh clone). 249-test offline suite.
Every commit is authored and signed off by the builder model - the full delegation
journal (decisions, briefs, verifications, receipts) ships in the repo as
JOURNAL.md. [LINK AT PUBLISH]

## 4. How I built it with open-source AI

The entire codebase was written by an open-weight model working as a delegated
builder — every commit authored and signed off by the model, verified by a
separate model acting as orchestrator.

The team is four roles wired into the coding agent (pi):

- **Owner** (me): decisions only. I set the rules and made seven determinations —
  sensor, site, scoring weights, verifier strictness — and then stepped out of
  the loop entirely.
- **Orchestrator** (GLM-5.3, max thinking): turns the task list into one-task
  briefs, launches builder sessions non-interactively, independently verifies
  every acceptance test before the next brief, and journals every outcome.
- **Architect** (GLM-5.3, high thinking): designed the modules, the exact scoring
  formula, and the verification rules — and surfaced every owner-level decision
  as options before embedding anything.
- **Builder** (GLM-5.3-flash, low thinking): wrote all code, one task per
  commit, tests with every module, offline test suite from committed fixtures.

Open-source AI is also *inside* the app, not just around it: the observing brief
for the top nights is written by a local open-weight model — but every time,
number, and event name it writes is checked by a verifier against the computed
data. A brief that invents anything gets sent back with its errors listed; if it
keeps failing, the app falls back to a clearly labeled template. **The LLM never
computes the score.** The deterministic core produces the numbers; the model only
turns them into words, and it is not trusted.

The delegation structure itself is part of the artifact: role charters, a
decision journal, and a progress tracker are committed in the repo, along with
the full record of how each determination was surfaced and ratified.

## 5. Why open innovation matters for this project

- **Your location stays yours.** Coordinates and sensor URLs live only in a
  gitignored local config. The committed demo uses a public dark-sky site
  (Black Mesa State Park, Oklahoma). The only data that ever leaves the machine
  is an anonymous forecast request for a place you chose to ask about.
- **The model is swappable by design.** The in-app brief writer speaks to any
  OpenAI-compatible endpoint — a local llama.cpp server with no key, or a hosted
  provider with one — configured in one line. Open weights mean the app still
  works when the cloud doesn't.
- **Keyless open data.** Open-Meteo forecasts, CelesTrak orbital elements, JPL
  ephemerides, the IMO meteor calendar. No accounts, no API keys, no telemetry —
  and every network call has a timeout and an offline fallback, so the whole
  thing runs airgapped from committed fixtures.
- **Verified generation, not trusted generation.** The verifier pattern —
  generate, check every claim against computed truth, retry or fall back — is
  how small local models become reliable enough to ship, and it's all in the
  open.

## 6. (Optional) agent session via DevRelay

[IF TIME BEFORE FREEZE — export the orchestrator session log; else cut.]

---

### Field test (to be written Thursday night, Oct 9)

[TEMPLATE — fill from the actual log entry:]
- What the plan predicted for Oct 9 (score, verdict, window, Draconids peak,
  moon conditions) — screenshot of that night's section. The sensor feed shown
  is met.no site conditions served through Home Assistant as an emulated sensor
  — stated as such, not claimed as a backyard instrument.
- What actually happened — the field-log entry: went out / clearness / meteors
  counted / ISS seen / notes.
- Prediction beside outcome, honestly: if clouds rolled in, say so and show the
  planner's cloud forecast for that night either way.

Facts on file for this section: at the demo site, Oct 9 2026 has 9.6 hours of
astronomical darkness and a 0.26%-illuminated New Moon that never rises into the
window — the Draconids peak under textbook conditions. The demo fixture records
0% mean cloud for that window. What the real sky does Thursday is up to the sky;
either way the post documents it.
