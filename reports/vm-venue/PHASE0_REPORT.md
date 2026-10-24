# Phase 0 report — PX4 build-comparison feasibility experiment
Machine: this VM (Ubuntu 24.04.5 LTS). Date: 2026-10-23/24 (UTC). Scope per preregistration
`~/workspace/your_files/px4-feasibility-experiment-prereg-2026-10-23.md` (as amended).
Everything below was observed on this machine unless explicitly marked as source analysis.
**No scored runs were performed.** All flight runs reported here are exploratory smokes.

## 1. Machine resources (observed)
- CPU: 2 cores (AMD EPYC 9D25, KVM). RAM: 7.7 GiB total, **no swap**. Disk: 100 GB volume, 97 GB free.
- OS/toolchain: Ubuntu 24.04.5, gcc 13.3.0, cmake 3.28.3 (system), git 2.43.0, Python 3.12.3.
- Consequence: builds work but are slow (full test-config build ≈ 10 min; SITL default build ≈ 7 min).
  The 2023-era PX4 setup script (`Tools/setup/ubuntu.sh` at the pinned commits) targets Ubuntu
  22.04/20.04/18.04 only — it was **not** used; a manual minimal recipe was used instead (§3).

## 2. Clone
- `git clone https://github.com/PX4/PX4-Autopilot.git` (full clone, no submodules initially):
  succeeded, ≈13 min, 1,015 MB, HEAD of main checked out, then detached checkouts of the pinned commits.
- Submodules initialized (at Build B): all `src/` submodules including nested ones
  (mavlink + its pymavlink, libevents + its nlohmann_json, libuavcan + dsdl/pyuavcan, cyphal x3,
  gps devices, monocypher, libtomcrypt, libtommath, Micro-XRCE-DDS-Client) — nested fetches done with
  `git submodule update --init --recursive --depth 1` after full fetches stalled on nlohmann/json.
  Also fetched: `Tools/simulation/gazebo-classic/sitl_gazebo-classic`.
  **Not fetched** (not needed for POSIX SITL/test builds): `platforms/nuttx/NuttX/{nuttx,apps}`,
  `Tools/simulation/jmavsim/jMAVSim`, `Tools/simulation/flightgear/flightgear_bridge`,
  `Tools/simulation/jsbsim/jsbsim_bridge`.

## 3. Environment recipe actually used (same for both commits)
- venv at `~/workspace/px4-experiment/venv` with PX4 `Tools/setup/requirements.txt` equivalents;
  **empy had to be pinned to 3.3.4** (pip initially installed empy 4.2.1, which breaks PX4 2023 codegen).
- apt: `ninja-build pkg-config libxml2-dev libxslt1-dev g++-multilib`.
- First build attempt failed verbatim:
  `platforms/posix/src/px4/common/px4_daemon/pxh.cpp:208:25: error: 'uint8_t' was not declared in this scope`
  (GCC 13 headers no longer transitively include `<cstdint>`). Workaround is environment-only
  (PX4 source untouched), applied identically to every build:
  `CXXFLAGS="-include cstdint -Wno-error=array-bounds -Wno-error=dangling-reference"`,
  `CFLAGS="-include stdint.h -Wno-error=array-bounds"`, build dir wiped, reconfigure.

## 4. Pinned commits — verification
Cross-checked three ways: GitHub API for PR #21403 (title "fix failsafe: correctly handle Hold RC
loss action", merged 2023-04-04, merge_commit_sha `aa5b9ae…`), local `git log`, and local diff.
- **Build B (fixed): `aa5b9ae638f1bf412102de8fabd06740c725abf1`** — subject "fix failsafe: correctly
  handle Hold RC loss action", author Beat Küng. Clone contains it. ✔
- **Build A (regression): `f7ed553f57d40073f0f3f3487509e6448a7727e6`** — verified locally as the
  **sole parent** of B (`git rev-parse aa5b9ae…^` = `f7ed553…`). Clone contains it. ✔
