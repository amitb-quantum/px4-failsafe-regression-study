# PX4 A/B comparison report — RC-loss Hold (PR #21403)

_Generated automatically by `harness/report.py` from ULog-derived `score.json` files. Rules: `harness/SCORING_RULES.md` (frozen before scored runs)._

## Verdict

**Meaningful behavioral difference FLAGGED** — both preregistered gate conditions hold.

| | Build B (fixed, control) | Build A (regression) |
|---|---|---|
| Commit | `aa5b9ae638` | `f7ed553f57` |
| Attempts / valid / invalid | 11 / 10 / 1 | 10 / 10 / 0 |
| SUSTAINED_HOLD (valid runs) | **10/10** | 0/10 |
| DEPARTED_RTL (valid runs) | 0/10 | **10/10** |
| OTHER (valid runs) | 0 | 0 |
| Gate condition | B ≥ 9/10 Hold: **MET** | A ≥ 8/10 RTL: **MET** |

## Differing observable

`vehicle_status.nav_state` inside the 25 s window after RC loss (RC loss = 0→1 edge of `failsafe_flags.manual_control_signal_lost` after the last valid MAVLink manual-control sample).

- RC-loss lag after last logged valid sample — B: min 0.28 / median 0.30 / max 0.30 s (n=10); A: min 0.29 / median 0.29 / max 0.31 s (n=10)
- RC loss → Hold entry — B: min 0.01 / median 0.01 / max 0.01 s (n=10); A: min 0.01 / median 0.01 / max 0.01 s (n=10)
- Time in Hold before departure — A: min 5.00 / median 5.00 / max 5.00 s (n=10); B: 0 departures
- Altitude at RC loss (SIH ground truth) — B: min 6.79 / median 6.89 / max 6.93 m (n=10); A: min 6.55 / median 6.90 / max 6.94 m (n=10)

Control variation (Build B, the noise floor): every valid B run's mode sequence is listed below; the categorical outcome is what the gate scores.

## Candidate cause (automatic: code diff between the builds)

```
src/modules/commander/failsafe/framework.cpp | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```
```diff
diff --git a/src/modules/commander/failsafe/framework.cpp b/src/modules/commander/failsafe/framework.cpp
index 9ef1a232c1..88123548a7 100644
--- a/src/modules/commander/failsafe/framework.cpp
+++ b/src/modules/commander/failsafe/framework.cpp
@@ -646,6 +646,7 @@ bool FailsafeBase::modeCanRun(const failsafe_flags_s &status_flags, uint8_t mode
 {
 	uint32_t mode_mask = 1u << mode;
 	// mode_req_wind_and_flight_time_compliance: does not need to be handled here (these are separate failsafe triggers)
+	// mode_req_manual_control: is handled separately
 	return
 		(!status_flags.angular_velocity_invalid || ((status_flags.mode_req_angular_velocity & mode_mask) == 0)) &&
 		(!status_flags.attitude_invalid || ((status_flags.mode_req_attitude & mode_mask) == 0)) &&
@@ -656,7 +657,6 @@ bool FailsafeBase::modeCanRun(const failsafe_flags_s &status_flags, uint8_t mode
 		(!status_flags.auto_mission_missing || ((status_flags.mode_req_mission & mode_mask) == 0)) &&
 		(!status_flags.offboard_control_signal_lost || ((status_flags.mode_req_offboard_signal & mode_mask) == 0)) &&
 		(!status_flags.home_position_invalid || ((status_flags.mode_req_home_position & mode_mask) == 0)) &&
-		(!status_flags.manual_control_signal_lost || ((status_flags.mode_req_manual_control & mode_mask) == 0)) &&
 		((status_flags.mode_req_other & mode_mask) == 0);
 }
```

Logged values of the `failsafe_flags` fields referenced by the changed lines, at the A departure (run A-01, t=46.11s):

- `manual_control_signal_lost` = 1
- `mode_req_manual_control` = 0x8407 → modes requiring it: MANUAL, ALTCTL, POSCTL, ACRO, STAB

