from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class VoiceAssistantConfig:
    api_key: str = ""
    voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    model_id: str = "eleven_multilingual_v2"
    audio_enabled: bool = False
    timeout_seconds: float = 8.0

    @classmethod
    def from_env(cls) -> "VoiceAssistantConfig":
        return cls(
            api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
            model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
            audio_enabled=_truthy(os.getenv("IMPACTIQ_VOICE_AUDIO_ENABLED", "false")),
            timeout_seconds=float(os.getenv("ELEVENLABS_TIMEOUT_SECONDS", "8")),
        )


@dataclass(frozen=True)
class VoiceAudioResult:
    enabled: bool
    status: str
    audio_base64: Optional[str] = None
    content_type: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "status": self.status,
            "audio_base64": self.audio_base64,
            "content_type": self.content_type,
            "error_message": self.error_message,
        }


def answer_voice_question(question: str, incident_state: Mapping[str, Any]) -> str:
    normalized = (question or "").strip().casefold()
    incident = incident_state.get("incident") or {}
    rca = incident_state.get("rca") or {}
    decision_ready = bool(incident_state.get("decision_ready"))
    confirmation_required = bool(incident_state.get("confirmation_required"))

    if confirmation_required:
        approval_status = "Approval is recorded, but rollback still requires the explicit second confirmation gate."
    elif decision_ready:
        approval_status = "Approval controls are available. Any change must still be made through the gated UI controls."
    else:
        approval_status = "Approval is not available yet. Triage must reach the human approval gate first."

    # TODO: ELEVENLABS_API_KEY integration should remain in the voice I/O layer.
    # Voice answers are read-only and must never call remediation or approval APIs.
    if not normalized:
        return "Enter a voice transcript to ask about the current incident."
    if any(token in normalized for token in ("status", "healthy", "degraded")):
        if not incident:
            return "Incident telemetry is still loading."
        return (
            f"The incident is currently {incident.get('status', 'unknown')} with "
            f"{incident.get('severity', 'unknown')} severity and {incident.get('confidence', 'unknown')} confidence."
        )
    if any(token in normalized for token in ("root", "cause", "rca")):
        return rca.get("root_cause") or "Root cause is not available yet. Run triage to synthesize RCA."
    if any(token in normalized for token in ("business", "impact", "revenue")):
        return rca.get("business_impact") or "Business impact is not available yet."
    if "confidence" in normalized:
        return f"The RCA confidence is {rca['confidence']}." if rca.get("confidence") else "Confidence is not available yet."
    if any(token in normalized for token in ("recommend", "action", "fix")):
        if rca.get("gated_action"):
            return f"Recommended action: {rca['gated_action']} This remains gated through the existing approval controls."
        return "No recommendation is available yet."
    if any(token in normalized for token in ("approval", "approve", "reject", "rollback")):
        return approval_status
    return (
        "I can answer questions about incident status, root cause, business impact, "
        "confidence, recommendation, and approval status."
    )


class ElevenLabsVoiceClient:
    def __init__(self, config: VoiceAssistantConfig | None = None) -> None:
        self.config = config or VoiceAssistantConfig.from_env()

    def status(self) -> Dict[str, Any]:
        return {
            "provider": "elevenlabs",
            "audio_enabled": self.config.audio_enabled,
            "api_key_configured": bool(self.config.api_key),
            "voice_id": self.config.voice_id,
            "model_id": self.config.model_id,
        }

    def synthesize(self, text: str) -> VoiceAudioResult:
        if not self.config.audio_enabled:
            return VoiceAudioResult(enabled=False, status="disabled")
        if not self.config.api_key:
            return VoiceAudioResult(
                enabled=True,
                status="auth_failure",
                error_message="ELEVENLABS_API_KEY is required when IMPACTIQ_VOICE_AUDIO_ENABLED=true.",
            )

        # TODO: move to the official ElevenLabs SDK if the project adopts it.
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.voice_id}"
        body = {
            "text": text,
            "model_id": self.config.model_id,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
        }
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.config.api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                audio = response.read()
            return VoiceAudioResult(
                enabled=True,
                status="ok",
                audio_base64=base64.b64encode(audio).decode("ascii"),
                content_type="audio/mpeg",
            )
        except HTTPError as exc:
            return VoiceAudioResult(enabled=True, status="unavailable", error_message=f"HTTP {exc.code}: {exc.reason}")
        except URLError as exc:
            return VoiceAudioResult(enabled=True, status="unavailable", error_message=str(exc.reason))
        except OSError as exc:
            return VoiceAudioResult(enabled=True, status="unavailable", error_message=str(exc))


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}
