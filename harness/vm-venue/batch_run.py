#!/usr/bin/env python3
"""Scored-batch runner (prereg: B control x10 valid first, then A x10 valid,
attempt cap 15 per build). Uses smoke_run.py (DEFAULT COM_FAIL_ACT_T=5,
NAV_RCL_ACT=1, RC_MAP_* set, window 35 s) per attempt in a fresh rootfs, then
analyze_ulog.py per run. A run is VALID iff, from its ULog:
  - manual_control_setpoint shows a valid stream (data_source 7) that stops
    (a >5 s sample gap exists after stream start), and
  - failsafe_flags.manual_control_signal_lost transitions 0->1 during the run.
Classification per run (recorded verbatim in the summary JSON):
  - mode sequence from vehicle_status.nav_state
  - departed_rtl: AUTO_RTL or AUTO_LAND appears after the RC-loss timestamp
  - hold_phase: AUTO_LOITER appears within 2 s after the RC-loss timestamp
Gate readings are computed in the write-up, not here.
Usage: batch_run.py <B|A> <build_dir> <out_root> [max_valid=10] [cap=15]
"""
import os, sys, subprocess, json, glob

VENV_PY = os.path.expanduser("~/workspace/px4-experiment/venv/bin/python")
HERE = os.path.expanduser("~/workspace/px4-experiment")

label, build_dir, out_root = sys.argv[1], sys.argv[2], sys.argv[3]
max_valid = int(sys.argv[4]) if len(sys.argv) > 4 else 10
cap = int(sys.argv[5]) if len(sys.argv) > 5 else 15
os.makedirs(out_root, exist_ok=True)

results = []
valid = 0
attempt = 0
while valid < max_valid and attempt < cap:
    attempt += 1
    run_dir = os.path.join(out_root, f"{label}_attempt{attempt:02d}")
    drv = subprocess.run([VENV_PY, os.path.join(HERE, "smoke_run.py"),
                          build_dir, run_dir, "35"],
                         capture_output=True, text=True, timeout=300)
    entry = {"attempt": attempt, "run_dir": run_dir,
             "driver_tail": drv.stdout.strip().splitlines()[-3:]}
    ulgs = glob.glob(os.path.join(run_dir, "log", "*", "*.ulg"))
    if not ulgs:
        entry["valid"] = False
        entry["invalid_reason"] = "no ULog produced"
        results.append(entry)
        continue
    ana = subprocess.run([VENV_PY, os.path.join(HERE, "analyze_ulog.py"), ulgs[0]],
                         capture_output=True, text=True)
    try:
        d = json.loads(ana.stdout)
    except Exception:
        entry["valid"] = False
        entry["invalid_reason"] = "ULog analysis failed"
        results.append(entry)
        continue
    mc = d["manual_control_setpoint"]
    lost = d["failsafe_flags.manual_control_signal_lost_changes"]
    lost_on = [t for t, v in lost if v == 1 and t > 5]
    stream_gap = any(g[1] > 5 for g in mc["gaps_over_1s"])
    is_valid = bool(lost_on) and stream_gap and (7 in mc["data_sources"])
    entry["valid"] = is_valid
    if not is_valid:
        entry["invalid_reason"] = ("rc loss not verified in log"
                                   if not lost_on else "no setpoint gap / stream")
    else:
        valid += 1
        seq = d["nav_state_sequence"]
        t_loss = lost_on[0]
        entry["rc_loss_s"] = t_loss
        entry["nav_sequence"] = seq
        entry["hold_phase"] = any(m == "AUTO_LOITER" and abs(t - t_loss) < 2.5
                                  for t, m in seq)
        entry["departed_rtl"] = any(m in ("AUTO_RTL", "AUTO_LAND") and t > t_loss
                                    for t, m in seq)
    results.append(entry)
    print(f"attempt {attempt}: valid={entry['valid']}", flush=True)

summary = {"label": label, "build_dir": build_dir, "attempts": attempt,
           "valid_runs": valid, "results": results}
with open(os.path.join(out_root, f"batch_{label}_summary.json"), "w") as fh:
    json.dump(summary, fh, indent=1)
print(json.dumps({k: summary[k] for k in ("label", "attempts", "valid_runs")}))