- Diff A→B is exactly one file, one line removed (plus one comment line added):
  `src/modules/commander/failsafe/framework.cpp`, in `FailsafeBase::modeCanRun()`: removal of
  `(!status_flags.manual_control_signal_lost || ((status_flags.mode_req_manual_control & mode_mask) == 0)) &&`
  and addition of the comment `// mode_req_manual_control: is handled separately`.
- PR body (API): *"Otherwise the additional mode check triggers an RTL which takes precedence over
  Hold. Introduced in 132e9d243966586d7aaf21d9600d9413993e5cc8."* Action precedence in
  `framework.h` confirms RTL > Hold ("Actions further down take precedence": …, Hold, RTL, Land, …).

## 5. Acceptance criterion 1 — do both pinned commits build in the SAME environment?
**YES (observed).** With the §3 recipe, at **each** commit:
- `make px4_sitl_test` — full test configuration built (1,179 targets).
- `make px4_sitl_default` — full SITL configuration built; `bin/px4` produced (44 MB) and started
  successfully in every smoke/debug run below.
- Caveat (same on both commits): the `gz_bridge` module was **skipped** by CMake on both builds —
  its CMakeLists only builds if `gz-transport12` (Gazebo Garden) is found; no gz runtime exists on
  Ubuntu 24.04 for this PX4 vintage (noble ships Harmonic/gz-transport13; Gazebo Classic is not
  packaged for noble; no docker on this VM). The SITL *binary* therefore builds and runs, but the
  preregistration's pinned **Gazebo gz venue could not be exercised on this machine**; all flight
  smokes used the in-tree **SIH simulator (`sihsim_quadx`, autostart 10040)** instead — a venue
  change that needs a preregistration amendment if scored runs are to use it (see §10).

