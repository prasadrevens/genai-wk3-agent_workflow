# Voice Assistant Integration Plan

## Goal

Add a voice assistant layer for ImpactIQ that lets operators ask incident questions without changing LangGraph orchestration, remediation behavior, or the existing human approval gate.

## Phase 1 - Implemented

- Add a Voice Incident Commander panel to the dashboard.
- Show suggested voice commands for common incident questions.
- Provide a text input that simulates a voice transcript.
- Keep the feature UI-only and deterministic.

## Phase 2 - Implemented

- Add `answer_voice_question(question, incident_state)`.
- Answer questions about incident status, root cause, business impact, confidence, recommendation, and approval status.
- Return text only.
- Do not trigger approvals, rollbacks, or production changes.

## Phase 3 - Sprint 11 Implemented

- Add backend voice assistant service boundary.
- Add `GET /api/voice/status`.
- Add `POST /api/voice/ask`.
- Add optional ElevenLabs text-to-speech client behind `IMPACTIQ_VOICE_AUDIO_ENABLED`.
- Keep dashboard transcript Q&A read-only and approval-gated.
- Do not expose `ELEVENLABS_API_KEY` in API responses.

## Future Phase 4

- TODO: Add speech-to-text microphone capture and transcript streaming.
- TODO: Add dashboard audio playback controls for synthesized responses.
- TODO: Log voice interactions for audit without storing secrets.

## Guardrails

- ElevenLabs is not called unless `IMPACTIQ_VOICE_AUDIO_ENABLED=true` and `ELEVENLABS_API_KEY` is configured.
- LangGraph agent logic is unchanged.
- Remediation behavior is unchanged.
- Approval remains gated through the existing UI controls.
