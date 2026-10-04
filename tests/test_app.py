import os
import tempfile
from pathlib import Path

import pytest

os.environ["FANTASY_DATA_DIR"] = tempfile.mkdtemp(prefix="fantasy-accepted-tests-")
os.environ["ADMIN_PASSWORD"] = "test-admin-secret"
os.environ["SITE_MODE"] = "adult"

from fastapi.testclient import TestClient
import app as app_module
from app import app, init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_site_mode():
    app_module.SITE_MODE = "adult"
    yield
    app_module.SITE_MODE = "adult"


def join(nickname, age=30, gender="female", region="center"):
    response = client.post(
        "/api/session",
        json={
            "nickname": nickname,
            "age": age,
            "gender": gender,
            "region": region,
            "marital_status": "single",
            "relationship_status": "single",
            "adult_confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['token']}"}


def create_fantasy(headers, allowed_genders=None, min_age=18, max_age=99, kind="adult", expect_status=200):
    response = client.post(
        "/api/fantasies",
        headers=headers,
        json={
            "title": "טיול לילי בעיר",
            "description": "פנטזיה חברתית שמתחילה בשיחה והיכרות ומחפשת משתתף נוסף.",
            "original_text": "טקסט מקורי",
            "mode": "either",
            "tags": ["שיחה", "היכרות"],
            "region": "center",
            "visibility": "public",
            "owner_participates": True,
            "kind": kind,
            "roles": [
                {
                    "name": "משתתף/ת נוסף/ת",
                    "description": "תפקיד פתוח",
                    "capacity": 1,
                    "min_age": min_age,
                    "max_age": max_age,
                    "allowed_genders": allowed_genders or [],
                    "region": "center",
                    "marital_status": "any",
                    "relationship_status": "any",
                    "required_verification": "none",
                }
            ],
        },
    )
    assert response.status_code == expect_status, response.text
    return response.json()


def test_adult_gate_rejects_minor():
    response = client.post(
        "/api/session",
        json={
            "nickname": "young",
            "age": 17,
            "gender": "male",
            "region": "",
            "marital_status": "single",
            "relationship_status": "single",
            "adult_confirm": True,
        },
    )
    assert response.status_code == 422


def test_create_and_list_fantasy_with_server_side_eligibility():
    owner, owner_h = join("owner", 34, "female")
    viewer, viewer_h = join("viewer", 28, "male")
    fantasy = create_fantasy(owner_h, allowed_genders=["male"], min_age=25, max_age=40)

    response = client.get("/api/fantasies", headers=viewer_h)
    assert response.status_code == 200
    found = next(x for x in response.json() if x["id"] == fantasy["id"])
    assert found["roles"][0]["eligible"] is True


def test_ineligible_application_is_rejected_by_server():
    owner, owner_h = join("owner2", 35, "female")
    viewer, viewer_h = join("viewer2", 22, "male")
    fantasy = create_fantasy(owner_h, allowed_genders=["male"], min_age=30, max_age=50)
    role_id = fantasy["roles"][0]["id"]

    response = client.post(
        f"/api/fantasies/{fantasy['id']}/apply",
        headers=viewer_h,
        json={"role_id": role_id, "message": "אשמח לדבר"},
    )
    assert response.status_code == 422


def test_application_owner_can_accept_and_message():
    owner, owner_h = join("owner3", 38, "female")
    applicant, applicant_h = join("candidate", 32, "male")
    fantasy = create_fantasy(owner_h, allowed_genders=["male"], min_age=25, max_age=45)
    role_id = fantasy["roles"][0]["id"]

    applied = client.post(
        f"/api/fantasies/{fantasy['id']}/apply",
        headers=applicant_h,
        json={"role_id": role_id, "message": "היי"},
    )
    assert applied.status_code == 200
    app_id = applied.json()["id"]

    decision = client.post(
        f"/api/applications/{app_id}/status",
        headers=owner_h,
        json={"status": "accepted"},
    )
    assert decision.status_code == 200

    sent = client.post(
        "/api/messages",
        headers=owner_h,
        json={"recipient_id": applicant["identity"]["id"], "text": "בוא נדבר", "fantasy_id": fantasy["id"]},
    )
    assert sent.status_code == 200

    conversation = client.get(f"/api/messages/{owner['identity']['id']}", headers=applicant_h)
    assert conversation.status_code == 200
    assert conversation.json()[-1]["text"] == "בוא נדבר"


def test_block_stops_new_message():
    a, a_h = join("blocker", 31, "female")
    b, b_h = join("blocked", 31, "male")
    target = b["identity"]["id"]
    assert client.post(f"/api/blocks/{target}", headers=a_h).status_code == 200
    response = client.post(
        "/api/messages",
        headers=b_h,
        json={"recipient_id": a["identity"]["id"], "text": "hello", "fantasy_id": None},
    )
    assert response.status_code == 403


def test_dnd_blocks_new_contacts_but_keeps_existing_conversation_open():
    a, a_h = join("dnd-owner", 33, "female")
    b, b_h = join("existing-contact", 34, "male")
    c, c_h = join("new-contact", 35, "male")

    # Establish B <-> A before DND.
    first = client.post(
        "/api/messages",
        headers=b_h,
        json={"recipient_id": a["identity"]["id"], "text": "היי", "fantasy_id": None},
    )
    assert first.status_code == 200

    assert client.post("/api/me/dnd?enabled=true", headers=a_h).status_code == 200

    existing = client.post(
        "/api/messages",
        headers=b_h,
        json={"recipient_id": a["identity"]["id"], "text": "ממשיכים", "fantasy_id": None},
    )
    assert existing.status_code == 200

    new_contact = client.post(
        "/api/messages",
        headers=c_h,
        json={"recipient_id": a["identity"]["id"], "text": "פנייה חדשה", "fantasy_id": None},
    )
    assert new_contact.status_code == 409


def test_manual_publish_rejects_minor_involvement_text():
    owner, owner_h = join("adult-owner", 40, "female")
    response = client.post(
        "/api/fantasies",
        headers=owner_h,
        json={
            "title": "בקשה אסורה",
            "description": "This request explicitly includes an underage participant.",
            "original_text": "",
            "mode": "either",
            "tags": [],
            "region": "",
            "visibility": "public",
            "roles": [{
                "name": "participant",
                "description": "",
                "capacity": 1,
                "min_age": 18,
                "max_age": 99,
                "allowed_genders": [],
                "region": "",
                "marital_status": "any",
                "relationship_status": "any",
                "required_verification": "none"
            }]
        },
    )
    assert response.status_code == 422


def test_owner_participation_is_stored_separately_from_recruitment_roles():
    owner, owner_h = join("organizer-owner", 36, "female")
    response = client.post(
        "/api/fantasies",
        headers=owner_h,
        json={
            "title": "מחווה למישהי אחרת",
            "description": "פנטזיה שבה היוזמת מארגנת מחווה עבור אדם אחר ומחפשת מבצע.",
            "original_text": "טקסט מקורי",
            "mode": "meeting",
            "tags": ["מחווה"],
            "region": "center",
            "visibility": "public",
            "owner_participates": False,
            "roles": [{
                "name": "מבצע/ת",
                "description": "מי שיבצע את המחווה",
                "capacity": 1,
                "min_age": 18,
                "max_age": 99,
                "allowed_genders": [],
                "region": "",
                "marital_status": "any",
                "relationship_status": "any",
                "required_verification": "none"
            }]
        },
    )
    assert response.status_code == 200, response.text
    fantasy = response.json()
    assert fantasy["owner_participates"] is False
    assert len(fantasy["roles"]) == 1


def test_general_and_adult_sites_are_server_side_isolated():
    owner, owner_h = join("track-owner", 41, "female")
    viewer, viewer_h = join("track-viewer", 39, "male")

    app_module.SITE_MODE = "general"
    general = create_fantasy(owner_h, kind="general")
    create_fantasy(owner_h, kind="adult", expect_status=409)

    general_feed = client.get("/api/fantasies", headers=viewer_h)
    assert general_feed.status_code == 200
    assert any(item["id"] == general["id"] for item in general_feed.json())
    assert all(item["kind"] == "general" for item in general_feed.json())
    assert client.get("/api/fantasies?kind=adult", headers=viewer_h).json() == []

    app_module.SITE_MODE = "adult"
    adult = create_fantasy(owner_h, kind="adult")
    adult_feed = client.get("/api/fantasies", headers=viewer_h)
    assert adult_feed.status_code == 200
    assert any(item["id"] == adult["id"] for item in adult_feed.json())
    assert all(item["kind"] == "adult" for item in adult_feed.json())
    assert client.get(f"/api/fantasies/{general['id']}", headers=viewer_h).status_code == 404

    app_module.SITE_MODE = "general"
    assert client.get(f"/api/fantasies/{adult['id']}", headers=viewer_h).status_code == 404


def test_announcement_list_is_public_and_admin_can_add_edit_delete():
    initial = client.get("/api/announcements")
    assert initial.status_code == 200
    assert isinstance(initial.json(), list)

    denied = client.post(
        "/api/admin/announcements",
        headers={"X-Admin-Key": "wrong"},
        json={"text": "חג סוכות שמח לכל בית ישראל"},
    )
    assert denied.status_code == 401

    first = client.post(
        "/api/admin/announcements",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"text": "מזל טוב על הגירושים גברת ר.ל."},
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = client.post(
        "/api/admin/announcements",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"text": "חג סוכות שמח לכל בית ישראל"},
    )
    assert second.status_code == 200
    second_id = second.json()["id"]

    public = client.get("/api/announcements")
    assert public.status_code == 200
    texts = [item["text"] for item in public.json()]
    assert "מזל טוב על הגירושים גברת ר.ל." in texts
    assert "חג סוכות שמח לכל בית ישראל" in texts

    aggregate = client.get("/api/announcement")
    assert aggregate.status_code == 200
    assert " ✦ " in aggregate.json()["text"]

    edited = client.put(
        f"/api/admin/announcements/{second_id}",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"text": "חג שמח לכל בית ישראל"},
    )
    assert edited.status_code == 200
    assert edited.json()["text"] == "חג שמח לכל בית ישראל"

    deleted_second = client.delete(
        f"/api/admin/announcements/{second_id}",
        headers={"X-Admin-Key": "test-admin-secret"},
    )
    assert deleted_second.status_code == 200

    deleted_first = client.delete(
        f"/api/admin/announcements/{first_id}",
        headers={"X-Admin-Key": "test-admin-secret"},
    )
    assert deleted_first.status_code == 200

    empty = client.get("/api/announcements")
    assert empty.status_code == 200
    assert empty.json() == []

    # A server restart must not resurrect the old single-message setting.
    init_db()
    after_restart = client.get("/api/announcements")
    assert after_restart.status_code == 200
    assert after_restart.json() == []


