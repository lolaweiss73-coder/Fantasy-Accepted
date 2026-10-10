"""Checks for the single-service Morin migration without making paid API calls."""
import asyncio

import app as site
import morin_gateway as gw
from fastapi import HTTPException
from fastapi.responses import Response


def test_embedded_speech_invokes_local_helper(monkeypatch):
    monkeypatch.setattr(gw, "OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(site, "_TTS_CACHE", {})

    async def fake_speech(info):
        assert info.text == "Embedded Morin test speech"
        return Response(content=b"sample-mp3", media_type="audio/mpeg")

    monkeypatch.setattr(gw, "speech_internal", fake_speech)
    result = asyncio.run(site.gateway_speech("Embedded Morin test speech"))
    assert result == b"sample-mp3"
    assert asyncio.run(site.gateway_speech("Embedded Morin test speech")) == b"sample-mp3"


def test_embedded_transcription_invokes_local_helper(monkeypatch):
    monkeypatch.setattr(gw, "OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(site, "current_identity", lambda token: {"id": "test-user", "gender": "female"})

    async def fake_transcribe(info):
        assert info.language == "he"
        return {"text": "בדיקה"}

    monkeypatch.setattr(gw, "transcribe_internal", fake_transcribe)
    result = asyncio.run(site.morin_transcribe(
        site.MorinTranscribeRequest(audio_base64="A" * 120, format="webm", language="he"),
        authorization="Bearer example",
    ))
    assert result == {"text": "בדיקה"}


def test_embedded_structuring_invokes_local_helper(monkeypatch):
    class FakeDb:
        def execute(self, *args):
            pass

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(site, "db", lambda: FakeDb())
    monkeypatch.setattr(gw, "openai_client", object())
    monkeypatch.setattr(site, "current_identity", lambda token: {"id": "test-user", "gender": "female"})
    monkeypatch.setattr(site, "current_site_mode", lambda: "general")

    async def fake_structure(info):
        assert info.track_hint == "general"
        return {
            "title": "Piano lesson", "description": info.text, "mode": "meeting",
            "tags": ["music"], "roles": [], "blocked_reason": None,
            "kind": "general", "morin_response": "אני יכולה לעזור",
            "morin_response_en": "I can help",
            "clarifying_questions": [], "clarifying_questions_en": [],
            "ready_to_draft": True,
            "owner_participates": True,
        }

    monkeypatch.setattr(gw, "structure_internal", fake_structure)
    result = asyncio.run(site.morin_structure(
        site.MorinStructureRequest(text="I would like someone to teach me piano."),
        authorization="Bearer example",
    ))
    assert result["title"] == "Piano lesson"
    assert result["kind"] == "general"
    assert result["morin_response"] == "אני יכולה לעזור"
    assert result["morin_response_en"] == "I can help"
    assert result["clarifying_questions_en"] == []


def test_gateway_auth_remains_required(monkeypatch):
    monkeypatch.setattr(gw, "SERVICE_TOKEN", "internal-secret")
    try:
        gw.require_service_token(None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Missing auth must be rejected")
    gw.require_service_token("Bearer internal-secret")


def test_voice_localization_preserves_caption_question_alignment():
    result = gw.normalize_result({
        "kind": "general",
        "morin_response": "אשמח לעזור",
        "morin_response_en": "I would love to help",
        "clarifying_questions": ["מתי?", "היכן?"],
        "clarifying_questions_en": ["When?", "Where?"],
        "roles": [],
    }, original_text="משאלה חדשה", track_hint="general")
    assert result["morin_response"] == "אשמח לעזור"
    assert result["morin_response_en"] == "I would love to help"
    assert result["clarifying_questions"] == ["מתי?", "היכן?"]
    assert result["clarifying_questions_en"] == ["When?", "Where?"]
