# Fantasy Accepted

**Name it. Match it. Make it real.**  
Hebrew-first wish and fantasy discovery product in the No Limit ecosystem.

The product now has two hard-separated public experiences over the same backend and database:
- **General wishes** — the default site, with no adult feed or adult content.
- **Adult fantasies** — a separate 18+ experience with an age declaration before any adult UI is shown.

This repository is a fresh implementation. It deliberately uses the same lightweight deployment style as `NoLimit-Chat` (FastAPI + SQLite + static frontend) so the two services can share infrastructure patterns while remaining separate products.

## Current baseline — v0.4.0

Working flows:

- Anonymous/discreet adult session with nickname, age, gender, general region, marital status and relationship status.
- Local service identity designed to accept a future shared Hub subject without forcing Fantasy Accepted users to create a No Limit Chat profile first.
- Fantasy feed and search.
- Create a fantasy with free text, tags, online/meeting mode, visibility and one or more missing roles.
- Structured role constraints: capacity, age range, gender and region.
- Server-side eligibility validation before an application is accepted.
- Applications, owner review, shortlist/accept/reject, and applicant withdrawal API.
- Private persistent messages.
- DND / break mode that blocks new approaches while existing conversations remain active.
- Bilateral communication blocking and reporting.
- Optional Morin draft-structuring endpoint through OpenRouter. The original user text and structured draft are kept separately; nothing is published by the AI automatically.
- Adult-only publishing guard applied server-side to both manual and Morin-assisted drafts.
- Mobile-first RTL interface.
- English-only Morin spoken narration with localized synchronized subtitles; users can speak or write in their own language.
- Preferred display language stored per profile, with browser-language fallback.
- Wish/fantasy photos (up to 8), normalized and stripped of EXIF metadata before storage.
- Profile photo gallery with per-photo public/private visibility, isolated between the general and 18+ sites.

## Product boundaries

Fantasy Acccepted is a separate product from:

1. **ללא גבולות** — community, profiles and blogs.
2. **No Limit Chat** — live chat and persistent relationships.
3. **Fantasy Accepted** — fantasy-first discovery, roles and matching.
4. The good-deeds product — documented positive actions, not a moral score.
5. **The Record / הרקורד** — documented negative incidents/claims with evidence/status/right of reply, not a globl judgment of a person.

The products are intended to share identity/permission infrastructure later. **Morin is the cross-ecosystem AI layer**, not the identity hub itself.

## Identity model

A direct visitor can enter Fantasy Accepted first and receive a local anonymous identity. `identities.hub_subject` is reserved for future linking to the shared Identity Hub. That means the eventual flow can support both directions:

- No Limit user → Fantasy Accepted with the same Hub identity.
- New Fantasy Accepted user → local identity now → optional Hub link later.

The service must not require No Limit Chat registration just to use Fantasy Accepted.

## Morin

Set both:

```bash
OPENROUTER_API_KEY=...
MORIN_MODEL=...
```

Morin currently performs one narrow job: convert the user's own adult free-text fantasy into a structured **draft**. The user reviews and edits it before publishing. The endpoint intentionally refuses to invent missing ages, genders or locations and requires all role ages to stay 18+.

Morin is expected to grow into the shared conversational layer across the ecosystem after identity permissions and consent scopes are implemented.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## Test

```bash
pytest -q
```

## Persistence

Set `FANTASY_DATA_DIR` to a durable mounted directory. Without it, `fantasy_accepted.db` is created next to the code, which is fine for local testing but not for an ephemeral deployment filesystem.

## Render

A `render.yaml` baseline is included. Before real users are admitted, configure durable storage, TLS, backups, rate limiting, a staffed moderation workflow, terms/privacy pages, stronger account recovery and a production database.

## Next implementation stages

- Shared Hub token verification/linking with No Limit Chat.
- Live notifications / WebSocket chat.
- Richer privacy scopes for limited fantasies.
- Verification badges (age, identity, linked social account) as separate facts.
- Match notifications when a missing role becomes satisfiable.
- Voice capture → transcription → Morin structuring workflow.
- Admin moderation queue and audit trail.
- Mutual final acceptance state for a fantasy after participants are chosen.

The `Accepted` state must never be treated as irreversible consent to a meeting; participants can withdraw at any stage.