def update_matching_profile(headers, *, skills=None, region="center", availability="evenings", adult_discovery=False):
    response = client.put(
        "/api/me/profile",
        headers=headers,
        json={
            "region": region,
            "skills": skills or [],
            "availability": availability,
            "travel_radius_km": 25,
            "bio": "פרופיל בדיקה",
            "adult_discovery": adult_discovery,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_general_wish_creates_proactive_match_and_notification():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("wish-owner", 35, "female", "center")
    candidate, candidate_h = join("wish-candidate", 30, "male", "center")
    update_matching_profile(candidate_h, skills=["שיחה", "היכרות"], adult_discovery=False)

    wish = create_fantasy(owner_h, allowed_genders=["male"], min_age=25, max_age=40, kind="general")

    matches = client.get("/api/me/matches", headers=candidate_h)
    assert matches.status_code == 200
    found = [m for m in matches.json() if m["fantasy_id"] == wish["id"]]
    assert found
    assert found[0]["score"] >= 60

    notifications = client.get("/api/notifications", headers=candidate_h)
    assert notifications.status_code == 200
    matching = [n for n in notifications.json() if n["fantasy_id"] == wish["id"] and n["kind"] == "match"]
    assert matching


def test_adult_proactive_matches_require_explicit_opt_in():
    owner, owner_h = join("adult-owner", 36, "female", "center")
    candidate, candidate_h = join("adult-candidate", 31, "male", "center")
    update_matching_profile(candidate_h, skills=["שיחה"], adult_discovery=False)

    fantasy = create_fantasy(owner_h, allowed_genders=["male"], min_age=25, max_age=40, kind="adult")

    before = client.get("/api/me/matches", headers=candidate_h)
    assert before.status_code == 200
    assert all(m["fantasy_id"] != fantasy["id"] for m in before.json())

    update_matching_profile(candidate_h, skills=["שיחה"], adult_discovery=True)
    after = client.get("/api/me/matches", headers=candidate_h)
    assert after.status_code == 200
    assert any(m["fantasy_id"] == fantasy["id"] for m in after.json())

    notifications = client.get("/api/notifications", headers=candidate_h)
    assert notifications.status_code == 200
    assert any(n["fantasy_id"] == fantasy["id"] and n["kind"] == "match" for n in notifications.json())


def test_wish_execution_lifecycle_requires_both_sides_to_confirm():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("flow-owner", 38, "female", "center")
    participant, participant_h = join("flow-participant", 32, "male", "center")
    update_matching_profile(participant_h, skills=["שיחה"], adult_discovery=False)
    wish = create_fantasy(owner_h, allowed_genders=["male"], min_age=25, max_age=40, kind="general")
    role_id = wish["roles"][0]["id"]

    applied = client.post(
        f"/api/fantasies/{wish['id']}/apply",
        headers=participant_h,
        json={"role_id": role_id, "message": "אשמח להשתתף"},
    )
    assert applied.status_code == 200, applied.text

    owner_notifications = client.get("/api/notifications", headers=owner_h)
    assert owner_notifications.status_code == 200
    assert any(
        n["fantasy_id"] == wish["id"] and n["kind"] == "application_received"
        for n in owner_notifications.json()
    )

    applications = client.get(f"/api/fantasies/{wish['id']}/applications", headers=owner_h)
    assert applications.status_code == 200
    application_id = applications.json()[0]["id"]

    accepted = client.post(
        f"/api/applications/{application_id}/status",
        headers=owner_h,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["fantasy_status"] == "connected"

    start = client.post(
        f"/api/fantasies/{wish['id']}/stage",
        headers=owner_h,
        json={"status": "in_progress"},
    )
    assert start.status_code == 200, start.text
    assert start.json()["workflow"]["status"] == "in_progress"

    participant_confirmation = client.post(
        f"/api/fantasies/{wish['id']}/confirm-fulfilled",
        headers=participant_h,
    )
    assert participant_confirmation.status_code == 200, participant_confirmation.text
    assert participant_confirmation.json()["workflow"]["status"] == "in_progress"
    assert participant_confirmation.json()["workflow"]["participant_confirmed"] is True
    assert participant_confirmation.json()["workflow"]["owner_confirmed"] is False

    owner_confirmation = client.post(
        f"/api/fantasies/{wish['id']}/confirm-fulfilled",
        headers=owner_h,
    )
    assert owner_confirmation.status_code == 200, owner_confirmation.text
    assert owner_confirmation.json()["workflow"]["status"] == "fulfilled"
    assert owner_confirmation.json()["workflow"]["owner_confirmed"] is True
    assert owner_confirmation.json()["workflow"]["participant_confirmed"] is True

    owner_wishes = client.get("/api/me/wishes", headers=owner_h)
    assert owner_wishes.status_code == 200
    assert any(
        item["id"] == wish["id"] and item["workflow"]["status"] == "fulfilled"
        for item in owner_wishes.json()
    )

    participant_wishes = client.get("/api/me/wishes", headers=participant_h)
    assert participant_wishes.status_code == 200
    assert any(
        item["id"] == wish["id"] and item["workflow"]["status"] == "fulfilled"
        for item in participant_wishes.json()
    )


def test_private_message_creates_notification():
    sender, sender_h = join("message-sender", 31, "female", "center")
    recipient, recipient_h = join("message-recipient", 33, "male", "center")
    sent = client.post(
        "/api/messages",
        headers=sender_h,
        json={"recipient_id": recipient["identity"]["id"], "text": "שלום, יש לי עדכון"},
    )
    assert sent.status_code == 200, sent.text

    notifications = client.get("/api/notifications", headers=recipient_h)
    assert notifications.status_code == 200
    assert any(
        n["kind"] == "message" and n["actor_id"] == sender["identity"]["id"]
        for n in notifications.json()
    )


def test_admin_auth_and_user_suspension():
    user, user_h = join("admin-suspend-user", 30, "female", "center")
    identity_id = user["identity"]["id"]

    denied = client.get("/api/admin/overview", headers={"X-Admin-Key": "wrong"})
    assert denied.status_code == 401

    overview = client.get("/api/admin/overview", headers={"X-Admin-Key": "test-admin-secret"})
    assert overview.status_code == 200
    assert overview.json()["users"] >= 1

    suspended = client.post(
        f"/api/admin/users/{identity_id}/suspension",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"suspended": True},
    )
    assert suspended.status_code == 200
    assert suspended.json()["suspended"] is True

    blocked = client.get("/api/me", headers=user_h)
    assert blocked.status_code == 403

    restored = client.post(
        f"/api/admin/users/{identity_id}/suspension",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"suspended": False},
    )
    assert restored.status_code == 200

    active_again = client.get("/api/me", headers=user_h)
    assert active_again.status_code == 200


def test_admin_can_hide_and_restore_wish():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("admin-wish-owner", 34, "female", "center")
    viewer, viewer_h = join("admin-wish-viewer", 32, "male", "center")
    wish = create_fantasy(owner_h, kind="general")

    before = client.get("/api/fantasies?kind=general", headers=viewer_h)
    assert before.status_code == 200
    assert any(item["id"] == wish["id"] for item in before.json())

    hidden = client.post(
        f"/api/admin/fantasies/{wish['id']}/status",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"status": "hidden"},
    )
    assert hidden.status_code == 200

    after = client.get("/api/fantasies?kind=general", headers=viewer_h)
    assert after.status_code == 200
    assert all(item["id"] != wish["id"] for item in after.json())

    restored = client.post(
        f"/api/admin/fantasies/{wish['id']}/status",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"status": "published"},
    )
    assert restored.status_code == 200


