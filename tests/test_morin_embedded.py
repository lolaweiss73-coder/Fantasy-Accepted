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
    monkeypatch.setattr(site, "current_identity", lambda token: {"id": "test-user"})

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
    monkeypatch.setattr(gw, "openai_client", object())
    monkeypatch.setattr(site, "current_identity", lambda token: {"id": "test-user"})
    monkeypatch.setattr(site, "current_site_mode", lambda: "general")

    async def fake_structure(info):
        assert info.track_hint == "general"
        return {
            "title": "Piano lesson", "description": info.text, "mode": "meeting",
            "tags": ["music"], "roles": [], "blocked_reason": None,
            "kind": "general", "morin_response": "I can help",
            "clarifying_questions": [], "ready_to_draft": True,
            "owner_participates": True,
        }

    monkeypatch.setattr(gw, "structure_internal", fake_structure)
    result = asyncio.run(site.morin_structure(
        site.MorinStructureRequest(text="I would like someone to teach me piano."),
        authorization="Bearer example",
    ))
    assert result["title"] == "Piano lesson"
    assert result["kind"] == "general"


def test_gateway_auth_remains_required(monkeypatch):
    monkeypatch.setattr(gw, "SERVICE_TOKEN", "internal-secret")
    try:
        gw.require_service_token(None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Missing auth must be rejected")
    gw.require_service_token("Bearer internal-secret")
