#!/usr/bin/env python3
"""
Scored batch for one build per SCORING_RULES.md: attempts <B>-01..<B>-15, stop at 10 valid.
Usage: batch.py --build {A,B}
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.expanduser("~/px4-regression")
H = f"{ROOT}/harness"
PY = sys.executable
CAP, NEED = 15, 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", choices=["A", "B"], required=True)
    b = ap.parse_args().build
    logp = f"{ROOT}/runs/scored/batch-{b}.jsonl"
    valid = 0
    for n in range(1, CAP + 1):
        label = f"{b}-{n:02d}"
        if os.path.exists(f"{ROOT}/runs/scored/{label}"):
            sys.exit(f"{label} already exists — refusing to overwrite or renumber attempts")
        subprocess.run([PY, f"{H}/run_once.py", "--build", b, "--kind", "scored", "--label", label],
                       stdout=open(f"{ROOT}/runs/scored/{label}.run_once.out", "w"), stderr=subprocess.STDOUT)
        os.makedirs(f"{ROOT}/runs/scored/{label}", exist_ok=True)  # attempt dir exists even if run_once died early
        os.replace(f"{ROOT}/runs/scored/{label}.run_once.out", f"{ROOT}/runs/scored/{label}/run_once.out")
        subprocess.run([PY, f"{H}/score.py", f"{ROOT}/runs/scored/{label}"], stdout=subprocess.DEVNULL)
        s = json.load(open(f"{ROOT}/runs/scored/{label}/score.json"))
        valid += bool(s["valid"])
        line = {"attempt": label, "utc": datetime.now(timezone.utc).isoformat(), "valid": s["valid"],
                "outcome": s["outcome"], "invalid_reason": s["invalid_reason"], "valid_so_far": valid}
        open(logp, "a").write(json.dumps(line) + "\n")
        print(json.dumps(line), flush=True)
        if valid >= NEED:
            break
    print(f"BUILD {b}: {valid} valid in {n} attempts (cap {CAP})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
