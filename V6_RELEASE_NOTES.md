# JARVIS V6 — Desktop + Remote + Local Voice

## New in V6
- Optional Vosk-based local/offline speech recognition for the Windows voice agent.
- Wake phrase detection can run locally when a Vosk model is configured.
- Online Google STT remains available as a fallback when offline mode is not configured.
- Windows Task Scheduler startup installer for automatic launch at user logon.
- Persistent user memory API in the backend (`/api/memory`).
- Voice bridge now supplies the shared `voice` memory profile as context.
- Mobile-first remote console at `/dashboard/remote.html` for iPhone access over the LAN.
- Existing V5 AI router, approval workflow, developer team, Git checkpoints, browser voice, and PWA remain the baseline.

## Safety boundary
The desktop voice agent only sends conversation requests to JARVIS. It does not expose arbitrary shell execution. Developer actions still require the existing approval workflow.

## Offline model
Vosk itself is not a model. Download a compatible Vosk model separately and point `JARVIS_VOSK_MODEL` to its extracted folder. The model is intentionally not bundled in the ZIP.

## V6 is not yet a privileged Windows service
The included startup installer uses the current Windows user's Task Scheduler and does not grant administrator privileges. This is deliberate. A future release can add a Windows service only after the command/permission boundary is finalized.
