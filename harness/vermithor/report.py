#!/usr/bin/env python3
"""
Generate the A/B comparison report from scored runs (runs/scored/<A|B>-NN/score.json).
Everything numeric comes from score.json (ULog-derived) and run.json; the code diff and
the logged values of the flags the diff references are pulled automatically.
Usage: report.py > reports/comparison-report.md
"""
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np
from pyulog import ULog

ROOT = os.path.expanduser("~/px4-regression")
A_HASH = "f7ed553f57d40073f0f3f3487509e6448a7727e6"
B_HASH = "aa5b9ae638f1bf412102de8fabd06740c725abf1"
NAVN = {0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION", 4: "AUTO_LOITER", 5: "AUTO_RTL",
        10: "ACRO", 12: "DESCEND", 13: "TERMINATION", 14: "OFFBOARD", 15: "STAB", 18: "AUTO_LAND"}


def load(build):
    runs = []
    for d in sorted(glob.glob(f"{ROOT}/runs/scored/{build}-[0-9][0-9]")):
        s = json.load(open(f"{d}/score.json"))
        rj = f"{d}/run.json"
        s["_run"] = json.load(open(rj)) if os.path.exists(rj) else {}
        s["_dir"] = d
        runs.append(s)
    return runs


def stats(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "n/a"
    return f"min {min(xs):.2f} / median {float(np.median(xs)):.2f} / max {max(xs):.2f} s (n={len(xs)})"


def seq_str(s):
    """Full in-window sequence: ULog time (s since log start) and offset from RC loss."""
    parts = [f"{m['nav']}{'' if m['armed'] else ' (disarmed)'} @ {m['t']:.3f} s ({m['t'] - s['t_loss']:+.3f})"
             for m in s.get("mode_sequence", [])]
    if s["outcome"] == "SUSTAINED_HOLD":
        parts.append(f"held to W end @ {s['window_end']:.3f} s (log continues to {s['log_end']:.3f} s)")
    elif s["log_end"] < s["window_end"]:
        parts.append(f"log ends @ {s['log_end']:.3f} s (disarm; SDLOG_MODE=1)")
    return " → ".join(parts)


def frozen_hashes():
    out = {}
    for ln in open(f"{ROOT}/SETUP_NOTES.md"):
        p = ln.split()
        if len(p) == 2 and len(p[0]) == 64:
            out[p[1]] = p[0]
    return out


def diff_fields():
    d = subprocess.run(["git", "-C", f"{ROOT}/build-B", "diff", A_HASH, B_HASH], capture_output=True,
                       text=True).stdout
    changed = [ln for ln in d.splitlines() if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    fields = sorted(set(re.findall(r"status_flags\.(\w+)", "\n".join(changed))))
    stat = subprocess.run(["git", "-C", f"{ROOT}/build-B", "diff", "--stat", A_HASH, B_HASH],
                          capture_output=True, text=True).stdout
    return d, stat, fields


def flags_at(run, t, fields):
    u = ULog(f"{run['_dir']}/{run['ulog']}", ["failsafe_flags"])
    ff = u.data_list[0].data
    tf = (ff["timestamp"].astype(np.int64) - np.int64(u.start_timestamp)) / 1e6
    i = max(0, np.searchsorted(tf, t) - 1)
    return {f: int(ff[f][i]) for f in fields if f in ff}


def main():
    A, B = load("A"), load("B")
    vA, vB = [r for r in A if r["valid"]], [r for r in B if r["valid"]]
    holdB = sum(r["outcome"] == "SUSTAINED_HOLD" for r in vB)
    rtlA = sum(r["outcome"] == "DEPARTED_RTL" for r in vA)
    gateB = len(vB) >= 10 and holdB >= 9
    gateA = len(vA) >= 10 and rtlA >= 8
    p = print

    p("# PX4 A/B comparison report — RC-loss Hold (PR #21403)\n")
    p("_Generated automatically by `harness/report.py` from ULog-derived `score.json` files. "
      "Rules: `harness/SCORING_RULES.md` (frozen before scored runs)._\n")
    p("## Verdict\n")
    if gateA and gateB:
        p("**Meaningful behavioral difference FLAGGED** — both preregistered gate conditions hold.\n")
    else:
        p("**Gate NOT met** — no difference is flagged under the preregistered rules.\n")
    p("| | Build B (fixed, control) | Build A (regression) |\n|---|---|---|")
    p(f"| Commit | `{B_HASH[:10]}` | `{A_HASH[:10]}` |")
    p(f"| Attempts / valid / invalid | {len(B)} / {len(vB)} / {len(B) - len(vB)} | "
      f"{len(A)} / {len(vA)} / {len(A) - len(vA)} |")
    p(f"| SUSTAINED_HOLD (valid runs) | **{holdB}/{len(vB)}** | {sum(r['outcome'] == 'SUSTAINED_HOLD' for r in vA)}/{len(vA)} |")
    p(f"| DEPARTED_RTL (valid runs) | {sum(r['outcome'] == 'DEPARTED_RTL' for r in vB)}/{len(vB)} | **{rtlA}/{len(vA)}** |")
    p(f"| OTHER (valid runs) | {sum(r['outcome'] == 'OTHER' for r in vB)} | {sum(r['outcome'] == 'OTHER' for r in vA)} |")
    p(f"| Gate condition | B ≥ 9/10 Hold: **{'MET' if gateB else 'NOT MET'}** | A ≥ 8/10 RTL: **{'MET' if gateA else 'NOT MET'}** |\n")

    p("## Differing observable\n")
    p("`vehicle_status.nav_state` inside the 25 s window after RC loss (RC loss = 0→1 edge of "
      "`failsafe_flags.manual_control_signal_lost` after the last valid MAVLink manual-control sample).\n")
    p(f"- RC-loss lag after last logged valid sample — B: {stats([r['loss_lag_s'] for r in vB])}; "
      f"A: {stats([r['loss_lag_s'] for r in vA])}")
    p(f"- RC loss → Hold entry — B: {stats([r['t_loss_to_hold_s'] for r in vB])}; "
      f"A: {stats([r['t_loss_to_hold_s'] for r in vA])}")
    p(f"- Time in Hold before departure — A: {stats([r['hold_before_departure_s'] for r in vA])}; "
      f"B: {sum(r['hold_before_departure_s'] is not None for r in vB)} departures")
    p(f"- Altitude at RC loss (SIH ground truth) — B: {stats([r['alt_at_loss_m'] for r in vB]).replace(' s ', ' m ')}; "
      f"A: {stats([r['alt_at_loss_m'] for r in vA]).replace(' s ', ' m ')}\n")
    p("Control variation (Build B, the noise floor): every valid B run's mode sequence is listed below; "
      "the categorical outcome is what the gate scores.\n")

    d, stat, fields = diff_fields()
    p("## Candidate cause (automatic: code diff between the builds)\n")
    p("```\n" + stat.strip() + "\n```\n```diff\n" + d.strip() + "\n```\n")
    if vA and fields:
        r = next(r for r in vA if r["outcome"] == "DEPARTED_RTL") if rtlA else vA[0]
        dep = next((m["t"] for m in r["mode_sequence"] if m["nav"] == "AUTO_RTL"), r["t_loss"])
        fl = flags_at(r, dep, fields)
        p(f"Logged values of the `failsafe_flags` fields referenced by the changed lines, at the A departure "
          f"(run {r['run']}, t={dep:.2f}s):\n")
        for k, v in fl.items():
            if k.startswith("mode_req"):
                bits = [NAVN.get(b, str(b)) for b in range(32) if v >> b & 1]
                p(f"- `{k}` = 0x{v:x} → modes requiring it: {', '.join(bits)}")
            else:
                p(f"- `{k}` = {v}")
        p("")
        p("Reading (analyst, from source at both commits — not generated): AUTO_LOITER is **not** in the "
          "manual-control requirement mask, so Hold itself stays runnable. The removed term instead makes the "
          "user's intended mode POSCTL — and its fallbacks ALTCTL and STAB, all in the mask — unrunnable "
          "while `manual_control_signal_lost`=1. `Failsafe::checkModeFallback()` then walks "
          "POSCTL→ALTCTL→STAB and ends at its final 'intended mode cannot run' branch, returning RTL, which "
          "outranks the configured RC-loss Hold once the COM_FAIL_ACT_T hold expires. In Build B, "
          "manual-control loss is left to the RC-loss failsafe alone (\"handled separately\"), so Hold "
          "stands. This is the function the historical `FailsafeTester` overrides to return `Action::None`, "
          "which is why PX4's own test cannot see it.\n")

    p("## Evidence (reproduce)\n")
    p("- Harness: `~/px4-regression/harness/` — scenario `smoke_manual_control.py`, launcher `run_once.py`, "
      "params `params.json`, rules `SCORING_RULES.md`, scorer `score.py`; frozen sha256 in `SETUP_NOTES.md`.")
    p("- Reproduce one run: `conda activate px4-regression && python harness/run_once.py --build {A|B} "
      "--kind scored --label <new> && python harness/score.py runs/scored/<new>`")
    p("- Build: both worktrees, `px4_sitl_default`, toolchain recipe in `SETUP_NOTES.md`; venue SIH "
      "`sihsim_quadx`, headless.\n")
    params = json.load(open(f"{ROOT}/harness/params.json"))["params"]
    p("Parameter set (applied and read back every run): " +
      ", ".join(f"`{k}={v['value']}`" for k, v in params.items()) + "\n")
    fh = frozen_hashes()
    p("Harness files frozen before scored attempt 1 (sha256 from `SETUP_NOTES.md`):\n")
    for f, h in fh.items():
        p(f"- `{f}`: `{h}`")
    keys = {"scenario_sha256": "smoke_manual_control.py", "params_sha256": "params.json",
            "run_once_sha256": "run_once.py"}
    mism = [(r["run"], k) for r in A + B for k, f in keys.items() if r["_run"].get(k) != fh.get(f)]
    bins = {b: sorted({r["_run"].get("binary_sha256", "")[:16] for r in runs}) for b, runs in (("A", A), ("B", B))}
    heads = {b: sorted({r["_run"].get("binary_git_version", "") for r in runs}) for b, runs in (("A", A), ("B", B))}
    p(f"\nPer-run check (from each `run.json`): scenario/params/launcher hashes equal the frozen values in "
      f"every attempt: **{not mism}**{'' if not mism else ' — mismatches: ' + str(mism)}. "
      f"Binary sha256 prefix per build: A {bins['A']}, B {bins['B']}; embedded git version: "
      f"A {heads['A']}, B {heads['B']}.\n")
    p("Times below are ULog seconds since log start; offsets are from the verified RC-loss edge (t_loss). "
      "W = [t_loss, t_loss + 25 s].\n")
    for name, runs in (("B", B), ("A", A)):
        p(f"### Build {name} runs\n")
        p("| Attempt | Valid | Outcome / invalid reason | Full mode sequence in W | Arm attempts | ULog (sha256 prefix) |")
        p("|---|---|---|---|---|---|")
        for r in runs:
            arm = ""
            ev = f"{r['_dir']}/scenario_events.json"
            if os.path.exists(ev):
                a = [e for e in json.load(open(ev))["events"] if e["event"] == "armed_confirmed"]
                arm = str(a[0]["attempts"]) if a else "—"
            sha = r["_run"].get("ulog_sha256", "")[:12]
            p(f"| {r['run']} | {'yes' if r['valid'] else 'NO'} | {r['outcome'] or r['invalid_reason']} | "
              f"{seq_str(r) if r['valid'] else ''} | {arm} | `{r['_dir'].replace(ROOT + '/', '')}/{r.get('ulog', '—')}` ({sha}) |")
        p("")
    inv = [r for r in A + B if not r["valid"]]
    p(f"### Invalid attempts (excluded from scoring): {len(inv)}\n")
    for r in inv:
        p(f"- {r['run']}: {r['invalid_reason']}")
    p("")
    p("## Reconciliation checks (automatic: `harness/reconcile.py`)\n")
    rec = subprocess.run([sys.executable, f"{ROOT}/harness/reconcile.py"], capture_output=True, text=True)
    p(rec.stdout + rec.stderr)
    notes = f"{ROOT}/harness/report_analyst_notes.md"
    if os.path.exists(notes):
        p(open(notes).read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
