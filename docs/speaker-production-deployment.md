# Speaker Service Deployment

Date: 2026-09-29

Use both Compose files for production rebuilds and updates:

```sh
docker compose -f docker-compose.yml -f docker-compose.speaker.yml build echo-speaker echo-backend
docker compose -f docker-compose.yml -f docker-compose.speaker.yml up -d --no-deps echo-speaker
docker compose -f docker-compose.yml -f docker-compose.speaker.yml up -d --no-deps echo-backend
```

Before switching the backend, verify the speaker container health. Back up the
production database, environment files, existing source changes and backend image.
Keep a single backend worker: live device sessions and calibration are in memory.
Restarting the backend interrupts device connections and active enrollment.

Place the existing approved model at `data/speaker-models/campplus-zh.onnx`.
Verify SHA-256 before startup:
`f682b514c05d947ee3fa91cd6ec6c5c7543479a128373fa29b1faedccd21fd11`.
The model is mounted read-only and is not stored in Git. The service has no host
port, uses one CPU thread, and is capped at 768 MiB. Validate real production
resource use; local measurements are not a production capacity guarantee.

Verify `/health/ready`, the speaker `/health` endpoint from inside the backend,
and authenticated speaker routes after rollout. Do not print credentials or
embeddings. Local test profiles are not automatically copied to production.

Speaker scores control expression only when explicitly asked about identity.
Ordinary conversation must not announce scores, guess names, or ask who is
speaking. A match does not grant account memory or tool permissions.
The current noise-trigger issue is not fixed by this rollout.

For rollback, stop the new backend and recreate it from the saved backend image
with the previous Compose configuration and environment. Do not remove database
volumes. New speaker tables are additive; do not delete user enrollments as part
of a routine code rollback.
