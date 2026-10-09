# JARVIS V6 Desktop Voice Agent

V6 adds an optional **fully local speech-recognition path** using Vosk. Once a Vosk model is installed on the laptop, wake-phrase detection and speech recognition can run without sending microphone audio to a cloud speech service.

## Quick start

1. Copy `.env.example` to `.env`.
2. Set `JARVIS_SERVER` and `JARVIS_VOICE_TOKEN`.
3. Run the normal requirements for the online fallback.
4. Start `run_voice_agent.ps1` from the V6 root.

## Offline voice

Install:

```powershell
python -m pip install -r voice-agent/requirements-offline.txt
```

Download a Vosk English/Indian-English model separately and extract it outside the repo. Set:

```env
JARVIS_VOSK_MODEL=C:\Models\vosk-model
JARVIS_OFFLINE_ONLY=true
```

Vosk model files are not bundled in the JARVIS release because they are large third-party assets.

## Windows startup

`install_startup_task.ps1` creates a per-user Windows Task Scheduler entry. It starts JARVIS at login without requiring Administrator privileges.

The desktop agent is intentionally **not** a remote shell. It only sends conversation requests to `/api/voice/chat`; developer commands continue through JARVIS's approval workflow.
