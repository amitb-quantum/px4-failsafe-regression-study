#!/usr/bin/env python3
"""
ULog checker for the PX4 regression experiment — v2 (2026-10-23).
Reports, FROM THE LOG (never from script prints). All times are seconds since
ULog start (ulog.start_timestamp).
  - vehicle_status: nav_state / arming_state / failsafe timeline (changes only)
  - manual_control_setpoint: samples, valid MAVLink samples (data_source=2),
    first/last valid sample. NOTE: the logger subsamples this topic (~2-5 Hz),
    so the logged count is far below the 20 Hz stream rate.
  - failsafe_flags.manual_control_signal_lost: full transition timeline
    (it is 1 at boot before any stream; the loss that matters is the 0->1
    edge AFTER the last valid sample)
  - every other failsafe flag that rises after arming (unrelated failsafes)
  - ground-truth altitude (SIH) around the manual-control stop

Changes from v1 (archive/ulog_check.v1-2026-10-23.py): time origin is the ULog
start (v1 used the first vehicle_status sample -> uint64 underflow); v1's
"FIRST SET" for signal_lost reported the boot state, not the loss.

Usage: python3 ulog_check.py <file.ulg>
"""
import sys

import numpy as np
from pyulog import ULog

NAV_STATES = {
    0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION", 4: "AUTO_LOITER",
    5: "AUTO_RTL", 6: "POSITION_SLOW", 10: "ACRO", 12: "DESCEND",
    13: "TERMINATION", 14: "OFFBOARD", 15: "STAB", 17: "AUTO_TAKEOFF",
    18: "AUTO_LAND", 19: "AUTO_FOLLOW_TARGET", 20: "AUTO_PRECLAND", 21: "ORBIT",
    22: "AUTO_VTOL_TAKEOFF",
}


def topic(ulog, name):
    for d in ulog.data_list:
        if d.name == name and d.multi_id == 0:
            return d.data
    return None


def changes(t, v):
    v = np.asarray(v).astype(int)
    idx = [0] + list(np.flatnonzero(np.diff(v)) + 1)
    return [(float(t[i]), int(v[i])) for i in idx]


def main(path):
    ulog = ULog(path)
    t0 = ulog.start_timestamp
    rel = lambda a: (np.asarray(a, dtype=np.int64) - np.int64(t0)) / 1e6  # noqa: E731
    print(f"log duration: {(ulog.last_timestamp - t0) / 1e6:.1f}s")

    vs = topic(ulog, "vehicle_status")
    if vs is None:
        print("vehicle_status: ABSENT")
        return 1
    tv = rel(vs["timestamp"])
    print("\nvehicle_status timeline (changes only):")
    prev = None
    for t, nav, arm, fs in zip(tv, vs["nav_state"], vs["arming_state"], vs["failsafe"]):
        cur = (int(nav), int(arm), int(fs))
        if cur != prev:
            print(f"  t={t:7.2f}s  nav_state={cur[0]:2d} ({NAV_STATES.get(cur[0], 'NAV%d' % cur[0])})"
                  f"  arming_state={cur[1]}  failsafe={cur[2]}")
            prev = cur

    mc = topic(ulog, "manual_control_setpoint")
    last_valid = None
    if mc is None:
        print("\nmanual_control_setpoint: ABSENT — no manual control stream reached PX4")
    else:
        tm = rel(mc["timestamp"])
        ok = (mc["valid"] == 1) & (mc["data_source"] == 2)
        print(f"\nmanual_control_setpoint: {len(tm)} logged samples; valid MAVLink (valid=1, data_source=2): "
              f"{int(ok.sum())}")
        print(f"  valid values seen: {sorted(set(int(v) for v in mc['valid']))}; "
              f"data_source values seen: {sorted(set(int(v) for v in mc['data_source']))}  (2=MAVLink instance 0)")
        if ok.any():
            last_valid = float(tm[ok][-1])
            print(f"  first valid t={tm[ok][0]:.2f}s, last valid t={last_valid:.2f}s")

    ff = topic(ulog, "failsafe_flags")
    if ff is None:
        print("\nfailsafe_flags: ABSENT")
    else:
        tf = rel(ff["timestamp"])
        print("\nfailsafe_flags.manual_control_signal_lost transitions:",
              ", ".join(f"t={t:.2f}s->{v}" for t, v in changes(tf, ff["manual_control_signal_lost"])))
        if last_valid is not None:
            sig = np.asarray(ff["manual_control_signal_lost"]).astype(int)
            after = np.flatnonzero((tf > last_valid) & (sig == 1))
            if len(after):
                print(f"  RC loss after stream: set at t={tf[after[0]]:.2f}s "
                      f"({tf[after[0]] - last_valid:.2f}s after last valid sample)")
            else:
                print("  RC loss after stream: NOT SET after last valid sample")
        arm = [t for t, v in changes(tv, vs["arming_state"]) if v == 2]
        if arm:
            t_arm = arm[0]
            others = []
            for k in ff:
                if k in ("timestamp", "manual_control_signal_lost") or k.startswith("mode_req"):
                    continue
                for t, v in changes(tf, ff[k])[1:]:
                    if v == 1 and t > t_arm:
                        others.append(f"{k}@{t:.2f}s")
            print(f"  other failsafe flags rising after arming (t={t_arm:.2f}s): {others or 'none'}")

    gt = topic(ulog, "vehicle_local_position_groundtruth")
    if gt is not None and last_valid is not None:
        tg = rel(gt["timestamp"])
        alt = -np.asarray(gt["z"])
        w = tg > last_valid
        i = min(np.searchsorted(tg, last_valid), len(tg) - 1)
        print(f"\nground-truth altitude: {alt[i]:.2f} m at last valid sample; after it min {alt[w].min():.2f} m, "
              f"max {alt[w].max():.2f} m, at log end {alt[-1]:.2f} m")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
