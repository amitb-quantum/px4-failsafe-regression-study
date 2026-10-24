#!/usr/bin/env python3
"""
One run of the RC-loss scenario on one build, end to end:
  verify build commit -> launch PX4 SIH headless (same env as the make target
  `sihsim_quadx`, daemon mode) -> apply params.json explicitly via pxh client
  -> fixed settle -> scenario script -> PX4 shutdown -> archive evidence.

Usage: run_once.py --build {A,B} --kind {smoke,scored} --label NAME
Evidence lands in ~/px4-regression/runs/<kind>/<label>/ (never overwritten):
  run.json, params_applied.txt, px4_console.log, scenario_console.log,
  scenario_events.json, <ulog>.ulg, ulog_check.txt
"""
import argparse
import glob
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
ROOT = f"{HOME}/px4-regression"
HARNESS = f"{ROOT}/harness"
PY = sys.executable
BUILDS = {
    "A": (f"{HOME}/build-A", "f7ed553f57d40073f0f3f3487509e6448a7727e6"),
    "B": (f"{ROOT}/build-B", "aa5b9ae638f1bf412102de8fabd06740c725abf1"),
}
SETTLE_S = 20.0           # fixed wait after PX4 boot before the scenario starts
BOOT_TIMEOUT_S = 60.0
SCENARIO_TIMEOUT_S = 240.0


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sh(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", choices=BUILDS, required=True)
    ap.add_argument("--kind", choices=["smoke", "scored"], required=True)
    ap.add_argument("--label", required=True)
    a = ap.parse_args()

    wt, want = BUILDS[a.build]
    out = f"{ROOT}/runs/{a.kind}/{a.label}"
    os.makedirs(out)  # fails if it exists: never overwrite evidence
    rootfs = f"{wt}/build/px4_sitl_default/rootfs"
    binp = f"{wt}/build/px4_sitl_default/bin"
    run = {"build": a.build, "kind": a.kind, "label": a.label,
           "started_utc": datetime.now(timezone.utc).isoformat()}

    # 1. build identity
    head = subprocess.run(["git", "-C", wt, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    with open(f"{wt}/build/px4_sitl_default/src/lib/version/build_git_version.h") as f:
        embedded = [ln.split('"')[1] for ln in f if "PX4_GIT_VERSION_STR" in ln][0]
    run.update(worktree=wt, git_head=head, binary_git_version=embedded,
               binary_sha256=sha256(f"{binp}/px4"),
               scenario_sha256=sha256(f"{HARNESS}/smoke_manual_control.py"),
               params_sha256=sha256(f"{HARNESS}/params.json"),
               run_once_sha256=sha256(__file__))
    if head != want or embedded != want:
        run["abort"] = f"commit mismatch: head={head} embedded={embedded} want={want}"
        json.dump(run, open(f"{out}/run.json", "w"), indent=1)
        print(run["abort"])
        return 1
    if subprocess.run(["pgrep", "-x", "px4"], capture_output=True).returncode == 0:
        run["abort"] = "a px4 process is already running"
        json.dump(run, open(f"{out}/run.json", "w"), indent=1)
        print(run["abort"])
        return 1

    before = set(glob.glob(f"{rootfs}/log/*/*.ulg"))

    # 2. launch PX4 (same env as the sihsim_quadx make target; -d = no interactive shell)
    env = dict(os.environ, PX4_SIM_MODEL="sihsim_quadx", PX4_SIMULATOR="sihsim")
    env.pop("PX4_SIM_SPEED_FACTOR", None)
    con = open(f"{out}/px4_console.log", "w")
    px4 = subprocess.Popen([f"{binp}/px4", "-d"], cwd=rootfs, env=env, stdout=con,
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    t_boot = time.time()
    while time.time() - t_boot < BOOT_TIMEOUT_S:
        if "Startup script returned successfully" in open(f"{out}/px4_console.log").read():
            break
        if px4.poll() is not None:
            break
        time.sleep(0.5)
    else:
        run["abort"] = "PX4 boot timeout"

    rc_scn = None
    try:
        if "abort" not in run and px4.poll() is None:
            # 3. explicit parameter set, every run
            params = json.load(open(f"{HARNESS}/params.json"))["params"]
            lines, ok = [], True
            for name, spec in params.items():
                _, o1 = sh([f"{binp}/px4-param", "set", name, str(spec["value"])], cwd=rootfs)
                _, o2 = sh([f"{binp}/px4-param", "show", name], cwd=rootfs)
                lines.append(f"## set {name} {spec['value']}\n{o1}{o2}")
                got = [ln for ln in o2.splitlines() if f" {name} " in f" {ln} " and ":" in ln]
                val = got[-1].split(":")[-1].strip() if got else None
                try:
                    match = val is not None and float(val) == float(spec["value"])
                except ValueError:
                    match = False
                ok &= match
                run.setdefault("params_applied", {})[name] = {"want": spec["value"], "readback": val, "ok": match}
            open(f"{out}/params_applied.txt", "w").write("\n".join(lines))
            if not ok:
                run["abort"] = "parameter readback mismatch"
            else:
                # 4. fixed settle, then scenario
                time.sleep(max(0.0, SETTLE_S - (time.time() - t_boot)))
                with open(f"{out}/scenario_console.log", "w") as sc:
                    try:
                        rc_scn = subprocess.run([PY, f"{HARNESS}/smoke_manual_control.py", "--events",
                                                 f"{out}/scenario_events.json"], stdout=sc,
                                                stderr=subprocess.STDOUT, timeout=SCENARIO_TIMEOUT_S).returncode
                    except subprocess.TimeoutExpired:
                        rc_scn = "timeout"
        else:
            run.setdefault("abort", "PX4 exited during boot")
    finally:
        # 5. shutdown (logger shutdown hook flushes the ULog)
        if px4.poll() is None:
            sh([f"{binp}/px4-shutdown"], cwd=rootfs)
            try:
                px4.wait(timeout=20)
                run["shutdown"] = "clean"
            except subprocess.TimeoutExpired:
                os.killpg(px4.pid, signal.SIGINT)
                try:
                    px4.wait(timeout=10)
                    run["shutdown"] = "SIGINT"
                except subprocess.TimeoutExpired:
                    os.killpg(px4.pid, signal.SIGKILL)
                    run["shutdown"] = "SIGKILL"
        con.close()

    run["scenario_exit"] = rc_scn
    run["px4_exit"] = px4.returncode

    # 6. evidence
    new = sorted(set(glob.glob(f"{rootfs}/log/*/*.ulg")) - before, key=os.path.getmtime)
    run["new_ulogs"] = new
    if len(new) == 1:
        import shutil
        dst = f"{out}/{os.path.basename(os.path.dirname(new[0]))}_{os.path.basename(new[0])}"
        shutil.copy2(new[0], dst)
        run["ulog"] = os.path.basename(dst)
        run["ulog_sha256"] = sha256(dst)
        r = subprocess.run([PY, f"{HARNESS}/ulog_check.py", dst], capture_output=True, text=True)
        open(f"{out}/ulog_check.txt", "w").write(r.stdout + r.stderr)
    else:
        run["evidence_problem"] = f"expected exactly 1 new ULog, found {len(new)}"
    run["finished_utc"] = datetime.now(timezone.utc).isoformat()
    json.dump(run, open(f"{out}/run.json", "w"), indent=1)
    print(json.dumps({k: run.get(k) for k in ("label", "scenario_exit", "shutdown", "ulog", "abort",
                                              "evidence_problem")}))
    if os.path.exists(f"{out}/ulog_check.txt"):
        print(open(f"{out}/ulog_check.txt").read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
