from __future__ import annotations

import json
import os
import re

from fastapi import FastAPI, Header, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

app = FastAPI(title="Fantasy Accepted Morin Gateway", version="0.1.0")

SERVICE_TOKEN = os.environ.get("FANTASY_SERVICE_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")
client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MINOR_TERM_PATTERN = re.compile(
    r"(?:\b(?:underage|minor|child|kid)\b|קטינ(?:ה|ים|ות)?|\b(?:[0-9]|1[0-7])\s*(?:yo|y/o|years?\s+old)\b|(?:בן|בת)\s*(?:[0-9]|1[0-7])\b)",
    re.IGNORECASE,
)


class StructureRequest(BaseModel):
    text: str = Field(min_length=10, max_length=12000)


def require_service_token(authorization: str | None) -> None:
    if not SERVICE_TOKEN:
        raise HTTPException(503, "Gateway token is not configured")
    if authorization != f"Bearer {SERVICE_TOKEN}":
        raise HTTPException(401, "Unauthorized")


@app.get("/health")
async def health():
    return {"ok": bool(client and SERVICE_TOKEN), "model": OPENAI_MODEL}


@app.post("/structure")
async def structure(info: StructureRequest, authorization: str | None = Header(default=None)):
    require_service_token(authorization)
    if not client:
        raise HTTPException(503, "OpenAI is not configured")
    if MINOR_TERM_PATTERN.search(info.text):
        return {
            "blocked_reason": "Fantasy Accepted מיועד לבני 18 ומעלה בלבד.",
            "title": "",
            "description": "",
            "mode": "either",
            "tags": [],
            "roles": [],
        }

    instructions = """You are Morin inside Fantasy Accepted.
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

    response = await client.responses.create(
        model=OPENAI_MODEL,
        reasoning={"effort": "low"},
        instructions=instructions,
        input=info.text,
    )
    content = (response.output_text or "").strip()
    fence = chr(96) * 3
    if content.startswith(fence):
        content = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", content)
        content = re.sub(r"\s*\x60\x60\x60$", "", content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "Morin returned invalid JSON") from exc

    roles = result.get("roles") if isinstance(result, dict) else []
    if not isinstance(roles, list):
        roles = []
        result["roles"] = roles
    for role in roles:
        if not isinstance(role, dict):
            continue
        min_age = role.get("min_age")
        role["min_age"] = 18 if min_age is None else max(18, int(min_age))
        max_age = role.get("max_age")
        role["max_age"] = 99 if max_age is None else max(role["min_age"], int(max_age))
        role["capacity"] = min(20, max(1, int(role.get("capacity") or 1)))

    result.setdefault("blocked_reason", None)
    result.setdefault("title", "")
    result.setdefault("description", info.text)
    result.setdefault("mode", "either")
    result.setdefault("tags", [])
    return result
