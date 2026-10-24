#!/usr/bin/env python3
"""
RC-loss scenario script — v2 (2026-10-23). The SAME script is used for smoke
(exploratory) and scored runs; run_once.py launches PX4, applies params.json,
calls this, shuts PX4 down and archives the evidence.

Scenario (prereg, amended): Position mode, neutral sticks, valid MAVLink
manual-control stream established before arming; GCS heartbeat kept alive the
whole time; then stop ONLY the manual-control stream and observe a fixed window.

Changes from v1 (archive/smoke_manual_control.v1-2026-10-23.py):
  - manual-control stream starts BEFORE mode switch / arming (POSCTL and arming
    both require manual control; v1 sent them with no stream present)
  - GCS heartbeat at 1 Hz throughout, including after the manual-control stop
    (v1 sent nothing after the stop, so telemetry was not actually "kept alive")
  - mode and arming are confirmed from HEARTBEAT; arming is retried on denial
    (normal arm only — never the force-arm magic value) with a bounded timeout
  - records PX4 boot time (time_boot_ms) at the manual-control stop, plus all
    STATUSTEXT / COMMAND_ACK, into an events JSON (context only; scoring is
    done from the ULog, never from these prints)

Exit codes: 0 scenario completed; 2 wrong sysid; 3 could not arm; 4 could not
enter POSCTL; 5 no heartbeat.
"""
import argparse
import json
import sys
import threading
import time

from pymavlink import mavutil

RATE_HZ = 20.0           # MANUAL_CONTROL rate
PRE_STREAM_S = 3.0       # neutral stream before mode switch / arm
CLIMB_S = 8.0            # throttle up, in Position mode (v2.1: was 4.0 — smoke-B-01 peaked at 0.6 m)
NEUTRAL_S = 6.0          # neutral sticks, stream still valid
OBSERVE_S = 30.0         # stream stopped: fixed observation window (> COM_RC_LOSS_T 0.5 + COM_FAIL_ACT_T 5)
ARM_RETRY_S = 2.0
ARM_TIMEOUT_S = 90.0
Z_NEUTRAL = 500          # -> throttle 0.0 (mavlink_receiver: z/1000*2-1)
Z_CLIMB = 850            # -> throttle 0.7 (v2.1: was 700 -> 0.4)
POSCTL = 3               # PX4 custom main mode


