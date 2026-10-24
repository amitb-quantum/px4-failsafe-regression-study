#!/usr/bin/env python3
"""Exploratory SIH smoke run (NOT a scored run).

Transport note: in this sandbox, Python UDP sendto() fails with EPERM, so the
MAVLink control channel runs over a socat PTY pair (serial mavlink instance
started from the pxh shell). Telemetry stays alive for the whole run via
pymavlink's heartbeat thread on that same serial link; only the RC stream
(RC_CHANNELS_OVERRIDE) is started/stopped.

Scenario: fresh rootfs, autostart 10040 (sihsim_quadx). Sets NAV_RCL_ACT=1
(Hold) and RC_MAP_ROLL/PITCH/THROTTLE/YAW=1/2/3/4 (compiled defaults are 0 =
unmapped). Arms in Position mode, climbs on throttle, hovers, stops RC,
observes WINDOW_S seconds, restores RC, lands, clean shutdown. The ULog in
the run dir is the evidence.
"""
import os, sys, time, threading, subprocess, signal

from pymavlink import mavutil

BUILD_DIR = sys.argv[1]
RUN_DIR = sys.argv[2]
WINDOW_S = float(sys.argv[3]) if len(sys.argv) > 3 else 35.0
TAG = os.path.basename(RUN_DIR.rstrip("/"))
SER_PX4 = f"/tmp/px4serial_{TAG}"
SER_GCS = f"/tmp/gcsserial_{TAG}"

os.makedirs(RUN_DIR, exist_ok=True)
link = os.path.join(RUN_DIR, "etc")
if not os.path.exists(link):
    os.symlink(os.path.join(BUILD_DIR, "etc"), link)
for p in (SER_PX4, SER_GCS):
    try: os.unlink(p)
    except FileNotFoundError: pass
socat = subprocess.Popen(["socat", "-d", "-d",
                          f"PTY,link={SER_PX4},rawer,echo=0",
                          f"PTY,link={SER_GCS},rawer,echo=0"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

env = dict(os.environ, PX4_SYS_AUTOSTART="10040", PX4_SIM_MODEL="sihsim_quadx")
console = open(os.path.join(RUN_DIR, "px4_console.log"), "wb")
px4 = subprocess.Popen([os.path.join(BUILD_DIR, "bin", "px4"), "-i", "0",
                        "-s", "etc/init.d-posix/rcS"],
                       cwd=RUN_DIR, env=env, stdin=subprocess.PIPE,
                       stdout=console, stderr=subprocess.STDOUT)

def pxh(cmd, wait=1.0):
    px4.stdin.write((cmd + "\n").encode()); px4.stdin.flush(); time.sleep(wait)

rc_state = {"on": False, "thr": 1000}
rc_stop_flag = threading.Event()

def rc_thread(master):
    while not rc_stop_flag.is_set():
        if rc_state["on"]:
            master.mav.manual_control_send(
                master.target_system, 0, 0, rc_state["thr"], 0, 0)
        time.sleep(0.05)

def wait_armed(master, timeout=3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=timeout)
        if msg and (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            return True
        if msg:
            return False
    return False

try:
    time.sleep(8)
    pxh("mavlink start -d " + SER_PX4 + " -b 921600 -r 4000000", 2)
    master = mavutil.mavlink_connection(SER_GCS, baud=921600, source_system=255)
    hb = master.wait_heartbeat(timeout=20)
    print("heartbeat:", hb is not None, "target:", master.target_system, flush=True)
    if hb is None:
        raise RuntimeError("no heartbeat over serial link")

    t = threading.Thread(target=rc_thread, args=(master,), daemon=True)
    t.start()

    def set_param(name, value):
        master.mav.param_set_send(master.target_system, master.target_component,
                                  name.encode(), float(value),
                                  mavutil.mavlink.MAV_PARAM_TYPE_INT32)
        time.sleep(0.3)
    PARAMS = (("NAV_RCL_ACT", 1), ("RC_MAP_ROLL", 1), ("RC_MAP_PITCH", 2),
              ("RC_MAP_THROTTLE", 3), ("RC_MAP_YAW", 4),
              ("COM_RC_IN_MODE", 1))  # <-- ONLY deviation from the scored batch
    for n, v in PARAMS:
        set_param(n, v)
    print("params set", flush=True)
    # Mandatory readback: PX4 silently ignores type-mismatched sets.
    readback = {}
    for n, v in PARAMS:
        master.mav.param_request_read_send(master.target_system,
                                           master.target_component,
                                           n.encode(), -1)
        t0 = time.time()
        while time.time() - t0 < 5:
            m = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=5)
            pid = m.param_id if m else None
            if isinstance(pid, bytes):
                pid = pid.decode()
            if m and pid.strip("\x00") == n:
                readback[n] = int(m.param_value)
                break
    print("param readback:", readback, flush=True)
    bad = {n: (readback.get(n), v) for n, v in PARAMS if readback.get(n) != v}
    if bad:
        raise RuntimeError(f"parameter readback mismatch: {bad}")

    rc_state["thr"] = 0
    rc_state["on"] = True
    time.sleep(2)

    master.mav.set_mode_send(master.target_system,
                             mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                             (3 << 16))  # PX4 main mode 3 = POSCTL
    time.sleep(1)

    armed = False
    for _ in range(40):
        master.mav.command_long_send(master.target_system, master.target_component,
                                     mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                     0, 1, 0, 0, 0, 0, 0, 0)
        if wait_armed(master):
            armed = True
            break
    if not armed:
        pxh("commander arm", 2)
        armed = wait_armed(master)
    print("armed:", armed, flush=True)
    if not armed:
        raise RuntimeError("could not arm")

    rc_state["thr"] = 750
    time.sleep(4)
    rc_state["thr"] = 500
    time.sleep(5)
    print("hovering; stopping RC stream now", flush=True)

    rc_state["on"] = False           # <-- RC LOSS (telemetry stays alive)
    time.sleep(WINDOW_S)
    print(f"window of {WINDOW_S}s elapsed; restoring RC", flush=True)

    rc_state["thr"] = 500
    rc_state["on"] = True
    time.sleep(3)

    master.mav.command_long_send(master.target_system, master.target_component,
                                 mavutil.mavlink.MAV_CMD_NAV_LAND,
                                 0, 0, 0, 0, 0, 0, 0, 0)
    landed = False
    t0 = time.time()
    while time.time() - t0 < 40:
        msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
        if msg and not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            landed = True
            break
    print("landed/disarmed:", landed, flush=True)
finally:
    rc_stop_flag.set()
    try:
        pxh("shutdown", 3)
        px4.wait(timeout=15)
    except Exception as e:
        print("shutdown fallback kill:", e, flush=True)
        try:
            px4.send_signal(signal.SIGTERM); px4.wait(timeout=10)
        except Exception:
            px4.kill()
    socat.terminate()
    print("px4 exit:", px4.returncode, flush=True)
