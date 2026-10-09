# JARVIS V5 — System Voice + Remote Control

V5 extends V4 from browser-only voice into a Windows desktop voice bridge and LAN/iPhone control.

## New
- Windows `voice-agent` that can listen for the wake phrase `Hey JARVIS` system-wide.
- Global hotkey `Ctrl+Alt+J` as a reliable fallback to start a command capture.
- Spoken replies using Windows text-to-speech via `pyttsx3`.
- Token-protected `/api/voice/chat` endpoint for the desktop voice service.
- `run_voice_agent.ps1` launcher and `.env.example` for the voice agent.
- LAN mode helper `run_lan.ps1` so an iPhone on the same Wi-Fi can open the JARVIS PWA.
- Remote/iPhone panel in the dashboard showing the current URL and LAN access instructions.
- Existing V4 browser voice mode remains available.

## Voice architecture
Windows microphone → speech recognition → wake phrase → `/api/voice/chat` → existing AI provider router → Windows TTS.

The default STT engine uses the SpeechRecognition Google recognizer. It requires an internet connection and sends the captured speech to the recognizer service. The service is configurable and can be replaced with a local/offline recognizer in a later release.

## Security
- The desktop voice bridge uses `VOICE_API_TOKEN`; do not expose or share this token.
- The voice endpoint only performs AI chat. It cannot directly execute shell commands.
- Developer commands remain behind the existing JARVIS approval workflow.
- For iPhone use, prefer a trusted home LAN and a strong account password. Do not port-forward the JARVIS server to the public internet.
