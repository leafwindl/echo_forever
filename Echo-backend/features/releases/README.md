# Releases

Publishes immutable Android APK metadata and returns short-lived COS download URLs.

- `GET /releases/latest` checks whether a newer active release exists.
- `POST /releases/{release_id}/download` mints a temporary private COS URL.
- Release endpoints are public so expired login sessions cannot block an app update.
