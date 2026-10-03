from __future__ import annotations

import json
import os
import re

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

app = FastAPI(title="Fantasy Accepted Morin Gateway", version="0.2.0")

SERVICE_TOKEN = os.environ.get("FANTASY_SERVICE_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPEN_ROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MORIN_MODEL", "openai/gpt-5.6")
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "marin")
OPENAI_TTS_INSTRUCTIONS = os.environ.get(
    "OPENAI_TTS_INSTRUCTIONS",
    "Speak as a warm, intelligent, confident adult woman. Natural conversational English, clear diction, gentle energy, subtle smile, no announcer voice, no exaggerated drama, medium pace."
)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MINOR_TERM_PATTERN = re.compile(
    r"(?:\b(?:underage|minor|child|kid)\b|קטינ(?:ה|ים|ות)?|\b(?:[0-9]|1[0-7])\s*(?:yo|y/o|years?\s+old)\b|(?:בן|בת)\s*(?:[0-9]|1[0-7])\b)",
    re.IGNORECASE,
)

INSTRUCTIONS = """You are Morin inside Fantasy Accepted.
The user speaks freely about a wish or fantasy. It may be a general non-sexual wish or an adult sexual fantasy. Convert it into a neutral, structured draft for the user to review.
Do not publish anything and do not claim the draft is consent to any real-world act.
All participants in this service are adults 18+.
Never invent missing ages, genders, locations, relationship status, or verification.
If the text requests sexual involvement of a minor, set blocked_reason and leave the fantasy fields empty.
Return valid JSON only, with these keys:
title: string
description: string
mode: one of online, meeting, either
tags: array of short strings
roles: array of EXTERNAL people still needed, with name, description, capacity, min_age, max_age, allowed_genders, region
owner_participates: boolean
kind: one of general, adult
morin_response: a concise, warm response in the user's language that reflects what you understood without embellishing it
clarifying_questions: array of at most 2 concise questions
ready_to_draft: boolean
blocked_reason: string or null

The fantasy creator is already present in the system. Never create a recruitment role for the creator.
Use kind=general for non-sexual wishes, help, experiences, creative requests, surprises, performances, or other ordinary requests.
Use kind=adult for sexual or explicitly adult fantasies.
If track_hint is supplied, respect it unless the content clearly requires the adult track.
Set owner_participates=true when the creator is themselves part of the fantasy.
Set owner_participates=false when the creator is only arranging something for other people.
Ask a clarifying question only when the missing fact materially affects matching or who needs to be recruited. Do not interrogate the user for decorative details.
If the fantasy is clear enough for matching, clarifying_questions must be [] and ready_to_draft=true.
Unknown non-essential values should be empty strings, empty arrays, or null. Every min_age must be at least 18."""


class StructureRequest(BaseModel):
    text: str = Field(min_length=10, max_length=12000)
    previous_questions: list[str] = Field(default_factory=list, max_length=2)
    track_hint: str | None = Field(default=None, pattern="^(general|adult)$")


class TranscriptionRequest(BaseModel):
    audio_base64: str = Field(min_length=100, max_length=20_000_000)
    format: str = Field(default="webm", pattern="^(webm|ogg|wav|mp3|m4a|aac|flac)$")
    language: str = Field(default="he", min_length=2, max_length=8)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


def require_service_token(authorization: str | None) -> None:
    if not SERVICE_TOKEN:
        raise HTTPException(503, "Gateway token is not configured")
    if authorization != f"Bearer {SERVICE_TOKEN}":
        raise HTTPException(401, "Unauthorized")


def parse_json_content(content: str) -> dict:
    content = (content or "").strip()
    fence = chr(96) * 3
    if content.startswith(fence):
        content = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", content)
        content = re.sub(r"\s*\x60\x60\x60$", "", content)
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("provider returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("provider returned non-object JSON")
    return result


async def call_openai(text: str, previous_questions: list[str], track_hint: str | None) -> dict:
    if not openai_client:
        raise RuntimeError("OpenAI not configured")
    response = await openai_client.responses.create(
        model=OPENAI_MODEL,
        reasoning={"effort": "low"},
        instructions=INSTRUCTIONS,
        input=text + (("\nTrack hint: " + track_hint) if track_hint else "") + (("\nPrevious clarifying questions: " + json.dumps(previous_questions, ensure_ascii=False)) if previous_questions else ""),
    )
    return parse_json_content(response.output_text or "")


async def call_openrouter(text: str, previous_questions: list[str], track_hint: str | None) -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OpenRouter not configured")
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": text + (("\nTrack hint: " + track_hint) if track_hint else "") + (("\nPrevious clarifying questions: " + json.dumps(previous_questions, ensure_ascii=False)) if previous_questions else "")},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://fantasy-accepted-production.up.railway.app",
                "X-Title": "Fantasy Accepted - Morin",
            },
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenRouter returned HTTP {response.status_code}")
    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    return parse_json_content(content)


