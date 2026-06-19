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

## Future Phase 3

- TODO: Add `ELEVENLABS_API_KEY` support for speech-to-text and text-to-speech.
- TODO: Add microphone capture and transcript streaming.
- TODO: Add spoken responses backed by the existing text answer function.
- TODO: Log voice interactions for audit without storing secrets.

## Guardrails

- ElevenLabs is not called in Phase 1 or Phase 2.
- LangGraph agent logic is unchanged.
- Remediation behavior is unchanged.
- Approval remains gated through the existing UI controls.
