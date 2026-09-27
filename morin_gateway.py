from __future__ import annotations

import json
import os
import re

import httpx
from fastapi import FastAPI, Header, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

app = FastAPI(title="Fantasy Accepted Morin Gateway", version="0.2.0")

SERVICE_TOKEN = os.environ.get("FANTASY_SERVICE_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPEN_ROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MORIN_MODEL", "openai/gpt-5.6")
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MINOR_TERM_PATTERN = re.compile(
    r"(?:\b(?:underage|minor|child|kid)\b|קטינ(?:ה|ים|ות)?|\b(?:[0-9]|1[0-7])\s*(?:yo|y/o|years?\s+old)\b|(?:בן|בת)\s*(?:[0-9]|1[0-7])\b)",
    re.IGNORECASE,
)

INSTRUCTIONS = """You are Morin inside Fantasy Accepted.
The user speaks freely about an adult fantasy. Convert it into a neutral, structured draft for the user to review.
Do not publish anything and do not claim the draft is consent to any real-world act.
All participants in this service are adults 18+.
Never invent missing ages, genders, locations, relationship status, or verification.
If the text requests sexual involvement of a minor, set blocked_reason and leave the fantasy fields empty.
Return valid JSON only, with these keys:
title: string
description: string
mode: one of online, meeting, either
tags: array of short strings
roles: array of objects with name, description, capacity, min_age, max_age, allowed_genders, region
blocked_reason: string or null
Unknown values should be empty strings, empty arrays, or null. Every min_age must be at least 18."""


class StructureRequest(BaseModel):
    text: str = Field(min_length=10, max_length=12000)


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


async def call_openai(text: str) -> dict:
    if not openai_client:
        raise RuntimeError("OpenAI not configured")
    response = await openai_client.responses.create(
        model=OPENAI_MODEL,
        reasoning={"effort": "low"},
        instructions=INSTRUCTIONS,
        input=text,
    )
    return parse_json_content(response.output_text or "")


async def call_openrouter(text: str) -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OpenRouter not configured")
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": text},
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


def normalize_result(result: dict, original_text: str) -> dict:
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
    }


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
        }

    errors = []
    result = None

    if openai_client:
        try:
            result = await call_openai(info.text)
        except Exception as exc:
            errors.append(f"openai:{type(exc).__name__}")

    if result is None and OPENROUTER_API_KEY:
        try:
            result = await call_openrouter(info.text)
        except Exception as exc:
            errors.append(f"openrouter:{type(exc).__name__}")

    if result is None:
        print("Morin provider failure:", ",".join(errors))
        raise HTTPException(502, "Morin providers are temporarily unavailable")

    return normalize_result(result, info.text)