Reading (analyst, from source at both commits — not generated): AUTO_LOITER is **not** in the manual-control requirement mask, so Hold itself stays runnable. The removed term instead makes the user's intended mode POSCTL — and its fallbacks ALTCTL and STAB, all in the mask — unrunnable while `manual_control_signal_lost`=1. `Failsafe::checkModeFallback()` then walks POSCTL→ALTCTL→STAB and ends at its final 'intended mode cannot run' branch, returning RTL, which outranks the configured RC-loss Hold once the COM_FAIL_ACT_T hold expires. In Build B, manual-control loss is left to the RC-loss failsafe alone ("handled separately"), so Hold stands. This is the function the historical `FailsafeTester` overrides to return `Action::None`, which is why PX4's own test cannot see it.

## Evidence (reproduce)

- Harness: `~/px4-regression/harness/` — scenario `smoke_manual_control.py`, launcher `run_once.py`, params `params.json`, rules `SCORING_RULES.md`, scorer `score.py`; frozen sha256 in `SETUP_NOTES.md`.
- Reproduce one run: `conda activate px4-regression && python harness/run_once.py --build {A|B} --kind scored --label <new> && python harness/score.py runs/scored/<new>`
- Build: both worktrees, `px4_sitl_default`, toolchain recipe in `SETUP_NOTES.md`; venue SIH `sihsim_quadx`, headless.

Parameter set (applied and read back every run): `NAV_RCL_ACT=1`, `COM_RC_IN_MODE=1`, `COM_RC_LOSS_T=0.5`, `COM_FAIL_ACT_T=5.0`, `COM_RCL_EXCEPT=0`, `NAV_DLL_ACT=0`, `COM_DL_LOSS_T=10`, `COM_DISARM_PRFLT=10.0`

Harness files frozen before scored attempt 1 (sha256 from `SETUP_NOTES.md`):

- `smoke_manual_control.py`: `fe96833dec74d19abe3bbe65bbab51347ab7cad23e9a94d05262518aabe875a0`
- `run_once.py`: `ae75cdc605520324c8f5dcc314af61bc4a0686178db1b87880ef482776c57891`
- `ulog_check.py`: `19f1200caee008cb437b31bf4dc5835f68ff78bf946a821af174176f60edf709`
- `score.py`: `0dac4661f6c065b0c77980c3d3d018ac34affe8aba62061453c0fb820ef36d56`
- `batch.py`: `ce6ae68540492edc48e7d2791c9dfd0db5a320a628336029b2a0674c3b3eb5e1`
- `params.json`: `83688d3b7987005b37d0885f54f46b19b24905d44d07cae4f76e28f3146d10ff`
- `SCORING_RULES.md`: `f4a414c48885e217179ec9fcb9fa556130f1f8b5f71c7deacfe5922b3c279071`

Per-run check (from each `run.json`): scenario/params/launcher hashes equal the frozen values in every attempt: **True**. Binary sha256 prefix per build: A ['84081f57a8cb43c3'], B ['83e2029d2533aa15']; embedded git version: A ['f7ed553f57d40073f0f3f3487509e6448a7727e6'], B ['aa5b9ae638f1bf412102de8fabd06740c725abf1'].

Times below are ULog seconds since log start; offsets are from the verified RC-loss edge (t_loss). W = [t_loss, t_loss + 25 s].

### Build B runs

