#!/usr/bin/env python3
"""Read a smoke-run ULog and print: manual-control stream evidence (present,
then stopped), failsafe flag transitions if logged, and the full vehicle
nav_state sequence with relative timestamps."""
import sys, glob, json
from pyulog import ULog

NAV_STATE = {0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION",
             4: "AUTO_LOITER", 5: "AUTO_RTL", 6: "ACRO", 10: "OFFBOARD",
             11: "STAB", 12: "AUTO_TAKEOFF", 13: "AUTO_LAND", 14: "DESCEND",
             15: "TERMINATION", 17: "ORBIT", 18: "AUTO_PRECLAND", 19: "AUTO_VTOL_TAKEOFF"}

path = sys.argv[1]
ulog = ULog(path)
names = sorted({d.name for d in ulog.data_list})
out = {"file": path, "topics_present": [n for n in names if n in
        ("manual_control_setpoint", "vehicle_status", "failsafe_flags",
         "input_rc", "vehicle_land_detected", "commander_state")]}

t0 = ulog.start_timestamp

def rel(ts):
    return round((ts - t0) / 1e6, 2)

mc = ulog.get_dataset("manual_control_setpoint")
ts = mc.data["timestamp"]
valid = mc.data.get("valid")
src = mc.data.get("data_source")
out["manual_control_setpoint"] = {
    "samples": len(ts),
    "first_s": rel(int(ts[0])), "last_s": rel(int(ts[-1])),
    "valid_values": sorted({int(v) for v in valid}) if valid is not None else None,
    "data_sources": sorted({int(v) for v in src}) if src is not None else None,
    "gaps_over_1s": [
        [rel(int(ts[i])), round((int(ts[i+1]) - int(ts[i])) / 1e6, 2)]
        for i in range(len(ts) - 1) if int(ts[i+1]) - int(ts[i]) > 1_000_000],
}

try:
    irc = ulog.get_dataset("input_rc")
    its = irc.data["timestamp"]
    out["input_rc"] = {"samples": len(its), "first_s": rel(int(its[0])),
                       "last_s": rel(int(its[-1]))}
except Exception as e:
    out["input_rc"] = f"absent: {e}"

vs = ulog.get_dataset("vehicle_status")
vts = vs.data["timestamp"]
nav = vs.data["nav_state"]
seq = []
last = None
for t, n in zip(vts, nav):
    n = int(n)
    if n != last:
        seq.append([rel(int(t)), NAV_STATE.get(n, str(n))])
        last = n
out["nav_state_sequence"] = seq
armed = vs.data.get("arming_state")
if armed is not None:
    aseq = []
    last = None
    for t, a in zip(vts, armed):
        a = int(a)
        if a != last:
            aseq.append([rel(int(t)), a])
            last = a
    out["arming_state_changes"] = aseq

try:
    ff = ulog.get_dataset("failsafe_flags")
    fts = ff.data["timestamp"]
    mcl = ff.data["manual_control_signal_lost"]
    fseq = []
    last = None
    for t, v in zip(fts, mcl):
        v = int(v)
        if v != last:
            fseq.append([rel(int(t)), v])
            last = v
    out["failsafe_flags.manual_control_signal_lost_changes"] = fseq
except Exception as e:
    out["failsafe_flags"] = f"absent: {e}"

print(json.dumps(out, indent=1))
