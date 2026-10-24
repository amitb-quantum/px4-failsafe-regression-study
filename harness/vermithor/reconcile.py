#!/usr/bin/env python3
"""
Reconciliation checks (reporting only, does not affect scoring) for the cross-venue
observation "Build B returns to POSCTL after the 5 s failsafe-action delay".
For every scored run on vermithor, from the ULog / run.json:
  (a) parameter sets: readback per run (run.json) + full ULog parameter set compared
      across all scored runs; parameters changed during the log
  (b) telemetry after the manual-control stop: gcs_connection_lost, GCS heartbeat age
      (telemetry_status.heartbeat_type_gcs), manual_control_signal_lost regain
  (c) window boundary / harness actions: every vehicle_command received, mode-intention
      changes, failsafe_and_user_took_over, and when the harness stopped relative to W
Usage: reconcile.py  (prints markdown)
"""
import glob
import json
import os

import numpy as np
from pyulog import ULog

ROOT = os.path.expanduser("~/px4-regression")
VOLATILE = ("LND_FLIGHT_T_", "COM_FLIGHT_UUID", "SYS_RESTART_TYPE", "CAL_", "SENS_BOARD_", "TC_",
            "EKF2_MAGBIAS_", "EKF2_MAG_DECL", "BAT1_V_LOAD", "COM_ARM_IMU")
CMD = {176: "DO_SET_MODE", 400: "ARM_DISARM", 1001: "PX4_INTERNAL(1001)", 511: "SET_MESSAGE_INTERVAL",
       512: "REQUEST_MESSAGE", 520: "REQUEST_AUTOPILOT_CAPABILITIES"}


def topic(u, name, mid=0):
    for d in u.data_list:
        if d.name == name and d.multi_id == mid:
            return d.data
    return None


def main():
    p = print
    runs = sorted(glob.glob(f"{ROOT}/runs/scored/[AB]-[0-9][0-9]"))
    allparams, rows = {}, []
    for d in runs:
        if not os.path.exists(f"{d}/score.json"):
            continue  # attempt still in progress
        s = json.load(open(f"{d}/score.json"))
        if not s.get("ulog"):
            continue
        r = json.load(open(f"{d}/run.json"))
        u = ULog(f"{d}/{s['ulog']}", ["vehicle_command", "failsafe_flags", "telemetry_status", "vehicle_status"])
        t0 = np.int64(u.start_timestamp)
        rel = lambda a: (np.asarray(a, dtype=np.int64) - t0) / 1e6  # noqa: E731
        allparams[s["run"]] = {k: v for k, v in u.initial_parameters.items() if not k.startswith(VOLATILE)}
        rb_ok = all(v["ok"] for v in r.get("params_applied", {}).values())
        row = {"run": s["run"], "valid": s["valid"], "outcome": s["outcome"], "readback_ok": rb_ok,
               "changed_in_log": [(round((t - t0) / 1e6, 2), n, v) for t, n, v in u.changed_parameters]}
        t_loss = s.get("t_loss")
        if t_loss is not None:
            w_end = t_loss + 25.0
            ff = topic(u, "failsafe_flags")
            tf = rel(ff["timestamp"])
            win = (tf >= t_loss) & (tf <= w_end)
            row["gcs_lost_in_W"] = bool(np.asarray(ff["gcs_connection_lost"])[win].any())
            row["mc_regained_in_W"] = bool((np.asarray(ff["manual_control_signal_lost"])[win] == 0).any())
            ts = topic(u, "telemetry_status")  # instance 0 = the harness link (data_source 2)
            tt = rel(ts["timestamp"])
            w2 = (tt >= t_loss) & (tt <= w_end)
            hb = np.asarray(ts["heartbeat_type_gcs"])[w2]  # bool: GCS heartbeat currently present
            row["gcs_hb_present_in_W"] = f"{int(hb.sum())}/{len(hb)}" if w2.any() else None
            vc = topic(u, "vehicle_command")
            tv = rel(vc["timestamp"])
            row["commands"] = [(round(float(t), 2), CMD.get(int(c), int(c)), float(a), float(b), int(ss))
                               for t, c, a, b, ss in zip(tv, vc["command"], vc["param1"], vc["param2"],
                                                         vc["source_system"])]
            row["commands_after_loss"] = [c for c in row["commands"] if c[0] >= t_loss]
            vs = topic(u, "vehicle_status")
            tvs = rel(vs["timestamp"])
            w3 = (tvs >= t_loss) & (tvs <= w_end)
            row["user_intention_in_W"] = sorted(set(int(x) for x in np.asarray(vs["nav_state_user_intention"])[w3]))
            row["took_over_in_W"] = bool(np.asarray(vs["failsafe_and_user_took_over"])[w3].any())
            ev = json.load(open(f"{d}/scenario_events.json"))["events"]
            end = [e for e in ev if e["event"] == "observe_end"]
            row["harness_stop_boot_s_minus_Wend"] = (round(end[0]["px4_boot_ms"] / 1000 - w_end, 2)
                                                     if end and end[0]["px4_boot_ms"] else None)
            row["log_end_minus_Wend"] = round((u.last_timestamp - t0) / 1e6 - w_end, 2)
        rows.append(row)

    # (a) full parameter-set comparison across runs
    names = sorted(set().union(*[set(v) for v in allparams.values()])) if allparams else []
    differing = {}
    for n in names:
        vals = {run: ps.get(n) for run, ps in allparams.items()}
        if len(set(map(str, vals.values()))) > 1:
            differing[n] = vals
    p("### (a) Parameter sets\n")
    p(f"- Explicit set read back OK in every scored run with a log: "
      f"**{all(r['readback_ok'] for r in rows)}** ({len(rows)} runs).")
    p(f"- Parameters changed during any log: {[(r['run'], r['changed_in_log']) for r in rows if r['changed_in_log']] or 'none'}.")
    p(f"- Full ULog parameter sets compared across all {len(allparams)} runs ({len(names)} parameters, excluding "
      f"volatile bookkeeping/calibration prefixes {', '.join(VOLATILE)}): "
      f"{len(differing)} differ.")
    for n, vals in list(differing.items())[:20]:
        p(f"  - `{n}`: " + ", ".join(f"{k}={v}" for k, v in vals.items()))
    p("")
    p("### (b) Telemetry after the manual-control stop (inside W)\n")
    p("| Run | Outcome | gcs_connection_lost in W | telemetry_status samples in W with GCS heartbeat present | manual control regained in W |")
    p("|---|---|---|---|---|")
    for r in rows:
        if "gcs_lost_in_W" in r:
            p(f"| {r['run']} | {r['outcome'] or 'invalid'} | {r['gcs_lost_in_W']} | {r['gcs_hb_present_in_W']} | "
              f"{r['mc_regained_in_W']} |")
    p("")
    p("### (c) Harness actions and window boundary\n")
    p("| Run | Commands received after RC loss | user-intended mode(s) in W | user took over in W | "
      "harness stop − W end (s) | log end − W end (s) |")
    p("|---|---|---|---|---|---|")
    for r in rows:
        if "commands" in r:
            p(f"| {r['run']} | {r['commands_after_loss'] or 'none'} | {r['user_intention_in_W']} | "
              f"{r['took_over_in_W']} | {r['harness_stop_boot_s_minus_Wend']} | {r['log_end_minus_Wend']} |")
    p("")
    p("All commands received per run (time, command, param1, param2, source sysid): " +
      "; ".join(f"{r['run']}: {r['commands']}" for r in rows if "commands" in r)[:4000])


if __name__ == "__main__":
    main()
