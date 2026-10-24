Baseline verdict (2026-10-23): functional-failsafe_test PASSES on both pinned commits
(A f7ed553f, B aa5b9ae6). The suite contains an RC-loss/Hold case but FailsafeTester
overrides checkModeFallback, replacing the code path PR #21403 fixed; the suite therefore
does not exercise the defect. Stopping rule does NOT fire. Proceed to smoke runs.
Mechanism (corrected from primary sources): PR #21403 removes one condition from
FailsafeBase::modeCanRun() in framework.cpp — with manual_control_signal_lost set,
Hold was judged unrunnable (it requires manual control), so fallback escalated to RTL.
FailsafeTester overrides checkModeFallback() to return Action::None, so the real
fallback chain — and modeCanRun with it — never executes under test; the tester also
hardcodes RC-loss -> RTL in its own checkStateAndMode. The defect is unreachable
from the suite, not merely uncaught by it.
