# JARVIS V9 Release Notes — Ollama-Only Local AI

## AI architecture
- Removed Gemini SDK dependency and Gemini provider implementation.
- Removed Groq and OpenRouter provider routing from the application.
- JARVIS now uses Ollama as its only AI provider.
- All AI service imports now resolve to `app.ai.providers`.
- `AI_PROVIDER=ollama` is the default.
- `OLLAMA_ENABLED=true` is the intended final configuration.

## Privacy / cost behavior
- The backend no longer requires any cloud AI API key.
- AI generation requests are sent only to the configured Ollama base URL.
- Research reports are explicitly marked as offline hypotheses and do not claim live web verification.

## Compatibility
- Existing desktop-control, approval, memory, voice, iPhone remote, team-planning, review and Git features are retained.
- Existing `provider` and `use_search` request fields remain accepted for API compatibility, but non-Ollama providers are rejected and `use_search` cannot create web grounding.

## Validation performed
- Python syntax compilation for all backend Python modules.
- Search of application code for removed cloud provider imports/configuration.
- Dashboard checks updated to present Ollama as the sole provider.

## V9.1 Integrated orchestration update
- iPhone/voice conversations now persist to dashboard chat history when a local user can be resolved.
- Voice activity is logged into the dashboard activity feed.
- Explicit voice memory requests are written to both the user memory profile and shared voice profile.
- Added `/api/live` for a single near-real-time dashboard snapshot and `/api/events` SSE support.
- Added `/api/voice/status` for the iPhone remote dashboard/status panel.
- Team build now runs a discovery phase, then creates a role-covered multi-agent plan and automatically starts orchestration.
- Every specialist role is required to receive a concrete task; independent ready tasks run concurrently in dependency waves.
- Agent status is updated to `working` while executing and returned to `idle` afterward; projects advance to completed or blocked automatically.
- QA review is automatically invoked after completed agent tasks.
- Existing approval workflow remains required for commands, installs and other controlled execution.