## 6. Acceptance criterion 2 — baseline `failsafe_test` outcomes (BASELINE-FIRST, actual runs)
Command (per the test file's own header, "to run: make tests TESTFILTER=failsafe_test"),
run at each commit **before any simulation batch exists**. Verbatim summaries:
- Build B (`aa5b9ae`): ctest — `1/1 Test #59: functional-failsafe_test .........   Passed`,
  `100% tests passed, 0 tests failed out of 1`. Direct gtest binary run —
  `[ RUN ] FailsafeTest.general [ OK ]`, `takeover [ OK ]`, `takeover_denied [ OK ]`, `defer [ OK ]`,
  `[  PASSED  ] 4 tests.` (full output: `failsafe_test_B_gtest.txt`)
- Build A (`f7ed553`): ctest — identical `Passed`, `100% tests passed, 0 tests failed out of 1`.
  Direct gtest run — `[  PASSED  ] 4 tests.` (full output: `failsafe_test_A_gtest.txt`)
- **The baseline does NOT expose the defect: the suite passes identically on the regression and
  fixed commits.** The preregistered stopping rule ("if the baseline already exposes the defect,
  stop") therefore does **not** fire.
- Source facts behind that result (from the sources at these commits):
  - `failsafe_test.cpp` is **byte-identical between A and B** (`git diff A B -- …/failsafe_test.cpp`
    = 0 lines); the only changed file is `framework.cpp`.
  - The test subclass overrides mode-fallback handling (the caveat in the preregistration is real).
    `failsafe_test.cpp` lines 43–71:
    ```cpp
    class FailsafeTester : public FailsafeBase
    {
    ...
        void checkStateAndMode(...) override
        {
            CHECK_FAILSAFE(status_flags, manual_control_signal_lost,
                   ActionOptions(Action::RTL).clearOn(ClearCondition::OnModeChangeOrDisarm));
            ...
        }
        Action checkModeFallback(const failsafe_flags_s &status_flags, uint8_t user_intended_mode) const override
        {
            return Action::None;
        }
    ```
    The defect lives in the **real** `Failsafe::checkModeFallback`
    (`src/modules/commander/failsafe/failsafe.cpp:480`), whose final block reads:
    `// Last, check can_run for intended mode  if (!modeCanRun(status_flags, user_intended_mode)) { action = Action::RTL; … }`
    — i.e. with intended mode POSCTL (which requires manual control, see §7) and manual control lost,
    Build A's `modeCanRun` returns false and an RTL action is produced that outranks the Hold action.
    The tester's stub returns `Action::None`, so this path is never exercised.
  - The test also **never sets any `mode_req_*` flag** (grep: no `mode_req` in `failsafe_test.cpp`),
    so even the framework-internal `modeCanRun` calls run with `mode_req_manual_control == 0`, a value
    for which A's removed condition evaluates identically to B. The test's own RC-loss case
    ("// RC lost -> Hold, then RTL", `TEST_F(FailsafeTest, general)`) therefore asserts the
    framework's delay-then-action timing under the *tester's* RTL mapping — it passes on both commits
    by construction and says nothing about the NAV_RCL_ACT=Hold path in the real Commander.

## 7. Scenario parameters — confirmed from source AT the pinned commits (identical in A and B;
the A→B diff touches only framework.cpp)
From `src/modules/commander/commander_params.c`:
- `COM_RC_LOSS_T` (RC-loss timeout): **default 0.5 s** (line 143, `PARAM_DEFINE_FLOAT(COM_RC_LOSS_T, 0.5f)`).
- `NAV_RCL_ACT` (RC-loss action): **default 2 (Return)**; documented values: `1 Hold mode`,
  `2 Return mode`, `3 Land mode`, `5 Terminate`, `6 Disarm` (lines ~796–806). Scenario must set **1**.
- `COM_RCL_EXCEPT` (RC-loss exceptions bitmask): **default 0**; bit 0 Mission, **bit 1 Hold**,
  bit 2 Offboard (line 820). Scenario keeps 0 (starting mode is POSCTL, which is not excepted anyway;
  the Hold *exception* concerns being already in AUTO_LOITER).
- `COM_RC_IN_MODE`: **default 3** ("RC or Joystick keep first"; 0=RC only, 1=Joystick only,
  2=either with fallback, 4=stick input disabled; line 186).
- `COM_FAIL_ACT_T` (failsafe action delay): **default 5.0 s** (line 284), documented:
  *"Before entering failsafe (RTL, Land, Hold), wait COM_FAIL_ACT_T seconds in Hold mode."*
  This is the "failsafe-action delay" the observation window must exceed.
- `RC_MAP_ROLL/PITCH/THROTTLE/YAW`: **compiled default 0 = unmapped** (`params.c` of rc_update,
  e.g. `PARAM_DEFINE_INT32(RC_MAP_ROLL, 0)`). Any RC-stream scenario must set them (we use 1/2/3/4).
Manual-control validity (from `HealthAndArmingChecks/checks/rcAndDataLinkCheck.cpp`):
`manual_control_signal_lost` is set when no `manual_control_setpoint` exists, or it is not `valid`,
or its timestamp is older than `COM_RC_LOSS_T`. This is the flag whose transitions independently
verify RC loss in the log (§8) — from the signal path, not from the resulting mode. ✔ non-circular.
Mode requirements (from `ModeUtil/mode_requirements.cpp`): POSCTL **requires** manual control
(`setRequirement(NAVIGATION_STATE_POSCTL, flags.mode_req_manual_control)`); AUTO_LOITER does **not**.
That asymmetry is exactly why the starting mode (POSCTL) is load-bearing, as the amended
preregistration states.
**Adopted scenario parameter set for the smokes (and proposed for the batch):** defaults except
`NAV_RCL_ACT=1`, `RC_MAP_ROLL=1, RC_MAP_PITCH=2, RC_MAP_THROTTLE=3, RC_MAP_YAW=4`;
observation window after RC loss = **35 s** (> 0.5 s RC-loss delay + 5 s action delay, with margin).

## 8. Acceptance criteria 3 & 4 — smoke runs (EXPLORATORY, not scored)
### Infrastructure findings (observed, verbatim where quoted)
- **Python UDP is blocked in this sandbox**: `socket.sendto()` → `PermissionError: [Errno 1]
  Operation not permitted` (venv and system Python alike). MAVLink-over-UDP therefore cannot be
  driven from Python here. (PX4's own UDP sockets bind fine; nothing was ever received either.)
- This PX4's mavlink module has **no TCP server** (`-t` is a partner-IP option at this commit).
- Working transport: **serial MAVLink over a socat PTY pair** — a second mavlink instance started
  from the pxh shell (`mavlink start -d /tmp/px4serial_<tag> -b 921600 -r 4000000`), pymavlink on the
  other PTY end. Heartbeat, PARAM_SET, SET_MODE, arm, NAV_LAND all verified over it.
- **RC_CHANNELS_OVERRIDE path (observed dead end):** override stream produces `input_rc`
  (values/channel_count/input_source=6 MAVLINK correct in-log) and `rc_channels` (correct scaled
  values), and — after RC_MAP_* are set — `manual_control_input` samples with `data_source: 1`
  (SOURCE_RC), but the ManualControl selector never validated them in any run (output setpoint stayed
  `valid: False`), and arming was denied. (Note: `rc_update`'s `UpdateManualControlInput` never sets
  the sample's `.valid` field at this commit; the selector computes validity itself — the precise
  reason the RC path stayed invalid here was not pinned down and is recorded as an open quirk.)
- **MANUAL_CONTROL path (adopted):** MAVLink `MANUAL_CONTROL` (the QGC-joystick path) produces
  `manual_control_setpoint` with `valid: True`, `data_source: 7`, immediately; arming in POSCTL
  succeeds. The scenario's "manual-control stream" is therefore this stream; stopping it is the
  RC-loss stimulus. Telemetry (heartbeat/commands) stays alive on the same link throughout. ✔
### Smoke results (driver: `smoke_run.py`; fresh rootfs per run; analysis: `analyze_ulog.py`)
Build B, run smoke_B3 (default COM_FAIL_ACT_T=5):
- `manual_control_setpoint`: valid stream (source 7) present; a **33.9 s sample gap** starting at
  rel. 23.64 s = the stopped-stream window. `failsafe_flags.manual_control_signal_lost`:
  1→0 at 11.02 s (stream established), 0→1 at **23.87 s** (loss, ~0.2–0.5 s after stop ✔),
  1→0 at 57.62 s (stream restored). **Criterion 3: PASS** — valid manual control followed by RC loss,
  verified from the signal/flag in the log, independent of the resulting mode.
- Mode sequence (`vehicle_status.nav_state`): POSCTL (11.02) → **AUTO_LOITER (23.88)** →
  POSCTL (28.89) → AUTO_PRECLAND (60.48, our land command) → POSCTL + disarm (69.44).
  I.e. on RC loss B enters Hold, and at the COM_FAIL_ACT_T expiry (+5.01 s) it returns to the
  user-intended POSCTL — **no RTL, no Land departure** at any point. Criterion 4 mechanics
  (Position start, neutral sticks, NAV_RCL_ACT=Hold, telemetry alive, failsafe path exercised): PASS,
  with the §9 interpretation caveat about what "sustains Hold" means in nav_state terms.
Build A, run smoke_A1 (identical driver/params):
- Same stream/flag pattern (loss at 23.78 s). Mode sequence: POSCTL (11.01) → AUTO_LOITER (23.79) →
  **AUTO_RTL (28.80)** → POSCTL only at disarm (42.57; the vehicle RTL-landed and disarmed).
  **The documented defect reproduces in SITL**: at exactly the delay expiry (+5.01 s), the unintended
  RTL overrides Hold. Contrast with B at the same instant is exact and binary.
Two further exploratory B runs: smoke_B4 (COM_FAIL_ACT_T sent as INT32 — a type-mismatched set that
PX4 silently ignored; sequence identical to B3, confirming the set did not land) and smoke_B5
(COM_FAIL_ACT_T=0.0 sent correctly as REAL32): B then showed **no failsafe engagement at all**
(nav stayed POSCTL, `vehicle_status.failsafe` never set, despite the lost flag being set for 34 s).
COM_FAIL_ACT_T=0 was therefore **rejected** as a scenario parameter — it suppresses the very
behavior under test on this version. A batch-runner validation run (B, via `batch_run.py`, 1 attempt)
reproduced the B3 pattern and was classified automatically: valid, `hold_phase: true`,
`departed_rtl: false`, delay expiry at +5.00 s.

## 9. The one decision blocking the scored batch (gate interpretation)
All four acceptance checks pass and the baseline does not expose the defect, so the conditional
proceed is *technically* unlocked. One preregistration term, however, is empirically ambiguous on
this PX4 version and must be settled by the preregistration owner before scored runs mean anything:
- The gate says Build B must "sustain the expected Hold behavior" and the scoring section says B
  "enters Hold and **sustains it to the end of the window**". Observed: with the historical default
  parameters, B's `nav_state` is AUTO_LOITER **only during the 5 s COM_FAIL_ACT_T delay phase**;
  afterwards it returns to user-intended POSCTL (position hold with zero stick input) for the rest
  of the window, with no RTL/Land departure. So under a literal nav_state reading, B "fails" its own
  gate for a bookkeeping reason; under a departure reading (no RTL/Land after RC loss; Hold phase
  present at loss+delay), B passes cleanly and A fails cleanly (RTL at expiry, ≥ the documented
  defect). The full mode sequences the batch records support either reading post-hoc, but the
  *verdict rule* should be fixed before the batch, not after seeing it.
- Recommended amendment (for the owner to approve): score per run — B valid-pass iff AUTO_LOITER
  appears at RC loss (within ~2.5 s) **and** neither AUTO_RTL nor AUTO_LAND appears during the
  window; A defect-positive iff AUTO_RTL (or Land following it) appears during the window.
  Window stays 35 s; parameters as §7.

## 10. Queued scored batch — exact next commands (after the §9 amendment is recorded)
```bash
cd ~/workspace/px4-experiment
# Build B control first (build dir currently at Build B), then Build A (snapshot build):
~/workspace/px4-experiment/venv/bin/python batch_run.py B \
  ~/workspace/px4-experiment/PX4-Autopilot/build/px4_sitl_default \
  ~/workspace/px4-experiment/batch_B 10 15
~/workspace/px4-experiment/venv/bin/python batch_run.py A \
  ~/workspace/px4-experiment/sitl_build_A \
  ~/workspace/px4-experiment/batch_A 10 15
```
`batch_run.py` runs each attempt in a fresh rootfs via the proven `smoke_run.py`, verifies RC loss
from the log (setpoint gap + lost-flag transition), enforces the 15-attempt cap, counts invalid
runs separately with reasons, and writes `batch_<X>_summary.json` with full mode sequences per run.
Runner mechanics were validated end-to-end on one exploratory B run (see §8). Estimated wall time
on this VM: ~15–25 min per build's batch (each attempt ≈ 80 s).
Venue note: these commands run the **SIH `sihsim_quadx`** venue, not Gazebo gz x500 (§5). If the
owner requires the pinned gz/x500 venue, the batch must move to a machine with Gazebo Garden —
that is an environment change requiring its own amendment; nothing about the A/B contrast observed
here depends on the simulator, since the defect is in Commander logic above the simulator layer.

## 11. Artifact index (this directory)
- `build_B_tests3.log`, `build_A_tests.log` — baseline test builds+runs (ctest summaries inside).
- `failsafe_test_B_gtest.txt`, `failsafe_test_A_gtest.txt` — verbatim gtest output, both commits.
- `build_B_sitl.log`, `build_A_sitl.log` — SITL builds. `PX4-Autopilot/` (at Build B) and
  `sitl_build_A/` — the two built trees.
- `smoke_run.py` (driver), `smoke_run0.py` (COM_FAIL_ACT_T variant, rejected), `analyze_ulog.py`,
  `batch_run.py`; smoke dirs `smoke_B3/`, `smoke_A1/`, `smoke_B4/`, `smoke_B5/` with ULogs + console
  logs; `batch_runner_validation/` (runner validation run + summary JSON).
- `build_B_tests.log`, `build_B_tests2.log` — the two failed build attempts (kept for the record).
