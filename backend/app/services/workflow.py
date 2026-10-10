"""Pure state-transition rules shared by the API and automated tests."""

APPROVAL_TRANSITIONS = {
    "pending": {"approved", "rejected"},
    "approved": {"executing"},
    "executing": {"executed", "failed"},
    "rejected": set(),
    "executed": set(),
    "failed": set(),
    "cancelled": set(),
}


def approval_transition_allowed(current: str, target: str) -> bool:
    """Return whether an approval may move to the requested next state."""
    return target in APPROVAL_TRANSITIONS.get(current, set())


def task_state_is_terminal(status: str) -> bool:
    return status in {"done", "cancelled"}
