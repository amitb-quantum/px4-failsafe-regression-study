# Scored batch report — PX4 build-comparison feasibility experiment (VM venue)
Machine: this VM (Ubuntu 24.04.5 LTS). Batch executed 2026-10-24 (UTC) under the preregistration
`~/workspace/your_files/px4-feasibility-experiment-prereg-2026-10-23.md` **as amended**, including the
gate-interpretation amendment approved by the preregistration owner 2026-10-23 17:17 PDT.
Phase 0 basis: `PHASE0_REPORT.md` (same directory). PX4 source untouched; no gate or parameter
changes were made during the batch.

## Setup (identical for every run)
- Venue: SIH `sihsim_quadx` (autostart 10040), fresh rootfs per attempt, serial MAVLink over a
  socat PTY pair (Python UDP is blocked in this sandbox — Phase 0 report §8).
- Driver: `smoke_run.py` via `batch_run.py`; analysis: `analyze_ulog.py`; summaries:
  `batch_B/batch_B_summary.json`, `batch_A/batch_A_summary.json`, plus the two top-up summaries.
- Parameters (Phase 0 report §7): historical defaults except `NAV_RCL_ACT=1` (Hold) and
  `RC_MAP_ROLL/PITCH/THROTTLE/YAW=1/2/3/4`; `COM_FAIL_ACT_T=5.0 s`, `COM_RC_LOSS_T=0.5 s`.
- Scenario: Position mode, neutral sticks, MAVLink MANUAL_CONTROL stream established and verified
  in-log, then stopped; telemetry alive throughout; observation window **35 s** after RC loss.
- RC loss verified per run from the signal itself: manual-control setpoint stream (data_source 7)
  stops with a >5 s gap **and** `failsafe_flags.manual_control_signal_lost` transitions 0→1.

## Approved scoring (gate-interpretation amendment, departure rule)
- **Build B run passes** iff AUTO_LOITER appears at RC loss (within ~2.5 s) **and** neither
  AUTO_RTL nor AUTO_LAND appears during the 35 s window.
- **Build A run is defect-positive** iff AUTO_RTL (or Land following it) appears during the window.
- **Gate:** B passes ≥9/10 valid runs **and** A defect-positive ≥8/10 valid runs →
  flag = *meaningful difference*. Invalid runs (missing logs, unverified RC loss, **unrelated
  failsafes intervening**) are excluded from scoring, reported separately, and replaced only up to
  the fixed cap of **15 attempts per build**.

## Verdict
| Build | Commit | Attempts used (cap 15) | Valid | Invalid | Scored outcome |
|---|---|---|---|---|---|
| B (fixed, control) | `aa5b9ae638f1bf412102de8fabd06740c725abf1` | 12 | 10 | 2 | **10/10 pass** (gate needs ≥9) ✔ |
| A (regression) | `f7ed553f57d40073f0f3f3487509e6448a7727e6` | 12 | 10 | 2 | **10/10 defect-positive** (gate needs ≥8) ✔ |

**Flag = meaningful difference: FIRES.** Both preregistered conditions hold at full strength:
in every valid run, Build A departs Hold via the documented unintended AUTO_RTL at the
failsafe-action-delay expiry (RC loss +5.0 s) while Build B shows the Hold phase and no RTL/Land
departure at any point in the window. The control (Build B) spread on the scored categorical
observables is zero across its 10 valid runs — the A/B contrast is not within run-to-run noise.

## Build B — per-run outcomes
Common prefix of every run: `AUTO_LOITER@≈-0.1 (boot) → POSCTL@11.0` (stream established,
position mode). Times below are seconds relative to log start; "loss" = in-log RC-loss time.
Post-window entries (AUTO_PRECLAND ≈60 s, from the driver's end-of-run land command after the
stream is restored) are outside the 35 s scoring window and are not departures.

