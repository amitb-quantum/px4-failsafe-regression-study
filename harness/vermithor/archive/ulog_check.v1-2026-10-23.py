#!/usr/bin/env python3
"""
ULog checker for the PX4 regression experiment (smoke + scored runs).
Verifies, FROM THE LOG (never from script prints):
  - manual_control_setpoint: was a valid manual-control stream present, and when did it stop?
  - failsafe_flags.manual_control_signal_lost: did RC loss register, and when?
  - vehicle_status: full nav_state / arming timeline (sustained behavior, not first mode)

Usage: python3 ulog_check.py <file.ulg>
Requires: pyulog (in the px4-regression conda env).
"""
import sys

from pyulog import ULog

NAV_STATES = {
    0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION", 4: "AUTO_LOITER",
    5: "AUTO_RTL", 6: "POSITION_SLOW", 10: "ACRO", 12: "DESCEND",
    13: "TERMINATION", 14: "OFFBOARD", 15: "STAB", 17: "AUTO_TAKEOFF",
    18: "AUTO_LAND", 19: "AUTO_FOLLOW_TARGET", 20: "AUTO_PRECLAND", 21: "ORBIT",
    22: "AUTO_VTOL_TAKEOFF",
}


def get(ulog, name):
    try:
        return ulog.get_dataset(name)
    except (KeyError, ValueError):
        return None


def main(path):
    ulog = ULog(path)
    t0 = None

    vs = get(ulog, "vehicle_status")
    if vs is None:
        print("vehicle_status: ABSENT")
        return 1
    ts = vs.data["timestamp"]
    t0 = ts[0]
    rel = lambda t: (t - t0) / 1e6  # noqa: E731

    print(f"log duration: {rel(ts[-1]):.1f}s")
    print("\nvehicle_status timeline (changes only):")
    prev = None
    for t, nav, arm in zip(ts, vs.data["nav_state"], vs.data["arming_state"]):
        cur = (int(nav), int(arm))
        if cur != prev:
            name = NAV_STATES.get(cur[0], f"NAV{cur[0]}")
            print(f"  t={rel(t):7.1f}s  nav_state={cur[0]:2d} ({name})  arming_state={cur[1]}")
            prev = cur

    mc = get(ulog, "manual_control_setpoint")
    if mc is None:
        print("\nmanual_control_setpoint: ABSENT — no manual control stream reached PX4")
    else:
        mts = mc.data["timestamp"]
        print(f"\nmanual_control_setpoint: {len(mts)} samples, "
              f"first t={rel(mts[0]):.1f}s, last t={rel(mts[-1]):.1f}s")
        if "valid" in mc.data:
            vals = sorted(set(int(v) for v in mc.data["valid"]))
            print(f"  valid values seen: {vals}")
        if "data_source" in mc.data:
            srcs = sorted(set(int(v) for v in mc.data["data_source"]))
            print(f"  data_source values seen: {srcs}  (0=unknown, 1=RC, 2=MAVLink, 3=MAVLink via GCS?)")

    ff = get(ulog, "failsafe_flags")
    if ff is None:
        print("\nfailsafe_flags: ABSENT")
    elif "manual_control_signal_lost" in ff.data:
        fts = ff.data["timestamp"]
        lost = [rel(t) for t, v in zip(fts, ff.data["manual_control_signal_lost"]) if v]
        if lost:
            print(f"\nfailsafe_flags.manual_control_signal_lost: FIRST SET at t={lost[0]:.1f}s")
        else:
            print("\nfailsafe_flags.manual_control_signal_lost: never set in this log")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
