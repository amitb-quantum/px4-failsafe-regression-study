# PX4 build-comparison feasibility experiment — preregistration
Written 2026-10-23, **before any runs**. Cap: 2–3 working days. This is a feasibility experiment, not a product sprint and not a venture.

## The proposition under test (narrowed)
> Given two PX4 builds, automatically identify meaningful changes in tested behavior and produce enough evidence for an engineer to reproduce and investigate them.

## Decisive question
Does a comparison harness provide useful information **beyond existing PX4 test results**, without repeatedly flagging simulation noise?
If the answer is no — because PX4's own CI/tests already surface the difference, or because run-to-run variation swamps real differences — the experiment fails and we stop. Commercial demand remains unproven either way; a successful result justifies a broader sprint and public domain credentials, nothing more.

## System (pinned)
- **One airframe:** PX4 x500 quadcopter, Gazebo (gz) SITL, headless.
- **Venue amendment (2026-10-23, environment-forced, applies identically to both builds):** the vermithor environment (Ubuntu 26.04) has no Gazebo Classic (dropped from current Ubuntu repos), no Java (jMAVSim unavailable), and no gz-transport (new Gazebo unusable). PX4's built-in **SIH simulator is available** (`sihsim_quadx` target present in the configured build). Venue is therefore **SIH, generic quadx airframe**, replacing x500/Gazebo. SIH simulates GPS/IMU/baro/mag internally with no external simulator — a venue change, and for repeatability arguably an upgrade: fewer moving parts between the two builds. Toolchain recipe that builds both commits on this machine (SETUP_NOTES on vermithor): pip CMake 3.28.4, empy==3.3.4, matplotlib spec patch (setup file only), force-include cstdint/stdint flags, `-Wno-error=array-bounds -Wno-error=dangling-reference` demotions for GCC 15 false positives. PX4 source untouched in all cases.
- **Pinned environment:** fixed PX4 commits (below), fixed simulator version, fixed parameter set exported and archived with the results. Any environment change after this document is written gets logged as an amendment, never silently absorbed.
- **Parameter-explicitness amendment (2026-10-23, added before any scored run; learned in smoke):** PX4 parameters **persist** in each build's stored parameter file across sessions. The harness must therefore set the complete relevant parameter set **explicitly at the start of every run** (including `NAV_RCL_ACT=1` — Hold; the default at this commit is 2 = Return) and archive the parameter set used with each run's evidence. No run may inherit parameter state left by an earlier session. Confirmed `NAV_RCL_ACT` values at this commit (commander_params.c): 1=Hold, 2=Return, 3=Land, 5=Terminate, 6=Disarm.
- **Scenario (amended 2026-10-23 — starting mode is load-bearing):** the vehicle must be in a mode **requiring manual control** when RC is lost. Starting in automatic Hold/Loiter would bypass the defect, because the changed condition concerns whether the intended mode requires manual control, and the source carries explicit RC-loss exceptions for automatic modes. Concretely: **Position mode, neutral simulated sticks**, a valid manual-control stream established and confirmed in-log *before* it is stopped; the telemetry (MAVLink) connection stays alive throughout. RC-loss action configured to **Hold**. All relevant parameters and flags (RC-loss delay, failsafe action, manual-control validity) are to be confirmed against these two historical commits during Phase 0 and recorded — not assumed from current PX4 documentation.

## The comparison — one documented historical regression and its fix
- **Regression:** PX4 failsafe mishandling of the Hold RC-loss action — an unintended RTL action overriding Hold (landing can follow RTL; RTL, not Land, is the expected first differing mode). The fixing change is PX4-Autopilot **PR #21403**, "fix failsafe: correctly handle Hold RC loss action," which removes one condition from the failsafe mode check — the condition concerning whether the intended mode requires manual control.
- **Build A (regression):** `f7ed553f57d40073f0f3f3487509e6448a7727e6`
- **Build B (fixed):** `aa5b9ae638f1bf412102de8fabd06740c725abf1`
- These are adjacent commits, verified against the actual PR and source (2026-10-23). If neither commit builds/runs in the pinned simulator, the fallback candidate is the EKF2 GPS-fusion regression (hardcoded 1-second no-aid timeout ignoring EKF2_NOAID_TOUT, plus GPS samples dropped during active fusion → blind-land failsafe), and switching to it requires a written amendment to this preregistration *before* runs.
- **Injection verification (mandatory, per PX4 docs; amended 2026-10-23):** failure injection support "may vary by failure type and between simulators and real vehicle," and unimplemented types return "unsupported." RC loss must be **verified independently of its resulting mode** — from the manual-control signal itself in the log (manual-control setpoint stream stops / RC validity flag drops), *not* inferred from the failsafe mode that follows. Verifying from the mode outcome would be circular, since the mode outcome is what is being scored. A run whose RC loss cannot be independently verified is invalid (see attempt cap under the gate).

## Scoring — sustained behavior, not first mode (amended 2026-10-23)
PX4 can temporarily Hold before executing another failsafe action, so "time to first Hold" would score both builds as correct. Instead:
- After RC loss is triggered, observe for a **fixed window extending beyond the configured RC-loss delay + failsafe-action delay** (exact seconds set in Phase 0 from the historical parameter values, recorded before scored runs).
- Record the **full mode sequence** per run from the ULog (e.g. Position → Hold → RTL → Land), with timestamps.
- **Build B's expected result:** enters Hold and **sustains** it to the end of the window (no RTL/Land departure).
- **Build A's documented defect:** departs Hold via the unintended RTL action (Land may follow RTL and counts as the same departure).

