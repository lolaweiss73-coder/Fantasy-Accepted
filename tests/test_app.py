import os
import tempfile
from pathlib import Path


os.environ["FANTASY_DATA_DIR"] = tempfile.mkdtemp(prefix="fantasy-accepted-tests-")
os.environ["ADMIN_PASSWORD"] = "test-admin-secret"

from fastapi.testclient import TestClient
from app import app, init_db

client = TestClient(app)



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
    return data, {"Authorization": f"Bearer {data['token']}", "X-Site-Mode": "adult"}


def site_headers(headers, mode):
    return {**headers, "X-Site-Mode": mode}


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

    general_h = site_headers(owner_h, "general")
    general_view_h = site_headers(viewer_h, "general")
    adult_h = site_headers(owner_h, "adult")
    adult_view_h = site_headers(viewer_h, "adult")

    general = create_fantasy(general_h, kind="general")
    create_fantasy(general_h, kind="adult", expect_status=409)

    general_feed = client.get("/api/fantasies", headers=general_view_h)
    assert general_feed.status_code == 200
    assert any(item["id"] == general["id"] for item in general_feed.json())
    assert all(item["kind"] == "general" for item in general_feed.json())
    assert client.get("/api/fantasies?kind=adult", headers=general_view_h).json() == []

    adult = create_fantasy(adult_h, kind="adult")
    adult_feed = client.get("/api/fantasies", headers=adult_view_h)
    assert adult_feed.status_code == 200
    assert any(item["id"] == adult["id"] for item in adult_feed.json())
    assert all(item["kind"] == "adult" for item in adult_feed.json())
    assert client.get(f"/api/fantasies/{general['id']}", headers=adult_view_h).status_code == 404
    assert client.get(f"/api/fantasies/{adult['id']}", headers=general_view_h).status_code == 404


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
    owner, owner_h = join("wish-owner", 35, "female", "center")
    candidate, candidate_h = join("wish-candidate", 30, "male", "center")
    owner_h = site_headers(owner_h, "general")
    candidate_h = site_headers(candidate_h, "general")
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
    owner, owner_h = join("flow-owner", 38, "female", "center")
    participant, participant_h = join("flow-participant", 32, "male", "center")
    owner_h = site_headers(owner_h, "general")
    participant_h = site_headers(participant_h, "general")
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
    owner, owner_h = join("admin-wish-owner", 34, "female", "center")
    viewer, viewer_h = join("admin-wish-viewer", 32, "male", "center")
    owner_h = site_headers(owner_h, "general")
    viewer_h = site_headers(viewer_h, "general")
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
    owner, owner_h = join("report-owner", 35, "female", "center")
    reporter, reporter_h = join("report-reporter", 31, "male", "center")
    owner_h = site_headers(owner_h, "general")
    reporter_h = site_headers(reporter_h, "general")
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
    owner, owner_h = join("record-owner", 39, "female", "center")
    participant, participant_h = join("record-participant", 33, "male", "center")
    owner_h = site_headers(owner_h, "general")
    participant_h = site_headers(participant_h, "general")
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
    owner, owner_h = join("hidden-owner", 35, "female", "center")
    viewer, viewer_h = join("hidden-viewer", 33, "male", "center")
    owner_h = site_headers(owner_h, "general")
    viewer_h = site_headers(viewer_h, "general")
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

    general_home = client.get("/")
    assert general_home.status_code == 200
    assert 'data-site-mode="general"' in general_home.text

    adult_home = client.get("/adult")
    assert adult_home.status_code == 200
    assert 'data-site-mode="adult"' in adult_home.text

    general_config = client.get("/api/site-config", headers={"X-Site-Mode": "general"})
    adult_config = client.get("/api/site-config", headers={"X-Site-Mode": "adult"})
    assert general_config.json()["mode"] == "general"
    assert adult_config.json()["mode"] == "adult"

    assert client.get("/static/index.html").status_code == 404


def test_messages_and_notifications_do_not_cross_site_boundary():
    a, a_h = join("site-msg-a", 31, "female")
    b, b_h = join("site-msg-b", 33, "male")

    adult_a_h = site_headers(a_h, "adult")
    adult_b_h = site_headers(b_h, "adult")
    general_a_h = site_headers(a_h, "general")
    general_b_h = site_headers(b_h, "general")

    sent = client.post(
        "/api/messages",
        headers=adult_a_h,
        json={"recipient_id": b["identity"]["id"], "text": "adult-side message", "fantasy_id": None},
    )
    assert sent.status_code == 200
    assert any(item["kind"] == "message" for item in client.get("/api/notifications", headers=adult_b_h).json())

    assert client.get("/api/inbox", headers=general_b_h).json() == []
    assert client.get(f"/api/messages/{a['identity']['id']}", headers=general_b_h).json() == []
    assert client.get("/api/notifications", headers=general_b_h).json() == []

    general_sent = client.post(
        "/api/messages",
        headers=general_a_h,
        json={"recipient_id": b["identity"]["id"], "text": "general-side message", "fantasy_id": None},
    )
    assert general_sent.status_code == 200
    general_conversation = client.get(f"/api/messages/{a['identity']['id']}", headers=general_b_h)
    assert [item["text"] for item in general_conversation.json()] == ["general-side message"]
