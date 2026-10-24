# PX4 build-comparison feasibility experiment — write-up

Date: 2026-10-23 (local; ULog/UTC timestamps 2026-10-24). Host: vermithor (WSL2, Ubuntu 26.04).
Governing document: `prereg/px4-feasibility-experiment-prereg-2026-10-23.md` (with its 2026-10-23
amendments). Detailed results: `reports/comparison-report.md`. Deviation log: `SETUP_NOTES.md`.

## What was tested

The narrow proposition in the preregistration: given two PX4 builds, can a harness automatically
identify a meaningful change in tested behavior, with enough evidence for an engineer to
reproduce and investigate it, beyond what PX4's own tests report and without flagging
simulation noise?

- **Case:** PX4 PR #21403 ("fix failsafe: correctly handle Hold RC loss action"). Build A
  `f7ed553f57d40073f0f3f3487509e6448a7727e6` (regression) vs Build B
  `aa5b9ae638f1bf412102de8fabd06740c725abf1` (fix). Adjacent commits; the diff is one removed line
  in `FailsafeBase::modeCanRun()` (`framework.cpp`).
- **Baseline, run before the simulation batch:** PX4's `functional-failsafe_test` passes on both
  commits (`reports/baseline-A.txt`, `baseline-B.txt`). The test's `FailsafeTester` overrides
  `checkModeFallback()` to return `Action::None`. That function is exactly where Build A's
  escalation to RTL is produced (see Mechanism), so the defect is unreachable from that test. The
  preregistered stopping rule did not fire.
- **Venue (amended):** PX4's built-in SIH simulator, `sihsim_quadx`, headless. Both builds use
  the same toolchain recipe, and PX4 source is untouched.
- **Scenario:** Position mode, neutral sticks, a MAVLink manual-control stream (20 Hz)
  established before arming, climb to ~7 m, a GCS heartbeat kept alive throughout, then stop
  only the manual-control stream. An explicit parameter set (`harness/params.json`, including
  NAV_RCL_ACT=1 Hold) is applied and read back at the start of every run.
- **Scoring:** from the ULog only, by rules frozen before the first scored run
  (`harness/SCORING_RULES.md`):
  - RC loss is verified from `manual_control_signal_lost` after the last valid manual-control
    sample, not from the resulting mode.
  - The outcome is the sustained mode sequence over a 25 s window, where COM_RC_LOSS_T +
    COM_FAIL_ACT_T = 5.5 s.

## What the gate returned

| | Build B (fixed, control) | Build A (regression) |
|---|---|---|
| Attempts / valid / invalid (cap 15) | 11 / 10 / 1 | 10 / 10 / 0 |
| Sustained Hold through the window | **10 / 10** | 0 / 10 |
| Departed Hold to RTL in the window | 0 / 10 | **10 / 10** |
| Preregistered condition | ≥ 9/10 Hold: **met** | ≥ 8/10 RTL: **met** |

**Meaningful difference flagged** under the preregistered rule.

Both builds enter Hold 0.012 s after the verified RC loss. Build A leaves Hold for AUTO_RTL
exactly 5.0 s later (= COM_FAIL_ACT_T) in every valid run, then lands and auto-disarms. Build B
stays in Hold, armed, through the window with no further state change. The control runs (Build
B) were identical in categorical outcome and near-identical in timing (RC-loss lag 0.28–0.30 s,
altitude at loss 6.79–6.93 m), so the A/B difference is not near the noise floor in this venue.

**Mechanism.** It is read from logs plus source; this is analyst reasoning, not generated output.
It corrects the earlier wording that "Hold was judged unrunnable".
- AUTO_LOITER does not require manual control. The logged `mode_req_manual_control` = 0x8407
  covers MANUAL, ALTCTL, POSCTL, ACRO and STAB.
- The removed term instead made the user's intended mode, POSCTL, and its fallbacks unrunnable.
  `checkModeFallback()` then ended in its "intended mode cannot run → RTL" branch, which overrides
  the configured Hold once the delay expires.

**Evidence chain:** every number in the comparison report traces back to:
- per-run ULogs with their sha256;
- the commit hashes, which are verified per run against both the worktree HEAD and the binary's
  embedded version;
- the binary sha256 (one value per build across all runs);
- `params.json` with a readback per run;
- the frozen harness hashes in `SETUP_NOTES.md`, which every run's `run.json` matches.

A run is reproduced with `harness/run_once.py` + `harness/score.py`.

## Invalid runs (reported separately)

**B-04: SITL sensor-publication stall at arming** (baro, mag, GPS, battery, cpuload stop
publishing; the EKF dead-reckons; PX4 falls back POSCTL → ALTCTL → STAB before RC loss). It is
excluded under the frozen rules. Root cause not determined; it is shared simulator
infrastructure, unrelated to the failsafe code, 1 of 21 scored attempts.

## Reconciliation item: second machine's Build B returning to POSCTL

On vermithor, all 10 valid Build B runs log the same sequence: POSCTL → AUTO_LOITER at
t_loss + 0.012 s, then no change (nav_state, arming, failsafe, user intention) through the window
and to log end. Nothing is logged at t_loss + 5 s. Checked in the requested order:
- **(a) Parameters:** identical across all 21 scored runs (779 compared), readback correct, none
  changed in-log.
- **(b) Telemetry:** a GCS heartbeat is present on every sample in the window, no datalink loss,
  and manual control never regained.
- **(c) Harness:** the harness sends no commands after RC loss, there is no user takeover, and it
  stops ~3.9 s after the window ends.

