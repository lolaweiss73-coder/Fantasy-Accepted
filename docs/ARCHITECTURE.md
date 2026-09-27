# Architecture notes

## Principle

Fantasy Accepted owns fantasy-specific data. It should not read No Limit Chat's database directly. Cross-product identity should flow through a shared Hub/API contract.

## Planned ecosystem relationship

```text
                         ┌───────────────────────┐
                         │     Identity Hub      │
                         │ subjects + permissions│
                         └──────────┬────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
  ללא גבולות                No Limit Chat            Fantasy Accepted
 community/profile          realtime chat             fantasy/matching
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                           Morin AI layer
                    permission-scoped cross-context

Additional connected products:
- Good-deeds activity record (documented actions, never a global goodness score)
- The Record / הרקורד (documented incidents/claims, evidence and status)
```

## Identity contract direction

Current local identity:

```json
{
  "id": "service-local-uuid",
  "hub_subject": null,
  "nickname": "...",
  "age": 34,
  "gender": "..."
}
```

Future linked identity:

```json
{
  "id": "service-local-uuid",
  "hub_subject": "hub-user-uuid",
  "nickname": "...",
  "age": 34,
  "gender": "..."
}
```

Hub linking must be explicit and scoped. Fantasy content must not silently become visible in another product merely because the same Hub subject is used there.

## Data ownership

Fantasy Accepted owns:
- fantasies
- missing roles / constraints
- applications
- Fantasy Accepted private messages
- local blocks/reports
- Morin fantasy-draft history generated inside this product

Hub eventually owns:
- stable cross-product subject
- authentication/link state
- cross-product permission grants

No Limit Chat owns its own rooms/messages/profiles and should access Fantasy Accepted only through an API contract when permission exists.

## Safety invariants in the current baseline

- Every local identity age is at least 18.
- Every role's minimum age is at least 18.
- Eligibility is checked again server-side when applying; the UI is not trusted.
- Blocks are bilateral for communication access.
- DND blocks new approaches while established conversations continue.
- Manual publishing and Morin-assisted drafting both enforce the adult-only boundary server-side.
- Morin cannot publish a generated structure automatically.
- Precise meeting location/time are not part of public fantasy fields.