class Link:
    """One MAVLink connection; a sender thread owns all periodic traffic."""

    def __init__(self, url):
        self.conn = mavutil.mavlink_connection(url, source_system=255, source_component=190)
        self.lock = threading.Lock()
        self.mc_enabled = False
        self.z = Z_NEUTRAL
        self.stop = False
        self.events = []
        self.boot_ms = None
        self.custom_mode = None
        self.armed = None
        self.t_start = time.time()

    def log(self, kind, **kw):
        ev = {"wall_s": round(time.time() - self.t_start, 3), "px4_boot_ms": self.boot_ms, "event": kind}
        ev.update(kw)
        self.events.append(ev)
        print(json.dumps(ev), flush=True)

    def send(self, fn, *a):
        with self.lock:
            fn(*a)

    def sender(self):
        next_hb = 0.0
        while not self.stop:
            now = time.time()
            if now >= next_hb:
                self.send(self.conn.mav.heartbeat_send, mavutil.mavlink.MAV_TYPE_GCS,
                          mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                next_hb = now + 1.0
            if self.mc_enabled:
                self.send(self.conn.mav.manual_control_send, self.conn.target_system, 0, 0, self.z, 0, 0)
            time.sleep(1.0 / RATE_HZ)

    def pump(self, seconds):
        """Receive for `seconds`, tracking mode/arming/time and logging texts/acks."""
        end = time.time() + seconds
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return
            msg = self.conn.recv_match(blocking=True, timeout=min(remaining, 0.2))
            if msg is None or msg.get_srcSystem() != 1:
                continue
            t = msg.get_type()
            if hasattr(msg, "time_boot_ms"):
                self.boot_ms = msg.time_boot_ms
            if t == "HEARTBEAT" and msg.get_srcComponent() == 1:
                armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                if msg.custom_mode != self.custom_mode or armed != self.armed:
                    self.custom_mode, self.armed = msg.custom_mode, armed
                    self.log("heartbeat_change", main_mode=(msg.custom_mode >> 16) & 0xFF,
                             sub_mode=(msg.custom_mode >> 24) & 0xFF, armed=armed)
            elif t == "STATUSTEXT":
                self.log("statustext", severity=msg.severity, text=msg.text)
            elif t == "COMMAND_ACK":
                self.log("command_ack", command=msg.command, result=msg.result)

    def main_mode(self):
        return None if self.custom_mode is None else (self.custom_mode >> 16) & 0xFF

    def command(self, cmd, *params):
        p = list(params) + [0] * (7 - len(params))
        self.send(self.conn.mav.command_long_send, self.conn.target_system, 1, cmd, 0, *p)


def run(link):
    hb = link.conn.wait_heartbeat(timeout=30)
    if hb is None:
        link.log("abort", reason="no heartbeat")
        return 5
    link.log("heartbeat", sysid=link.conn.target_system)
    if link.conn.target_system != 1:
        link.log("abort", reason=f"heartbeat from sysid {link.conn.target_system}, not PX4 (1)")
        return 2
    link.conn.target_component = 1

    threading.Thread(target=link.sender, daemon=True).start()
    link.z, link.mc_enabled = Z_NEUTRAL, True
    link.log("mc_stream_start", z=Z_NEUTRAL)
    link.pump(PRE_STREAM_S)

    for _ in range(3):
        link.command(mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                     mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, POSCTL)
        link.pump(2.0)
        if link.main_mode() == POSCTL:
            break
    if link.main_mode() != POSCTL:
        link.log("abort", reason="could not enter POSCTL")
        return 4
    link.log("posctl_confirmed")

    t_arm = time.time()
    attempts = 0
    while not link.armed and time.time() - t_arm < ARM_TIMEOUT_S:
        attempts += 1
        link.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1, 0)  # normal arm, never force
        link.pump(ARM_RETRY_S)
    if not link.armed:
        link.log("abort", reason="could not arm", attempts=attempts)
        return 3
    link.log("armed_confirmed", attempts=attempts, main_mode=link.main_mode())

    link.z = Z_CLIMB
    link.log("climb", z=Z_CLIMB, seconds=CLIMB_S)
    link.pump(CLIMB_S)
    link.z = Z_NEUTRAL
    link.log("neutral", z=Z_NEUTRAL, seconds=NEUTRAL_S)
    link.pump(NEUTRAL_S)

    link.mc_enabled = False
    link.log("mc_stream_stop", main_mode=link.main_mode(), armed=link.armed)
    link.pump(OBSERVE_S)
    link.log("observe_end", main_mode=link.main_mode(), sub_mode=(link.custom_mode >> 24) & 0xFF,
             armed=link.armed)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True, help="output events JSON path")
    args = ap.parse_args()
    # SERVER mode required: PX4 SITL listens on 18570 and sends to 14550.
    link = Link("udpin:0.0.0.0:14550")
    try:
        rc = run(link)
    finally:
        link.stop = True
        time.sleep(0.2)
        with open(args.events, "w") as f:
            json.dump({"constants": {"RATE_HZ": RATE_HZ, "PRE_STREAM_S": PRE_STREAM_S, "CLIMB_S": CLIMB_S,
                                     "NEUTRAL_S": NEUTRAL_S, "OBSERVE_S": OBSERVE_S, "Z_NEUTRAL": Z_NEUTRAL,
                                     "Z_CLIMB": Z_CLIMB},
                       "events": link.events}, f, indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
