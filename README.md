# px4-failsafe-regression-study

A **closed, preregistered feasibility study** testing one narrow question: given two PX4 builds,
can an automated harness detect a meaningful change in tested behavior, beyond what PX4's own
tests report and without being fooled by simulation noise, and produce enough evidence for an
engineer to reproduce and investigate it?

It was tested on **one historical PX4 regression**: the RC-loss "Hold" failsafe bug fixed by
[PX4-Autopilot PR #21403](https://github.com/PX4/PX4-Autopilot/pull/21403).

## Read this first: scope and limits

- **One case, two pinned commits, simulation only.** Build A (regression)
  `f7ed553f57d40073f0f3f3487509e6448a7727e6` and Build B (fix)
  `aa5b9ae638f1bf412102de8fabd06740c725abf1`. These are adjacent commits; the diff is one removed
  line in `FailsafeBase::modeCanRun()`. All flights ran in PX4's built-in **SIH** simulator
  (`sihsim_quadx`, headless). No real aircraft, no Gazebo, no other regressions.
- **The gate is a feasibility acceptance rule, not a reliability statistic.** It asks for 10
  valid runs per build, with B holding in ≥ 9/10 and A departing to RTL in ≥ 8/10. Ten runs cannot
  establish rates, and no reliability claim is made.
- **Commercial demand is unproven.** This study did not test it, and the result says nothing about
  it.
- **The study is closed.** It was run on two machines ("venues"). Both venues' gates fired, so a
  meaningful difference was flagged on each.
- **The cross-venue difference in Build B is still open.** After the 5 s failsafe-action delay,
  **VM Build B clears the failsafe and returns to POSCTL**, while **vermithor Build B sustains
  Hold** with the failsafe never clearing. Neither venue's diagnostic explains this (see
  [Open question](#open-question-the-cross-venue-build-b-difference)).
- **Raw flight logs (ULogs) are not in this repository** (~300 MB). Every log is identified by
  its sha256 so a reader holding the files can match them exactly.

## Contents

1. [Results at a glance](#results-at-a-glance)
2. [What was tested, and why PX4's own test misses it](#what-was-tested-and-why-px4s-own-test-misses-it)
3. [Open question: the cross-venue Build B difference](#open-question-the-cross-venue-build-b-difference)
4. [Prerequisites](#prerequisites)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Usage](#usage)
8. [Examples](#examples)
9. [Troubleshooting](#troubleshooting)
10. [The VM venue](#the-vm-venue)
11. [File map](#file-map)
12. [License](#license)

## Results at a glance

### Vermithor venue (WSL2, Ubuntu 26.04, MAVLink over UDP)

Scored under [`harness/vermithor/SCORING_RULES.md`](harness/vermithor/SCORING_RULES.md), which
was frozen before the first scored run:
- **Window:** 25 s from the RC-loss edge verified in the log.
- **B passes** only if the vehicle enters AUTO_LOITER and **stays** there, armed, to the end of the
  window.
- **A is defect-positive** if AUTO_RTL appears inside the window.

| | Build B (fix, control) | Build A (regression) |
|---|---|---|
| Attempts / valid / invalid (cap 15) | 11 / 10 / 1 | 10 / 10 / 0 |
| Sustained Hold through the window | **10 / 10** | 0 / 10 |
| Departed Hold to AUTO_RTL in the window | 0 / 10 | **10 / 10** |
| Gate condition | ≥ 9/10: **met** | ≥ 8/10: **met** |

**Timing:**
- Both builds enter Hold 0.012 s after the verified RC loss.
- Build A switches to AUTO_RTL **exactly 5.00 s later** in every valid run. That equals
  `COM_FAIL_ACT_T`, the failsafe-action delay.

**Invalid attempt B-04:** baro/mag/GPS/battery topics stopped publishing at arming, so PX4 fell
back POSCTL → ALTCTL → STAB before RC loss. Root cause not determined; unrelated to the code under
test.

Full per-run tables: [`reports/vermithor/comparison-report.md`](reports/vermithor/comparison-report.md).

### VM venue (Ubuntu 24.04 VM, MAVLink over a serial PTY)

Scored under the preregistration's **gate-interpretation amendment** (a "departure rule"),
approved before the VM's scored runs:
- **Window:** 35 s.
- **B passes** if AUTO_LOITER appears at RC loss and **neither AUTO_RTL nor AUTO_LAND** appears in
  the window.
- **A is defect-positive** if AUTO_RTL appears in the window.

| | Build B (fix, control) | Build A (regression) |
|---|---|---|
| Attempts / valid / invalid (cap 15) | 12 / 10 / 2 | 12 / 10 / 2 |
| Passes the departure rule | **10 / 10** | n/a |
| Departed Hold to AUTO_RTL in the window | 0 / 10 | **10 / 10** |
| Gate condition | ≥ 9/10: **met** | ≥ 8/10: **met** |

**Timing and invalid runs:**
- On the VM, Build B is in AUTO_LOITER only for the 5 s delay. It then returns to POSCTL with no
  RTL or Land, which is why the departure rule was needed.
- Build A switches to AUTO_RTL at +5.01–5.02 s.
- All four invalid VM runs had an unrelated position-estimate failsafe before RC loss.

Full report: [`reports/vm-venue/BATCH_REPORT.md`](reports/vm-venue/BATCH_REPORT.md). **Read it
together with [`reports/vm-venue/ERRATUM-2026-10-24.md`](reports/vm-venue/ERRATUM-2026-10-24.md).**
The VM analyzer mislabels nav_state values ≥ 6. That does not change the VM gate (its scored modes
are 2/4/5, labelled correctly, and all 24 runs were re-checked), but it does change the published
sequences of the four invalid runs.

> The two venues' rule sets differ (window length, literal vs departure rule) and are reported
> side by side, not merged. Both flag the same A/B difference: **A leaves Hold for RTL at the
> 5 s delay expiry; B never does.**

### Baseline: PX4's own test

`functional-failsafe_test` **passes on both commits**, on both venues
([`reports/vermithor/baseline-A.txt`](reports/vermithor/baseline-A.txt),
[`baseline-B.txt`](reports/vermithor/baseline-B.txt),
[`reports/vm-venue/PHASE0_REPORT.md`](reports/vm-venue/PHASE0_REPORT.md) §6). The suite cannot
reach the defect (next section), so the preregistered stopping rule ("stop if PX4's tests already
show it") did not fire. Only this test was run as the baseline; other PX4 CI was not.

## What was tested, and why PX4's own test misses it

**Scenario:**
1. Fly in **Position mode** (POSCTL) with neutral sticks, on a MAVLink `MANUAL_CONTROL` stream.
2. Set the RC-loss action to **Hold** (`NAV_RCL_ACT=1`; the default at these commits is 2 =
   Return).
3. Stop only the manual-control stream; the telemetry link stays up.
4. RC loss is verified **from the signal itself**: the `failsafe_flags.manual_control_signal_lost`
   0→1 edge after the last valid manual-control sample. It is never inferred from the resulting
   mode, which would be circular.

**Mechanism.** This is from source at both commits plus logged flag values. It supersedes earlier
shorthand; see the amendment in [`prereg/`](prereg/px4-feasibility-experiment-prereg-2026-10-23.md).
- Hold (AUTO_LOITER) does **not** require manual control. The logged
  `failsafe_flags.mode_req_manual_control = 0x8407` covers MANUAL, ALTCTL, POSCTL, ACRO and STAB
  only.
- In Build A, the line PR #21403 removed makes the **user's intended mode** (POSCTL, and its
  fallbacks ALTCTL and STAB) unrunnable while manual control is lost.
- The real `Failsafe::checkModeFallback()` then ends in its "intended mode cannot run → RTL"
  branch. RTL outranks the configured Hold once the `COM_FAIL_ACT_T` delay (5 s) expires.
- PX4's test subclass `FailsafeTester` overrides exactly `checkModeFallback()` to return
  `Action::None`, so the test never executes the path that produces the bug.

## Open question: the cross-venue Build B difference

**What differs.** After RC loss, both venues' Build B enter Hold. At +5 s:
- On the **VM**, `vehicle_status.failsafe` clears (1→0) and the vehicle returns to POSCTL, while
  `manual_control_signal_lost` stays set.
- On **vermithor**, `failsafe` stays 1 and Hold continues to the end of the log (~29 s after RC
  loss), with no change of any kind at +5 s (all 10 valid runs, plus one diagnostic run).

**What has been checked:**

| Check | Result | Report |
|---|---|---|
| Vermithor: parameter sets, telemetry after the stop, harness actions at the window boundary | Parameters identical across all 21 scored runs (779 compared). GCS heartbeat present on every sample in the window. No harness command after RC loss, no user takeover. **Nothing on vermithor could produce a POSCTL return.** | [`comparison-report.md`](reports/vermithor/comparison-report.md) (reconciliation sections) |
| VM: Build B with `COM_RC_IN_MODE=1` (vermithor's value) | **Neither confirmed nor refuted.** On the VM's serial-PTY transport, mode 1 let the manual-control stream validate for ~0.2 s, then dropped it; arming was denied in 2/2 attempts; RC loss was never reached. | [`DISCRIMINATING_TEST_COM_RC_IN_MODE.md`](reports/vm-venue/DISCRIMINATING_TEST_COM_RC_IN_MODE.md) |
| Vermithor: Build B with `COM_RC_IN_MODE=3` (the VM's value) | **Refuted** (prediction fixed before the run). The run was valid; the failsafe stayed set and Hold was sustained, exactly as in the batch. The parameter does not explain the difference. | [`experiment-writeup.md`](reports/vermithor/experiment-writeup.md), "Post-experiment diagnostics" |

**Status: open.** By the prediction fixed before the runs, the difference lies in the
transport/link setup, which has not been characterized. Known differences between the venues'
setups:

| | vermithor | VM |
|---|---|---|
| MAVLink transport | UDP (`udpin:0.0.0.0:14550`), MAVLink instance 0, `data_source=2` | serial PTY via `socat`, extra MAVLink instance, `data_source=7` |
| GCS heartbeat from harness | 1 Hz, whole run | **none sent**, per the driver code (unverified in VM logs; [erratum §3](reports/vm-venue/ERRATUM-2026-10-24.md)) |
| `COM_RC_IN_MODE` | 1 (explicit) | 3 (default) |
| `RC_MAP_*` | defaults | set to 1/2/3/4 |
| Parameter handling | persistent rootfs; full explicit set applied and read back every run | fresh rootfs per run; `NAV_RCL_ACT` + `RC_MAP_*` set |
| After the window | harness stops; PX4 shut down (no further commands) | stream restored, then `MAV_CMD_NAV_LAND` |
| OS / compiler | Ubuntu 26.04, GCC 15.2 | Ubuntu 24.04, GCC 13.3 |

**Next step if anyone reopens this (not planned).** From Build B's source, after the failsafe has
engaged, a return to POSCTL needs either manual control regained or a mode-change request treated
as a user takeover. On the VM, manual control was **not** regained when POSCTL resumed (smoke_B3:
lost-flag set until 57.62 s, POSCTL at 28.89 s). The VM's ULogs should therefore be checked for:
- `vehicle_command` 176 (or `SET_MODE`) after RC loss;
- `vehicle_status.failsafe_and_user_took_over`;
- `telemetry_status.heartbeat_type_gcs` and `failsafe_flags.gcs_connection_lost`.

## Prerequisites

This section reproduces the **vermithor** venue, which has the most complete harness. The VM venue
is summarized in [The VM venue](#the-vm-venue).

| Need | Version used on vermithor | Notes |
|---|---|---|
| Linux host | Ubuntu 26.04.1 LTS under WSL2 | Any recent Ubuntu should work with the recipe below; only these two were exercised. |
| C/C++ toolchain | GCC 15.2.0, ninja 1.13.2, git 2.53.0 | PX4's usual Linux build dependencies. Vermithor's base packages predate this study's records; the VM recorded `ninja-build pkg-config libxml2-dev libxslt1-dev g++-multilib` on top of a standard toolchain. |
| Conda (e.g. Miniforge) | conda env with Python 3.11.17 | System CMake 4.x **cannot** configure these 2023 commits; CMake comes from pip inside the env. |
| Disk | ~8 GB | On vermithor: main clone 4.8 GB, Build A worktree 1.5 GB, Build B worktree 1.3 GB. |
| Python packages | cmake 3.28.4, empy 3.3.4, pyulog 1.3.0, pymavlink 2.4.50, numpy 2.4.6 | empy **must** be 3.3.4: `empy>=3.3` now resolves to 4.x, which breaks PX4's code generator. |
| Time | one flight run ~72 s; one 10-valid batch ~12–14 min (measured on vermithor) | Vermithor build times were not recorded. The VM (2 cores) reported ~7 min for the SITL build and ~10 min for the test build. |

Simulators: **none to install.** SIH is compiled into PX4. Gazebo Classic, gz and jMAVSim are not
used; they were unavailable on Ubuntu 26.04 for this PX4 vintage, which is why the preregistration
moved the venue to SIH.

## Installation

The harness uses fixed paths (see [Configuration](#configuration)). These commands create exactly
that layout.

**1. Clone PX4 and create one worktree per pinned commit.**

```bash
git clone https://github.com/PX4/PX4-Autopilot.git ~/PX4-Autopilot
cd ~/PX4-Autopilot
mkdir -p ~/px4-regression
git worktree add --detach ~/build-A f7ed553f57d40073f0f3f3487509e6448a7727e6
git worktree add --detach ~/px4-regression/build-B aa5b9ae638f1bf412102de8fabd06740c725abf1
```

```bash
git -C ~/build-A submodule update --init --recursive
```

```bash
git -C ~/px4-regression/build-B submodule update --init --recursive
```

Build A lives at `~/build-A`, not inside `~/px4-regression/`. That is because `git worktree move`
refuses trees that contain submodules, and the harness expects this layout.

**2. Create the Python environment.**

```bash
conda create -y -n px4-regression python=3.11
```

```bash
conda activate px4-regression
```

```bash
pip install cmake==3.28.4 empy==3.3.4
```

PX4's `Tools/setup/requirements.txt` at these commits contains `matplotlib>=3.0.*`, which modern
pip rejects. Install from a corrected copy; this is a setup file only, and PX4 source stays
untouched:

```bash
sed 's/matplotlib>=3.0.\*/matplotlib>=3.0/' ~/px4-regression/build-B/Tools/setup/requirements.txt > /tmp/px4-req.txt && pip install -r /tmp/px4-req.txt
```

```bash
pip install empy==3.3.4
```

(Re-pinning empy afterwards guards against the requirements file upgrading it.) On vermithor the
patch was applied in Build B's worktree file only; Build A's copy was never patched. That makes no
difference to the binaries, because both builds use the same environment.

**3. Build SITL at each commit with the same command.**

```bash
cd ~/build-A && CFLAGS="-include stdint.h" CXXFLAGS="-include cstdint -Wno-error=array-bounds -Wno-error=dangling-reference" make px4_sitl
```

```bash
cd ~/px4-regression/build-B && CFLAGS="-include stdint.h" CXXFLAGS="-include cstdint -Wno-error=array-bounds -Wno-error=dangling-reference" make px4_sitl
```

Why the flags:
- Newer GCC no longer pulls in `<cstdint>`/`<stdint.h>` indirectly, so they are force-included.
- Two GCC 15 false-positive warnings are demoted from errors. They still appear in the build
  output.

Each build produces `build/px4_sitl_default/bin/px4`. Check that the binary embeds the right
commit:

```bash
grep PX4_GIT_VERSION_STR ~/build-A/build/px4_sitl_default/src/lib/version/build_git_version.h ~/px4-regression/build-B/build/px4_sitl_default/src/lib/version/build_git_version.h
```

**4. (Optional) Re-run the baseline**, using the command from the test file's own header, in each
worktree with the same flags:

```bash
cd ~/build-A && CFLAGS="-include stdint.h" CXXFLAGS="-include cstdint -Wno-error=array-bounds -Wno-error=dangling-reference" make tests TESTFILTER=failsafe_test
```

Expected: `functional-failsafe_test ... Passed` on **both** commits.

**5. Install the harness.**

```bash
git clone https://github.com/amitb-quantum/px4-failsafe-regression-study.git ~/px4-failsafe-regression-study
```

```bash
mkdir -p ~/px4-regression/harness ~/px4-regression/runs/smoke ~/px4-regression/runs/scored ~/px4-regression/reports && cp -r ~/px4-failsafe-regression-study/harness/vermithor/. ~/px4-regression/harness/
```

## Configuration

**Paths (hardcoded in `run_once.py`, `batch.py`, `report.py`, `reconcile.py`):**

| Constant | Value |
|---|---|
| `ROOT` | `~/px4-regression` |
| `HARNESS` | `~/px4-regression/harness` |
| Build A worktree | `~/build-A`, must be at `f7ed553f…` |
| Build B worktree | `~/px4-regression/build-B`, must be at `aa5b9ae6…` |

To use other paths, edit the `BUILDS` dict and `ROOT` in `run_once.py` (and `ROOT` in the other
three). `run_once.py` refuses to run if the worktree HEAD or the binary's embedded version differs
from the pin.

**Parameters ([`params.json`](harness/vermithor/params.json)).** PX4 SITL **persists** parameters
across runs. Every run therefore applies this full set explicitly, then reads each value back and
aborts on any mismatch:

| Parameter | Value | Meaning |
|---|---|---|
| `NAV_RCL_ACT` | 1 | RC-loss action = Hold (default 2 = Return) |
| `COM_RC_IN_MODE` | 1 | MAVLink joystick input only |
| `COM_RC_LOSS_T` | 0.5 | manual-control loss timeout, s |
| `COM_FAIL_ACT_T` | 5.0 | failsafe-action delay (Hold first), s |
| `COM_RCL_EXCEPT` | 0 | no RC-loss exceptions |
| `NAV_DLL_ACT` | 0 | datalink-loss action disabled |
| `COM_DL_LOSS_T` | 10 | datalink-loss timeout, s |
| `COM_DISARM_PRFLT` | 10.0 | auto-disarm if no takeoff within 10 s |

**Scenario constants ([`smoke_manual_control.py`](harness/vermithor/smoke_manual_control.py)):**
- 20 Hz `MANUAL_CONTROL` stream; neutral throttle `z=500`.
- 3 s of stream before switching mode and arming.
- Climb at `z=850` (stick 0.7) for 8 s, then 6 s neutral at ~7 m.
- Stop the stream and observe for 30 s.
- GCS heartbeat at 1 Hz throughout.

**Scoring ([`SCORING_RULES.md`](harness/vermithor/SCORING_RULES.md)), frozen before the first scored
run.** A run must pass these six validity checks:
1. Log present.
2. ≥ 50 valid manual-control samples, with the stream acquired before arming.
3. RC loss verified within 2 s of the last valid sample, and no valid samples after it.
4. POSCTL, armed, and ≥ 3 m ground-truth altitude at the moment of loss.
5. No unrelated failsafe flag rising between arming and the end of the window.
6. The window is covered by the log.

Valid runs are classified SUSTAINED_HOLD, DEPARTED_RTL or OTHER from the mode sequence inside the
25 s window.

## Usage

Activate the environment first (`conda activate px4-regression`). Only one PX4 instance can run at
a time; the launcher checks for this.

**One run, end to end.** It verifies the commit, starts PX4 SIH headless, applies and reads back
parameters, waits 20 s to settle, flies the scenario, shuts PX4 down and archives the evidence:

```bash
python ~/px4-regression/harness/run_once.py --build B --kind smoke --label my-smoke-B-01
```

Evidence lands in `~/px4-regression/runs/smoke/my-smoke-B-01/`: `run.json`, `params_applied.txt`,
`px4_console.log`, `scenario_console.log`, `scenario_events.json`, the `.ulg`, and
`ulog_check.txt`. The folder must not already exist; evidence is never overwritten.

**Inspect any ULog** (mode timeline, manual-control evidence, RC-loss edge, other failsafes,
altitude):

```bash
python ~/px4-regression/harness/ulog_check.py <path/to/file.ulg>
```

**Score a run** under the frozen rules (writes `score.json` into the run folder):

```bash
python ~/px4-regression/harness/score.py ~/px4-regression/runs/smoke/my-smoke-B-01
```

**A scored batch** (B-01…B-15, stops at 10 valid; then the same for A):

```bash
python ~/px4-regression/harness/batch.py --build B
```

```bash
python ~/px4-regression/harness/batch.py --build A
```

**Comparison report** (gate verdict, per-run tables, code diff, hash checks, reconciliation):

```bash
python ~/px4-regression/harness/report.py > ~/px4-regression/reports/comparison-report.md
```

`batch.py` refuses to overwrite an existing attempt folder. To run a fresh batch, move
`~/px4-regression/runs/scored/` aside first.

## Examples

Excerpt of `ulog_check.txt` for scored run **A-01** (Build A; full file in
`evidence/vermithor/scored/A-01/`). Hold at 41.11 s, then AUTO_RTL at 46.11 s (+5.0 s), then
landing and auto-disarm:

```
vehicle_status timeline (changes only):
  t=  20.04s  nav_state= 2 (POSCTL)  arming_state=1  failsafe=0
  t=  24.79s  nav_state= 2 (POSCTL)  arming_state=2  failsafe=0
  t=  41.11s  nav_state= 4 (AUTO_LOITER)  arming_state=2  failsafe=1
  t=  46.11s  nav_state= 5 (AUTO_RTL)  arming_state=2  failsafe=1
  t=  61.38s  nav_state= 2 (POSCTL)  arming_state=1  failsafe=0

manual_control_setpoint: 108 logged samples; valid MAVLink (valid=1, data_source=2): 106
failsafe_flags.manual_control_signal_lost transitions: t=-0.05s->1, t=20.04s->0, t=41.10s->1
  RC loss after stream: set at t=41.10s (0.29s after last valid sample)
  other failsafe flags rising after arming (t=24.79s): none
```

Abridged `score.json` for scored run **B-01** (Build B; full file in
`evidence/vermithor/scored/B-01/`). Hold 0.012 s after RC loss, held to the window end (66.1 s),
log continues to 70.0 s:

```json
{"run": "B-01", "valid": true, "outcome": "SUSTAINED_HOLD", "t_loss": 41.1, "loss_lag_s": 0.304,
 "alt_at_loss_m": 6.91, "mode_sequence": [{"t": 41.1, "nav": "POSCTL", "armed": true},
 {"t": 41.112, "nav": "AUTO_LOITER", "armed": true}], "window_end": 66.1, "log_end": 70.028}
```

All 21 scored runs, the 3 smokes and the diagnostic run are in [`evidence/vermithor/`](evidence/vermithor/).
Each run's `run.json` records:
- the commit, both as worktree HEAD and as embedded in the binary;
- the binary sha256 (one value per build across all runs);
- the sha256 of the scenario, parameters and launcher, all equal to the frozen values in
  [`SETUP_NOTES.md`](reports/vermithor/SETUP_NOTES.md);
- the ULog filename and sha256.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Commands seem to go nowhere; the log shows no arming and a single invalid `manual_control_setpoint` | pymavlink opened in **client** mode (`udp:`) | PX4 SITL listens on 18570 and **sends to 14550**. Use server mode `udpin:0.0.0.0:14550` (the scenario does) and check that the heartbeat sysid is 1. |
| CMake fails to configure | System CMake 4.x | Use pip `cmake==3.28.4` inside the conda env. |
| Codegen error about `em.RAW_OPT` / empy | empy 4.x | `pip install empy==3.3.4` |
| `pip install -r requirements.txt` rejects `matplotlib>=3.0.*` | Spec invalid for modern pip | Use the `sed`-corrected copy (Installation step 2). |
| `'uint8_t' was not declared in this scope` | Newer GCC dropped the indirect include | Use the `CFLAGS`/`CXXFLAGS` from Installation step 3. |
| Build stops on `array-bounds` / `dangling-reference` | GCC 15 false positives | Already demoted by `-Wno-error=…` in the build command. |
| `Preflight Fail: horizontal velocity unstable` / `velocity estimate error`, on and off, even long after boot | **SIH characteristic at these commits:** it injects IMU noise (accel σ 0.5/1.7/1.4 m/s², gyro σ 0.14/0.07/0.03 rad/s, `sih.cpp:440-441`) far above EKF2's defaults, so the estimate drifts while stationary (flag set ~6% of the time). Identical in A and B. | Do **not** force-arm. The scenario retries a normal arm for up to 90 s; every scored run armed first try. |
| A run is invalid with POSCTL → ALTCTL → STAB before RC loss, `No valid data from Baro 0 / Compass 0`, `Battery unhealthy` | Sensor topics stopped publishing at arming (vermithor B-04; root cause not determined) | Nothing to fix; the rules exclude it and the batch replaces it, up to the 15-attempt cap. |
| `a px4 process is already running` | A previous run did not exit | `pkill -x px4`, then re-run with a **new** label. |
| `run_once.py` fails because the folder exists | Evidence is never overwritten | Use a new `--label`. |
| A Build A log ends ~4 s before the window end | `SDLOG_MODE=1` logs from boot **until disarm**; Build A lands and disarms after RTL | Expected. The rules accept it, because the departure was already observed. |
| A parameter "set" has no effect | PX4 silently ignores type-mismatched sets (seen on the VM) | The launcher reads every value back and aborts on mismatch. |
| The vehicle barely leaves the ground | Climb too short or weak (the first smoke reached only 0.6 m) | Already fixed in v2.1 (8 s at stick 0.7); the rules require ≥ 3 m at loss. |

## The VM venue

The VM run used its own driver, because Python UDP was blocked in that sandbox
([`PHASE0_REPORT.md`](reports/vm-venue/PHASE0_REPORT.md) §8):
- MAVLink over a **socat PTY pair**, with a second PX4 MAVLink instance started from the pxh shell.
- A fresh rootfs per attempt.
- `NAV_RCL_ACT=1` and `RC_MAP_*=1/2/3/4` set over MAVLink.
- A 35 s window; afterwards the stream is restored and a land command sent.

Scripts are in [`harness/vm-venue/`](harness/vm-venue/) and are **published unmodified**. They
hardcode `~/workspace/px4-experiment/` paths and expect `socat`. The exact batch commands are in
`PHASE0_REPORT.md` §10. The VM's runner summaries are in [`evidence/vm-venue/`](evidence/vm-venue/);
its ULogs are identified in its reports.

**Before relying on the VM files, read [`ERRATUM-2026-10-24.md`](reports/vm-venue/ERRATUM-2026-10-24.md):**
- `analyze_ulog.py` mislabels nav_state values ≥ 6.
- `batch_run.py`'s `departed_rtl` field has no window limit.
- The docstrings name the wrong stream type.
- The drivers send no GCS heartbeat.

None of these changes the VM gate. The first changes the published invalid-run sequences.

## File map

```
README.md                         this file
LICENSE                           MIT
.gitignore                        excludes ULogs, PX4 trees, build trees, binaries, rootfs, run dirs
prereg/
  px4-feasibility-experiment-prereg-2026-10-23.md   canonical amended preregistration (governs everything)
harness/vermithor/
  smoke_manual_control.py         scenario script v2.1 (same for smoke and scored runs)
  run_once.py                     one run end to end: verify build, launch SIH, params, scenario, shutdown, evidence
  params.json                     explicit parameter set applied and read back every run
  ulog_check.py                   human-readable ULog check (v2)
  SCORING_RULES.md                validity + outcome rules, frozen before scored run 1
  score.py                        applies SCORING_RULES.md -> score.json
  batch.py                        scored batch driver (10 valid, cap 15)
  report.py                       generates the comparison report
  reconcile.py                    cross-venue reconciliation checks (params, telemetry, harness actions)
  report_analyst_notes.md         labelled analyst text embedded by report.py
  archive/                        v1 scenario and checker, as received (superseded before any scored run)
  diagnostics/                    post-experiment COM_RC_IN_MODE=3 diagnostic (params copy + launcher copy)
harness/vm-venue/
  smoke_run.py, batch_run.py, analyze_ulog.py, discriminating_run.py   VM drivers (unmodified)
reports/vermithor/
  comparison-report.md            auto-generated gate verdict, per-run tables, diff, hashes, reconciliation
  experiment-writeup.md           results, limits, post-experiment diagnostics
  SETUP_NOTES.md                  dated deviation log, harness freeze hashes, every decision
  baseline-A.txt, baseline-B.txt, baseline-verdict.md   PX4 failsafe_test on both commits
  baseline-A.INVALID-ran-in-build-B.txt                 a mis-located baseline run, kept for the record
reports/vm-venue/
  PHASE0_REPORT.md                VM environment, commit verification, baseline, smokes
  BATCH_REPORT.md                 VM scored batch
  DISCRIMINATING_TEST_COM_RC_IN_MODE.md   VM post-experiment diagnostic
  ERRATUM-2026-10-24.md           review notes on the VM bundle (written on vermithor)
evidence/vermithor/
  scored/<A|B>-NN/                run.json, score.json, ulog_check.txt, params_applied.txt, scenario_events.json, run_once.out
  scored/batch-A.jsonl, batch-B.jsonl   attempt-by-attempt batch log
  smoke/, diagnostic/             exploratory runs (never scored)
  ulog-sha256.txt                 sha256 of all 26 vermithor ULogs (logs not published)
evidence/vm-venue/
  batch_*_summary.json            VM runner output (unmodified)
  MANIFEST.txt                    VM bundle manifest
```

## License

[MIT](LICENSE). The license covers this repository's harness, reports and documentation. PX4
itself is not included and is licensed separately (BSD-3-Clause) by its authors.
