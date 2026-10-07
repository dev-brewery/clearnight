# clearnight — Agent Wiring

Stargazing planner for the DEV Hacktoberfest Week 1 "Touch Grass" challenge.
**Source of truth: `PROJECTGUIDELINES.md` (owner-maintained).** `ARCHITECTURE.md` is the
design, `TASKS.md` the build plan, `IMPLEMENTATIONPLAN.md` the calendar gates. If any file
disagrees with the guidelines, the guidelines win until Michael changes them.

## Roles

| Role | Who | Model | Charter |
|---|---|---|---|
| **Owner** | Michael (human) | — | All determinations (scope, standards, priorities, §10 questions), the real sensor and site, outdoor testing, final approval, clicking Publish. Decision rights are his alone; see standing rules. |
| **Orchestrator** | pi session | GLM-5.3, thinking: max | `.pi/skills/orchestrator/` — task briefs from `TASKS.md`, launches builder sessions, verifies acceptance criteria, records outcomes in `JOURNAL.md`, guards scope and the post deadline. Never writes application code, never commits. |
| **Architect** | pi session | GLM-5.3, thinking: high | `.pi/skills/architect/` — produces and maintains `ARCHITECTURE.md` + `TASKS.md` per guidelines §9. Never writes application code. |
| **Builder** | pi session | GLM-5.3-flash, thinking: low | `.pi/skills/builder/` — writes all code, tests, and commits, one `TASKS.md` task at a time. The only role that touches git in this repo. |

## Activation

All agent-role models run direct against the **z.ai** provider (`zai` in pi's catalog).
Load the charter before acting in a role:

- Architect: `pi --model zai/glm-5.3:high` then `/skill:architect`
- Builder: `pi --model zai/glm-5.3-flash:low` then `/skill:builder`
- Orchestrator: `pi --model zai/glm-5.3:max` then `/skill:orchestrator`

Project-local skills load only after the project is trusted. The first pi session in this
repo prompts for trust; approve it and run `/trust` to persist the decision.

## Delegation protocol (orchestrator-driven)

The owner is hands-off for day-to-day execution. The orchestrator launches sub-agents
non-interactively and verifies their output:

```
pi -p -a --no-skills --model <model> --name "<role>-<order>" @.pi/skills/<role>/SKILL.md "<brief>"
```

- `-p` — print mode: one shot, result to stdout, captured by the orchestrator.
- `-a` — approves project-local resources for the run (`.pi/skills/` is trust-gated
  in non-interactive mode).
- `--no-skills` + `@<charter>` — attaches the role charter directly into the first
  message. Skills are progressive-disclosure by design (the model chooses whether to
  read them), which is nondeterministic for delegation; the `@file` attachment is
  deterministic and was validated by smoke test.
- Briefs reference a `TASKS.md` task or a work order in `JOURNAL.md`. Sub-agents never
  ask questions; blockers are reported in stdout and the orchestrator journals them.
- The orchestrator verifies every result against its acceptance criteria before the
  next brief, and records outcomes in `JOURNAL.md` and the progress tracker atop
  `IMPLEMENTATIONPLAN.md` — both ride the next builder commit. Cadence: brief →
  build → verify → accept → journal + tracker → next brief. One task, one commit.
- Owner-required, non-delegable actions stay flagged in `JOURNAL.md`: the Thursday
  field test (D3) and clicking Publish (D1).

## Standing rules (all roles)

1. The global relationship rules in the system prompt are non-negotiable: surface
   owner-level determinations as options with trade-offs and wait for Michael's call;
   own any deviation immediately, without technicalities.
2. Role boundaries are hard. Architect and orchestrator never write application code.
   Only the builder commits (guidelines A12: every commit authored by the builder model).
3. One task, one commit, tests in the same task, network always mocked (guidelines §7).
4. Course-correct protocol for any role: stop → re-read `PROJECTGUIDELINES.md` →
   realign → await direction.
5. The published DEV post is the deliverable. Nothing delays it past the internal
   deadline (guidelines §1, §8). If scope must shrink, cut in the §8 order.
