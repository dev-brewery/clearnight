# POST — clearnight (DEV Hacktoberfest Week 1: "Touch Grass")

Status: FINAL — publish today (owner order, Oct 9). Tags: `devchallenge`,
`hf26challenge`. Account: dev.to/devbrewery. Images: docs/plan-offline.png,
docs/fieldlog-comparison.png. Repo: github.com/dev-brewery/clearnight.
Everything below the line is the post body, ready to paste.

---

## What I built and how it gets people outdoors

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
  conditions as JSON over HTTP: a real instrument, a Home Assistant entity, or
  (as in this proof of concept) a mock file with preset values through the same
  adapter. It feeds a dew-risk estimate and a pressure trend, and a
  source-agreement view against the forecast. The adapter is the point: any
  JSON source plugs in with a config change and zero code.

Each night gets a deterministic 0–100 score with a per-factor breakdown and a
plain verdict — PRIME, WORTH IT, Marginal, or STAY IN BED — and the plan renders
as a red-on-black single page you can read on a phone in the dark without
ruining your night vision.

It gets people outdoors by removing every excuse: the exact window, the exact
things to look for, and honesty when the answer is "stay in bed." And it holds
itself accountable — a built-in field log records what actually happened, and
the next plan shows its own past predictions next to your outcomes.

## Demo

The full offline plan — seven ranked nights, verdicts, the Draconids peak
marked, an honestly overcast weekend capped at STAY IN BED, and the labeled
brief:

![clearnight offline plan — red-on-black, ranked nights with verdicts](https://raw.githubusercontent.com/dev-brewery/clearnight/main/docs/plan-offline.png)

A night's prediction rendered beside its logged outcome — the accountability
loop, demonstrated with a mock log entry:

![prediction beside field-log outcome](https://raw.githubusercontent.com/dev-brewery/clearnight/main/docs/fieldlog-comparison.png)

Both regenerate from a fresh clone: `python -m clearnight plan --offline`.

**The verifier in action.** When the local model wrote a brief that corrupted
the dark-window times, the plan refused to show it — the retry loop fed the
violations back, and the surviving brief cites only computed values:

> Go out at Black Mesa State Park (demo) on 2026-10-08 from 8:55 pm to 6:25 am.
> Face E, S, or SE. Look for Draconids, ZHR 10, and Orionids, ZHR 20. New Moon,
> 2% illumination. Cloud 0%, humidity 44%, wind 11.8 km/h, visibility 43.0 km.
> Score 100, PRIME.

Footer: `brief: llm-verified (2 LLM call(s), 17 claims checked)`.

**Accuracy.** Computed dark windows match timeanddate.com for the demo site
within 1 minute; the Oct 9 near-new Moon (never above the horizon all night)
matches the independent reference. The cross-check ships as a test
(`tests/test_accuracy.py`), not a claim.

## Code

**github.com/dev-brewery/clearnight** (MIT). Python 3.12, one pinned runtime
dependency (skyfield) plus a Windows tzdata marker, standard library for
everything else. No API keys for any data source, no accounts, no telemetry.
`python -m clearnight plan --offline` reproduces the demo plan from committed
fixtures with zero network — verified from a fresh clone. A 269-test suite runs
fully offline. Every commit is authored and signed off by the builder model,
and the complete delegation journal — every decision, brief, verification, and
correction — ships in the repo as `JOURNAL.md`.

## How I built it with open-source AI

The entire codebase was written by an open-weight model working as a delegated
builder — every commit authored and signed off by the model, verified by a
separate model acting as orchestrator. I made the decisions and then stepped
out of the loop entirely.

The team is four roles wired into the coding agent (pi), each with a committed
charter:

- **Owner** (me): decisions only — sensor, site, scoring weights, verifier
  strictness. Seven determinations, then hands off.
- **Orchestrator** (GLM-5.3, max thinking): turns the task list into one-task
  briefs, launches builder sessions non-interactively, independently verifies
  every acceptance test before the next brief, and journals every outcome —
  including its own mistakes, which are on the record.
- **Architect** (GLM-5.3, high thinking): designed the modules, the exact
  scoring formula, and the verification rules — and surfaced every
  owner-level decision as options before embedding anything.
- **Builder** (GLM-5.3-flash, low thinking): wrote all code, one task per
  commit, tests with every module.

Open-source AI is also *inside* the app, not just around it: the observing
brief is written by an open-weight model — but every time, number, and event
name it writes is checked by a verifier against the computed data. A brief
that invents anything gets sent back with its errors listed; if it keeps
failing, the app falls back to a clearly labeled template. **The LLM never
computes the score.** The deterministic core produces the numbers; the model
only turns them into words, and it is not trusted.

## Why open innovation matters for this project

- **Your location stays yours.** Coordinates and endpoints live only in a
  gitignored local config; the committed demo uses a public dark-sky site
  (Black Mesa State Park, Oklahoma). This proof of concept even ran its sensor
  feed from a local mock file — the whole demo reproduces with zero network.
- **The model is swappable by design.** The in-app brief writer speaks to any
  OpenAI-compatible endpoint — a local llama.cpp server with no key, or a
  hosted provider with one — configured in one line. Open weights mean the app
  still works when the cloud doesn't.
- **Keyless open data.** Open-Meteo forecasts, CelesTrak orbital elements, JPL
  ephemerides, the IMO meteor calendar — no accounts, no keys, no telemetry,
  and every network call has a timeout and an offline fallback.
- **Verified generation, not trusted generation.** The verifier pattern —
  generate, check every claim against computed truth, retry or fall back — is
  how small open models become reliable enough to ship, and it's all in the
  open.

## The outdoor loop, demonstrated with mock data

Full honesty up front: this is a proof of concept, completed with mock data —
no field test was conducted before the submission deadline. What that means
concretely:

- The **sky, weather, and scoring** are real computed data for a real public
  site — the planner genuinely says the Draconids peak night (Oct 9) carries
  9.6 hours of astronomical darkness with a Moon that never rises into it,
  under a fixture-recorded 0% cloud cover, scoring it PRIME.
- The **sensor feed** is a mock: an HA-shaped JSON file with preset values,
  read through the same adapter a real instrument would use.
- The **prediction-versus-outcome loop** is demonstrated with a mock log entry
  (second screenshot above) — the feature works exactly as designed; the entry
  in it is labeled demo.

In a real deployment you carry the plan outside, and `python -m clearnight log
--date YYYY-MM-DD --went-out --clearness 4 --meteors 12` records what the sky
actually did, right beside what the planner predicted. The loop that keeps the
tool honest is built, tested, and demonstrated — the night out is left as an
exercise for the reader, ideally on a PRIME one.

---

*Built in ~48 hours by a four-role open-weight AI team with a human owner who
only answered questions and clicked nothing else. The full record — every
decision, every brief, every correction, including the orchestrator's own
misreads — is in the repo's JOURNAL.md.*