def test_admin_report_workflow():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("report-owner", 35, "female", "center")
    reporter, reporter_h = join("report-reporter", 31, "male", "center")
    wish = create_fantasy(owner_h, kind="general")

    report = client.post(
        "/api/reports",
        headers=reporter_h,
        json={"target_fantasy_id": wish["id"], "reason": "בדיקת דיווח", "details": "פרטים לבדיקה"},
    )
    assert report.status_code == 200
    report_id = report.json()["id"]

    rows = client.get(
        "/api/admin/reports?status=pending",
        headers={"X-Admin-Key": "test-admin-secret"},
    )
    assert rows.status_code == 200
    assert any(row["id"] == report_id for row in rows.json())

    resolved = client.post(
        f"/api/admin/reports/{report_id}/status",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_completion_summary_is_factual_and_counts_fulfilled_wishes():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("record-owner", 39, "female", "center")
    participant, participant_h = join("record-participant", 33, "male", "center")
    wish = create_fantasy(owner_h, allowed_genders=["male"], min_age=25, max_age=45, kind="general")
    role_id = wish["roles"][0]["id"]

    applied = client.post(
        f"/api/fantasies/{wish['id']}/apply",
        headers=participant_h,
        json={"role_id": role_id, "message": ""},
    )
    assert applied.status_code == 200

    apps = client.get(f"/api/fantasies/{wish['id']}/applications", headers=owner_h)
    application_id = apps.json()[0]["id"]
    accepted = client.post(
        f"/api/applications/{application_id}/status",
        headers=owner_h,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200

    started = client.post(
        f"/api/fantasies/{wish['id']}/stage",
        headers=owner_h,
        json={"status": "in_progress"},
    )
    assert started.status_code == 200

    assert client.post(f"/api/fantasies/{wish['id']}/confirm-fulfilled", headers=participant_h).status_code == 200
    finished = client.post(f"/api/fantasies/{wish['id']}/confirm-fulfilled", headers=owner_h)
    assert finished.status_code == 200
    assert finished.json()["workflow"]["status"] == "fulfilled"

    owner_stats = client.get("/api/me/activity-summary", headers=owner_h)
    participant_stats = client.get("/api/me/activity-summary", headers=participant_h)
    assert owner_stats.status_code == 200
    assert participant_stats.status_code == 200
    assert owner_stats.json()["fulfilled_as_owner"] >= 1
    assert participant_stats.json()["fulfilled_as_participant"] >= 1


def test_profile_can_store_optional_relationship_details_after_signup():
    user, headers = join("profile-details", 34, "female", "center")
    response = client.put(
        "/api/me/profile",
        headers=headers,
        json={
            "region": "north",
            "marital_status": "divorced",
            "relationship_status": "single",
            "skills": ["צילום", "נהיגה"],
            "availability": "סופי שבוע",
            "travel_radius_km": 40,
            "bio": "פרופיל התאמה",
            "adult_discovery": False,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["region"] == "north"
    assert data["marital_status"] == "divorced"
    assert data["relationship_status"] == "single"
    assert data["skills"] == ["צילום", "נהיגה"]


def test_admin_hidden_wish_is_not_directly_viewable_by_other_users():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("hidden-owner", 35, "female", "center")
    viewer, viewer_h = join("hidden-viewer", 33, "male", "center")
    wish = create_fantasy(owner_h, kind="general")

    hidden = client.post(
        f"/api/admin/fantasies/{wish['id']}/status",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"status": "hidden"},
    )
    assert hidden.status_code == 200

    outsider = client.get(f"/api/fantasies/{wish['id']}", headers=viewer_h)
    assert outsider.status_code == 404

    owner_view = client.get(f"/api/fantasies/{wish['id']}", headers=owner_h)
    assert owner_view.status_code == 200


def test_split_site_template_and_adult_gate_regression():
    root = Path(__file__).resolve().parents[1]
    core = (root / "static" / "core.js").read_text(encoding="utf-8")
    onboarding = (root / "static" / "onboarding.js").read_text(encoding="utf-8")
    template = (root / "templates" / "index.html").read_text(encoding="utf-8")

    assert "SITE_MODE" in core
    assert "ADULT_GATE_KEY" in core
    assert "fa:adult-gate-accepted" in core
    assert "adultAgeGate" in template
    assert 'data-site-mode="__SITE_MODE__"' in template
    assert "maybeOpenWelcome" in onboarding
    assert "fa:adult-gate-accepted" in onboarding
    assert not (root / "static" / "index.html").exists()

    app_module.SITE_MODE = "general"
    general_home = client.get("/")
    assert general_home.status_code == 200
    assert 'data-site-mode="general"' in general_home.text

    app_module.SITE_MODE = "adult"
    adult_home = client.get("/")
    assert adult_home.status_code == 200
    assert 'data-site-mode="adult"' in adult_home.text

    assert client.get("/static/index.html").status_code == 404


def test_messages_and_notifications_do_not_cross_site_boundary():
    a, a_h = join("site-msg-a", 31, "female")
    b, b_h = join("site-msg-b", 33, "male")

    app_module.SITE_MODE = "adult"
    sent = client.post(
        "/api/messages",
        headers=a_h,
        json={"recipient_id": b["identity"]["id"], "text": "adult-side message", "fantasy_id": None},
    )
    assert sent.status_code == 200
    assert any(item["kind"] == "message" for item in client.get("/api/notifications", headers=b_h).json())

    app_module.SITE_MODE = "general"
    assert client.get("/api/inbox", headers=b_h).json() == []
    assert client.get(f"/api/messages/{a['identity']['id']}", headers=b_h).json() == []
    assert client.get("/api/notifications", headers=b_h).json() == []

    general_sent = client.post(
        "/api/messages",
        headers=a_h,
        json={"recipient_id": b["identity"]["id"], "text": "general-side message", "fantasy_id": None},
    )
    assert general_sent.status_code == 200
    general_conversation = client.get(f"/api/messages/{a['identity']['id']}", headers=b_h)
    assert [item["text"] for item in general_conversation.json()] == ["general-side message"]


def test_adult_path_is_separate_site_and_scopes_api():
    app_module.SITE_MODE = "general"

    general_home = client.get("/")
    assert general_home.status_code == 200
    assert 'data-site-mode="general"' in general_home.text
    assert 'data-api-base=""' in general_home.text

    adult_home = client.get("/adult")
    assert adult_home.status_code == 200
    assert 'data-site-mode="adult"' in adult_home.text
    assert 'data-api-base="/adult"' in adult_home.text

    general_config = client.get("/api/site-config")
    assert general_config.status_code == 200
    assert general_config.json()["mode"] == "general"
    assert general_config.json()["api_base"] == ""

    adult_config = client.get("/adult/api/site-config")
    assert adult_config.status_code == 200
    assert adult_config.json()["mode"] == "adult"
    assert adult_config.json()["api_base"] == "/adult"


def test_adult_path_cannot_read_general_wish():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("adult-path-owner", 37, "female", "center")
    general = create_fantasy(owner_h, kind="general")

    adult_list = client.get("/adult/api/fantasies", headers=owner_h)
    assert adult_list.status_code == 200
    assert all(item["kind"] == "adult" for item in adult_list.json())

    adult_direct = client.get(f"/adult/api/fantasies/{general['id']}", headers=owner_h)
    assert adult_direct.status_code == 404


# v0.4 language and media regression tests
PHOTO_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_session_and_profile_keep_preferred_language():
    app_module.SITE_MODE = "general"
    response = client.post(
        "/api/session",
        json={
            "nickname": "language-user",
            "age": 33,
            "gender": "male",
            "region": "center",
            "marital_status": "prefer_not_to_say",
            "relationship_status": "prefer_not_to_say",
            "preferred_language": "he",
            "adult_confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    headers = {"Authorization": f"Bearer {data['token']}"}
    assert data["identity"]["preferred_language"] == "he"

    updated = client.put(
        "/api/me/profile",
        headers=headers,
        json={
            "region": "center",
            "marital_status": "prefer_not_to_say",
            "relationship_status": "prefer_not_to_say",
            "skills": [],
            "availability": "",
            "travel_radius_km": 0,
            "bio": "",
            "adult_discovery": False,
            "preferred_language": "en",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["preferred_language"] == "en"
    assert client.get("/api/me", headers=headers).json()["preferred_language"] == "en"


def test_profile_photo_visibility_and_site_isolation():
    app_module.SITE_MODE = "adult"
    owner, owner_h = join("photo-owner", 34, "female")
    viewer, viewer_h = join("photo-viewer", 35, "male")

    private_upload = client.post(
        "/api/photos",
        headers=owner_h,
        json={"purpose": "profile", "visibility": "private", "data_url": PHOTO_DATA_URL},
    )
    assert private_upload.status_code == 200, private_upload.text
    private_photo = private_upload.json()
    assert private_photo["visibility"] == "private"

    public_for_viewer = client.get(
        f"/api/identities/{owner['identity']['id']}/photos",
        headers=viewer_h,
    )
    assert public_for_viewer.status_code == 200
    assert all(item["id"] != private_photo["id"] for item in public_for_viewer.json())

    hidden_binary = client.get(f"/api/photos/{private_photo['id']}", headers=viewer_h)
    assert hidden_binary.status_code == 404

    made_public = client.put(
        f"/api/me/photos/{private_photo['id']}",
        headers=owner_h,
        json={"visibility": "public"},
    )
    assert made_public.status_code == 200
    assert made_public.json()["visibility"] == "public"

    now_visible = client.get(
        f"/api/identities/{owner['identity']['id']}/photos",
        headers=viewer_h,
    )
    assert any(item["id"] == private_photo["id"] for item in now_visible.json())

    binary = client.get(f"/api/photos/{private_photo['id']}", headers=viewer_h)
    assert binary.status_code == 200
    assert binary.headers["content-type"].startswith("image/jpeg")

    app_module.SITE_MODE = "general"
    isolated = client.get("/api/me/photos", headers=owner_h)
    assert isolated.status_code == 200
    assert all(item["id"] != private_photo["id"] for item in isolated.json())
    isolated_binary = client.get(f"/api/photos/{private_photo['id']}", headers=owner_h)
    assert isolated_binary.status_code == 404


def test_fantasy_photo_is_returned_in_wish_payload():
    app_module.SITE_MODE = "general"
    owner, owner_h = join("wish-photo-owner", 38, "female")
    wish = create_fantasy(owner_h, kind="general")

    uploaded = client.post(
        "/api/photos",
        headers=owner_h,
        json={
            "purpose": "fantasy",
            "fantasy_id": wish["id"],
            "visibility": "private",
            "data_url": PHOTO_DATA_URL,
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    photo = uploaded.json()
    # Wish photos follow the wish visibility and are not a separate private profile image.
    assert photo["visibility"] == "public"

    detail = client.get(f"/api/fantasies/{wish['id']}", headers=owner_h)
    assert detail.status_code == 200
    assert any(item["id"] == photo["id"] for item in detail.json()["photos"])


def test_invalid_photo_data_is_rejected():
    app_module.SITE_MODE = "general"
    _, headers = join("bad-photo", 31, "male")
    response = client.post(
        "/api/photos",
        headers=headers,
        json={
            "purpose": "profile",
            "visibility": "public",
            "data_url": "data:image/png;base64," + ("A" * 100),
        },
    )
    assert response.status_code == 422


def test_template_uses_english_voice_subtitles_and_media_controls():
    app_module.SITE_MODE = "general"
    page = client.get("/")
    assert page.status_code == 200
    html = page.text
    assert "/static/i18n.js" in html
    assert "/static/media.js" in html
    assert 'id="morinSubtitles"' in html
    assert 'id="fantasyPhotos"' in html
    assert 'id="profilePhotoInput"' in html
    assert 'id="profileLanguage"' in html
    assert 'id="welcomeFemaleVoice"' not in html
    assert 'id="welcomeMaleVoice"' not in html


def test_registration_frontend_uses_query_selector_all_for_track_groups():
    source = (Path(__file__).resolve().parents[1] / "static" / "core.js").read_text(encoding="utf-8")
    assert "$('.track-tab,.track-choice').forEach" in source


def test_public_welcome_audio_uses_server_side_whitelisted_script(monkeypatch):
    app_module.SITE_MODE = "general"

    async def fake_gateway_speech(text: str) -> bytes:
        assert text == app_module.WELCOME_AUDIO["general"][0]
        return b"fake-mp3"

    monkeypatch.setattr(app_module, "gateway_speech", fake_gateway_speech)
    response = client.get("/api/morin/welcome-audio/0")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"fake-mp3"

    missing = client.get("/api/morin/welcome-audio/999")
    assert missing.status_code == 404


def test_arbitrary_morin_speech_requires_login(monkeypatch):
    app_module.SITE_MODE = "general"

    async def fake_gateway_speech(text: str) -> bytes:
        return b"fake-mp3"

    monkeypatch.setattr(app_module, "gateway_speech", fake_gateway_speech)

    blocked = client.post("/api/morin/speak", json={"text": "Hello"})
    assert blocked.status_code == 401

    _, headers = join("voice-user", 35, "female")
    allowed = client.post("/api/morin/speak", headers=headers, json={"text": "Hello"})
    assert allowed.status_code == 200
    assert allowed.content == b"fake-mp3"


def test_onboarding_no_longer_uses_browser_speech_synthesis():
    source = (Path(__file__).resolve().parents[1] / "static" / "onboarding.js").read_text(encoding="utf-8")
    assert "speechSynthesis" not in source
    assert "/api/morin/welcome-audio/" in source
    assert "new Audio(" in source


def test_stable_account_recovery_restores_same_identity_on_second_device():
    app_module.SITE_MODE = "general"
    created = client.post(
        "/api/session",
        json={
            "nickname": "same-person",
            "age": 39,
            "gender": "male",
            "region": "center",
            "marital_status": "prefer_not_to_say",
            "relationship_status": "prefer_not_to_say",
            "preferred_language": "he",
            "adult_confirm": True,
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    account_id = payload["identity"]["account_id"]
    recovery_code = payload["recovery_code"]
    original_id = payload["identity"]["id"]
    original_headers = {"Authorization": f"Bearer {payload['token']}"}

    recovered = client.post(
        "/api/session/recover",
        json={"account_id": account_id.lower(), "recovery_code": recovery_code.lower()},
    )
    assert recovered.status_code == 200, recovered.text
    recovered_payload = recovered.json()
    assert recovered_payload["identity"]["id"] == original_id
    assert recovered_payload["identity"]["account_id"] == account_id
    recovered_headers = {"Authorization": f"Bearer {recovered_payload['token']}"}

    # Recovery adds a second valid device session instead of logging out the first.
    assert client.get("/api/me", headers=original_headers).json()["id"] == original_id
    assert client.get("/api/me", headers=recovered_headers).json()["id"] == original_id


def test_duplicate_nicknames_get_distinct_stable_account_ids():
    app_module.SITE_MODE = "general"
    first, _ = join("duplicate-name", 32, "female")
    second, _ = join("duplicate-name", 34, "male")
    assert first["identity"]["nickname"] == second["identity"]["nickname"]
    assert first["identity"]["id"] != second["identity"]["id"]
    assert first["identity"]["account_id"] != second["identity"]["account_id"]
    assert first["identity"]["public_tag"] != second["identity"]["public_tag"]


def test_recovery_key_rotation_invalidates_old_key_but_not_existing_session():
    app_module.SITE_MODE = "general"
    created = client.post(
        "/api/session",
        json={
            "nickname": "rotate-key",
            "age": 41,
            "gender": "female",
            "region": "",
            "marital_status": "prefer_not_to_say",
            "relationship_status": "prefer_not_to_say",
            "preferred_language": "en",
            "adult_confirm": True,
        },
    ).json()
    headers = {"Authorization": f"Bearer {created['token']}"}
    account_id = created["identity"]["account_id"]
    old_code = created["recovery_code"]

    rotated = client.post("/api/me/recovery-key", headers=headers)
    assert rotated.status_code == 200, rotated.text
    new_code = rotated.json()["recovery_code"]
    assert new_code != old_code

    old_attempt = client.post(
        "/api/session/recover",
        json={"account_id": account_id, "recovery_code": old_code},
    )
    assert old_attempt.status_code == 401

    new_attempt = client.post(
        "/api/session/recover",
        json={"account_id": account_id, "recovery_code": new_code},
    )
    assert new_attempt.status_code == 200
    assert new_attempt.json()["identity"]["id"] == created["identity"]["id"]

    # Rotating a recovery key does not revoke an already-open device.
    assert client.get("/api/me", headers=headers).status_code == 200


def test_invalid_recovery_details_do_not_reveal_account_access():
    app_module.SITE_MODE = "general"
    created, _ = join("recover-invalid", 36, "male")
    response = client.post(
        "/api/session/recover",
        json={
            "account_id": created["identity"]["account_id"],
            "recovery_code": "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF",
        },
    )
    assert response.status_code == 401


def test_account_recovery_controls_are_present_in_template_and_frontend():
    app_module.SITE_MODE = "general"
    page = client.get("/")
    assert page.status_code == 200
    html = page.text
    assert 'id="recoverAccountId"' in html
    assert 'id="recoverCode"' in html
    assert 'id="accountRecoveryModal"' in html
    assert 'id="profileAccountId"' in html

    core = (Path(__file__).resolve().parents[1] / "static" / "core.js").read_text(encoding="utf-8")
    assert "/api/session/recover" in core
    assert "/api/me/recovery-key" in core
    assert "identityLabel" in core


def test_security_audit_registration_records_ip_and_account():
    app_module.SITE_MODE = "general"
    response = client.post(
        "/api/session",
        headers={"X-Forwarded-For": "198.51.100.24"},
        json={
            "nickname": "audit-register",
            "age": 37,
            "gender": "female",
            "region": "center",
            "marital_status": "prefer_not_to_say",
            "relationship_status": "prefer_not_to_say",
            "preferred_language": "he",
            "adult_confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    account_id = response.json()["identity"]["account_id"]

    con = app_module.db()
    row = con.execute(
        "SELECT * FROM security_audit_log WHERE event_type='account_register' AND account_id=? ORDER BY occurred_at DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    con.close()
    assert row is not None
    assert row["result"] == "success"
    assert row["ip_address"] == "198.51.100.24"
    assert row["session_id"]
    assert row["retention_until"] - row["occurred_at"] >= 760 * 24 * 60 * 60 - 1


def test_security_audit_failed_recovery_records_denied_without_secret():
    app_module.SITE_MODE = "general"
    created = client.post(
        "/api/session",
        json={
            "nickname": "audit-recover",
            "age": 40,
            "gender": "male",
            "region": "",
            "marital_status": "prefer_not_to_say",
            "relationship_status": "prefer_not_to_say",
            "preferred_language": "en",
            "adult_confirm": True,
        },
    ).json()
    account_id = created["identity"]["account_id"]
    bad_code = "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF"

    response = client.post(
        "/api/session/recover",
        headers={"X-Forwarded-For": "203.0.113.77"},
        json={"account_id": account_id, "recovery_code": bad_code},
    )
    assert response.status_code == 401

    con = app_module.db()
    row = con.execute(
        "SELECT * FROM security_audit_log WHERE event_type='account_recover' AND account_id=? ORDER BY occurred_at DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    con.close()
    assert row is not None
    assert row["result"] == "denied"
    assert row["ip_address"] == "203.0.113.77"
    assert bad_code not in row["metadata"]


def test_security_audit_profile_update_links_account_and_session():
    app_module.SITE_MODE = "general"
    created, headers = join("audit-profile", 35, "female")
    response = client.put(
        "/api/me/profile",
        headers={**headers, "X-Forwarded-For": "192.0.2.44"},
        json={
            "region": "north",
            "marital_status": "prefer_not_to_say",
            "relationship_status": "prefer_not_to_say",
            "skills": ["piano"],
            "availability": "evenings",
            "travel_radius_km": 10,
            "bio": "audit profile",
            "adult_discovery": False,
            "preferred_language": "he",
        },
    )
    assert response.status_code == 200, response.text

    con = app_module.db()
    row = con.execute(
        "SELECT * FROM security_audit_log WHERE event_type='profile_update' AND account_id=? ORDER BY occurred_at DESC LIMIT 1",
        (created["identity"]["account_id"],),
    ).fetchone()
    con.close()
    assert row is not None
    assert row["result"] == "success"
    assert row["identity_id"] == created["identity"]["id"]
    assert row["session_id"]
    assert row["ip_address"] == "192.0.2.44"


def test_security_audit_prunes_expired_records():
    con = app_module.db()
    old_id = app_module.uid()
    ts = app_module.now() - 100
    con.execute(
        """
        INSERT INTO security_audit_log
        (id,occurred_at,account_id,identity_id,session_id,event_type,result,site_mode,ip_address,user_agent_hash,path,method,target_type,target_id,metadata,retention_until)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            old_id, ts, None, None, None, "test_expired", "success", "general",
            "", "", "/test", "GET", None, None, "{}", app_module.now() - 1,
        ),
    )
    con.commit()
    con.close()

    app_module.prune_audit_logs(force=True)

    con = app_module.db()
    row = con.execute("SELECT id FROM security_audit_log WHERE id=?", (old_id,)).fetchone()
    con.close()
    assert row is None


def test_admin_can_query_audit_logs_and_regular_user_cannot():
    app_module.SITE_MODE = "general"
    created, headers = join("audit-query", 33, "male")

    blocked = client.get("/api/admin/audit-logs", headers=headers)
    assert blocked.status_code == 401

    allowed = client.get(
        f"/api/admin/audit-logs?account_id={created['identity']['account_id']}&limit=20",
        headers={"X-Admin-Key": "test-admin-secret", "X-Forwarded-For": "203.0.113.50"},
    )
    assert allowed.status_code == 200, allowed.text
    assert isinstance(allowed.json(), list)
    assert any(item["account_id"] == created["identity"]["account_id"] for item in allowed.json())


def test_privacy_notice_discloses_ip_security_logging_and_retention():
    app_module.SITE_MODE = "general"
    page = client.get("/")
    assert page.status_code == 200
    html = page.text
    assert "פרטיות ואבטחת מידע / Privacy" in html
    assert "כתובת IP" in html
    assert "760 יום" in html
    assert "The IP address is not used as the account identity" in html
    assert "AI providers" in html


def test_privacy_notice_is_reachable_before_registration():
    app_module.SITE_MODE = "general"
    html = client.get("/").text
    gate_index = html.index('id="gate"')
    privacy_index = html.index("פרטיות ואבטחת מידע / Privacy", gate_index)
    enter_index = html.index('id="enterBtn"', gate_index)
    assert privacy_index > enter_index
