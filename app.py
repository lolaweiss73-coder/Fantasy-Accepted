from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from storage import DATA_DIR, INTEGRITY_ERRORS, backend_name, db

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

SITE_MODE = os.environ.get("SITE_MODE", "general").strip().lower()
if SITE_MODE not in {"general", "adult"}:
    SITE_MODE = "general"

app = FastAPI(title="Fantasy Accepted", version="0.3.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def now() -> float:
    return time.time()


def uid() -> str:
    return str(uuid.uuid4())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


MINOR_TERM_PATTERN = re.compile(
    r"(?:\b(?:underage|minor|child|kid)\b|קטינ(?:ה|ים|ות)?|\b(?:[0-9]|1[0-7])\s*(?:yo|y/o|years?\s+old)\b|(?:בן|בת)\s*(?:[0-9]|1[0-7])\b)",
    re.IGNORECASE,
)


def ensure_adult_only_text(*parts: str) -> None:
    text = " ".join(part for part in parts if part)
    if MINOR_TERM_PATTERN.search(text):
        raise HTTPException(
            422,
            "Fantasy Accepted מיועד לבני 18 ומעלה בלבד, ולכן אי אפשר לפרסם תוכן שמערב קטינים.",
        )


def ensure_site_kind(kind: str, *, not_found: bool = False) -> None:
    if kind == SITE_MODE:
        return
    if not_found:
        raise HTTPException(404, "המשאלה או הפנטזיה לא נמצאה באתר הזה")
    target = "האתר הכללי" if kind == "general" else "אתר המבוגרים"
    raise HTTPException(409, f"הפרסום הזה שייך ל{target}")


def init_db() -> None:
    con = db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS identities (
            id TEXT PRIMARY KEY,
            token_hash TEXT UNIQUE NOT NULL,
            hub_subject TEXT UNIQUE,
            nickname TEXT NOT NULL,
            age INTEGER NOT NULL CHECK(age >= 18),
            gender TEXT NOT NULL,
            region TEXT NOT NULL DEFAULT '',
            marital_status TEXT NOT NULL DEFAULT 'prefer_not_to_say',
            relationship_status TEXT NOT NULL DEFAULT 'prefer_not_to_say',
            dnd INTEGER NOT NULL DEFAULT 0,
            skills TEXT NOT NULL DEFAULT '[]',
            availability TEXT NOT NULL DEFAULT '',
            travel_radius_km INTEGER NOT NULL DEFAULT 0,
            bio TEXT NOT NULL DEFAULT '',
            adult_discovery INTEGER NOT NULL DEFAULT 0,
            suspended INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fantasies (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            original_text TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL DEFAULT 'either',
            tags TEXT NOT NULL DEFAULT '[]',
            region TEXT NOT NULL DEFAULT '',
            visibility TEXT NOT NULL DEFAULT 'public',
            status TEXT NOT NULL DEFAULT 'published',
            owner_participates INTEGER NOT NULL DEFAULT 1,
            kind TEXT NOT NULL DEFAULT 'adult',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS roles (
            id TEXT PRIMARY KEY,
            fantasy_id TEXT NOT NULL REFERENCES fantasies(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            capacity INTEGER NOT NULL DEFAULT 1 CHECK(capacity >= 1 AND capacity <= 20),
            min_age INTEGER NOT NULL DEFAULT 18 CHECK(min_age >= 18),
            max_age INTEGER NOT NULL DEFAULT 99 CHECK(max_age >= min_age),
            allowed_genders TEXT NOT NULL DEFAULT '[]',
            region TEXT NOT NULL DEFAULT '',
            marital_status TEXT NOT NULL DEFAULT 'any',
            relationship_status TEXT NOT NULL DEFAULT 'any',
            required_verification TEXT NOT NULL DEFAULT 'none'
        );

        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            fantasy_id TEXT NOT NULL REFERENCES fantasies(id) ON DELETE CASCADE,
            role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            applicant_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            message TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(role_id, applicant_id)
        );

        CREATE TABLE IF NOT EXISTS blocks (
            blocker_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            blocked_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            created_at REAL NOT NULL,
            PRIMARY KEY(blocker_id, blocked_id)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            reporter_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            target_identity_id TEXT REFERENCES identities(id) ON DELETE SET NULL,
            target_fantasy_id TEXT REFERENCES fantasies(id) ON DELETE SET NULL,
            reason TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            sender_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            recipient_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            fantasy_id TEXT REFERENCES fantasies(id) ON DELETE SET NULL,
            created_at REAL NOT NULL,
            read_at REAL
        );

        CREATE TABLE IF NOT EXISTS morin_messages (
            id TEXT PRIMARY KEY,
            identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS site_announcements (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS match_suggestions (
            id TEXT PRIMARY KEY,
            fantasy_id TEXT NOT NULL REFERENCES fantasies(id) ON DELETE CASCADE,
            role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            score INTEGER NOT NULL DEFAULT 0,
            reasons TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'suggested',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(fantasy_id, role_id, identity_id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            recipient_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            fantasy_id TEXT REFERENCES fantasies(id) ON DELETE CASCADE,
            role_id TEXT REFERENCES roles(id) ON DELETE CASCADE,
            actor_id TEXT REFERENCES identities(id) ON DELETE SET NULL,
            created_at REAL NOT NULL,
            read_at REAL
        );

        CREATE TABLE IF NOT EXISTS fulfillment_confirmations (
            fantasy_id TEXT NOT NULL REFERENCES fantasies(id) ON DELETE CASCADE,
            identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
            confirmed_at REAL NOT NULL,
            PRIMARY KEY(fantasy_id, identity_id)
        );

        CREATE INDEX IF NOT EXISTS idx_fantasies_created ON fantasies(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_roles_fantasy ON roles(fantasy_id);
        CREATE INDEX IF NOT EXISTS idx_applications_fantasy ON applications(fantasy_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender_id, recipient_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_match_identity ON match_suggestions(identity_id, status, score DESC);
        CREATE INDEX IF NOT EXISTS idx_match_fantasy ON match_suggestions(fantasy_id, score DESC);
        CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id, read_at, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fulfillment_fantasy ON fulfillment_confirmations(fantasy_id, confirmed_at);
        """
    )

    # Lightweight schema migration for databases created before owner_participates existed.
    if getattr(con, "postgres", False):
        column_exists = con.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name='fantasies' AND column_name='owner_participates'"
        ).fetchone()
    else:
        column_exists = any(row["name"] == "owner_participates" for row in con.execute("PRAGMA table_info(fantasies)").fetchall())
    if not column_exists:
        con.execute("ALTER TABLE fantasies ADD COLUMN owner_participates INTEGER NOT NULL DEFAULT 1")

    if getattr(con, "postgres", False):
        kind_exists = con.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name='fantasies' AND column_name='kind'"
        ).fetchone()
    else:
        kind_exists = any(row["name"] == "kind" for row in con.execute("PRAGMA table_info(fantasies)").fetchall())
    if not kind_exists:
        con.execute("ALTER TABLE fantasies ADD COLUMN kind TEXT NOT NULL DEFAULT 'adult'")

    # Profile fields added for matching and proactive discovery.
    identity_columns = [
        ("skills", "TEXT NOT NULL DEFAULT '[]'"),
        ("availability", "TEXT NOT NULL DEFAULT ''"),
        ("travel_radius_km", "INTEGER NOT NULL DEFAULT 0"),
        ("bio", "TEXT NOT NULL DEFAULT ''"),
        ("adult_discovery", "INTEGER NOT NULL DEFAULT 0"),
        ("suspended", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for column_name, column_sql in identity_columns:
        if getattr(con, "postgres", False):
            exists = con.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name='identities' AND column_name=?",
                (column_name,),
            ).fetchone()
        else:
            exists = any(row["name"] == column_name for row in con.execute("PRAGMA table_info(identities)").fetchall())
        if not exists:
            con.execute(f"ALTER TABLE identities ADD COLUMN {column_name} {column_sql}")

    # One-time migration from the old single-announcement setting.
    # The marker prevents intentionally deleting every ticker message from
    # causing the legacy announcement to reappear after a restart.
    migration_marker = con.execute(
        "SELECT value FROM site_settings WHERE key='announcement_list_migrated_v2'"
    ).fetchone()
    if not migration_marker:
        existing_announcement = con.execute(
            "SELECT value FROM site_settings WHERE key='announcement'"
        ).fetchone()
        announcement_count = con.execute(
            "SELECT COUNT(*) AS n FROM site_announcements"
        ).fetchone()["n"]
        if announcement_count == 0:
            legacy_text = (existing_announcement["value"] if existing_announcement else "").strip()
            if legacy_text:
                ts = now()
                con.execute(
                    "INSERT INTO site_announcements (id,text,created_at,updated_at) VALUES (?,?,?,?)",
                    (uid(), legacy_text, ts, ts),
                )
        marker_ts = now()
        con.execute(
            "INSERT INTO site_settings (key,value,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            ("announcement_list_migrated_v2", "1", marker_ts),
        )

    con.commit()
    con.close()


init_db()


class SessionCreate(BaseModel):
    nickname: str = Field(min_length=2, max_length=40)
    age: int = Field(ge=18, le=120)
    gender: str = Field(min_length=1, max_length=40)
    region: str = Field(default="", max_length=80)
    marital_status: str = Field(default="prefer_not_to_say", max_length=40)
    relationship_status: str = Field(default="prefer_not_to_say", max_length=40)
    adult_confirm: bool


class ProfileUpdate(BaseModel):
    region: str = Field(default="", max_length=80)
    marital_status: str = Field(default="prefer_not_to_say", max_length=40)
    relationship_status: str = Field(default="prefer_not_to_say", max_length=40)
    skills: list[str] = Field(default_factory=list, max_length=30)
    availability: str = Field(default="", max_length=160)
    travel_radius_km: int = Field(default=0, ge=0, le=500)
    bio: str = Field(default="", max_length=1200)
    adult_discovery: bool = False


class RoleInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=700)
    capacity: int = Field(default=1, ge=1, le=20)
    min_age: int = Field(default=18, ge=18, le=120)
    max_age: int = Field(default=99, ge=18, le=120)
    allowed_genders: list[str] = Field(default_factory=list, max_length=10)
    region: str = Field(default="", max_length=80)
    marital_status: str = Field(default="any", max_length=40)
    relationship_status: str = Field(default="any", max_length=40)
    required_verification: str = Field(default="none", max_length=40)


class FantasyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=6000)
    original_text: str = Field(default="", max_length=12000)
    mode: str = Field(default="either", pattern="^(online|meeting|either)$")
    tags: list[str] = Field(default_factory=list, max_length=20)
    region: str = Field(default="", max_length=80)
    visibility: str = Field(default="public", pattern="^(public|limited|private)$")
    owner_participates: bool = True
    kind: str = Field(default="adult", pattern="^(general|adult)$")
    roles: list[RoleInput] = Field(min_length=1, max_length=12)


class ApplicationCreate(BaseModel):
    role_id: str
    message: str = Field(default="", max_length=1500)


class ApplicationDecision(BaseModel):
    status: str = Field(pattern="^(pending|shortlisted|accepted|rejected|withdrawn)$")


class FantasyStageUpdate(BaseModel):
    status: str = Field(pattern="^(matching|connected|in_progress|cancelled)$")


class MessageCreate(BaseModel):
    recipient_id: str
    text: str = Field(min_length=1, max_length=3000)
    fantasy_id: str | None = None


class AdminUserSuspension(BaseModel):
    suspended: bool


class AdminFantasyStatus(BaseModel):
    status: str = Field(pattern="^(published|matching|connected|in_progress|fulfilled_pending|fulfilled|cancelled|hidden)$")


class AdminReportStatus(BaseModel):
    status: str = Field(pattern="^(pending|reviewed|resolved|dismissed)$")


class ReportCreate(BaseModel):
    target_identity_id: str | None = None
    target_fantasy_id: str | None = None
    reason: str = Field(min_length=2, max_length=120)
    details: str = Field(default="", max_length=2000)


class AnnouncementUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=220)


class MorinStructureRequest(BaseModel):
    text: str = Field(min_length=10, max_length=12000)
    previous_questions: list[str] = Field(default_factory=list, max_length=2)
    track_hint: str | None = Field(default=None, pattern="^(general|adult)$")


class MorinTranscribeRequest(BaseModel):
    audio_base64: str = Field(min_length=100, max_length=20_000_000)
    format: str = Field(default="webm", pattern="^(webm|ogg|wav|mp3|m4a|aac|flac)$")
    language: str = Field(default="he", min_length=2, max_length=8)


def current_identity(authorization: str | None) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "נדרשת התחברות")
    token = authorization.removeprefix("Bearer ").strip()
    con = db()
    row = con.execute("SELECT * FROM identities WHERE token_hash=?", (token_hash(token),)).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "ההתחברות אינה תקפה")
    keys = set(row.keys())
    if "suspended" in keys and bool(row["suspended"]):
        raise HTTPException(403, "החשבון הושהה על ידי מנהל האתר")
    return row


def identity_public(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    return {
        "id": row["id"],
        "nickname": row["nickname"],
        "age": row["age"],
        "gender": row["gender"],
        "region": row["region"],
        "marital_status": row["marital_status"],
        "relationship_status": row["relationship_status"],
        "dnd": bool(row["dnd"]),
        "skills": json_load(row["skills"], []) if "skills" in keys else [],
        "availability": row["availability"] if "availability" in keys else "",
        "travel_radius_km": row["travel_radius_km"] if "travel_radius_km" in keys else 0,
        "bio": row["bio"] if "bio" in keys else "",
        "adult_discovery": bool(row["adult_discovery"]) if "adult_discovery" in keys else False,
    }


def completion_stats(con: sqlite3.Connection, identity_id: str) -> dict[str, int]:
    owned = con.execute(
        "SELECT COUNT(*) AS n FROM fantasies WHERE owner_id=? AND status='fulfilled'",
        (identity_id,),
    ).fetchone()["n"]
    participated = con.execute(
        """
        SELECT COUNT(DISTINCT f.id) AS n
        FROM fantasies f
        JOIN applications a ON a.fantasy_id=f.id
        WHERE a.applicant_id=? AND a.status='accepted' AND f.status='fulfilled'
        """,
        (identity_id,),
    ).fetchone()["n"]
    return {
        "fulfilled_as_owner": int(owned),
        "fulfilled_as_participant": int(participated),
        "fulfilled_total": int(owned) + int(participated),
    }


def blocked_between(con: sqlite3.Connection, a: str, b: str) -> bool:
    return bool(
        con.execute(
            "SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)",
            (a, b, b, a),
        ).fetchone()
    )


def role_eligible(role: sqlite3.Row, person: sqlite3.Row) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if person["age"] < role["min_age"] or person["age"] > role["max_age"]:
        reasons.append("age")
    allowed = json_load(role["allowed_genders"], [])
    if allowed and person["gender"] not in allowed:
        reasons.append("gender")
    if role["region"] and person["region"] != role["region"]:
        reasons.append("region")
    if role["marital_status"] != "any" and person["marital_status"] != role["marital_status"]:
        reasons.append("marital_status")
    if role["relationship_status"] != "any" and person["relationship_status"] != role["relationship_status"]:
        reasons.append("relationship_status")
    return not reasons, reasons


def match_tokens(*parts: str) -> set[str]:
    text = " ".join(part or "" for part in parts).lower()
    return {
        token
        for token in re.findall(r"[\w\u0590-\u05FF]+", text, flags=re.UNICODE)
        if len(token) >= 2
    }


def match_score(fantasy: sqlite3.Row, role: sqlite3.Row, person: sqlite3.Row) -> tuple[int, list[str]]:
    eligible, _ = role_eligible(role, person)
    if not eligible:
        return 0, []
    if fantasy["kind"] == "adult" and not bool(person["adult_discovery"]):
        return 0, []

    score = 60
    reasons = ["עומד/ת בתנאי התפקיד"]
    if fantasy["mode"] == "online":
        score += 10
        reasons.append("המשאלה זמינה אונליין")
    elif role["region"] and person["region"] == role["region"]:
        score += 15
        reasons.append("אותו אזור")
    elif fantasy["region"] and person["region"] == fantasy["region"]:
        score += 10
        reasons.append("אזור מתאים")

    skills = [str(skill).strip() for skill in json_load(person["skills"], []) if str(skill).strip()]
    skill_tokens = match_tokens(*skills)
    target_tokens = match_tokens(
        role["name"],
        role["description"],
        fantasy["title"],
        fantasy["description"],
        " ".join(json_load(fantasy["tags"], [])),
    )
    overlap = sorted(skill_tokens & target_tokens)
    if overlap:
        score += min(25, 8 + len(overlap) * 5)
        reasons.append("יכולות תואמות: " + ", ".join(overlap[:4]))
    elif skills:
        score += 3

    if person["availability"]:
        score += 5
        reasons.append("הוגדרה זמינות")
    return min(score, 100), reasons


def add_notification(
    con: sqlite3.Connection,
    recipient_id: str,
    kind: str,
    text: str,
    fantasy_id: str | None = None,
    role_id: str | None = None,
    actor_id: str | None = None,
) -> str:
    notification_id = uid()
    con.execute(
        "INSERT INTO notifications (id,recipient_id,kind,text,fantasy_id,role_id,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (notification_id, recipient_id, kind, text, fantasy_id, role_id, actor_id, now()),
    )
    return notification_id


def refresh_matches_for_fantasy(con: sqlite3.Connection, fantasy_id: str) -> int:
    fantasy = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    if not fantasy or fantasy["status"] not in ("published", "matching"):
        return 0
    roles = con.execute("SELECT * FROM roles WHERE fantasy_id=?", (fantasy_id,)).fetchall()
    people = con.execute("SELECT * FROM identities WHERE id<>? AND dnd=0", (fantasy["owner_id"],)).fetchall()
    created = 0
    for role in roles:
        candidates: list[tuple[int, sqlite3.Row, list[str]]] = []
        for person in people:
            if blocked_between(con, fantasy["owner_id"], person["id"]):
                continue
            score, reasons = match_score(fantasy, role, person)
            if score:
                candidates.append((score, person, reasons))
        candidates.sort(key=lambda item: item[0], reverse=True)
        for score, person, reasons in candidates[:12]:
            suggestion_id = uid()
            ts = now()
            try:
                con.execute(
                    "INSERT INTO match_suggestions (id,fantasy_id,role_id,identity_id,score,reasons,status,created_at,updated_at) VALUES (?,?,?,?,?,?,'suggested',?,?)",
                    (suggestion_id, fantasy_id, role["id"], person["id"], score, json_dump(reasons), ts, ts),
                )
            except INTEGRITY_ERRORS:
                continue
            label = "משאלה" if fantasy["kind"] == "general" else "פנטזיה"
            add_notification(
                con,
                person["id"],
                "match",
                f"מורין מצאה {label} שיכולה להתאים לך: {fantasy['title']} · תפקיד: {role['name']}",
                fantasy_id,
                role["id"],
                fantasy["owner_id"],
            )
            created += 1
    return created


def refresh_matches_for_identity(con: sqlite3.Connection, identity_id: str) -> int:
    person = con.execute("SELECT * FROM identities WHERE id=?", (identity_id,)).fetchone()
    if not person or person["dnd"]:
        return 0
    con.execute(
        "UPDATE match_suggestions SET status='stale',updated_at=? WHERE identity_id=? AND status='suggested'",
        (now(), identity_id),
    )
    rows = con.execute(
        """
        SELECT f.id AS fantasy_id, r.id AS role_id
        FROM fantasies f
        JOIN roles r ON r.fantasy_id=f.id
        WHERE f.status IN ('published','matching') AND f.owner_id<>?
        ORDER BY f.created_at DESC LIMIT 300
        """,
        (identity_id,),
    ).fetchall()
    created = 0
    for link in rows:
        fantasy = con.execute("SELECT * FROM fantasies WHERE id=?", (link["fantasy_id"],)).fetchone()
        role = con.execute("SELECT * FROM roles WHERE id=?", (link["role_id"],)).fetchone()
        if not fantasy or not role or blocked_between(con, fantasy["owner_id"], identity_id):
            continue
        score, reasons = match_score(fantasy, role, person)
        if not score:
            continue
        suggestion_id = uid()
        ts = now()
        try:
            con.execute(
                "INSERT INTO match_suggestions (id,fantasy_id,role_id,identity_id,score,reasons,status,created_at,updated_at) VALUES (?,?,?,?,?,?,'suggested',?,?)",
                (suggestion_id, fantasy["id"], role["id"], identity_id, score, json_dump(reasons), ts, ts),
            )
        except INTEGRITY_ERRORS:
            # An old suggestion can be reactivated after profile changes without re-notifying.
            con.execute(
                "UPDATE match_suggestions SET score=?,reasons=?,status='suggested',updated_at=? WHERE fantasy_id=? AND role_id=? AND identity_id=?",
                (score, json_dump(reasons), ts, fantasy["id"], role["id"], identity_id),
            )
            continue
        label = "משאלה" if fantasy["kind"] == "general" else "פנטזיה"
        add_notification(
            con,
            identity_id,
            "match",
            f"מורין מצאה {label} שיכולה להתאים לך: {fantasy['title']} · תפקיד: {role['name']}",
            fantasy["id"],
            role["id"],
            fantasy["owner_id"],
        )
        created += 1
    return created


def accepted_participant_ids(con: sqlite3.Connection, fantasy_id: str) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT applicant_id FROM applications WHERE fantasy_id=? AND status='accepted'",
        (fantasy_id,),
    ).fetchall()
    return [row["applicant_id"] for row in rows]


def fantasy_roles_filled(con: sqlite3.Connection, fantasy_id: str) -> bool:
    roles = con.execute("SELECT id,capacity FROM roles WHERE fantasy_id=?", (fantasy_id,)).fetchall()
    if not roles:
        return False
    for role in roles:
        count = con.execute(
            "SELECT COUNT(*) AS n FROM applications WHERE fantasy_id=? AND role_id=? AND status='accepted'",
            (fantasy_id, role["id"]),
        ).fetchone()["n"]
        if count < role["capacity"]:
            return False
    return True


def workflow_payload(con: sqlite3.Connection, fantasy: sqlite3.Row, viewer: sqlite3.Row | None) -> dict[str, Any]:
    accepted_ids = accepted_participant_ids(con, fantasy["id"])
    confirmations = con.execute(
        "SELECT identity_id,confirmed_at FROM fulfillment_confirmations WHERE fantasy_id=?",
        (fantasy["id"],),
    ).fetchall()
    confirmed_ids = {row["identity_id"] for row in confirmations}
    viewer_id = viewer["id"] if viewer else None
    return {
        "status": fantasy["status"],
        "roles_filled": fantasy_roles_filled(con, fantasy["id"]),
        "accepted_count": len(accepted_ids),
        "owner_confirmed": fantasy["owner_id"] in confirmed_ids,
        "participant_confirmed": any(identity_id in confirmed_ids for identity_id in accepted_ids),
        "viewer_confirmed": bool(viewer_id and viewer_id in confirmed_ids),
        "viewer_is_accepted": bool(viewer_id and viewer_id in accepted_ids),
        "can_confirm": bool(
            viewer_id
            and fantasy["status"] in ("in_progress", "fulfilled_pending")
            and (viewer_id == fantasy["owner_id"] or viewer_id in accepted_ids)
        ),
    }


def fantasy_payload(con: sqlite3.Connection, row: sqlite3.Row, viewer: sqlite3.Row | None = None) -> dict[str, Any]:
    owner = con.execute("SELECT * FROM identities WHERE id=?", (row["owner_id"],)).fetchone()
    roles = con.execute("SELECT * FROM roles WHERE fantasy_id=? ORDER BY id", (row["id"],)).fetchall()
    role_items = []
    for role in roles:
        item = dict(role)
        item["allowed_genders"] = json_load(item["allowed_genders"], [])
        item["eligible"] = None
        item["ineligible_reasons"] = []
        if viewer:
            item["eligible"], item["ineligible_reasons"] = role_eligible(role, viewer)
        role_items.append(item)
    return {
        "id": row["id"],
        "owner": identity_public(owner),
        "title": row["title"],
        "description": row["description"],
        "original_text": row["original_text"] if viewer and viewer["id"] == row["owner_id"] else "",
        "mode": row["mode"],
        "tags": json_load(row["tags"], []),
        "region": row["region"],
        "visibility": row["visibility"],
        "status": row["status"],
        "owner_participates": bool(row["owner_participates"]),
        "kind": row["kind"],
        "roles": role_items,
        "workflow": workflow_payload(con, row, viewer),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@app.get("/")
def home():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("__SITE_MODE__", SITE_MODE)
    return HTMLResponse(html)


@app.get("/api/site-config")
def site_config():
    return {
        "mode": SITE_MODE,
        "adult": SITE_MODE == "adult",
        "service": "Fantasy Accepted Adult" if SITE_MODE == "adult" else "משאלה התקבלה",
    }


def require_admin(x_admin_key: str | None) -> None:
    configured_password = os.environ.get("ADMIN_PASSWORD", "")
    configured_hash = os.environ.get(
        "ADMIN_PASSWORD_HASH",
        "bc3f409d5818ce56cb8d749d65dc67fb14991e1f8b9503ca34ee5ae9ceb3ab93",
    )
    if configured_password:
        valid = bool(x_admin_key) and secrets.compare_digest(x_admin_key, configured_password)
    else:
        supplied_hash = hashlib.sha256((x_admin_key or "").encode("utf-8")).hexdigest()
        valid = secrets.compare_digest(supplied_hash, configured_hash)
    if not valid:
        raise HTTPException(401, "סיסמת מנהל שגויה")


@app.get("/api/announcements")
def list_announcements():
    con = db()
    rows = con.execute(
        "SELECT id,text,created_at,updated_at FROM site_announcements ORDER BY created_at ASC"
    ).fetchall()
    con.close()
    return [
        {
            "id": row["id"],
            "text": row["text"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


@app.get("/api/announcement")
def get_announcement():
    """Backward-compatible aggregate endpoint."""
    con = db()
    rows = con.execute("SELECT text FROM site_announcements ORDER BY created_at ASC").fetchall()
    con.close()
    return {"text": " ✦ ".join(row["text"] for row in rows)}


@app.post("/api/admin/announcements")
def add_announcement(
    info: AnnouncementUpdate,
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    value = info.text.strip()
    if not value:
        raise HTTPException(422, "הודעה לא יכולה להיות ריקה")
    item_id = uid()
    ts = now()
    con = db()
    con.execute(
        "INSERT INTO site_announcements (id,text,created_at,updated_at) VALUES (?,?,?,?)",
        (item_id, value, ts, ts),
    )
    con.commit()
    con.close()
    return {"id": item_id, "text": value, "created_at": ts, "updated_at": ts}


@app.put("/api/admin/announcements/{announcement_id}")
def edit_announcement(
    announcement_id: str,
    info: AnnouncementUpdate,
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    value = info.text.strip()
    if not value:
        raise HTTPException(422, "הודעה לא יכולה להיות ריקה")
    con = db()
    row = con.execute("SELECT id FROM site_announcements WHERE id=?", (announcement_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "ההודעה לא נמצאה")
    ts = now()
    con.execute(
        "UPDATE site_announcements SET text=?, updated_at=? WHERE id=?",
        (value, ts, announcement_id),
    )
    con.commit()
    con.close()
    return {"id": announcement_id, "text": value, "updated_at": ts}


@app.delete("/api/admin/announcements/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    con = db()
    row = con.execute("SELECT id FROM site_announcements WHERE id=?", (announcement_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "ההודעה לא נמצאה")
    con.execute("DELETE FROM site_announcements WHERE id=?", (announcement_id,))
    con.commit()
    con.close()
    return {"ok": True, "id": announcement_id}


@app.get("/api/health")
def health():
    gateway_ready = bool(os.environ.get("MORIN_GATEWAY_URL") and os.environ.get("MORIN_GATEWAY_TOKEN"))
    direct_ready = bool(
        (os.environ.get("OPENROUTER_API_KEY") and os.environ.get("MORIN_MODEL"))
        or (os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_MODEL"))
    )
    return {
        "ok": True,
        "service": "Fantasy Accepted",
        "version": "0.3.0",
        "site_mode": SITE_MODE,
        "database": backend_name(),
        "data_dir_configured": "FANTASY_DATA_DIR" in os.environ,
        "morin_configured": gateway_ready or direct_ready,
    }


@app.post("/api/session")
def create_session(info: SessionCreate):
    if not info.adult_confirm:
        raise HTTPException(400, "יש לאשר שכל המשתתפים באתר הם בני 18 ומעלה")
    token = secrets.token_urlsafe(32)
    identity_id = uid()
    con = db()
    con.execute(
        "INSERT INTO identities (id,token_hash,nickname,age,gender,region,marital_status,relationship_status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            identity_id,
            token_hash(token),
            info.nickname.strip(),
            info.age,
            info.gender,
            info.region.strip(),
            info.marital_status,
            info.relationship_status,
            now(),
        ),
    )
    con.commit()
    row = con.execute("SELECT * FROM identities WHERE id=?", (identity_id,)).fetchone()
    con.close()
    return {"token": token, "identity": identity_public(row)}


@app.get("/api/me")
def me(authorization: str | None = Header(default=None)):
    return identity_public(current_identity(authorization))


@app.get("/api/me/activity-summary")
def my_activity_summary(authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    stats = completion_stats(con, person["id"])
    con.close()
    return stats


@app.get("/api/identities/{identity_id}/activity-summary")
def identity_activity_summary(identity_id: str, authorization: str | None = Header(default=None)):
    current_identity(authorization)
    con = db()
    person = con.execute("SELECT id FROM identities WHERE id=?", (identity_id,)).fetchone()
    if not person:
        con.close()
        raise HTTPException(404, "המשתמש לא נמצא")
    stats = completion_stats(con, identity_id)
    con.close()
    return stats


@app.put("/api/me/profile")
def update_profile(info: ProfileUpdate, authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    clean_skills = []
    seen = set()
    for skill in info.skills:
        value = skill.strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            clean_skills.append(value)
    con = db()
    con.execute(
        "UPDATE identities SET region=?,marital_status=?,relationship_status=?,skills=?,availability=?,travel_radius_km=?,bio=?,adult_discovery=? WHERE id=?",
        (
            info.region.strip(),
            info.marital_status,
            info.relationship_status,
            json_dump(clean_skills),
            info.availability.strip(),
            info.travel_radius_km,
            info.bio.strip(),
            1 if info.adult_discovery else 0,
            person["id"],
        ),
    )
    refresh_matches_for_identity(con, person["id"])
    con.commit()
    row = con.execute("SELECT * FROM identities WHERE id=?", (person["id"],)).fetchone()
    con.close()
    return identity_public(row)


@app.get("/api/me/matches")
def my_matches(authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    rows = con.execute(
        """
        SELECT ms.*, f.title, f.kind, f.mode, f.region AS fantasy_region,
               r.name AS role_name, r.description AS role_description,
               i.nickname AS owner_nickname
        FROM match_suggestions ms
        JOIN fantasies f ON f.id=ms.fantasy_id
        JOIN roles r ON r.id=ms.role_id
        JOIN identities i ON i.id=f.owner_id
        WHERE ms.identity_id=? AND ms.status='suggested'
          AND f.status IN ('published','matching')
          AND f.kind=?
        ORDER BY ms.score DESC, ms.created_at DESC
        LIMIT 60
        """,
        (person["id"], SITE_MODE),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["reasons"] = json_load(item["reasons"], [])
        out.append(item)
    con.close()
    return out


@app.get("/api/notifications")
def list_notifications(authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    rows = con.execute(
        """
        SELECT n.*
        FROM notifications n
        LEFT JOIN fantasies f ON f.id=n.fantasy_id
        WHERE n.recipient_id=?
          AND (n.fantasy_id IS NULL OR f.kind=?)
        ORDER BY n.created_at DESC
        LIMIT 100
        """,
        (person["id"], SITE_MODE),
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]


@app.post("/api/notifications/{notification_id}/read")
def read_notification(notification_id: str, authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    row = con.execute(
        "SELECT id FROM notifications WHERE id=? AND recipient_id=?",
        (notification_id, person["id"]),
    ).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "ההתראה לא נמצאה")
    con.execute("UPDATE notifications SET read_at=? WHERE id=?", (now(), notification_id))
    con.commit()
    con.close()
    return {"ok": True}


@app.post("/api/me/dnd")
def set_dnd(enabled: bool = Query(...), authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    con.execute("UPDATE identities SET dnd=? WHERE id=?", (1 if enabled else 0, person["id"]))
    con.commit()
    con.close()
    return {"ok": True, "dnd": enabled}


@app.get("/api/fantasies")
def list_fantasies(
    q: str = Query(default="", max_length=100),
    tag: str = Query(default="", max_length=60),
    region: str = Query(default="", max_length=80),
    kind: str = Query(default="", pattern="^(|general|adult)$"),
    authorization: str | None = Header(default=None),
):
    viewer = current_identity(authorization)
    con = db()
    blocked_ids = {
        r["blocked_id"]
        for r in con.execute(
            "SELECT blocked_id FROM blocks WHERE blocker_id=? UNION SELECT blocker_id FROM blocks WHERE blocked_id=?",
            (viewer["id"], viewer["id"]),
        ).fetchall()
    }
    clauses = ["f.status IN ('published','matching')", "f.visibility='public'", "f.kind=?"]
    params: list[Any] = [SITE_MODE]
    if q:
        clauses.append("(f.title LIKE ? OR f.description LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if region:
        clauses.append("(f.region='' OR f.region=?)")
        params.append(region)
    if kind and kind != SITE_MODE:
        con.close()
        return []
    rows = con.execute(
        f"SELECT f.* FROM fantasies f WHERE {' AND '.join(clauses)} ORDER BY f.created_at DESC LIMIT 100",
        params,
    ).fetchall()
    result = []
    for row in rows:
        if row["owner_id"] in blocked_ids:
            continue
        item = fantasy_payload(con, row, viewer)
        if tag and tag not in item["tags"]:
            continue
        result.append(item)
    con.close()
    return result


@app.get("/api/fantasies/{fantasy_id}")
def get_fantasy(fantasy_id: str, authorization: str | None = Header(default=None)):
    viewer = current_identity(authorization)
    con = db()
    row = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "המשאלה או הפנטזיה לא נמצאה")
    if row["kind"] != SITE_MODE:
        con.close()
        raise HTTPException(404, "המשאלה או הפנטזיה לא נמצאה באתר הזה")
    if row["status"] == "hidden" and row["owner_id"] != viewer["id"]:
        con.close()
        raise HTTPException(404, "המשאלה או הפנטזיה לא נמצאה")
    if row["visibility"] == "private" and row["owner_id"] != viewer["id"]:
        con.close()
        raise HTTPException(404, "המשאלה או הפנטזיה לא נמצאה")
    if blocked_between(con, viewer["id"], row["owner_id"]):
        con.close()
        raise HTTPException(403, "אין גישה בין המשתמשים")
    payload = fantasy_payload(con, row, viewer)
    con.close()
    return payload


@app.post("/api/fantasies")
def create_fantasy(info: FantasyCreate, authorization: str | None = Header(default=None)):
    owner = current_identity(authorization)
    ensure_site_kind(info.kind)
    if owner["dnd"]:
        raise HTTPException(409, "החשבון בהפסקה; כבה נא לא להפריע לפני פרסום חדש")
    ensure_adult_only_text(
        info.title,
        info.description,
        info.original_text,
        *(part for role in info.roles for part in (role.name, role.description)),
    )
    for role in info.roles:
        if role.max_age < role.min_age:
            raise HTTPException(400, "טווח גילאים לא תקין")
    fantasy_id = uid()
    ts = now()
    con = db()
    con.execute(
        "INSERT INTO fantasies (id,owner_id,title,description,original_text,mode,tags,region,visibility,status,owner_participates,kind,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            fantasy_id,
            owner["id"],
            info.title.strip(),
            info.description.strip(),
            info.original_text.strip(),
            info.mode,
            json_dump([t.strip() for t in info.tags if t.strip()]),
            info.region.strip(),
            info.visibility,
            "published",
            1 if info.owner_participates else 0,
            info.kind,
            ts,
            ts,
        ),
    )
    for role in info.roles:
        con.execute(
            "INSERT INTO roles (id,fantasy_id,name,description,capacity,min_age,max_age,allowed_genders,region,marital_status,relationship_status,required_verification) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid(),
                fantasy_id,
                role.name.strip(),
                role.description.strip(),
                role.capacity,
                role.min_age,
                role.max_age,
                json_dump(role.allowed_genders),
                role.region.strip(),
                role.marital_status,
                role.relationship_status,
                role.required_verification,
            ),
        )
    con.commit()
    row = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    payload = fantasy_payload(con, row, owner)
    refresh_matches_for_fantasy(con, fantasy_id)
    con.commit()
    con.close()
    return payload


@app.post("/api/fantasies/{fantasy_id}/apply")
def apply_to_fantasy(
    fantasy_id: str,
    info: ApplicationCreate,
    authorization: str | None = Header(default=None),
):
    applicant = current_identity(authorization)
    con = db()
    fantasy = con.execute("SELECT * FROM fantasies WHERE id=? AND status IN ('published','matching')", (fantasy_id,)).fetchone()
    role = con.execute("SELECT * FROM roles WHERE id=? AND fantasy_id=?", (info.role_id, fantasy_id)).fetchone()
    if not fantasy or not role:
        con.close()
        raise HTTPException(404, "הפרסום או התפקיד לא נמצאו")
    if fantasy["owner_id"] == applicant["id"]:
        con.close()
        raise HTTPException(400, "אי אפשר להגיש מועמדות לפרסום שלך")
    if blocked_between(con, applicant["id"], fantasy["owner_id"]):
        con.close()
        raise HTTPException(403, "אין גישה בין המשתמשים")
    owner = con.execute("SELECT * FROM identities WHERE id=?", (fantasy["owner_id"],)).fetchone()
    if owner["dnd"]:
        con.close()
        raise HTTPException(409, "המפרסם/ת כרגע בהפסקה")
    eligible, reasons = role_eligible(role, applicant)
    if not eligible:
        con.close()
        raise HTTPException(422, {"message": "המועמדות אינה עומדת בתנאי החובה", "reasons": reasons})
    app_id = uid()
    ts = now()
    try:
        con.execute(
            "INSERT INTO applications (id,fantasy_id,role_id,applicant_id,message,status,created_at,updated_at) VALUES (?,?,?,?,?,'pending',?,?)",
            (app_id, fantasy_id, info.role_id, applicant["id"], info.message.strip(), ts, ts),
        )
        if fantasy["status"] == "published":
            con.execute("UPDATE fantasies SET status='matching',updated_at=? WHERE id=?", (ts, fantasy_id))
        con.execute(
            "UPDATE match_suggestions SET status='responded',updated_at=? WHERE fantasy_id=? AND role_id=? AND identity_id=?",
            (ts, fantasy_id, info.role_id, applicant["id"]),
        )
        add_notification(
            con,
            fantasy["owner_id"],
            "application_received",
            f"מועמדות חדשה למשאלה: {fantasy['title']} · תפקיד: {role['name']}",
            fantasy_id,
            role["id"],
            applicant["id"],
        )
        con.commit()
    except INTEGRITY_ERRORS:
        con.close()
        raise HTTPException(409, "כבר הוגשה מועמדות לתפקיד הזה")
    con.close()
    return {"id": app_id, "status": "pending"}


@app.get("/api/fantasies/{fantasy_id}/applications")
def list_applications(fantasy_id: str, authorization: str | None = Header(default=None)):
    owner = current_identity(authorization)
    con = db()
    fantasy = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    if not fantasy or fantasy["owner_id"] != owner["id"]:
        con.close()
        raise HTTPException(403, "רק מפרסם/ת המשאלה או הפנטזיה יכול/ה לראות מועמדויות")
    rows = con.execute(
        """
        SELECT a.*, i.nickname, i.age, i.gender, i.region, r.name AS role_name
        FROM applications a
        JOIN identities i ON i.id=a.applicant_id
        JOIN roles r ON r.id=a.role_id
        WHERE a.fantasy_id=?
        ORDER BY a.created_at DESC
        """,
        (fantasy_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["completion_stats"] = completion_stats(con, row["applicant_id"])
        out.append(item)
    con.close()
    return out


@app.post("/api/applications/{application_id}/status")
def decide_application(
    application_id: str,
    info: ApplicationDecision,
    authorization: str | None = Header(default=None),
):
    owner = current_identity(authorization)
    con = db()
    row = con.execute(
        "SELECT a.*, f.owner_id FROM applications a JOIN fantasies f ON f.id=a.fantasy_id WHERE a.id=?",
        (application_id,),
    ).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "המועמדות לא נמצאה")
    if row["applicant_id"] == owner["id"] and info.status == "withdrawn":
        pass
    elif row["owner_id"] != owner["id"]:
        con.close()
        raise HTTPException(403, "אין הרשאה לעדכן את המועמדות")
    fantasy = con.execute("SELECT * FROM fantasies WHERE id=?", (row["fantasy_id"],)).fetchone()
    if fantasy["status"] in ("in_progress", "fulfilled_pending", "fulfilled", "cancelled"):
        con.close()
        raise HTTPException(409, "אי אפשר לשנות משתתפים אחרי שהביצוע התחיל או הסתיים")

    if info.status == "accepted":
        role = con.execute("SELECT * FROM roles WHERE id=?", (row["role_id"],)).fetchone()
        accepted_now = con.execute(
            "SELECT COUNT(*) AS n FROM applications WHERE role_id=? AND status='accepted' AND id<>?",
            (row["role_id"], application_id),
        ).fetchone()["n"]
        if accepted_now >= role["capacity"]:
            con.close()
            raise HTTPException(409, "כל המקומות בתפקיד הזה כבר התמלאו")

    con.execute("UPDATE applications SET status=?,updated_at=? WHERE id=?", (info.status, now(), application_id))
    if info.status == "accepted":
        label = "המשאלה" if fantasy["kind"] == "general" else "הפנטזיה"
        add_notification(
            con,
            row["applicant_id"],
            "application_accepted",
            f"המועמדות שלך התקבלה עבור {label}: {fantasy['title']}",
            row["fantasy_id"],
            row["role_id"],
            row["owner_id"],
        )
        if fantasy_roles_filled(con, row["fantasy_id"]):
            con.execute(
                "UPDATE fantasies SET status='connected',updated_at=? WHERE id=?",
                (now(), row["fantasy_id"]),
            )
            for participant_id in accepted_participant_ids(con, row["fantasy_id"]):
                add_notification(
                    con,
                    participant_id,
                    "team_ready",
                    f"הצוות הושלם עבור: {fantasy['title']}. אפשר לעבור לביצוע.",
                    row["fantasy_id"],
                    actor_id=row["owner_id"],
                )
        else:
            con.execute(
                "UPDATE fantasies SET status='matching',updated_at=? WHERE id=?",
                (now(), row["fantasy_id"]),
            )
    elif info.status in ("rejected", "withdrawn") and fantasy["status"] == "connected":
        if not fantasy_roles_filled(con, row["fantasy_id"]):
            con.execute(
                "UPDATE fantasies SET status='matching',updated_at=? WHERE id=?",
                (now(), row["fantasy_id"]),
            )
    con.commit()
    updated_fantasy = con.execute("SELECT status FROM fantasies WHERE id=?", (row["fantasy_id"],)).fetchone()
    con.close()
    return {"ok": True, "status": info.status, "fantasy_status": updated_fantasy["status"]}


@app.get("/api/me/wishes")
def my_wishes(authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    rows = con.execute(
        """
        SELECT DISTINCT f.*
        FROM fantasies f
        LEFT JOIN applications a ON a.fantasy_id=f.id AND a.status='accepted'
        WHERE (f.owner_id=? OR a.applicant_id=?)
          AND f.kind=?
        ORDER BY f.updated_at DESC
        LIMIT 100
        """,
        (person["id"], person["id"], SITE_MODE),
    ).fetchall()
    out = [fantasy_payload(con, row, person) for row in rows]
    con.close()
    return out


@app.post("/api/fantasies/{fantasy_id}/stage")
def update_fantasy_stage(
    fantasy_id: str,
    info: FantasyStageUpdate,
    authorization: str | None = Header(default=None),
):
    owner = current_identity(authorization)
    con = db()
    fantasy = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    if not fantasy or fantasy["owner_id"] != owner["id"]:
        con.close()
        raise HTTPException(403, "רק יוזם/ת המשאלה יכול/ה לעדכן את שלב הביצוע")

    current = fantasy["status"]
    transitions = {
        "published": {"matching", "cancelled"},
        "matching": {"connected", "cancelled"},
        "connected": {"in_progress", "cancelled"},
        "in_progress": {"cancelled"},
        "fulfilled_pending": {"in_progress", "cancelled"},
    }
    if info.status not in transitions.get(current, set()):
        con.close()
        raise HTTPException(409, f"אי אפשר לעבור מ-{current} ל-{info.status}")
    if info.status in ("connected", "in_progress", "fulfilled_pending") and not fantasy_roles_filled(con, fantasy_id):
        con.close()
        raise HTTPException(409, "עדיין חסרים משתתפים כדי לעבור לשלב הזה")

    con.execute("UPDATE fantasies SET status=?,updated_at=? WHERE id=?", (info.status, now(), fantasy_id))
    accepted_ids = accepted_participant_ids(con, fantasy_id)
    status_text = {
        "matching": "המשאלה מחפשת התאמות",
        "connected": "כל המשתתפים נמצאו",
        "in_progress": "המשאלה עברה לביצוע",
        "cancelled": "המשאלה בוטלה",
    }[info.status]
    for participant_id in accepted_ids:
        add_notification(
            con,
            participant_id,
            "workflow",
            f"{status_text}: {fantasy['title']}",
            fantasy_id,
            actor_id=owner["id"],
        )
    con.commit()
    row = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    payload = fantasy_payload(con, row, owner)
    con.close()
    return payload


@app.post("/api/fantasies/{fantasy_id}/confirm-fulfilled")
def confirm_fulfilled(fantasy_id: str, authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    fantasy = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    if not fantasy:
        con.close()
        raise HTTPException(404, "המשאלה לא נמצאה")
    accepted_ids = accepted_participant_ids(con, fantasy_id)
    if person["id"] != fantasy["owner_id"] and person["id"] not in accepted_ids:
        con.close()
        raise HTTPException(403, "רק משתתפים במשאלה יכולים לאשר הגשמה")
    if fantasy["status"] not in ("in_progress", "fulfilled_pending"):
        con.close()
        raise HTTPException(409, "אפשר לאשר הגשמה רק כשהמשאלה בביצוע או ממתינה לאישור")

    con.execute(
        "INSERT INTO fulfillment_confirmations (fantasy_id,identity_id,confirmed_at) VALUES (?,?,?) ON CONFLICT(fantasy_id,identity_id) DO NOTHING",
        (fantasy_id, person["id"], now()),
    )
    confirmed_rows = con.execute(
        "SELECT identity_id FROM fulfillment_confirmations WHERE fantasy_id=?",
        (fantasy_id,),
    ).fetchall()
    confirmed_ids = {row["identity_id"] for row in confirmed_rows}
    owner_confirmed = fantasy["owner_id"] in confirmed_ids
    participant_confirmed = any(identity_id in confirmed_ids for identity_id in accepted_ids)

    new_status = fantasy["status"]
    if owner_confirmed and participant_confirmed:
        new_status = "fulfilled"
    elif owner_confirmed:
        new_status = "fulfilled_pending"

    if new_status != fantasy["status"]:
        con.execute("UPDATE fantasies SET status=?,updated_at=? WHERE id=?", (new_status, now(), fantasy_id))

    recipients = set(accepted_ids + [fantasy["owner_id"]])
    recipients.discard(person["id"])
    if new_status == "fulfilled":
        notice = f"המשאלה הוגשמה ואושרה משני הצדדים: {fantasy['title']}"
    else:
        notice = f"התקבל אישור הגשמה עבור: {fantasy['title']}. ממתינים לאישור מהצד השני."
    for recipient_id in recipients:
        add_notification(
            con,
            recipient_id,
            "fulfillment",
            notice,
            fantasy_id,
            actor_id=person["id"],
        )

    con.commit()
    row = con.execute("SELECT * FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    payload = fantasy_payload(con, row, person)
    con.close()
    return payload


@app.get("/api/inbox")
def inbox(authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    rows = con.execute(
        """
        SELECT CASE WHEN sender_id=? THEN recipient_id ELSE sender_id END AS other_id,
               MAX(created_at) AS last_ts,
               SUM(CASE WHEN recipient_id=? AND read_at IS NULL THEN 1 ELSE 0 END) AS unread
        FROM messages
        WHERE sender_id=? OR recipient_id=?
        GROUP BY other_id ORDER BY last_ts DESC
        """,
        (person["id"], person["id"], person["id"], person["id"]),
    ).fetchall()
    out = []
    for row in rows:
        other = con.execute("SELECT * FROM identities WHERE id=?", (row["other_id"],)).fetchone()
        if other:
            out.append({"identity": identity_public(other), "last_ts": row["last_ts"], "unread": row["unread"]})
    con.close()
    return out


@app.get("/api/messages/{other_id}")
def conversation(other_id: str, authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    con = db()
    if blocked_between(con, person["id"], other_id):
        con.close()
        raise HTTPException(403, "אין גישה בין המשתמשים")
    con.execute(
        "UPDATE messages SET read_at=? WHERE recipient_id=? AND sender_id=? AND read_at IS NULL",
        (now(), person["id"], other_id),
    )
    rows = con.execute(
        """
        SELECT * FROM messages
        WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)
        ORDER BY created_at ASC LIMIT 200
        """,
        (person["id"], other_id, other_id, person["id"]),
    ).fetchall()
    con.commit()
    con.close()
    return [dict(r) for r in rows]


@app.post("/api/messages")
def send_message(info: MessageCreate, authorization: str | None = Header(default=None)):
    sender = current_identity(authorization)
    con = db()
    recipient = con.execute("SELECT * FROM identities WHERE id=?", (info.recipient_id,)).fetchone()
    if not recipient:
        con.close()
        raise HTTPException(404, "המשתמש לא נמצא")
    if blocked_between(con, sender["id"], recipient["id"]):
        con.close()
        raise HTTPException(403, "אין גישה בין המשתמשים")
    if recipient["dnd"]:
        established = con.execute(
            "SELECT 1 FROM messages WHERE (sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?) LIMIT 1",
            (sender["id"], recipient["id"], recipient["id"], sender["id"]),
        ).fetchone()
        if not established:
            con.close()
            raise HTTPException(409, "המשתמש/ת כרגע בהפסקה ולא מקבל/ת פניות חדשות")
    if info.fantasy_id:
        fantasy = con.execute("SELECT * FROM fantasies WHERE id=?", (info.fantasy_id,)).fetchone()
        if not fantasy:
            con.close()
            raise HTTPException(404, "המשאלה או הפנטזיה לא נמצאה")
    message_id = uid()
    con.execute(
        "INSERT INTO messages (id,sender_id,recipient_id,text,fantasy_id,created_at) VALUES (?,?,?,?,?,?)",
        (message_id, sender["id"], recipient["id"], info.text.strip(), info.fantasy_id, now()),
    )
    add_notification(
        con,
        recipient["id"],
        "message",
        f"הודעה חדשה מאת {sender['nickname']}",
        info.fantasy_id,
        actor_id=sender["id"],
    )
    con.commit()
    con.close()
    return {"id": message_id, "ok": True}


@app.post("/api/blocks/{identity_id}")
def block(identity_id: str, authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    if identity_id == person["id"]:
        raise HTTPException(400, "אי אפשר לחסום את עצמך")
    con = db()
    con.execute(
        "INSERT INTO blocks (blocker_id,blocked_id,created_at) VALUES (?,?,?) ON CONFLICT(blocker_id,blocked_id) DO NOTHING",
        (person["id"], identity_id, now()),
    )
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/api/admin/overview")
def admin_overview(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    con = db()
    users = con.execute("SELECT COUNT(*) AS n FROM identities").fetchone()["n"]
    suspended = con.execute("SELECT COUNT(*) AS n FROM identities WHERE suspended=1").fetchone()["n"]
    wishes = con.execute("SELECT COUNT(*) AS n FROM fantasies").fetchone()["n"]
    active = con.execute(
        "SELECT COUNT(*) AS n FROM fantasies WHERE status IN ('published','matching','connected','in_progress','fulfilled_pending')"
    ).fetchone()["n"]
    fulfilled = con.execute("SELECT COUNT(*) AS n FROM fantasies WHERE status='fulfilled'").fetchone()["n"]
    pending_reports = con.execute("SELECT COUNT(*) AS n FROM reports WHERE status='pending'").fetchone()["n"]
    applications = con.execute("SELECT COUNT(*) AS n FROM applications").fetchone()["n"]
    con.close()
    return {
        "users": int(users),
        "suspended_users": int(suspended),
        "wishes": int(wishes),
        "active_wishes": int(active),
        "fulfilled_wishes": int(fulfilled),
        "pending_reports": int(pending_reports),
        "applications": int(applications),
    }


@app.get("/api/admin/users")
def admin_users(
    limit: int = Query(default=100, ge=1, le=300),
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    con = db()
    rows = con.execute(
        "SELECT * FROM identities ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for row in rows:
        item = {
            "id": row["id"],
            "nickname": row["nickname"],
            "age": row["age"],
            "gender": row["gender"],
            "region": row["region"],
            "dnd": bool(row["dnd"]),
            "suspended": bool(row["suspended"]),
            "created_at": row["created_at"],
            "completion_stats": completion_stats(con, row["id"]),
        }
        out.append(item)
    con.close()
    return out


@app.post("/api/admin/users/{identity_id}/suspension")
def admin_user_suspension(
    identity_id: str,
    info: AdminUserSuspension,
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    con = db()
    row = con.execute("SELECT id FROM identities WHERE id=?", (identity_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "המשתמש לא נמצא")
    con.execute("UPDATE identities SET suspended=? WHERE id=?", (1 if info.suspended else 0, identity_id))
    con.commit()
    con.close()
    return {"ok": True, "suspended": info.suspended}


@app.get("/api/admin/fantasies")
def admin_fantasies(
    limit: int = Query(default=100, ge=1, le=300),
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    con = db()
    rows = con.execute(
        """
        SELECT f.id,f.title,f.kind,f.status,f.visibility,f.created_at,f.updated_at,
               i.id AS owner_id,i.nickname AS owner_nickname,
               (SELECT COUNT(*) FROM applications a WHERE a.fantasy_id=f.id) AS application_count,
               (SELECT COUNT(*) FROM reports r WHERE r.target_fantasy_id=f.id AND r.status='pending') AS pending_reports
        FROM fantasies f
        JOIN identities i ON i.id=f.owner_id
        ORDER BY f.updated_at DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]


@app.post("/api/admin/fantasies/{fantasy_id}/status")
def admin_fantasy_status(
    fantasy_id: str,
    info: AdminFantasyStatus,
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    con = db()
    row = con.execute("SELECT id FROM fantasies WHERE id=?", (fantasy_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "המשאלה לא נמצאה")
    con.execute("UPDATE fantasies SET status=?,updated_at=? WHERE id=?", (info.status, now(), fantasy_id))
    con.commit()
    con.close()
    return {"ok": True, "status": info.status}


@app.get("/api/admin/reports")
def admin_reports(
    status: str = Query(default="", pattern="^(|pending|reviewed|resolved|dismissed)$"),
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    con = db()
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("r.status=?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = con.execute(
        f"""
        SELECT r.*, reporter.nickname AS reporter_nickname,
               target.nickname AS target_nickname,
               f.title AS fantasy_title
        FROM reports r
        JOIN identities reporter ON reporter.id=r.reporter_id
        LEFT JOIN identities target ON target.id=r.target_identity_id
        LEFT JOIN fantasies f ON f.id=r.target_fantasy_id
        {where}
        ORDER BY r.created_at DESC LIMIT 200
        """,
        params,
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]


@app.post("/api/admin/reports/{report_id}/status")
def admin_report_status(
    report_id: str,
    info: AdminReportStatus,
    x_admin_key: str | None = Header(default=None),
):
    require_admin(x_admin_key)
    con = db()
    row = con.execute("SELECT id FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "הדיווח לא נמצא")
    con.execute("UPDATE reports SET status=? WHERE id=?", (info.status, report_id))
    con.commit()
    con.close()
    return {"ok": True, "status": info.status}


@app.post("/api/reports")
def report(info: ReportCreate, authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    if not info.target_identity_id and not info.target_fantasy_id:
        raise HTTPException(400, "צריך לבחור יעד לדיווח")
    con = db()
    report_id = uid()
    con.execute(
        "INSERT INTO reports (id,reporter_id,target_identity_id,target_fantasy_id,reason,details,created_at) VALUES (?,?,?,?,?,?,?)",
        (
            report_id,
            person["id"],
            info.target_identity_id,
            info.target_fantasy_id,
            info.reason.strip(),
            info.details.strip(),
            now(),
        ),
    )
    con.commit()
    con.close()
    return {"ok": True, "id": report_id}


@app.post("/api/morin/transcribe")
async def morin_transcribe(info: MorinTranscribeRequest, authorization: str | None = Header(default=None)):
    current_identity(authorization)

    gateway_url = os.environ.get("MORIN_GATEWAY_URL", "").rstrip("/")
    gateway_token = os.environ.get("MORIN_GATEWAY_TOKEN", "")
    if not gateway_url or not gateway_token:
        raise HTTPException(503, "התמלול הקולי עדיין לא מחובר באתר")

    async with httpx.AsyncClient(timeout=80) as client:
        response = await client.post(
            f"{gateway_url}/transcribe",
            headers={
                "Authorization": f"Bearer {gateway_token}",
                "Content-Type": "application/json",
            },
            json={
                "audio_base64": info.audio_base64,
                "format": info.format,
                "language": info.language,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(502, "לא הצלחתי לתמלל את ההקלטה כרגע")
    return response.json()


@app.post("/api/morin/structure")
async def morin_structure(info: MorinStructureRequest, authorization: str | None = Header(default=None)):
    person = current_identity(authorization)
    ensure_adult_only_text(info.text)

    gateway_url = os.environ.get("MORIN_GATEWAY_URL", "").rstrip("/")
    gateway_token = os.environ.get("MORIN_GATEWAY_TOKEN", "")

    if gateway_url and gateway_token:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{gateway_url}/structure",
                headers={
                    "Authorization": f"Bearer {gateway_token}",
                    "Content-Type": "application/json",
                },
                json={"text": info.text, "previous_questions": info.previous_questions, "track_hint": SITE_MODE},
            )
        if response.status_code >= 400:
            raise HTTPException(502, "מורין לא הצליחה לעבד את הבקשה כרגע")
        result = response.json()
    else:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        model = os.environ.get("MORIN_MODEL")
        if not api_key or not model:
            raise HTTPException(503, "מורין עדיין לא מחוברת לספק AI באתר")

        system = (
            "You are Morin inside Fantasy Accepted. Convert an adult user's free-text wish or fantasy into neutral structured metadata. "
            "All participants on this service must be 18+. Never invent missing ages, genders, locations, or consent conditions. "
            "If the text appears to request sexual involvement of a minor, return JSON with blocked_reason and no fantasy fields. "
            "The service supports both general wishes and adult fantasies. Return strict JSON only with keys: title, description, mode, tags, roles, blocked_reason, morin_response, clarifying_questions, ready_to_draft, owner_participates, kind. "
            "roles is an array of external people still needed, each {name, description, capacity, min_age, max_age, allowed_genders, region}. "
            "Do not create a role for the fantasy creator. Set owner_participates true if the creator is part of the fantasy, false if they are only arranging it for others. "
            "kind must be general for non-sexual wishes and adult for sexual/adult fantasies. Respect track_hint when supplied unless the content clearly belongs in the adult track. "
            "Ask at most two clarifying questions, and only when an ambiguity materially affects matching. Use null or empty arrays for unknown values; min_age must never be below 18."
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": info.text + "\nTrack hint: " + SITE_MODE + (("\nPrevious clarifying questions: " + json_dump(info.previous_questions)) if info.previous_questions else "")},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code >= 400:
            raise HTTPException(502, "ספק ה-AI לא החזיר תשובה תקינה")
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(502, "מורין החזירה מבנה שלא ניתן לקרוא")

    if result.get("blocked_reason"):
        return result

    roles = result.get("roles") or []
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

    questions = result.get("clarifying_questions") or []
    if not isinstance(questions, list):
        questions = []
    result["clarifying_questions"] = [str(q).strip() for q in questions if str(q).strip()][:2]
    result["owner_participates"] = bool(result.get("owner_participates", True))
    result["kind"] = "adult" if result.get("kind") == "adult" else ("general" if result.get("kind") == "general" else SITE_MODE)
    if result["kind"] != SITE_MODE:
        return {
            "blocked_reason": (
                "הבקשה הזו שייכת לאתר המבוגרים הנפרד." if result["kind"] == "adult"
                else "הבקשה הזו שייכת לאתר המשאלות הכללי."
            ),
            "kind": result["kind"],
            "clarifying_questions": [],
            "ready_to_draft": False,
        }
    result["morin_response"] = str(result.get("morin_response") or "").strip()
    result["ready_to_draft"] = bool(result.get("ready_to_draft", not result["clarifying_questions"])) and not result["clarifying_questions"]

    con = db()
    con.execute(
        "INSERT INTO morin_messages (id,identity_id,role,text,created_at) VALUES (?,?,?,?,?)",
        (uid(), person["id"], "user", info.text, now()),
    )
    con.execute(
        "INSERT INTO morin_messages (id,identity_id,role,text,created_at) VALUES (?,?,?,?,?)",
        (uid(), person["id"], "assistant", json_dump(result), now()),
    )
    con.commit()
    con.close()
    return result