| Attempt | Valid | Outcome / invalid reason | Full mode sequence in W | Arm attempts | ULog (sha256 prefix) |
|---|---|---|---|---|---|
| B-01 | yes | SUSTAINED_HOLD | POSCTL @ 41.100 s (+0.000) → AUTO_LOITER @ 41.112 s (+0.012) → held to W end @ 66.100 s (log continues to 70.028 s) | 1 | `runs/scored/B-01/2026-10-24_00_12_56.ulg` (d6150143b391) |
| B-02 | yes | SUSTAINED_HOLD | POSCTL @ 41.096 s (+0.000) → AUTO_LOITER @ 41.108 s (+0.012) → held to W end @ 66.096 s (log continues to 70.020 s) | 1 | `runs/scored/B-02/2026-10-24_00_14_08.ulg` (3428e113cc58) |
| B-03 | yes | SUSTAINED_HOLD | POSCTL @ 41.100 s (+0.000) → AUTO_LOITER @ 41.112 s (+0.012) → held to W end @ 66.100 s (log continues to 70.020 s) | 1 | `runs/scored/B-03/2026-10-24_00_15_21.ulg` (c3031f15a5ef) |
| B-04 | NO | V4 precondition: at loss nav=15 arm=2 (need POSCTL, armed) |  | 1 | `runs/scored/B-04/2026-10-24_00_16_33.ulg` (4d8438f85eed) |
| B-05 | yes | SUSTAINED_HOLD | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → held to W end @ 66.104 s (log continues to 70.068 s) | 1 | `runs/scored/B-05/2026-10-24_00_17_45.ulg` (30ea72c95f02) |
| B-06 | yes | SUSTAINED_HOLD | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → held to W end @ 66.104 s (log continues to 70.052 s) | 1 | `runs/scored/B-06/2026-10-24_00_18_58.ulg` (46a2abab54ee) |
| B-07 | yes | SUSTAINED_HOLD | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → held to W end @ 66.104 s (log continues to 70.028 s) | 1 | `runs/scored/B-07/2026-10-24_00_20_10.ulg` (60022aa898df) |
| B-08 | yes | SUSTAINED_HOLD | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → held to W end @ 66.104 s (log continues to 69.980 s) | 1 | `runs/scored/B-08/2026-10-24_00_21_22.ulg` (2dc47b038edc) |
| B-09 | yes | SUSTAINED_HOLD | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → held to W end @ 66.104 s (log continues to 70.004 s) | 1 | `runs/scored/B-09/2026-10-24_00_22_35.ulg` (c10bdde6bf4c) |
| B-10 | yes | SUSTAINED_HOLD | POSCTL @ 41.096 s (+0.000) → AUTO_LOITER @ 41.108 s (+0.012) → held to W end @ 66.096 s (log continues to 70.044 s) | 1 | `runs/scored/B-10/2026-10-24_00_23_47.ulg` (3f2c2f4b2fbf) |
| B-11 | yes | SUSTAINED_HOLD | POSCTL @ 41.100 s (+0.000) → AUTO_LOITER @ 41.112 s (+0.012) → held to W end @ 66.100 s (log continues to 70.024 s) | 1 | `runs/scored/B-11/2026-10-24_00_24_59.ulg` (5db23fcdd62a) |

### Build A runs

