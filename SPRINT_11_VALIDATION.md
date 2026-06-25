# Sprint 11 Validation - ElevenLabs Voice Assistant Boundary

Sprint 11 adds a backend voice assistant boundary and optional ElevenLabs
text-to-speech support without changing LangGraph or remediation behavior.

## Scope

Included:

- `voice_assistant.py` read-only answer and ElevenLabs client boundary.
- `GET /api/voice/status`.
- `POST /api/voice/ask`.
- React Voice Incident Commander now calls the backend voice endpoint.
- Environment flags for optional ElevenLabs audio output.
- Tests that verify no network call occurs when audio is disabled.

Not included:

- Microphone capture.
- Speech-to-text streaming.
- Audio playback controls in the dashboard.
- Any approval, rollback, or LangGraph behavior changes.

## Environment

Text mode works without ElevenLabs credentials.

```text
IMPACTIQ_VOICE_AUDIO_ENABLED=false
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```

Set `IMPACTIQ_VOICE_AUDIO_ENABLED=true` only when you explicitly want backend
text-to-speech synthesis.

## Run

```bash
.venv/bin/python -m unittest tests.test_voice_assistant -v
```

Full validation:

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors tests.test_o11y_emitter tests.test_time_window tests.test_evaluation_harness tests.test_voice_assistant -v
```