def normalize_result(result: dict, original_text: str, track_hint: str | None = None) -> dict:
    roles = result.get("roles") or []
    if not isinstance(roles, list):
        roles = []
    clean_roles = []
    for role in roles:
        if not isinstance(role, dict):
            continue
        min_age = role.get("min_age")
        min_age = 18 if min_age in (None, "") else max(18, int(min_age))
        max_age = role.get("max_age")
        max_age = 99 if max_age in (None, "") else max(min_age, int(max_age))
        clean_roles.append(
            {
                "name": str(role.get("name") or "").strip(),
                "description": str(role.get("description") or "").strip(),
                "capacity": min(20, max(1, int(role.get("capacity") or 1))),
                "min_age": min_age,
                "max_age": max_age,
                "allowed_genders": role.get("allowed_genders") if isinstance(role.get("allowed_genders"), list) else [],
                "region": str(role.get("region") or "").strip(),
            }
        )
    owner_participates = result.get("owner_participates")
    result["owner_participates"] = True if owner_participates is None else bool(owner_participates)
    result["kind"] = "adult" if result.get("kind") == "adult" else ("general" if result.get("kind") == "general" else (track_hint or "general"))

    creator_terms = ("יוזם", "יוזמת", "המפנטז", "המפנטזת", "מפרסם", "מפרסמת", "creator", "initiator", "owner")
    if result["owner_participates"]:
        clean_roles = [
            role for role in clean_roles
            if not any(term in role["name"].lower() for term in creator_terms)
        ]

    questions = result.get("clarifying_questions") or []
    if not isinstance(questions, list):
        questions = []
    result["clarifying_questions"] = [str(q).strip() for q in questions if str(q).strip()][:2]
    result["ready_to_draft"] = bool(result.get("ready_to_draft", not result["clarifying_questions"])) and not result["clarifying_questions"]
    result["morin_response"] = str(result.get("morin_response") or "").strip()
    result["roles"] = clean_roles
    result.setdefault("blocked_reason", None)
    result.setdefault("title", "")
    result.setdefault("description", original_text)
    result.setdefault("mode", "either")
    result.setdefault("tags", [])
    return result


@app.get("/health")
async def health():
    providers = []
    if openai_client:
        providers.append("openai")
    if OPENROUTER_API_KEY:
        providers.append("openrouter")
    return {
        "ok": bool(SERVICE_TOKEN and providers),
        "model": OPENAI_MODEL if openai_client else OPENROUTER_MODEL,
        "providers": providers,
        "tts_model": OPENAI_TTS_MODEL if OPENAI_API_KEY else None,
        "tts_voice": OPENAI_TTS_VOICE if OPENAI_API_KEY else None,
    }


@app.post("/transcribe")
async def transcribe(info: TranscriptionRequest, authorization: str | None = Header(default=None)):
    require_service_token(authorization)
    if not OPENROUTER_API_KEY:
        raise HTTPException(503, "Transcription provider is not configured")

    payload = {
        "model": os.environ.get("OPENROUTER_TRANSCRIBE_MODEL", "openai/whisper-large-v3"),
        "input_audio": {
            "data": info.audio_base64,
            "format": info.format,
        },
        "language": info.language,
        "temperature": 0,
    }
    async with httpx.AsyncClient(timeout=75) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/audio/transcriptions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://fantasy-accepted-production.up.railway.app",
                "X-Title": "Fantasy Accepted - Morin",
            },
            json=payload,
        )
    if response.status_code >= 400:
        print("Morin transcription failure:", response.status_code)
        raise HTTPException(502, "Transcription provider is temporarily unavailable")

    result = response.json()
    transcript = str(result.get("text") or "").strip()
    if not transcript:
        raise HTTPException(502, "Transcription provider returned no text")
    return {"text": transcript}


@app.post("/speak")
async def speak(info: SpeechRequest, authorization: str | None = Header(default=None)):
    require_service_token(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(503, "OpenAI speech is not configured")

    async with httpx.AsyncClient(timeout=75) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_TTS_MODEL,
                "voice": OPENAI_TTS_VOICE,
                "input": info.text,
                "instructions": OPENAI_TTS_INSTRUCTIONS,
                "response_format": "mp3",
            },
        )
    if response.status_code >= 400:
        print("Morin TTS failure:", response.status_code, response.text[:300])
        raise HTTPException(502, "OpenAI speech is temporarily unavailable")

    return Response(
        content=response.content,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/structure")
async def structure(info: StructureRequest, authorization: str | None = Header(default=None)):
    require_service_token(authorization)

    if MINOR_TERM_PATTERN.search(info.text):
        return {
            "blocked_reason": "Fantasy Accepted מיועד לבני 18 ומעלה בלבד.",
            "title": "",
            "description": "",
            "mode": "either",
            "tags": [],
            "roles": [],
            "owner_participates": False,
            "kind": info.track_hint or "general",
            "morin_response": "",
            "clarifying_questions": [],
            "ready_to_draft": False,
        }

    errors = []
    result = None

    if openai_client:
        try:
            result = await call_openai(info.text, info.previous_questions, info.track_hint)
        except Exception as exc:
            errors.append(f"openai:{type(exc).__name__}")

    if result is None and OPENROUTER_API_KEY:
        try:
            result = await call_openrouter(info.text, info.previous_questions, info.track_hint)
        except Exception as exc:
            errors.append(f"openrouter:{type(exc).__name__}")

    if result is None:
        print("Morin provider failure:", ",".join(errors))
        raise HTTPException(502, "Morin providers are temporarily unavailable")

    return normalize_result(result, info.text, info.track_hint)
