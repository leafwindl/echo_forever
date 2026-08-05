# Echo production deployment

## Server layout

- Repository: `/opt/echo/app`
- Public API: `https://api.echoaiforever.cn`
- Backend listener: `127.0.0.1:8000`
- Nginx configuration: `/etc/nginx/conf.d/echo.conf`

Only ports 22, 80, and 443 should be public. PostgreSQL 5432 and backend 8000 stay local.

## Backend environment

Keep production secrets in `/opt/echo/app/Echo-backend/.env`. Do not commit this file.

Required production overrides:

```dotenv
PUBLIC_BASE_URL=https://api.echoaiforever.cn
APP_VERSION=0.1.0
BUILD_REVISION=unknown

ENABLE_API_DOCS=false
ENABLE_LEGACY_USER_ID_AUTH=false
ENABLE_ADMIN_DEBUG_API=false

SMS_PROVIDER=log
SMS_LOG_VERIFICATION_CODE=false
SMS_FIXED_VERIFICATION_CODE=123456
SMS_STUB_DELIVERY_ENABLED=true
```

The fixed SMS code is for closed testing only. Replace it with a real provider before public release.

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
  --dart-define=APP_VERSION=0.1.0
```

The APK is written to `app/build/app/outputs/flutter-apk/app-release.apk`.
