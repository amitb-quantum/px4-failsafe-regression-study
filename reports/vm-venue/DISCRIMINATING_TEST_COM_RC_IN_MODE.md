# Discriminating test — COM_RC_IN_MODE as the venue-difference candidate
**Labeled post-experiment diagnostic, 2026-10-24. NOT a scored run, NOT a reopening
of the batch. Scored results in `BATCH_REPORT.md` are unchanged.**

## Question
In the VM scored batch, fixed Build B (`aa5b9ae638`) returned from AUTO_LOITER to
POSCTL at exactly RC loss +5.0 s, with `vehicle_status.failsafe` clearing (1→0)
while `manual_control_signal_lost` stayed set. On vermithor, Build B sustained
AUTO_LOITER for the full window and the failsafe never cleared. One scenario
parameter genuinely differed between venues: COM_RC_IN_MODE — VM default 3
("RC or Joystick, keep first"), vermithor explicitly 1 ("Joystick only", read back
in all 21 runs).

## Prediction (fixed before the run)
- **HOLDS** if, with COM_RC_IN_MODE=1, the failsafe stays set (failsafe=1) and
  AUTO_LOITER sustains through the 35 s window with no POSCTL return.
- **REFUTED** if the failsafe clears at ~+5.0 s and the vehicle returns to POSCTL
  as in the scored batch.

## Method (identical to the scored batch except the one parameter)
- Build: `~/workspace/px4-experiment/PX4-Autopilot/build/px4_sitl_default`
  (Build B, `aa5b9ae638`), SIH `sihsim_quadx`, fresh rootfs per attempt.
- Driver: `discriminating_run.py` = `smoke_run.py` verbatim except (a) the
  parameter list gains `("COM_RC_IN_MODE", 1)`, and (b) a mandatory readback
  block (request each parameter's value, abort on mismatch). All other
  parameters, timing, and scenario steps are unchanged: NAV_RCL_ACT=1,
  RC_MAP_ROLL/PITCH/THROTTLE/YAW=1/2/3/4, COM_FAIL_ACT_T=5.0 s,
  COM_RC_LOSS_T=0.5 s, Position mode, neutral sticks, MAVLink MANUAL_CONTROL
  stream established then stopped, telemetry alive, 35 s window.
- Runs live in `disc_B_com_rc_in_mode/` (separate from `batch_B/`/`batch_A/`,
  which were not touched). Analysis is from the ULog in each run dir.

## Attempt 0 — driver bug, no flight (not counted as an attempt)
The first launch crashed in the readback block (`param_id` is already a `str`
in this pymavlink version; the code called `.decode()` on it). PX4 shut down
cleanly before arming. Fixed by handling both `str` and `bytes`, and re-ran.

## Attempt 1 — arming denied (invalid, unrelated to the failsafe under test)
- Run dir: `disc_B_com_rc_in_mode/attempt01`, ULog `log/2026-10-24/16_43_46.ulg`.
- **Parameter readback (all landed, including the test parameter):**
  `NAV_RCL_ACT=1, RC_MAP_ROLL=1, RC_MAP_PITCH=2, RC_MAP_THROTTLE=3,
  RC_MAP_YAW=4, COM_RC_IN_MODE=1`. No type-mismatch correction was needed.
- Manual-control stream: 5 `manual_control_setpoint` samples, valid values
  seen, data_source 7 (same as the scored batch).
- ULog timeline (changes only):
  - t=0.00 nav=AUTO_LOITER, arm=standby, failsafe=0, preflight_pass=0
  - t=7.30 preflight_pass=1
  - t=11.56 nav=POSCTL, `manual_control_signal_lost` 1→0, preflight_pass=1
  - t=11.78 `manual_control_signal_lost` 1 (set again), t=11.89 preflight_pass=0
- Outcome: arming denied on all 40 MAVLink attempts and on the `commander arm`
  fallback (repeated negative tone). The vehicle never armed, so the scenario
  never reached RC loss. Invalid for the discriminating question.

## Attempt 2 — replacement attempt, same outcome (invalid, same reason)
- Run dir: `disc_B_com_rc_in_mode/attempt02`, ULog `log/2026-10-24/16_45_32.ulg`.
- Parameter readback identical to attempt 1, COM_RC_IN_MODE=1 confirmed landed.
- ULog timeline (changes only):
  - t=0.00 nav=AUTO_LOITER, arm=standby, failsafe=0, preflight_pass=0
  - t=7.51 preflight_pass=1
  - t=11.56 nav=POSCTL, `manual_control_signal_lost` 1→0, preflight_pass=1
  - t=11.84 `manual_control_signal_lost` 1 (set again), t=11.95 preflight_pass=0
- Outcome: arming denied identically. No flight, no RC-loss window.

## Verdict
**The prediction is neither confirmed nor refuted: the test could not be executed,
because on this VM's transport (MAVLink MANUAL_CONTROL over a serial-PTY second
mavlink instance), COM_RC_IN_MODE=1 systematically breaks sustained manual-control
validity — the stream validates for ~0.2 s and then drops, preflight fails, and
arming is denied in 2/2 attempts — whereas the same driver and stream armed in
24/24 scored-batch attempts under the default COM_RC_IN_MODE=3, and the same
parameter value armed fine on vermithor's UDP GCS link.**

## What this does and does not establish
- It **does** establish that COM_RC_IN_MODE is not behavior-neutral across
  transports: on the VM it changes the arming path itself (manual-control
  validity collapses ~0.2 s after first validation, deterministically timed in
  both attempts), so the venue difference cannot be attributed to this parameter
  by this test — and, importantly, the original cross-venue verdict is
  unaffected: both venues' gates fired (B passes, A departs to RTL at the
  delay expiry) under their own frozen rules, and the departure-based defect
  verdict does not depend on what Build B does after the delay.
- It **does not** establish whether COM_RC_IN_MODE explains the failsafe-clear
  difference, because the scenario never reached the RC-loss window under
  COM_RC_IN_MODE=1 on this transport. The mechanism by which the selector drops
  the serial-instance MANUAL_CONTROL stream under mode 1 (source-classification
  vs instance handling) is unverified and would need source-level investigation
  of the manual-control selector — out of scope for this diagnostic.
- It **does not** change any scored result, parameter set, or conclusion of the
  closed experiment. No further runs were made: the authorized allowance was
  one attempt plus one replacement, and both are reported above.
