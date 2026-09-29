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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from storage import DATA_DIR, INTEGRITY_ERRORS, backend_name, db

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Fantasy Accepted", version="0.2.0")
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

        CREATE INDEX IF NOT EXISTS idx_fantasies_created ON fantasies(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_roles_fantasy ON roles(fantasy_id);
        CREATE INDEX IF NOT EXISTS idx_applications_fantasy ON applications(fantasy_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender_id, recipient_id, created_at);
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

    existing_announcement = con.execute("SELECT value FROM site_settings WHERE key='announcement'").fetchone()
    if not existing_announcement:
        con.execute(
            "INSERT INTO site_settings (key,value,updated_at) VALUES (?,?,?)",
            ("announcement", "מזל טוב על הגרושים שלך מיסיס ר.ל.", now()),
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


class MessageCreate(BaseModel):
    recipient_id: str
    text: str = Field(min_length=1, max_length=3000)
    fantasy_id: str | None = None


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
    return row


def identity_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "nickname": row["nickname"],
        "age": row["age"],
        "gender": row["gender"],
        "region": row["region"],
        "marital_status": row["marital_status"],
        "relationship_status": row["relationship_status"],
        "dnd": bool(row["dnd"]),
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
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/announcement")
def get_announcement():
    con = db()
    row = con.execute("SELECT value,updated_at FROM site_settings WHERE key='announcement'").fetchone()
    con.close()
    return {
        "text": row["value"] if row else "",
        "updated_at": row["updated_at"] if row else None,
    }


@app.post("/api/admin/announcement")
def update_announcement(
    info: AnnouncementUpdate,
    x_admin_key: str | None = Header(default=None),
):
    expected = os.environ.get("ADMIN_PASSWORD", "")
    if not expected:
        raise HTTPException(503, "ניהול האתר עדיין לא הוגדר")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(401, "סיסמת מנהל שגויה")

    value = info.text.strip()
    con = db()
    row = con.execute("SELECT key FROM site_settings WHERE key='announcement'").fetchone()
    if row:
        con.execute(
            "UPDATE site_settings SET value=?, updated_at=? WHERE key='announcement'",
            (value, now()),
        )
    else:
        con.execute(
            "INSERT INTO site_settings (key,value,updated_at) VALUES (?,?,?)",
            ("announcement", value, now()),
        )
    con.commit()
    con.close()
    return {"ok": True, "text": value}


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
        "version": "0.2.0",
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
    clauses = ["f.status='published'", "f.visibility='public'"]
    params: list[Any] = []
    if q:
        clauses.append("(f.title LIKE ? OR f.description LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if region:
        clauses.append("(f.region='' OR f.region=?)")
        params.append(region)
    if kind:
        clauses.append("f.kind=?")
        params.append(kind)
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
        raise HTTPException(404, "הפנטזיה לא נמצאה")
    if row["visibility"] == "private" and row["owner_id"] != viewer["id"]:
        con.close()
        raise HTTPException(404, "הפנטזיה לא נמצאה")
    if blocked_between(con, viewer["id"], row["owner_id"]):
        con.close()
        raise HTTPException(403, "אין גישה בין המשתמשים")
    payload = fantasy_payload(con, row, viewer)
    con.close()
    return payload


@app.post("/api/fantasies")
def create_fantasy(info: FantasyCreate, authorization: str | None = Header(default=None)):
    owner = current_identity(authorization)
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
    fantasy = con.execute("SELECT * FROM fantasies WHERE id=? AND status='published'", (fantasy_id,)).fetchone()
    role = con.execute("SELECT * FROM roles WHERE id=? AND fantasy_id=?", (info.role_id, fantasy_id)).fetchone()
    if not fantasy or not role:
        con.close()
        raise HTTPException(404, "הפנטזיה או התפקיד לא נמצאו")
    if fantasy["owner_id"] == applicant["id"]:
        con.close()
        raise HTTPException(400, "אי אפשר להגיש מועמדות לפנטזיה שלך")
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
        raise HTTPException(403, "רק מפרסם הפנטזיה יכול לראות מועמדויות")
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
    con.close()
    return [dict(r) for r in rows]


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
    con.execute("UPDATE applications SET status=?,updated_at=? WHERE id=?", (info.status, now(), application_id))
    con.commit()
    con.close()
    return {"ok": True, "status": info.status}


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
            raise HTTPException(404, "הפנטזיה לא נמצאה")
    message_id = uid()
    con.execute(
        "INSERT INTO messages (id,sender_id,recipient_id,text,fantasy_id,created_at) VALUES (?,?,?,?,?,?)",
        (message_id, sender["id"], recipient["id"], info.text.strip(), info.fantasy_id, now()),
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
                json={"text": info.text, "previous_questions": info.previous_questions, "track_hint": info.track_hint},
            )
        if response.status_code >= 400:
            raise HTTPException(502, "מורין לא הצליחה לעבד את הפנטזיה כרגע")
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
                {"role": "user", "content": info.text + (("\nTrack hint: " + info.track_hint) if info.track_hint else "") + (("\nPrevious clarifying questions: " + json_dump(info.previous_questions)) if info.previous_questions else "")},
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
    result["kind"] = "adult" if result.get("kind") == "adult" else ("general" if result.get("kind") == "general" else (info.track_hint or "general"))
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
