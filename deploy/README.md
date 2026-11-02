# Echo production deployment

## Current production

- API: `https://api.echoaiforever.cn`
- APK download: `https://download.echoaiforever.cn`
- Repository: `/opt/echo/app`
- Current release: Android `1.1.10+26`, backend branch `master`

## Server layout

- Repository: `/opt/echo/app`
- Public API: `https://api.echoaiforever.cn`
- Backend listener: `127.0.0.1:8000`
- Nginx configuration: `/etc/nginx/sites-enabled/echo-backend`
- Desktop node WebSocket: `/desktop/nodes/ws` must pass `Upgrade`/`Connection` headers

Only ports 22, 80, and 443 should be public. PostgreSQL 5432 and backend 8000 stay local.

## Backend environment

Keep production secrets in `/opt/echo/app/Echo-backend/.env`. Do not commit this file.

Required production overrides:

```dotenv
PUBLIC_BASE_URL=https://api.echoaiforever.cn
APP_VERSION=1.1.0
BUILD_REVISION=<deployed-git-revision>

ENABLE_API_DOCS=false

SMS_PROVIDER=log
SMS_LOG_VERIFICATION_CODE=false
SMS_FIXED_VERIFICATION_CODE=123456
SMS_STUB_DELIVERY_ENABLED=true
```

The fixed SMS code is for closed testing only. Replace it with a real provider before public release.

COS is prepared but does not affect current app traffic until explicitly enabled. Configure the
private bucket and run the storage smoke test by following
`doc/deploy/COS 对象存储配置说明.md`. Keep `LETTER_IMAGE_GENERATION_ENABLED=false` until an
image-generation provider is selected.

## Deploy

```bash
cd /opt/echo/app
git pull --ff-only origin master
docker compose up -d --build
docker compose ps
docker compose logs --tail=200 echo-backend
curl http://127.0.0.1:8000/health/ready
```

Install the Nginx configuration and request the TLS certificate:

```bash
sudo cp deploy/nginx/echo.conf /etc/nginx/conf.d/echo.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d api.echoaiforever.cn
curl https://api.echoaiforever.cn/health/ready
```

## Android release

Create `app/android/key.properties` outside Git with these keys:

```properties
storePassword=replace-me
keyPassword=replace-me
keyAlias=echo
storeFile=replace-with-absolute-keystore-path
```

Build the production APK from `app/`:

```powershell
flutter build apk --release --no-pub `
  --dart-define=ECHO_ENV=production `
  --dart-define=ECHO_BASE_URL=https://api.echoaiforever.cn `
  --dart-define=APP_VERSION=1.1.0
```

The APK is written to `app/build/app/outputs/flutter-apk/app-release.apk`.

The server does not build Android APKs. Build the signed APK on the development workstation,
upload it to COS, and register the release metadata in the production database with
`scripts/publish_android_release.py`. The server only pulls Git code and runs the backend.

## Showcase site

The static site is served from `/var/www/echoaiforever.cn`. After pulling the repository, sync the
tracked site files and reload Nginx:

```bash
sudo rsync -a --delete site/echoaiforever.cn/ /var/www/echoaiforever.cn/
sudo nginx -t
sudo systemctl reload nginx
```

The page uses `GET https://api.echoaiforever.cn/releases/latest` to render the public Android
version, publication date, and release notes at runtime. The HTML contains the current version as a
fallback, so a temporary API failure does not leave the version area blank.