| Attempt | Loss @ | Outcome | Mode sequence after POSCTL |
|---|---|---|---|
| 1 | 23.68 | **INVALID** (see register) | ALTCTL@18.7 → TERMINATION@23.7 |
| 2 | 23.81 | valid — PASS | AUTO_LOITER@23.8 → POSCTL@28.8 → AUTO_PRECLAND@60.4 → POSCTL@67.4 |
| 3 | 23.78 | valid — PASS | AUTO_LOITER@23.8 → POSCTL@28.8 → AUTO_PRECLAND@60.1 → POSCTL@68.4 |
| 4 | 23.85 | valid — PASS | AUTO_LOITER@23.9 → POSCTL@28.9 → AUTO_PRECLAND@60.5 → POSCTL@66.7 |
| 5 | 23.90 | valid — PASS | AUTO_LOITER@23.9 → POSCTL@28.9 → AUTO_PRECLAND@60.5 → POSCTL@67.1 |
| 6 | 23.86 | valid — PASS | AUTO_LOITER@23.9 → POSCTL@28.9 → AUTO_PRECLAND@60.5 → POSCTL@67.8 |
| 7 | 23.89 | valid — PASS | AUTO_LOITER@23.9 → POSCTL@28.9 → AUTO_PRECLAND@60.5 |
| 8 | 23.87 | **INVALID** (see register) | ALTCTL@18.9 → TERMINATION@23.9 |
| 9 | 23.91 | valid — PASS | AUTO_LOITER@23.9 → POSCTL@28.9 → AUTO_PRECLAND@60.5 → POSCTL@67.2 |
| 10 | 23.88 | valid — PASS | AUTO_LOITER@23.9 → POSCTL@28.9 → AUTO_PRECLAND@60.5 → POSCTL@68.7 |
| 11 (top-up 1) | 23.80 | valid — PASS | AUTO_LOITER@23.8 → POSCTL@28.8 → AUTO_PRECLAND@60.2 → POSCTL@67.4 |
| 12 (top-up 2) | 23.74 | valid — PASS | AUTO_LOITER@23.8 → POSCTL@28.8 → AUTO_PRECLAND@60.4 → POSCTL@68.2 |

Descriptive timing: in all 10 valid B runs the Hold phase (AUTO_LOITER) lasts from RC loss to
loss +5.0 s, after which B returns to the user-intended POSCTL for the rest of the window — the
exact behavior the gate-interpretation amendment was written against.

## Build A — per-run outcomes
Same boot prefix (`AUTO_LOITER@≈-0.1 → POSCTL@11.0`).

| Attempt | Loss @ | Outcome | Mode sequence after POSCTL |
|---|---|---|---|
| 1 | 23.59 | valid — DEFECT+ | AUTO_LOITER@23.6 → AUTO_RTL@28.6 → POSCTL@36.3 (after RTL landing/disarm) |
| 2 | 23.72 | valid — DEFECT+ | AUTO_LOITER@23.7 → AUTO_RTL@28.7 → POSCTL@36.7 |
| 3 | 23.86 | **INVALID** (see register) | ALTCTL@18.8 → TERMINATION@23.8 → AUTO_LAND@23.9 |
| 4 | 23.80 | **INVALID** (see register) | ALTCTL@18.8 → AUTO_TAKEOFF@23.8 → AUTO_LAND@23.8 |
| 5 | 23.88 | valid — DEFECT+ | AUTO_LOITER@23.9 → AUTO_RTL@28.9 → POSCTL@37.4 |
| 6 | 23.89 | valid — DEFECT+ | AUTO_LOITER@23.9 → AUTO_RTL@28.9 → POSCTL@36.7 |
| 7 | 23.72 | valid — DEFECT+ | AUTO_LOITER@23.7 → AUTO_RTL@28.7 → POSCTL@37.2 |
| 8 | 23.84 | valid — DEFECT+ | AUTO_LOITER@23.9 → AUTO_RTL@28.9 → POSCTL@37.3 |
| 9 | 23.75 | valid — DEFECT+ | AUTO_LOITER@23.8 → AUTO_RTL@28.8 → POSCTL@36.0 |
| 10 | 23.79 | valid — DEFECT+ | AUTO_LOITER@23.8 → AUTO_RTL@28.8 → POSCTL@36.6 |
| 11 (top-up 1) | 23.76 | valid — DEFECT+ | AUTO_LOITER@23.8 → AUTO_RTL@28.8 → POSCTL@37.3 |
| 12 (top-up 2) | 23.84 | valid — DEFECT+ | AUTO_LOITER@23.9 → AUTO_RTL@28.9 → POSCTL@36.2 |

Descriptive timing: in all 10 valid A runs, AUTO_RTL appears at RC loss **+5.01–5.02 s** —
exactly the `COM_FAIL_ACT_T` expiry, the moment the Hold action should have engaged — matching
PR #21403's description ("the additional mode check triggers an RTL which takes precedence over
Hold"). Spread across the 10 runs: ≤0.01 s. No valid A run shows Land as the first differing mode.

