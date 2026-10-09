# JARVIS V4 Release Notes

V4 is built directly from the supplied JARVIS V3 baseline.

## Added
- Browser-native voice input.
- “Hey JARVIS” wake phrase handling.
- Voice command capture.
- Spoken AI responses using browser SpeechSynthesis.
- Voice status/orb UI.
- Voice selection.
- Start/stop voice controls.
- Stop speaking control.
- Voice test checklist.

## Preserved
- Existing V3 AI provider router.
- Gemini 3.6 Flash configuration.
- Existing software developer team, approvals, reviews, Git, research, laptop agent and dashboard functionality.

## Security
- No API key is added for voice.
- Browser voice audio is handled by the browser speech APIs rather than a new backend audio upload endpoint.
- Existing human approval model for sensitive developer commands remains unchanged.
