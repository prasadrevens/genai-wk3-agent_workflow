import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from mini_shop_with_ui.app import app
from voice_assistant import (
    ElevenLabsVoiceClient,
    VoiceAssistantConfig,
    answer_voice_question,
)


client = TestClient(app)


class VoiceAssistantTests(unittest.TestCase):
    def test_answer_voice_question_reports_status_without_side_effects(self):
        answer = answer_voice_question(
            "what is the incident status?",
            {
                "incident": {"status": "degraded", "severity": "critical", "confidence": "high"},
                "rca": {},
                "decision_ready": False,
                "confirmation_required": False,
            },
        )

        self.assertIn("degraded", answer)
        self.assertIn("critical", answer)

    def test_answer_voice_question_keeps_approval_gated(self):
        answer = answer_voice_question(
            "approve rollback",
            {
                "incident": {},
                "rca": {},
                "decision_ready": True,
                "confirmation_required": False,
            },
        )

        self.assertIn("gated UI controls", answer)
        self.assertNotIn("rollback applied", answer.lower())

    def test_elevenlabs_client_is_disabled_by_default(self):
        config = VoiceAssistantConfig(api_key="", audio_enabled=False)
        result = ElevenLabsVoiceClient(config).synthesize("hello")

        self.assertFalse(result.enabled)
        self.assertEqual(result.status, "disabled")
        self.assertIsNone(result.audio_base64)

    def test_elevenlabs_client_does_not_call_network_when_audio_disabled(self):
        config = VoiceAssistantConfig(api_key="secret", audio_enabled=False)
        with mock.patch("voice_assistant.urlopen") as urlopen:
            result = ElevenLabsVoiceClient(config).synthesize("hello")

        urlopen.assert_not_called()
        self.assertEqual(result.status, "disabled")

    def test_voice_ask_endpoint_returns_text_only_by_default(self):
        response = client.post("/api/voice/ask", json={"question": "what is the recommendation?"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["answer"])
        self.assertEqual(payload["audio"]["status"], "not_requested")
        self.assertFalse(payload["audio"]["enabled"])

    def test_voice_status_does_not_expose_secret(self):
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret"}, clear=False):
            response = client.get("/api/voice/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["api_key_configured"])
        self.assertNotIn("secret", str(payload))


if __name__ == "__main__":
    unittest.main()
