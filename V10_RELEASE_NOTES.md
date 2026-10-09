# JARVIS V10 — Ollama Secure Orchestration

## Included
- Ollama-only provider with configurable 8192-token context and 300-second request timeout.
- Shell-free allowlisted command execution, strict argument/path checks, and human approval remains required.
- Single-owner registration lock and per-process login throttling.
- Desktop action result state accepts results only after the poll endpoint claims the action (`approved` → `executing` → `executed/failed`).
- User memory is injected into dashboard chat context; iPhone voice conversations remain connected to history and memory.
- Structured Ollama JSON output for agent tasks/team planning/reviews, with one parse-repair retry for developer tasks.
- Git checkpoints around agent task runs, truthful checkpoint reporting, failed-test output persistence, and bounded repair tasks.
- Rejected QA reviews block the reviewed task and queue repair tasks.
- Research instructions prohibit fabricated interviews, quotations, statistics and citations; an existing sample research artifact that claimed fictional interviews has been corrected to a transparent research plan.
- Dashboard and remote HTML JavaScript syntax checked; command-policy regression tests added.
- Clean release excludes populated `.env`, SQLite database, `.git`, virtual environments, caches and duplicate nested project copies.

## Verification
- Python compileall: passed.
- Command-policy regression tests: 4 passed.
- Dashboard and remote JavaScript syntax (`node --check`): passed.
- Windows/Ollama runtime, iPhone LAN connectivity and desktop-agent integration were not available in the build environment and must be tested locally.
