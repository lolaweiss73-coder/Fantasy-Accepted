import os
import tempfile

os.environ["FANTASY_DATA_DIR"] = tempfile.mkdtemp(prefix="fantasy-accepted-tests-")
os.environ["ADMIN_PASSWORD"] = "test-admin-secret"

from fastapi.testclient import TestClient
from app import app

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
    return data, {"Authorization": f"Bearer {data['token']}"}


def create_fantasy(headers, allowed_genders=None, min_age=18, max_age=99, kind="adult"):
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
    assert response.status_code == 200, response.text
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


def test_general_and_adult_tracks_are_filtered_separately():
    owner, owner_h = join("track-owner", 41, "female")
    viewer, viewer_h = join("track-viewer", 39, "male")

    general = create_fantasy(owner_h, kind="general")
    adult = create_fantasy(owner_h, kind="adult")

    general_feed = client.get("/api/fantasies?kind=general", headers=viewer_h)
    assert general_feed.status_code == 200
    general_ids = {item["id"] for item in general_feed.json()}
    assert general["id"] in general_ids
    assert adult["id"] not in general_ids
    assert all(item["kind"] == "general" for item in general_feed.json())

    adult_feed = client.get("/api/fantasies?kind=adult", headers=viewer_h)
    assert adult_feed.status_code == 200
    adult_ids = {item["id"] for item in adult_feed.json()}
    assert adult["id"] in adult_ids
    assert general["id"] not in adult_ids
    assert all(item["kind"] == "adult" for item in adult_feed.json())


def test_announcement_list_is_public_and_admin_can_add_edit_delete():
    initial = client.get("/api/announcements")
    assert initial.status_code == 200
    initial_items = initial.json()
    assert any(item["text"] == "מזל טוב על הגרושים שלך מיסיס ר.ל." for item in initial_items)

    denied = client.post(
        "/api/admin/announcements",
        headers={"X-Admin-Key": "wrong"},
        json={"text": "חג סוכות שמח לכל בית ישראל"},
    )
    assert denied.status_code == 401

    added = client.post(
        "/api/admin/announcements",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"text": "חג סוכות שמח לכל בית ישראל"},
    )
    assert added.status_code == 200
    added_id = added.json()["id"]

    public = client.get("/api/announcements")
    assert public.status_code == 200
    texts = [item["text"] for item in public.json()]
    assert "מזל טוב על הגרושים שלך מיסיס ר.ל." in texts
    assert "חג סוכות שמח לכל בית ישראל" in texts

    aggregate = client.get("/api/announcement")
    assert aggregate.status_code == 200
    assert " ✦ " in aggregate.json()["text"]

    edited = client.put(
        f"/api/admin/announcements/{added_id}",
        headers={"X-Admin-Key": "test-admin-secret"},
        json={"text": "חג שמח לכל בית ישראל"},
    )
    assert edited.status_code == 200
    assert edited.json()["text"] == "חג שמח לכל בית ישראל"

    deleted = client.delete(
        f"/api/admin/announcements/{added_id}",
        headers={"X-Admin-Key": "test-admin-secret"},
    )
    assert deleted.status_code == 200

    after_delete = client.get("/api/announcements")
    assert after_delete.status_code == 200
    assert all(item["id"] != added_id for item in after_delete.json())


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
