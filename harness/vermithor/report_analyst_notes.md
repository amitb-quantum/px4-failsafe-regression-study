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