**The cause of the second machine's observation is not identifiable from vermithor's logs.** It
stands as an unexplained venue/harness difference. From Build B's source, only two PX4 paths lead
from that Hold back to POSCTL, and each has a specific log signature to check in the other
machine's ULogs (details in the comparison report):
- manual control regained: `manual_control_signal_lost` 1→0;
- any mode-change request after loss, which Build B honors as a takeover into POSCTL even without
  manual control: `vehicle_command` 176 / `failsafe_and_user_took_over` = 1.

If the observation came from live HEARTBEAT decoding rather than the ULog, rule out a sub-mode
decoding slip first.

## Limits

- **SIH's injected sensor noise exceeds EKF2's default noise model.** Diagnosed from the
  pre-batch log (`sih.cpp:440-441`: accel σ 0.5/1.7/1.4 m/s², gyro σ 0.14/0.07/0.03 rad/s vs
  EKF2_ACC_NOISE 0.35, EKF2_GYR_NOISE 0.015). It causes ±5° attitude wander, accel-bias
  saturation, ~1 m/s velocity drift on a stationary vehicle and intermittent preflight failures.
  It is identical across builds (the A..B diff touches neither SIH nor EKF2) and was handled
  without parameter or source changes or force-arming. It does mean this venue is noisier than
  real hardware or tuned sims, and timing observables are SIH-specific.
- **One historical regression case only.** It is a clean, discrete, mode-level defect with a
  5 s deterministic signature. Nothing here shows the harness would separate subtler, continuous
  or intermittent regressions from noise. The preregistered fallback case (EKF2 GPS-fusion) was
  not run.
- **The gate is a feasibility acceptance rule, not a reliability statistic.** 10 valid runs per
  build cannot establish rates; 10/10 and 0/10 support "consistently different in this setup",
  nothing more.
- **Cross-venue disagreement on Build B is unresolved.** A second machine saw a different Build B
  sequence. Until explained, the result should be read as holding for this venue and harness, not
  as a venue-independent behavioral claim.
- **The "automatic" explanation is partly automatic.** The report generates the behavioral
  difference, the per-run evidence, the code diff and the logged values of the flags the diff
  references. Mapping them to the `checkModeFallback()` path was analyst work from source. The
  flag extraction relies on the diff naming `status_flags.*` fields, a pattern that suits this
  case and is not general.
- **Baseline breadth.** Only `functional-failsafe_test` was run as PX4's own coverage. Other CI
  (e.g. MAVSDK SITL integration tests) was not run at these commits.
- **Harness iterated during smoke.** The scenario changed v1 → v2 → v2.1 before the freeze,
  driven by smoke observations including the low-altitude smoke-B-01. All of this is logged and
  happened before any scored run, but the smokes informed the scenario.
- **Venue and layout deviations** (SIH instead of Gazebo x500, toolchain pins, build-A location,
  daemon-mode launch) are logged in `SETUP_NOTES.md` and applied identically to both builds.
- **Commercial demand remains unproven.** This experiment did not test it, and the result says
  nothing about it.

## Status

The experiment ends with this report. No further cases, sprints or write-ups were started. What
happens next is Amit's decision. `SETUP_NOTES.md` is complete through the final scored run (A-10)
and report generation.

## Post-experiment diagnostics on the venue difference (2026-10-24; labelled, not scored)

These two diagnostics were run after the experiment closed. They do not touch any scored result
or the gate.

**(1) VM test, Build B with `COM_RC_IN_MODE=1` (as reported from the VM; not re-checked on
vermithor): neither confirmed nor refuted.**
- On the VM's serial-PTY transport, mode 1 let the MANUAL_CONTROL stream validate for only
  ~0.2 s before dropping it, and arming was denied in both attempts, so the run never reached the
  RC-loss window.
- It established that the parameter is not behavior-neutral across transports. It did not test
  whether the parameter explains the venue difference.

**(2) Vermithor reciprocal test, Build B with `COM_RC_IN_MODE=3` (the VM default): REFUTED.**
- **Setup:** one attempt (`runs/diagnostic/diag-B-rcin3-01/`), identical to the scored batch
  (same commit, binary, scenario script and other parameters) except COM_RC_IN_MODE=3.
- **Parameter confirmed before flight:** set 1 → 3, read back as `3` and in use before the scenario
  started; the ULog also records the change. Applied at runtime per `ManualControl.cpp:91`.
- **Valid under the frozen rules:** 106 valid MAVLink manual-control samples, RC loss verified
  0.30 s after the last one, 6.91 m altitude, no other failsafe. No replacement attempt was needed.
- **Outcome:** POSCTL → AUTO_LOITER at t_loss + 0.012 s (ULog 41.112 s), then:
  - `failsafe` = 1 and `manual_control_signal_lost` = 1 through the whole window;
  - no takeover; user intention stays POSCTL;
  - no harness command after RC loss, nothing logged at +5 s;
  - log continues to 70.0 s.
- **Reading:** this is the same sequence as all 10 scored Build B runs. Against the prediction
  fixed before the run, the failsafe did not clear and Hold was sustained.

**Final status of the venue difference: still open.** COM_RC_IN_MODE (1 vs 3) does not explain
it. On vermithor's UDP transport, the two values produce identical Build B behavior in this
scenario (n = 1 for mode 3). Per the preregistered reading, the difference lies in the
transport/link setup, which has not been characterized. Whether the VM's Build B POSCTL return
comes from manual control being regained or from a mode-change takeover can only be settled from
the VM's ULogs (signatures in `comparison-report.md`). The experiment remains closed.
