#!/usr/bin/env python3
"""
Apply SCORING_RULES.md to one run directory; writes <run>/score.json and prints it.
Usage: score.py <run_dir>
"""
import glob
import json
import os
import sys

import numpy as np
from pyulog import ULog

WINDOW_S = 25.0
MIN_VALID_SAMPLES = 50
MAX_LOSS_LAG_S = 2.0
MIN_ALT_M = 3.0
NAV = {2: "POSCTL", 4: "AUTO_LOITER", 5: "AUTO_RTL", 18: "AUTO_LAND", 12: "DESCEND", 13: "TERMINATION"}


def topic(ulog, name):
    for d in ulog.data_list:
        if d.name == name and d.multi_id == 0:
            return d.data
    return None


def edges(t, v, to):
    v = np.asarray(v).astype(int)
    i = np.flatnonzero(np.diff(v)) + 1
    return [float(t[k]) for k in i if v[k] == to]


def score(run_dir):
    res = {"run": os.path.basename(run_dir.rstrip("/")), "valid": False, "invalid_reason": None,
           "outcome": None}
    rj = os.path.join(run_dir, "run.json")
    run = json.load(open(rj)) if os.path.exists(rj) else {}
    res["build"] = run.get("build")
    res["scenario_exit"] = run.get("scenario_exit")

    def invalid(reason):
        res["invalid_reason"] = reason
        return res

    logs = glob.glob(os.path.join(run_dir, "*.ulg"))
    if len(logs) != 1:
        return invalid(f"V1 log: {len(logs)} ULogs in run dir ({run.get('abort') or run.get('evidence_problem')})")
    res["ulog"] = os.path.basename(logs[0])
    try:
        ulog = ULog(logs[0])
    except Exception as e:  # noqa: BLE001
        return invalid(f"V1 log unparseable: {e}")
    t0 = ulog.start_timestamp
    rel = lambda a: (np.asarray(a, dtype=np.int64) - np.int64(t0)) / 1e6  # noqa: E731
    t_end = (ulog.last_timestamp - t0) / 1e6
    vs, ff, mc = (topic(ulog, n) for n in ("vehicle_status", "failsafe_flags", "manual_control_setpoint"))
    if vs is None or ff is None or mc is None:
        return invalid("V1 log: required topic missing")
    tv, tf, tm = rel(vs["timestamp"]), rel(ff["timestamp"]), rel(mc["timestamp"])
    nav, arm = np.asarray(vs["nav_state"]).astype(int), np.asarray(vs["arming_state"]).astype(int)

    ok = (np.asarray(mc["valid"]) == 1) & (np.asarray(mc["data_source"]) == 2)
    res["valid_mc_samples"] = int(ok.sum())
    arm_t = [float(tv[i]) for i in range(len(arm)) if arm[i] == 2]
    if not arm_t:
        return invalid("V2 never armed")
    t_arm = arm_t[0]
    res["t_arm"] = round(t_arm, 3)
    acquired = [t for t in edges(tf, ff["manual_control_signal_lost"], 0) if t < t_arm]
    if res["valid_mc_samples"] < MIN_VALID_SAMPLES or not acquired:
        return invalid(f"V2 manual control not established ({res['valid_mc_samples']} valid samples, "
                       f"acquired before arm: {bool(acquired)})")
    last_valid = float(tm[ok][-1])
    res["last_valid_mc"] = round(last_valid, 3)
    lost = [t for t in edges(tf, ff["manual_control_signal_lost"], 1) if t > last_valid]
    if not lost:
        return invalid("V3 RC loss not verified: signal_lost never set after last valid sample")
    t_loss = lost[0]
    res["t_loss"] = round(t_loss, 3)
    res["loss_lag_s"] = round(t_loss - last_valid, 3)
    if t_loss - last_valid > MAX_LOSS_LAG_S:
        return invalid(f"V3 RC loss lag {t_loss - last_valid:.2f}s > {MAX_LOSS_LAG_S}s")
    if (ok & (tm > t_loss)).any():
        return invalid("V3 valid manual-control samples after t_loss (stream not stopped)")

    pre = np.flatnonzero(tv < t_loss)
    if not len(pre) or nav[pre[-1]] != 2 or arm[pre[-1]] != 2:
        k = pre[-1] if len(pre) else None
        return invalid(f"V4 precondition: at loss nav={None if k is None else nav[k]} "
                       f"arm={None if k is None else arm[k]} (need POSCTL, armed)")
    gt = topic(ulog, "vehicle_local_position_groundtruth")
    if gt is None:
        return invalid("V4 precondition: no ground truth")
    tg = rel(gt["timestamp"])
    alt = -float(np.asarray(gt["z"])[min(np.searchsorted(tg, t_loss), len(tg) - 1)])
    res["alt_at_loss_m"] = round(alt, 2)
    if alt < MIN_ALT_M:
        return invalid(f"V4 precondition: altitude {alt:.2f} m < {MIN_ALT_M} m at loss")

    w_end = t_loss + WINDOW_S
    others = []
    for k in ff:
        if k in ("timestamp", "manual_control_signal_lost") or k.startswith("mode_req"):
            continue
        for t in edges(tf, ff[k], 1):
            if t_arm <= t <= w_end:
                others.append(f"{k}@{t:.2f}")
    if others:
        return invalid(f"V5 unrelated failsafe: {others}")

    # mode sequence in window (state at t_loss, then changes)
    k0 = pre[-1]
    seq = [(round(t_loss, 3), int(nav[k0]), int(arm[k0]))]
    for i in range(k0 + 1, len(tv)):
        if tv[i] > w_end:
            break
        if (nav[i], arm[i]) != (seq[-1][1], seq[-1][2]):
            seq.append((round(float(tv[i]), 3), int(nav[i]), int(arm[i])))
    res["mode_sequence"] = [{"t": t, "nav": NAV.get(n, n), "armed": a == 2} for t, n, a in seq]
    navs = [s[1] for s in seq]
    hold_t = next((s[0] for s in seq if s[1] == 4), None)
    rtl_t = next((s[0] for s in seq if s[1] == 5), None)
    res["t_loss_to_hold_s"] = None if hold_t is None else round(hold_t - t_loss, 3)
    res["hold_before_departure_s"] = (None if hold_t is None or rtl_t is None else round(rtl_t - hold_t, 3))

    departed = rtl_t is not None or any(n not in (2, 4) for n in navs) or any(s[2] != 2 for s in seq)
    if t_end < w_end and not departed:
        return invalid(f"V6 log ends at {t_end:.2f}s before window end {w_end:.2f}s with no departure")
    res["window_end"] = round(w_end, 3)
    res["log_end"] = round(t_end, 3)
    res["valid"] = True

    if rtl_t is not None:
        res["outcome"] = "DEPARTED_RTL"
    elif hold_t is not None and seq[-1][1] == 4 and seq[-1][2] == 2 and all(
            s[1] == 4 and s[2] == 2 for s in seq if s[0] >= hold_t) and t_end >= w_end:
        res["outcome"] = "SUSTAINED_HOLD"
    else:
        res["outcome"] = "OTHER"
    return res


def main(run_dir):
    res = score(run_dir)
    json.dump(res, open(os.path.join(run_dir, "score.json"), "w"), indent=1)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