## Control — measuring ordinary variation
- **10 valid repeat runs of Build B**, identical scenario and parameters. The full mode sequence and sustain outcome per run are recorded.
- The control distribution *is* the noise floor. No threshold invented after seeing Build A's data.

## Baseline — run BEFORE the simulation batch (amended 2026-10-23)
- Run the historical `failsafe_test.cpp` suite (and any CI test covering RC-loss Hold behavior) **on both commits and record actual pass/fail outcomes** — inspection alone cannot support a claim about what the existing tests do. Caveat to check explicitly: the historical test uses a test subclass that **overrides mode-fallback handling**, which may mask this exact defect; coverage of the defect must be argued from the test source, not assumed from the presence of an RC-loss test.
- If the baseline already exposes the defect clearly, the preregistered stopping rule applies: **stop before the sim batch** and report that the comparison adds nothing on this case.

## Added result (the thing being tested)
An automatically generated comparison report that:
1. States whether a meaningful behavioral difference exists between Build A and Build B, per the gate below;
2. Names the differing observable(s) with per-build values and the control-run variation next to them;
3. Links every claim to reproducible evidence: exact commit hashes, parameter set, scenario script, and the ULogs of the runs behind each number.

## Preregistered gate (amended 2026-10-23 — reference build must be *correct*, not merely consistent)
- **Build B (reference):** sustains the expected Hold behavior in **≥9 of 10 valid runs**. (The original gate only required B to be self-consistent; a consistently-wrong B could have passed. B must now match the documented expected behavior.)
- **Build A (regression):** exhibits the documented unintended departure from Hold (RTL override) in **≥8 of 10 valid runs**.
- **Flag = meaningful difference** iff both conditions hold. These are feasibility acceptance rules, not statistical proof of reliability — 10 runs cannot establish reliability rates and no such claim will be made.
- **Invalid runs** — missing logs, unverified RC loss, unrelated failsafes intervening — are excluded from scoring, **reported separately with counts and reasons**, and replaced only up to a **fixed attempt cap of 15 attempts per build** to obtain 10 valid runs. If the cap is hit, the shortfall is reported as a finding, not worked around.
- Timing observables (time in Hold before departure, etc.) are reported descriptively per build against the control spread; no significance claim beyond the categorical gate.
- Any other outcome — including "difference is real but PX4's own tests already show it" — is reported as the experiment's finding, not massaged.

## Out of scope (explicit)
RflyMAD · ALFA · post-quantum signatures · signed bundles · AIP/Palantir integration · branding · venture formation · any real aircraft.

## Schedule (cap 2–3 working days; order amended 2026-10-23)
- **Phase 0 / Day 1:** clone PX4-Autopilot at the two pinned commits, build SITL for x500/Gazebo, smoke-test one flight, verify RC loss takes effect in-log (independently of mode outcome), confirm scenario parameters/flags against the historical source.
- **Baseline (before any scored batch):** run `failsafe_test` on both commits, record actual outcomes, assess defect coverage given the test subclass's mode-fallback override. Stopping rule applies here.
- **Day 2:** control runs (Build B ×10 valid), then Build A ×10 valid, same script throughout, attempt cap 15 per build.
- **Day 3:** generate the comparison report, write up results *and* limits, publish internally for Amit's decision on a broader sprint.

## Amendments recorded 2026-10-23 (after Phase 0, before any scored run on either venue)
- **Mechanism correction (supersedes earlier shorthand in working documents):** Hold was never the mode judged unrunnable. The condition removed by PR #21403 made the **user-intended mode** — Position, and the modes in its fallback chain — unrunnable while `manual_control_signal_lost` was set; the real `Failsafe::checkModeFallback` then escalated to RTL, which outranks Hold. That fallback check is precisely the function PX4's own test subclass stubs out, which strengthens the baseline finding. Any earlier phrasing of the form "Hold itself was judged unrunnable" is superseded by this paragraph.
- **Gate-interpretation amendment (approved by the preregistration owner 2026-10-23, after VM Phase 0 smoke evidence, before VM scored runs):** on the VM venue, Build B's `nav_state` is AUTO_LOITER only during the `COM_FAIL_ACT_T` delay phase (5 s), after which it returns to the user-intended POSCTL for the rest of the window with no RTL/Land departure. "Sustains the expected Hold behavior" is therefore scored as a **departure rule**, not a literal nav_state rule: a Build B run passes iff AUTO_LOITER appears at RC loss (within ~2.5 s) **and** neither AUTO_RTL nor AUTO_LAND appears during the observation window; a Build A run is defect-positive iff AUTO_RTL (or Land following it) appears during the window. The ≥9/10 (B) and ≥8/10 (A) thresholds, the 10-valid-runs target, and the 15-attempt cap are unchanged. Full mode sequences are recorded for every run, so the literal reading remains computable post-hoc. The vermithor venue scores under its own `SCORING_RULES.md`, frozen before its first scored run (25 s window); venue rule sets are reported alongside results, not merged silently.
- **Setup-record correction:** Build A's `Tools/setup/requirements.txt` was never patched on vermithor, contrary to an earlier SETUP_NOTES entry; the matplotlib spec patch was applied to Build B's copy only (and to the setup file on other venues as logged). This does not affect the built binaries (dependencies resolve through the environment, not the worktree file).

## Stop conditions
- Injection unverifiable in Gazebo gz after one switch of simulator (gz ↔ Gazebo Classic) → stop, report infeasibility as the result.
- Regression not reproducible in SITL on either candidate (primary or the one amended fallback) → stop, report that.
- Time cap reached → stop wherever it stands; a partial, honest report is the deliverable, not an extension.
