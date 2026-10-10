import unittest

from app.services.workflow import approval_transition_allowed, task_state_is_terminal


class ApprovalTransitionTests(unittest.TestCase):
    def test_pending_can_be_approved_or_rejected(self):
        self.assertTrue(approval_transition_allowed("pending", "approved"))
        self.assertTrue(approval_transition_allowed("pending", "rejected"))

    def test_decisions_cannot_be_reversed_or_replayed(self):
        for state in ("approved", "rejected", "executing", "executed", "failed", "cancelled"):
            with self.subTest(state=state):
                self.assertFalse(approval_transition_allowed(state, "approved"))
                self.assertFalse(approval_transition_allowed(state, "rejected"))

    def test_execution_is_one_way(self):
        self.assertTrue(approval_transition_allowed("approved", "executing"))
        self.assertTrue(approval_transition_allowed("executing", "executed"))
        self.assertTrue(approval_transition_allowed("executing", "failed"))
        self.assertFalse(approval_transition_allowed("executed", "executing"))
        self.assertFalse(approval_transition_allowed("failed", "executing"))

    def test_terminal_task_states(self):
        self.assertTrue(task_state_is_terminal("done"))
        self.assertTrue(task_state_is_terminal("cancelled"))
        self.assertFalse(task_state_is_terminal("blocked"))
        self.assertFalse(task_state_is_terminal("awaiting_verification"))


if __name__ == "__main__":
    unittest.main()
