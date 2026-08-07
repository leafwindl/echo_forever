from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "Echo-backend"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env", override=False)

from features.releases.infrastructure.postgres_repository import (  # noqa: E402
    PostgresReleaseRepository,
)
from shared.storage import get_cos_object_storage  # noqa: E402

EXPECTED_PACKAGE_NAME = "cn.echoaiforever.echo_app"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_android_sdk() -> Path | None:
    properties_path = PROJECT_ROOT / "app" / "android" / "local.properties"
    if not properties_path.is_file():
        return None
    for line in properties_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("sdk.dir="):
            value = line.removeprefix("sdk.dir=").replace("\\:", ":").replace("\\\\", "\\")
            return Path(value)
    return None


def _find_apkanalyzer(explicit: str) -> Path:
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"apkanalyzer not found: {candidate}")

    executable = shutil.which("apkanalyzer") or shutil.which("apkanalyzer.bat")
    if executable:
        return Path(executable)

    sdk_roots = [
        Path(value)
        for value in (os.getenv("ANDROID_SDK_ROOT"), os.getenv("ANDROID_HOME"))
        if value
    ]
    local_sdk = _local_android_sdk()
    if local_sdk is not None:
        sdk_roots.append(local_sdk)
    names = ("apkanalyzer.bat", "apkanalyzer") if os.name == "nt" else ("apkanalyzer",)
    for sdk_root in sdk_roots:
        for relative in (Path("cmdline-tools/latest/bin"), Path("tools/bin")):
            for name in names:
                candidate = sdk_root / relative / name
                if candidate.is_file():
                    return candidate
    raise FileNotFoundError(
        "apkanalyzer was not found; install Android command-line tools or pass --apkanalyzer"
    )


def _analyze(tool: Path, apk: Path, field: str) -> str:
    command = [str(tool), "manifest", field, str(apk)]
    if os.name == "nt" and tool.suffix.lower() in {".bat", ".cmd"}:
        command = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/q",
            "/c",
            *command,
        ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_android_tool_environment(),
    )
    return completed.stdout.strip()


def _android_tool_environment() -> dict[str, str]:
    environment = os.environ.copy()
    if environment.get("JAVA_HOME") or shutil.which("java"):
        return environment
    flutter = shutil.which("flutter") or shutil.which("flutter.bat")
    if not flutter:
        return environment
    command = [flutter, "config", "--machine"]
    if os.name == "nt" and Path(flutter).suffix.lower() in {".bat", ".cmd"}:
        command = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/q",
            "/c",
            *command,
        ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        jdk_dir = str(json.loads(completed.stdout).get("jdk-dir", "")).strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        return environment
    if jdk_dir and (Path(jdk_dir) / "bin" / ("java.exe" if os.name == "nt" else "java")).is_file():
        environment["JAVA_HOME"] = jdk_dir
    return environment


def _validate_apk(apk: Path, tool: Path) -> tuple[str, str, int]:
    package_name = _analyze(tool, apk, "application-id")
    version_name = _analyze(tool, apk, "version-name")
    version_code = int(_analyze(tool, apk, "version-code"))
    if package_name != EXPECTED_PACKAGE_NAME:
        raise ValueError(
            f"Unexpected package name: expected {EXPECTED_PACKAGE_NAME}, got {package_name}"
        )
    if not version_name or version_code <= 0:
        raise ValueError("APK version metadata is invalid")
    return package_name, version_name, version_code


def _validate_declared_metadata(
    package_name: str,
    version_name: str,
    version_code: int,
) -> tuple[str, str, int]:
    if package_name != EXPECTED_PACKAGE_NAME:
        raise ValueError(
            f"Unexpected package name: expected {EXPECTED_PACKAGE_NAME}, got {package_name}"
        )
    if not version_name.strip() or version_code <= 0:
        raise ValueError("APK version metadata is invalid")
    return package_name, version_name, version_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an Echo Android direct-update release")
    parser.add_argument(
        "--apk",
        type=Path,
        default=PROJECT_ROOT / "app/build/app/outputs/flutter-apk/app-release.apk",
    )
    parser.add_argument("--channel", default="internal", choices=("internal",))
    parser.add_argument("--minimum-version-code", type=int, default=1)
    parser.add_argument("--mandatory", action="store_true")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--apkanalyzer", default="")
    parser.add_argument("--package-name")
    parser.add_argument("--version-name")
    parser.add_argument("--version-code", type=int)
    args = parser.parse_args()

    apk = args.apk.resolve()
    if not apk.is_file() or apk.stat().st_size <= 0:
        raise SystemExit(f"APK not found or empty: {apk}")

    declared_metadata = (args.package_name, args.version_name, args.version_code)
    if any(value is not None for value in declared_metadata):
        if any(value is None for value in declared_metadata):
            raise SystemExit(
                "--package-name, --version-name and --version-code must be supplied together"
            )
        try:
            package_name, version_name, version_code = _validate_declared_metadata(
                args.package_name,
                args.version_name,
                args.version_code,
            )
        except ValueError as exc:
            raise SystemExit(f"APK validation failed: {exc}") from None
    else:
        try:
            package_name, version_name, version_code = _validate_apk(
                apk,
                _find_apkanalyzer(args.apkanalyzer),
            )
        except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
            raise SystemExit(f"APK validation failed: {exc}") from None
    if not 0 < args.minimum_version_code <= version_code:
        raise SystemExit("--minimum-version-code must be between 1 and the APK versionCode")

    digest = _sha256(apk)
    size_bytes = apk.stat().st_size
    repository = PostgresReleaseRepository()
    existing = repository.get_by_version("android", args.channel, version_code)
    if existing is not None:
        raise SystemExit(
            f"Release already exists for android/{args.channel} versionCode={version_code}: "
            f"{existing.release_id}"
        )
    relative_key = (
        f"releases/android/{args.channel}/{version_name}+{version_code}/"
        f"echo-{digest[:12]}.apk"
    )
    storage = get_cos_object_storage()
    object_key = storage.put_file(
        relative_key,
        apk,
        "application/vnd.android.package-archive",
        cache_control="private, max-age=31536000, immutable",
    )
    try:
        metadata = storage.head(object_key)
        if metadata.content_length != size_bytes:
            raise RuntimeError(
                f"COS size mismatch: expected {size_bytes}, got {metadata.content_length}"
            )
        release = repository.publish(
            platform="android",
            channel=args.channel,
            package_name=package_name,
            version_name=version_name,
            version_code=version_code,
            minimum_version_code=args.minimum_version_code,
            cos_object_key=object_key,
            sha256=digest,
            size_bytes=size_bytes,
            release_notes=args.note,
            mandatory=args.mandatory,
        )
    except Exception:
        storage.delete(object_key)
        raise

    print(
        f"Published {release.release_id}: {package_name} "
        f"{version_name}+{version_code} ({size_bytes} bytes, sha256={digest})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
