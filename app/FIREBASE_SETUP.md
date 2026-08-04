# Firebase / FCM release setup

FCM code is present, but Firebase is disabled by default so local builds do not
depend on a project credential file. The app handles the missing default Firebase
app as an unavailable capability and never asks for notification permission.

1. Create or select the Echo Firebase project.
2. Register Android package `cn.echoaiforever.echo_app`.
3. Download `google-services.json` to `android/app/google-services.json`. Never
   commit a file from a personal/test Firebase project.
4. Set `echo.enableFirebase=true` in `android/gradle.properties`, or pass
   `-Pecho.enableFirebase=true` to Gradle in CI.
5. Build and install on a Google Play services device, open Notification Settings,
   accept the value explanation, and grant the Android notification permission.
6. Implement `PUT /push/tokens/me` and `DELETE /push/tokens/me/{device_id}` in
   Echo-backend, plus FCM service-account sending. Tokens and credentials must be
   redacted from logs.
7. Verify foreground delivery, background tap, terminated tap, token rotation,
   multi-device ownership, account switching, and invalid-token deactivation.
