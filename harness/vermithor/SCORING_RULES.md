# Scoring and validity rules — frozen 2026-10-23, BEFORE any scored run

Implements the preregistration (amended 2026-10-23) for the scored batch. Written after
the exploratory smokes (smoke-B-01, smoke-B-02, smoke-A-01) and before scored attempt 1.
Applied automatically by `score.py`; any later change is an amendment logged in SETUP_NOTES.

Everything below is read from the run's ULog (all times = seconds since ULog start).
Script prints are never used for scoring.

## Definitions
- **Valid manual-control sample:** `manual_control_setpoint` with `valid=1` and
  `data_source=2` (MAVLink instance 0 = the harness stream).
- **last_valid:** time of the last valid manual-control sample.
- **t_loss (RC loss, verified from the signal itself):** first 0→1 edge of
  `failsafe_flags.manual_control_signal_lost` after `last_valid`.
- **Observation window W = [t_loss, t_loss + 25.0 s].** Rationale (Phase 0, from
  historical source and params.json): COM_RC_LOSS_T 0.5 s + COM_FAIL_ACT_T 5.0 s = 5.5 s;
  25 s is more than 4× that and fits inside the scenario's 30 s post-stop observation.
- **t_arm:** first `vehicle_status.arming_state` = 2.

## Validity (all must hold; otherwise INVALID with the first failing reason)
1. **Log present:** exactly one new ULog for the attempt, parseable, containing
   `vehicle_status`, `failsafe_flags`, `manual_control_setpoint`.
2. **Valid manual control established:** ≥ 50 valid manual-control samples logged, and
   `manual_control_signal_lost` had a 1→0 edge (stream acquired) before t_arm.
3. **RC loss verified from the signal:** t_loss exists, `t_loss − last_valid ≤ 2.0 s`, and
   no valid manual-control sample is logged after t_loss.
4. **Scenario precondition at loss (not the outcome):** at the last `vehicle_status`
   sample before t_loss, nav_state = 2 (POSCTL) and arming_state = 2 (armed); SIH
   ground-truth altitude at t_loss ≥ 3.0 m.
5. **No unrelated failsafe:** no `failsafe_flags` field other than
   `manual_control_signal_lost` (and excluding `mode_req_*` masks) has a 0→1 edge in
   [t_arm, end of W].
6. **Window covered:** the log extends to the end of W, OR the log ends earlier because
   the vehicle disarmed after a departure from Hold already observed inside W
   (SDLOG_MODE=1 stops logging at disarm). A log that ends early with no departure is
   INVALID (truncated).

## Outcome (valid runs only), from the `vehicle_status.nav_state` sequence inside W
The full mode sequence in W is recorded with timestamps for every run.
- **SUSTAINED_HOLD:** nav_state enters 4 (AUTO_LOITER) inside W and stays 4, armed,
  until the end of W.
- **DEPARTED_RTL:** nav_state 5 (AUTO_RTL) occurs inside W (AUTO_LAND or disarm may
  follow; same departure).
- **OTHER:** anything else (e.g. never Hold, departure to Land without RTL, disarm while
  in Hold). Counts as neither outcome; reported with its sequence.

Descriptive timing (no significance claims): time from t_loss to Hold entry; time in Hold
before departure (A); per-build min/median/max.

## Gate (from the preregistration, unchanged)
- Build B: SUSTAINED_HOLD in ≥ 9 of 10 valid runs.
- Build A: DEPARTED_RTL in ≥ 8 of 10 valid runs.
- Meaningful difference flagged iff both hold.

## Batch protocol
- Build B first, attempts B-01..B-15, stopping at 10 valid; then Build A, A-01..A-15,
  stopping at 10 valid. Every invocation of run_once.py counts as an attempt, including
  harness aborts. Validity is decided by score.py right after each attempt.
- Same harness files (sha256 recorded per run), same params.json, every run.
- If the cap is hit before 10 valid, the shortfall is reported as a finding.