| Attempt | Valid | Outcome / invalid reason | Full mode sequence in W | Arm attempts | ULog (sha256 prefix) |
|---|---|---|---|---|---|
| A-01 | yes | DEPARTED_RTL | POSCTL @ 41.096 s (+0.000) → AUTO_LOITER @ 41.108 s (+0.012) → AUTO_RTL @ 46.112 s (+5.016) → POSCTL (disarmed) @ 61.376 s (+20.280) → log ends @ 62.372 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-01/2026-10-24_00_26_19.ulg` (ba8895a4ad12) |
| A-02 | yes | DEPARTED_RTL | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → AUTO_RTL @ 46.120 s (+5.016) → POSCTL (disarmed) @ 61.468 s (+20.364) → log ends @ 62.464 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-02/2026-10-24_00_27_32.ulg` (dfaba8e86d37) |
| A-03 | yes | DEPARTED_RTL | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → AUTO_RTL @ 46.120 s (+5.016) → POSCTL (disarmed) @ 61.480 s (+20.376) → log ends @ 62.480 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-03/2026-10-24_00_28_44.ulg` (d57bfac1d4cb) |
| A-04 | yes | DEPARTED_RTL | POSCTL @ 41.100 s (+0.000) → AUTO_LOITER @ 41.112 s (+0.012) → AUTO_RTL @ 46.116 s (+5.016) → POSCTL (disarmed) @ 61.476 s (+20.376) → log ends @ 62.476 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-04/2026-10-24_00_29_56.ulg` (672dca69485e) |
| A-05 | yes | DEPARTED_RTL | POSCTL @ 41.096 s (+0.000) → AUTO_LOITER @ 41.108 s (+0.012) → AUTO_RTL @ 46.112 s (+5.016) → POSCTL (disarmed) @ 61.436 s (+20.340) → log ends @ 62.432 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-05/2026-10-24_00_31_09.ulg` (7864100930a3) |
| A-06 | yes | DEPARTED_RTL | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → AUTO_RTL @ 46.120 s (+5.016) → POSCTL (disarmed) @ 61.396 s (+20.292) → log ends @ 62.392 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-06/2026-10-24_00_32_21.ulg` (15754f62a56c) |
| A-07 | yes | DEPARTED_RTL | POSCTL @ 41.100 s (+0.000) → AUTO_LOITER @ 41.112 s (+0.012) → AUTO_RTL @ 46.116 s (+5.016) → POSCTL (disarmed) @ 61.476 s (+20.376) → log ends @ 62.476 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-07/2026-10-24_00_33_33.ulg` (a3886fff4203) |
| A-08 | yes | DEPARTED_RTL | POSCTL @ 41.104 s (+0.000) → AUTO_LOITER @ 41.116 s (+0.012) → AUTO_RTL @ 46.120 s (+5.016) → POSCTL (disarmed) @ 61.480 s (+20.376) → log ends @ 62.480 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-08/2026-10-24_00_34_45.ulg` (6605b2a67193) |
| A-09 | yes | DEPARTED_RTL | POSCTL @ 41.100 s (+0.000) → AUTO_LOITER @ 41.112 s (+0.012) → AUTO_RTL @ 46.116 s (+5.016) → POSCTL (disarmed) @ 61.488 s (+20.388) → log ends @ 62.488 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-09/2026-10-24_00_35_58.ulg` (c0f7e413dcc2) |
| A-10 | yes | DEPARTED_RTL | POSCTL @ 41.100 s (+0.000) → AUTO_LOITER @ 41.112 s (+0.012) → AUTO_RTL @ 46.116 s (+5.016) → POSCTL (disarmed) @ 61.776 s (+20.676) → log ends @ 62.776 s (disarm; SDLOG_MODE=1) | 1 | `runs/scored/A-10/2026-10-24_00_37_10.ulg` (96d04635e28d) |

### Invalid attempts (excluded from scoring): 1

- B-04: V4 precondition: at loss nav=15 arm=2 (need POSCTL, armed)

## Reconciliation checks (automatic: `harness/reconcile.py`)

### (a) Parameter sets

- Explicit set read back OK in every scored run with a log: **True** (21 runs).
- Parameters changed during any log: none.
- Full ULog parameter sets compared across all 21 runs (779 parameters, excluding volatile bookkeeping/calibration prefixes LND_FLIGHT_T_, COM_FLIGHT_UUID, SYS_RESTART_TYPE, CAL_, SENS_BOARD_, TC_, EKF2_MAGBIAS_, EKF2_MAG_DECL, BAT1_V_LOAD, COM_ARM_IMU): 0 differ.

### (b) Telemetry after the manual-control stop (inside W)

| Run | Outcome | gcs_connection_lost in W | telemetry_status samples in W with GCS heartbeat present | manual control regained in W |
|---|---|---|---|---|
| A-01 | DEPARTED_RTL | False | 21/21 | False |
| A-02 | DEPARTED_RTL | False | 21/21 | False |
| A-03 | DEPARTED_RTL | False | 21/21 | False |
| A-04 | DEPARTED_RTL | False | 21/21 | False |
| A-05 | DEPARTED_RTL | False | 21/21 | False |
| A-06 | DEPARTED_RTL | False | 21/21 | False |
| A-07 | DEPARTED_RTL | False | 21/21 | False |
| A-08 | DEPARTED_RTL | False | 21/21 | False |
| A-09 | DEPARTED_RTL | False | 21/21 | False |
| A-10 | DEPARTED_RTL | False | 21/21 | False |
| B-01 | SUSTAINED_HOLD | False | 25/25 | False |
| B-02 | SUSTAINED_HOLD | False | 26/26 | False |
| B-03 | SUSTAINED_HOLD | False | 25/25 | False |
| B-04 | invalid | False | 25/25 | False |
| B-05 | SUSTAINED_HOLD | False | 26/26 | False |
| B-06 | SUSTAINED_HOLD | False | 26/26 | False |
| B-07 | SUSTAINED_HOLD | False | 25/25 | False |
| B-08 | SUSTAINED_HOLD | False | 25/25 | False |
| B-09 | SUSTAINED_HOLD | False | 25/25 | False |
| B-10 | SUSTAINED_HOLD | False | 25/25 | False |
| B-11 | SUSTAINED_HOLD | False | 25/25 | False |

### (c) Harness actions and window boundary

| Run | Commands received after RC loss | user-intended mode(s) in W | user took over in W | harness stop − W end (s) | log end − W end (s) |
|---|---|---|---|---|---|
| A-01 | [(59.37, 0, 0.0, 2.0, 1)] | [2] | False | 3.87 | -3.86 |
| A-02 | [(59.48, 0, 0.0, 2.0, 1)] | [2] | False | 3.86 | -3.88 |
| A-03 | [(59.48, 0, 0.0, 2.0, 1)] | [2] | False | 3.88 | -3.87 |
| A-04 | [(59.47, 0, 0.0, 2.0, 1)] | [2] | False | 3.88 | -3.87 |
| A-05 | [(59.47, 0, 0.0, 2.0, 1)] | [2] | False | 3.85 | -3.9 |
| A-06 | [(59.43, 0, 0.0, 2.0, 1)] | [2] | False | 3.85 | -3.84 |
| A-07 | [(59.47, 0, 0.0, 2.0, 1)] | [2] | False | 3.88 | -3.87 |
| A-08 | [(59.48, 0, 0.0, 2.0, 1)] | [2] | False | 3.86 | -3.87 |
| A-09 | [(59.47, 0, 0.0, 2.0, 1)] | [2] | False | 3.89 | -3.86 |
| A-10 | [(59.78, 0, 0.0, 2.0, 1)] | [2] | False | 3.88 | -3.35 |
| B-01 | none | [2] | False | 3.85 | 3.82 |
| B-02 | none | [2] | False | 3.88 | 3.85 |
| B-03 | none | [2] | False | 3.86 | 3.83 |
| B-04 | [(41.03, 208, 2.0, 0.0, 1)] | [2] | False | 3.92 | 3.9 |
| B-05 | none | [2] | False | 3.9 | 3.87 |
| B-06 | none | [2] | False | 3.87 | 3.85 |
| B-07 | none | [2] | False | 3.84 | 3.82 |
| B-08 | none | [2] | False | 3.84 | 3.82 |
| B-09 | none | [2] | False | 3.86 | 3.83 |
| B-10 | none | [2] | False | 3.87 | 3.84 |
| B-11 | none | [2] | False | 3.86 | 3.83 |

All commands received per run (time, command, param1, param2, source sysid): A-01: [(-0.15, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.37, 0, 0.0, 2.0, 1)]; A-02: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.48, 0, 0.0, 2.0, 1)]; A-03: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.83, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.48, 0, 0.0, 2.0, 1)]; A-04: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.47, 0, 0.0, 2.0, 1)]; A-05: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.47, 0, 0.0, 2.0, 1)]; A-06: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.43, 0, 0.0, 2.0, 1)]; A-07: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.47, 0, 0.0, 2.0, 1)]; A-08: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.48, 0, 0.0, 2.0, 1)]; A-09: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.47, 0, 0.0, 2.0, 1)]; A-10: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (59.78, 0, 0.0, 2.0, 1)]; B-01: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-02: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-03: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-04: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255), (41.03, 208, 2.0, 0.0, 1)]; B-05: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-06: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-07: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-08: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-09: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-10: [(-0.15, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.83, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]; B-11: [(-0.14, 'PX4_INTERNAL(1001)', -3.0, -3.0, 1), (22.82, 'DO_SET_MODE', 1.0, 3.0, 255), (24.78, 'ARM_DISARM', 1.0, 0.0, 255)]

## Reconciliation: Build B returning to POSCTL on a second machine (analyst section)

_Written by the executing assistant from vermithor's logs and from source at both commits; not generated._

**Observation to reconcile.** A parallel run on a second machine (same commits, same SIH venue,
different transport) observed Build B return to POSCTL after the 5 s failsafe-action delay. On
vermithor, Build B sustained Hold for the full window in 10/10 valid runs.

**Vermithor's Build B mode sequences, exactly as logged** (`vehicle_status`, ULog seconds since log
start; nav 2 = POSCTL, 4 = AUTO_LOITER; arm 2 = armed; fs = `failsafe`; intent =
`nav_state_user_intention`). All 10 valid runs have the same shape:

| Run | t_loss | Timeline (changes only, whole log) | Log end |
|---|---|---|---|
| B-01 | 41.100 | −0.132 nav4/arm1/fs0/intent4 · 20.040 nav2/arm1 · 24.792 nav2/arm2 · **41.112 nav4/arm2/fs1/intent2** | 70.028 |
| B-02 | 41.096 | −0.128 nav4/arm1 · 20.044 nav2/arm1 · 24.784 nav2/arm2 · **41.108 nav4/arm2/fs1/intent2** | 70.020 |
| B-03 | 41.100 | −0.132 nav4/arm1 · 20.040 nav2/arm1 · 24.792 nav2/arm2 · **41.112 nav4/arm2/fs1/intent2** | 70.020 |
| B-05 | 41.104 | −0.128 nav4/arm1 · 20.044 nav2/arm1 · 24.796 nav2/arm2 · **41.116 nav4/arm2/fs1/intent2** | 70.068 |
| B-06 | 41.104 | −0.128 nav4/arm1 · 20.044 nav2/arm1 · 24.784 nav2/arm2 · **41.116 nav4/arm2/fs1/intent2** | 70.052 |
| B-07 | 41.104 | −0.128 nav4/arm1 · 20.044 nav2/arm1 · 24.784 nav2/arm2 · **41.116 nav4/arm2/fs1/intent2** | 70.028 |
| B-08 | 41.104 | −0.128 nav4/arm1 · 20.044 nav2/arm1 · 24.784 nav2/arm2 · **41.116 nav4/arm2/fs1/intent2** | 69.980 |
| B-09 | 41.104 | −0.128 nav4/arm1 · 20.044 nav2/arm1 · 24.784 nav2/arm2 · **41.116 nav4/arm2/fs1/intent2** | 70.004 |
| B-10 | 41.096 | −0.136 nav4/arm1 · 20.036 nav2/arm1 · 24.788 nav2/arm2 · **41.108 nav4/arm2/fs1/intent2** | 70.044 |
| B-11 | 41.100 | −0.132 nav4/arm1 · 20.040 nav2/arm1 · 24.792 nav2/arm2 · **41.112 nav4/arm2/fs1/intent2** | 70.024 |

After the bold entry there is **no further change** in nav_state, arming, failsafe or user
intention until the log ends (~29 s after RC loss, ~3.9 s past the window end). PX4's own logged
messages in the window are, in every run: `invalid setpoints` / `Failsafe: stop and wait`
(mc_pos_control), `Failsafe activated, entering Hold for 5 seconds` (failsafe), and a tone-alarm
line. Nothing is logged at t_loss + 5 s in Build B: the delayed Hold becomes the configured Hold
action silently. In Build A, the same instant logs `Failsafe activated` + `RTL HOME activated`.

**Plausible causes, checked in the order requested (vermithor side):**

- **(a) Parameter sets.** The explicit set read back correctly in every scored run; no parameter
  changed during any log; the full ULog parameter sets (779 parameters, excluding volatile
  bookkeeping/calibration prefixes) are identical across all 21 scored runs (A and B). Nothing
  here distinguishes runs. Whether the other machine's set differs can only be checked against its
  ULogs. Note that no single value of the scenario parameters explains "Hold for 5 s, then
  POSCTL" in Build B: NAV_RCL_ACT=2/3 would give RTL/Land, COM_RC_IN_MODE=4 would give no RC-loss
  failsafe at all, and COM_RCL_EXCEPT does not cover POSCTL.
- **(b) GCS heartbeat / telemetry after the stream stops.** The harness sends a 1 Hz GCS
  heartbeat throughout. In every scored run, `telemetry_status.heartbeat_type_gcs` is present on
  every sample in W, `gcs_connection_lost` never rises, and `manual_control_signal_lost` never
  returns to 0 in W (no manual-control regain from any source). NAV_DLL_ACT=0, so even a
  datalink loss would add no action.
- **(c) Harness behavior at the window boundary.** The harness sends nothing after stopping the
  stream. `vehicle_command` in every valid run contains only the boot-internal command and the
  harness's own DO_SET_MODE (t≈22.82 s) and ARM (t≈24.78 s), both before RC loss. (The
  post-loss entries in table (c) for A-runs at landing and for invalid B-04 (208 = flight
  termination) have source sysid 1, i.e. PX4 itself, not the harness, which is sysid 255.) There is no
  user takeover (`failsafe_and_user_took_over` = 0) and no change of user intention in W. The
  harness stops listening ~3.9 s after W ends, and PX4 is shut down only after that. Nothing in W
  is caused by the harness.

**Finding.** The cause of the second machine's POSCTL return **cannot be identified from
vermithor's logs**: vermithor shows none of the conditions that could produce it. It is an
unexplained venue/harness difference.

**What would discriminate it (from source at Build B, for whoever holds the other machine's
ULogs).** There are only two paths in Build B from the RC-loss Hold back to POSCTL, and each has a
specific log signature:

1. **Manual control regained.** The Hold action from NAV_RCL_ACT=1 has clear condition
   `WhenConditionClears`. If any MAVLink source delivers valid MANUAL_CONTROL again (for example, a
   ground-station virtual joystick on a second link, or a transport that keeps or resumes sending), the
   action clears and the vehicle returns to the user-intended mode, POSCTL. Signature:
   `failsafe_flags.manual_control_signal_lost` 1→0 and valid `manual_control_setpoint` samples
   (check `data_source`) after the intended stop.
2. **Any mode-change request, even re-requesting POSCTL.** Commander forwards mode-change
   requests to the failsafe framework even when the intended mode is unchanged ("might lead to a
   user-takeover"), and takeover by mode switch is allowed during and after the delay. In Build B,
   the takeover lands in POSCTL **and stays there without manual control**, because the fix removed
   the manual-control term from `modeCanRun()`. In Build A, the same request would fall back to RTL.
   Signature: a `vehicle_command` 176 (DO_SET_MODE) or a SET_MODE message after t_loss, and
   `vehicle_status.failsafe_and_user_took_over` = 1. A harness that re-commands the mode, retries a
   command, or acts at its own window boundary near t_loss + 5 s would produce exactly this.

A third, non-PX4 possibility is worth ruling out first. If the second machine's "POSCTL" came from
live HEARTBEAT decoding rather than from ULog `vehicle_status`, check the decoding:
`custom_mode` main mode 3 = POSCTL, but AUTO_LOITER is main mode 4 with **sub-mode 3**, so a
byte-order slip labels Hold as "3".

## Invalid attempt B-04 (analyst section)

B-04 is excluded under rule V4, and V5 would also have excluded it. At arming (t = 24.78 s),
`sensor_baro`, `sensor_mag`, `sensor_gps`, `battery_status` and `cpuload` stop publishing for the
rest of the log, while `sensor_accel` and SIH ground truth continue. PX4 reports `No valid data
from Baro 0 / Compass 0`, then `Battery unhealthy`. EKF2 dead-reckons (eph 0.3 → 6.8 m), the local
position becomes invalid at 29.76 s, and PX4 falls back POSCTL → ALTCTL (29.78 s) → STAB (34.76 s)
before RC loss, then Termination (41.03 s) after it.

The baro, mag, GPS and battery simulators and tone_alarm all run on the `hp_default` work queue,
and the stall begins right after tone_alarm's arming tune. `cpuload` (on `lp_default`) also stops.
This looks like a SITL work-queue stall. **Root cause not determined.** It is simulator
infrastructure shared by both builds and is unrelated to the failsafe code under test. It occurred
in 1 of 21 scored attempts (and 0 of 3 smokes).

