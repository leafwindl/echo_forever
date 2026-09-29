"""Start the full backend locally against a separate lab database.

No production connection strings are used. Test DB credentials are read into
memory from the existing local container; never print them or write a file.
Run from the project root with the existing backend Python environment.
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo
from dotenv import load_dotenv


def configure(hardware=None):
    root = Path(__file__).resolve().parents[1]
    data = json.loads(subprocess.check_output(
        ["docker", "inspect", "echo-postgres-test"], text=True,
    ))[0]
    env = dict(item.split("=", 1) for item in data["Config"]["Env"] if "=" in item)
    ports = data["HostConfig"]["PortBindings"].get("5432/tcp", [])
    if not ports or ports[0]["HostIp"] != "127.0.0.1" or ports[0]["HostPort"] != "15432":
        raise RuntimeError("Expected isolated test PostgreSQL on 127.0.0.1:15432")
    credentials = dict(host="127.0.0.1", port=15432,
        user=env.get("POSTGRES_USER", "postgres"), password=env["POSTGRES_PASSWORD"])
    with psycopg.connect(**credentials, dbname="postgres", autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", ("echo_device_lab",)).fetchone():
            conn.execute("CREATE DATABASE echo_device_lab")
    load_dotenv(root / "Echo-backend" / ".env", override=False)
    os.environ.update({
        "DATABASE_URL": make_conninfo(**credentials, dbname="echo_device_lab"),
        "PUBLIC_BASE_URL": "http://127.0.0.1:18000",
        "ECHO_SPEAKER_SERVICE_URL": "http://127.0.0.1:18100",
        "ECHO_VOICE_ENROLLMENT_ENABLED": "true",
        "AUTH_TOKEN_SECRET": secrets.token_hex(32),
        "ECHO_DEVICE_USER_MAP_JSON": "{}", "ECHO_DEVICE_TOKEN": "",
        "COS_ENABLED": "false", "PUSH_ENABLED": "false",
        "DAILY_LETTER_ENABLED": "false", "PROACTIVE_CHAT_ENABLED": "false",
        "STICKER_GENERATION_ENABLED": "false", "CHAT_ASYNC_ENABLED": "false",
        "SMS_PROVIDER": "log", "SMS_STUB_DELIVERY_ENABLED": "true",
        "SMS_FIXED_VERIFICATION_CODE": "123456", "SMS_LOG_VERIFICATION_CODE": "false",
    })
    if hardware:
        with psycopg.connect(**credentials, dbname="echo_device_lab") as conn:
            users = conn.execute("SELECT user_id FROM users ORDER BY created_at").fetchall()
        if len(users) != 1:
            raise RuntimeError("Hardware lab requires exactly one local account; select an owner explicitly first")
        os.environ["PUBLIC_BASE_URL"] = "http://192.168.137.1:18000"
        os.environ["ECHO_DEVICE_USER_MAP_JSON"] = json.dumps({
            f"{hardware[0]}|{hardware[1]}": users[0][0],
        })
        print("Hardware lab: one local account; production credentials are not imported")
    os.chdir(root / "Echo-backend")
    sys.path.insert(0, str(root / "Echo-backend"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--hardware-lab", action="store_true",
                        help="Listen on the computer hotspot and allow the designated physical device")
    args = parser.parse_args()
    hardware = ("e0:72:a1:d5:34:2c", "f7d10172-9ca7-4409-a529-4a88c4768e68") if args.hardware_lab else None
    configure(hardware)
    if args.test:
        import pytest
        os.environ["ECHO_LAB_DB_TEST"] = "1"
        sys.exit(pytest.main(["tests/test_speaker_lab.py", "-q"]))
    elif args.init_only:
        from db.postgres_schema import init_db
        init_db()
        print("Local lab schema ready")
    else:
        import uvicorn
        # A single worker owns the device websocket registry and enrollment sessions.
        if args.hardware_lab:
            from main import app

            async def restricted_app(scope, receive, send):
                if scope["type"] in ("http", "websocket"):
                    peer = (scope.get("client") or ("",))[0]
                    if peer not in {"127.0.0.1", "192.168.137.190"}:
                        if scope["type"] == "websocket":
                            await send({"type": "websocket.close", "code": 1008})
                        else:
                            await send({"type": "http.response.start", "status": 403, "headers": []})
                            await send({"type": "http.response.body", "body": b"Local lab only"})
                        return
                await app(scope, receive, send)

            sockets = []
            try:
                for address in ("127.0.0.1", "192.168.137.1"):
                    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sockets.append(listener)
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    listener.bind((address, 18000))
                server = uvicorn.Server(uvicorn.Config(restricted_app, workers=1, proxy_headers=False))
                server.run(sockets=sockets)
            finally:
                for listener in sockets:
                    listener.close()
        else:
            uvicorn.run("main:app", host="127.0.0.1", port=18000, workers=1)