## Invalid-run register (excluded from scoring, per preregistration)
All four invalid runs share one cause: an **unrelated failsafe intervened before the scripted RC
loss**. In each, at ~18.7–18.9 s (≈5 s before the stream was stopped), the in-log
`failsafe_flags` show `local_position_invalid`, `local_velocity_invalid` and
`global_position_invalid` re-setting (they had cleared at ~7.4 s) with `battery_unhealthy`
setting at the same moment and `vehicle_status.failsafe` asserting — a position-estimate event
in the SIH/EKF chain on this machine, identical in kind on both builds. POSCTL (which requires
local position) fell back to ALTCTL, and when RC loss then arrived with position (and, in B,
altitude) still invalid, Commander escalated to TERMINATION instead of the Hold path. The
scenario's outcome in these runs was decided by that event, not by the failsafe logic under
test, so they carry no evidence about the A/B question in either direction.

| Run | Evidence (times rel. to log start) |
|---|---|
| B attempt 1 | pos/vel/global invalid @18.70; battery_unhealthy @18.82; ALTCTL @18.7; loss @23.68; TERMINATION @23.7 |
| B attempt 8 | pos/vel/global invalid @18.89; battery_unhealthy @18.89; ALTCTL @18.9; loss @23.87; TERMINATION @23.9 |
| A attempt 3 | pos invalid @~18.8; battery_unhealthy @18.88; ALTCTL @18.8; loss @23.86; TERMINATION @23.8 → AUTO_LAND @23.9 |
| A attempt 4 | pos invalid @~18.8; battery_unhealthy @18.94; ALTCTL @18.8; loss @23.80; AUTO_TAKEOFF @23.8 → AUTO_LAND @23.8 |

Notes on classification honesty:
- `batch_run.py`'s built-in validity check (setpoint-stream gap + lost-flag transition) counts
  these four runs as "valid" — the RC-loss injection itself *was* verified in their logs. The
  preregistration additionally excludes runs with **unrelated failsafes intervening**; that
  exclusion was applied here, in the write-up, from the `failsafe_flags` timelines quoted above.
  The runner summary JSONs on disk are **unmodified**; the reclassification exists only in this
  report, with its evidence, and the top-up runs it triggered stayed inside the 15-attempt cap
  (12 used per build). Gate readings in the write-up rather than the runner is also the runner's
  own documented design ("Gate readings are computed in the write-up, not here").
- A attempts 3–4 superficially contain AUTO_LAND after RC loss. That Land follows the
  Termination/position-loss event, is not preceded by a Hold phase, and is **not** counted as
  defect evidence. A's 10/10 rests only on the clean runs' AUTO_RTL signature.

## Anomalies and limits
1. **Recurring estimator event (4 of 24 attempts, both builds):** the mid-flight position-estimate
   loss described above struck at a strikingly consistent ~18.7–18.9 s into the run.
   `estimator_status` innovation/health flags stayed 0 throughout, so the invalidity surfaced via
   the Commander health checks rather than an EKF innovation failure; the precise root cause
   (SIH sensor timing under this 2-core VM's load is a plausible contributor) was not pinned down
   and is recorded as an open environment quirk. It is build-independent (2 hits per build) and
   therefore cannot manufacture the A/B contrast; its cost was 4 attempts of cap headroom.
2. **Zero measured noise floor on the scored observables:** all 10 valid control (B) runs produce
   the identical categorical sequence, and all 10 valid A runs produce the identical defect
   sequence with ≤0.01 s timing spread. On *this* scenario the harness separates the builds
   perfectly; this says nothing about noisier scenarios, other regressions, or real hardware —
   10 runs per build are feasibility acceptance counts, not reliability rates (per preregistration).
3. **Venue scope:** this batch ran on the VM venue (SIH, 35 s window, departure rule). The
   vermithor venue scores under its own frozen `SCORING_RULES.md` (25 s window); the two venues'
   rule sets and results are reported separately and are not merged here.
4. **Baseline context (Phase 0):** PX4's own `failsafe_test` passes identically on both commits
   and structurally cannot reach the defective code path — so the difference this batch flags is
   one the existing test suite does not surface, which is the experiment's decisive question
   answered in the affirmative **for this case**.

## Artifact index (this directory)
- `batch_B/`, `batch_B_topup/` — B attempts 1–10 and top-ups 1–2 (ULogs + px4 console logs per run).
- `batch_A/`, `batch_A_topup/` — A attempts 1–10 and top-ups 1–2.
- `batch_B_summary.json` / `batch_A_summary.json` (inside the batch dirs) and the two top-up
  summaries — runner output, unmodified.
- `batch_B_console.log`, `batch_A_console.log`, `batch_B_topup_console.log`,
  `batch_A_topup_console.log` — runner console transcripts.
- `PHASE0_REPORT.md` — environment, commit verification, baseline results, smoke evidence.
