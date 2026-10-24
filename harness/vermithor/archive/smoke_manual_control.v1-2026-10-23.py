#!/usr/bin/env python3
"""
Smoke-run harness (EXPLORATORY — never scored).
PX4 SIH SITL: stream MAVLink MANUAL_CONTROL in Position mode, then stop the
stream and watch the nav-state sequence live. Validates Phase 0 checks:
  #3 logs confirm valid manual control followed by RC loss (signal itself)
  #4 scenario exercises the intended failsafe path (Position -> failsafe)

Prereqs:
  - PX4 running:  HEADLESS=1 make px4_sitl sihsim_quadx   (in build-A or build-B)
  - In the pxh shell BEFORE running this script:
        param set NAV_RCL_ACT <Hold value>   # confirm enum from commander_params.c
        param set COM_RC_LOSS_T 0.5          # if present at this commit
  - conda env px4-regression active (pymavlink is a PX4 requirement)

After the script ends: in pxh run `shutdown`, then find the log:
  ls -lt <build>/build/px4_sitl_default/rootfs/log/ | head
"""
import sys
import time

from pymavlink import mavutil

RATE_HZ = 20.0
CLIMB_S = 4.0        # throttle up, in Position mode
NEUTRAL_S = 6.0      # neutral sticks, stream still valid
OBSERVE_S = 30.0     # stream stopped: observe failsafe window live


def stream(conn, seconds, z):
    """Send MANUAL_CONTROL at RATE_HZ. z: 0..1000 (500 = neutral throttle)."""
    end = time.time() + seconds
    while time.time() < end:
        conn.mav.manual_control_send(
            conn.target_system, 0, 0, z, 0, 0  # x, y neutral; r (yaw) neutral
        )
        time.sleep(1.0 / RATE_HZ)


def main():
    # SERVER mode is required: PX4 SITL listens on UDP 18570 and SENDS to 14550.
    # 'udp:...' (client mode) addresses our commands to 14550, where nothing
    # listens — attempt 2026-10-23 #2 proved it: the log showed no arm, no mode
    # change, and a single invalid manual_control_setpoint sample. Use udpin.
    conn = mavutil.mavlink_connection("udpin:0.0.0.0:14550")
    hb = conn.wait_heartbeat(timeout=30)
    print(f"heartbeat from system {conn.target_system}", flush=True)
    if conn.target_system != 1:
        raise SystemExit(
            f"heartbeat came from sysid {conn.target_system}, not PX4 (1). "
            "Something else is speaking MAVLink on 14550 — aborting."
        )
    conn.target_component = 1

    # PX4 custom main mode 3 = POSCTL, via MAV_CMD_DO_SET_MODE
    # (pymavlink's set_mode_px4 signature varies by version — do not use it)
    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 3, 0, 0, 0, 0, 0,
    )
    time.sleep(1.0)

    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 0, 0, 0, 0, 0, 0,
    )
    print("arm sent; streaming manual control (climb)", flush=True)
    stream(conn, CLIMB_S, z=700)
    print("neutral sticks, stream still valid", flush=True)
    stream(conn, NEUTRAL_S, z=500)

    print("STREAM STOPPED — RC loss clock starts; observing nav states", flush=True)
    t0 = time.time()
    last = None
    while time.time() - t0 < OBSERVE_S:
        msg = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
        if msg is None:
            continue
        state = msg.custom_mode
        if state != last:
            print(f"t={time.time() - t0:5.1f}s  custom_mode(main_mode)={state}", flush=True)
            last = state
    print("observation window done — shut PX4 down with pxh `shutdown`, then locate the .ulg", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
