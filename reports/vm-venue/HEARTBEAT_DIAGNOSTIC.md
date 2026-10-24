# Heartbeat diagnostic — GCS heartbeat as the venue-difference candidate
**Labeled post-experiment diagnostic, 2026-10-24. NOT a scored run, NOT a reopening
of the batch. Scored results in `BATCH_REPORT.md` are unchanged.**

## Question
In the VM scored batch, fixed Build B (`aa5b9ae638`) returned from AUTO_LOITER to
POSCTL at exactly RC loss +5.0 s, with `vehicle_status.failsafe` clearing (1→0)
while `manual_control_signal_lost` stayed set. On vermithor, Build B sustained
AUTO_LOITER and the failsafe never cleared. COM_RC_IN_MODE was tested in both
directions and ruled out (VM direction could not execute; vermithor direction
refuted it). A post-publication audit then found the sharpest remaining
characterized difference: the VM harness sends NO GCS heartbeat, while
vermithor's sends 1 Hz throughout. Verified in VM logs: in a valid VM batch B
run, `failsafe_flags.gcs_connection_lost` = 1 for the entire log and
`telemetry_status.heartbeat_type_gcs` = 0 on every sample.

## Prediction (fixed before the run)
- **HOLDS** if, with a 1 Hz GCS heartbeat added, the failsafe stays set
  (failsafe=1) and AUTO_LOITER sustains through the 35 s window with no POSCTL
  return — the GCS heartbeat explains the venue difference.
- **REFUTED** if the failsafe clears at ~+5.0 s and the vehicle returns to POSCTL
  as in the scored batch — the heartbeat is ruled out too.

## Method (identical to the scored batch except the one change)
- Build: `~/workspace/px4-experiment/PX4-Autopilot/build/px4_sitl_default`
  (Build B, `aa5b9ae638`), SIH `sihsim_quadx`, fresh rootfs.
- Driver: `heartbeat_run.py` = `smoke_run.py` verbatim except a background
  thread sending a MAVLink HEARTBEAT of type MAV_TYPE_GCS (6) at 1 Hz on the
  same serial link, from before arming until the run ends. All other
  parameters, timing, and scenario steps are unchanged: NAV_RCL_ACT=1,
  RC_MAP_ROLL/PITCH/THROTTLE/YAW=1/2/3/4, COM_FAIL_ACT_T=5.0 s,
  COM_RC_LOSS_T=0.5 s, COM_RC_IN_MODE left at its VM default 3 (NOT set to 1,
  which breaks arming on this transport), Position mode, neutral sticks,
  MAVLink MANUAL_CONTROL stream established then stopped, 35 s window.
- Run dir: `disc_B_heartbeat/attempt01`, ULog `log/2026-10-24/17_46_03.ulg`.
  `batch_B/`/`batch_A/` and their summaries were not touched.
- Driver output: heartbeat thread started, params set, armed first try,
  hovering, RC stream stopped, 35 s window elapsed, landed/disarmed, px4 exit 0.

## Step 1 — did the manipulation land? NO (with one partial, unexplained change)
- `telemetry_status.heartbeat_type_gcs` = **0 on every sample, on all four
  logged telemetry_status instances** (67 samples each). By the pre-fixed
  step-1 rule, a registered GCS heartbeat never appeared in the log.
- `failsafe_flags.gcs_connection_lost` was **not** stuck at 1 this run
  (fraction set 0.458; transitions 1→0 at t=9.52, →1 at t=40.03, →0 at t=60.50),
  unlike the batch run where it was 1.000 throughout. The 9.52 clear coincides
  with link-up; the 40.03 set and 60.50 clear bracket the console's
  "Connection to ground station lost" / "GCS connection regained" lines around
  the window end and landing. The cause of this toggling is unexplained, and
  it cannot be attributed to a registered GCS heartbeat, since none registered.
- Driver-side check (offline loopback, same pymavlink call): `heartbeat_send`
  emits a valid HEARTBEAT with type=6, sysid 255, compid 0. The sending code
  is therefore not obviously buggy; the failure to register is on PX4's side
  of this serial link (candidate: the serial instance's receiver does not
  classify these heartbeats for telemetry — note all logged telemetry_status
  instances show rx_message_count 0, suggesting the serial instance's
  telemetry is not the logged one — but this mechanism is unverified).
- Per the pre-fixed rule, the attempt is **INCONCLUSIVE (manipulation failed)**,
  not a refutation. No replacement attempt was run: the rule allows a rerun
  only on a clear driver bug, and none was found.

## Step 2 — outcome (observed, but NOT scored as a verdict)
The flight itself was otherwise clean and identical to the batch pattern:
- ULog timeline (changes only): t=0.00 nav=AUTO_LOITER, arm=standby, fs=0;
  t=11.16 nav=POSCTL; t=13.91 armed; t=23.95 nav=AUTO_LOITER, fs=1;
  **t=28.96 nav=POSCTL, fs=0** (loss +5.01 s); t=60.50 nav=AUTO_LAND
  (driver's end-of-run land command); t=66.55 disarmed.
- `manual_control_signal_lost`: 1→0 at t=11.16, →1 at t=23.94 (loss), →0 at
  t=57.64 (stream restore). It stayed set across the 28.96 POSCTL return.
- `manual_control_setpoint`: 118 samples, valid values seen, data_source 7;
  33.9 s gap from t=23.64 to t=57.54 (the stopped-stream window).
- `vehicle_command` after RC loss: only the driver's NAV_LAND (cmd 21) at
  t=60.48. `failsafe_and_user_took_over` = 0 throughout; user intention
  stayed POSCTL (2) throughout.
- This is the same pattern as the scored batch and is *consistent with* the
  REFUTED pattern — but it does **not** constitute refutation, because the
  manipulation failed step 1. The run cannot test the heartbeat hypothesis.

## Verdict
**INCONCLUSIVE: the manipulation failed to register — a 1 Hz MAV_TYPE_GCS
heartbeat sent on this VM's serial link never appeared as
`telemetry_status.heartbeat_type_gcs` in the log, so the heartbeat hypothesis
was not tested.**

## What this does and does not establish
- It **does** establish that sending type-6 heartbeats on this serial-PTY
  link does not register as a GCS heartbeat in PX4's logged telemetry at
  these commits — a transport/instance-classification quirk, not a driver
  emission bug (loopback proves emission). Any future heartbeat test on this
  transport must first solve the registration problem (e.g. verify which
  mavlink channel/instance PX4 credits with GCS heartbeats) before it can
  test the hypothesis.
- It **does not** establish whether a GCS heartbeat explains the failsafe-clear
  difference, because no registered heartbeat was present during the
  RC-loss window. The observed POSCTL return at +5.01 s is consistent with
  the batch pattern and with refutation, but it is not evidence either way.
- It **does not** change any scored result, parameter set, or conclusion of
  the closed experiment. The open question (why VM Build B clears the
  failsafe at +5 s while vermithor's does not) remains open. The one new
  secondary observation — `gcs_connection_lost` toggling instead of stuck
  at 1 — is unexplained and is recorded here rather than interpreted.
