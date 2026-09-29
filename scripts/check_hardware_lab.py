"""Physical-device checks against the isolated local lab.

Uses a local SMS-stub login; credentials and audio are never written or printed.
Do not use simulated WebSockets or audio to claim a hardware acceptance pass.
--reboot-probe briefly enters the real device bootloader, then always reboots it.
"""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from run_device_lab import configure

DEVICE_ID = "e0:72:a1:d5:34:2c"
BASE = "http://127.0.0.1:18000"
http = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, headers=headers,
                                 data=json.dumps(data).encode() if data is not None else None)
    try:
        with http.open(req, timeout=12) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        body = json.loads(error.read())
        return error.code, {"detail": body.get("detail"), "code": body.get("code")}


def login():
    from db.postgres_connection import get_connection
    with get_connection() as conn:
        users = conn.execute("SELECT user_id, phone FROM users").fetchall()
    if len(users) != 1 or not users[0]["phone"]:
        raise RuntimeError("Expected exactly one local phone account")
    phone = users[0]["phone"]
    device_id = str(uuid.uuid4())
    status, challenge = request("/login/phone", {
        "phone": phone, "device_id": device_id, "purpose": "login",
    })
    if status != 202:
        raise RuntimeError(f"Local SMS login failed: HTTP {status}")
    status, session = request("/login/verify", {
        "phone": phone, "device_id": device_id, "request_id": challenge["request_id"],
        "code": "123456",
    })
    if status != 200:
        raise RuntimeError(f"Local verification failed: HTTP {status}")
    return session["access_token"]


def status():
    from db.postgres_connection import get_connection
    with get_connection() as conn:
        if conn.info.dbname != "echo_device_lab":
            raise RuntimeError("Refusing non-lab database")
        device = conn.execute(
            "SELECT status,firmware_version,last_seen_at,owner_user_id IS NOT NULL AS bound "
            "FROM devices WHERE device_id=%s", (DEVICE_ID,),
        ).fetchone()
        people = conn.execute(
            "SELECT status,jsonb_array_length(samples) AS sample_count FROM speaker_people "
            "WHERE device_id=%s ORDER BY created_at", (DEVICE_ID,),
        ).fetchall()
    return {"physical_device": device, "speaker_progress": people}


def reboot_probe(token):
    command = ["esptool", "--chip", "esp32s3", "--port", "COM5"]
    try:
        result = subprocess.run([*command, "--after", "no-reset", "flash-id"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode or DEVICE_ID not in result.stdout.lower():
            raise RuntimeError("Expected physical device not confirmed on COM5")
        code, reply = request(f"/devices/{DEVICE_ID}/probe", {}, token)
        print(json.dumps({"real_device_in_bootloader": True, "http_status": code,
                          "acknowledged": (reply or {}).get("acknowledged", False)},
                         ensure_ascii=False), flush=True)
        if code == 200 or (reply or {}).get("acknowledged"):
            raise RuntimeError("Offline hardware must not acknowledge")
    finally:
        reset = subprocess.run([*command, "run"], capture_output=True, text=True, timeout=30)
        if reset.returncode:
            raise RuntimeError("Device reset failed; check USB and restore normal startup")
    for _ in range(15):
        time.sleep(2)
        code, reply = request(f"/devices/{DEVICE_ID}/probe", {}, token)
        if code == 200 and reply.get("acknowledged") is True:
            print("Reboot recovery: real hardware acknowledgement restored", flush=True)
            return
    raise RuntimeError("Hardware did not reconnect after reset")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--reboot-probe", action="store_true")
    parser.add_argument("--watch-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.reboot_probe and not args.probe:
        parser.error("--reboot-probe requires --probe")
    configure()
    if args.probe:
        token = login()
        if args.reboot_probe:
            reboot_probe(token)
        for index in range(3):
            started = time.monotonic()
            code, result = request(f"/devices/{DEVICE_ID}/probe", {}, token)
            print(json.dumps({"probe": index + 1, "http_status": code,
                              "acknowledged": (result or {}).get("acknowledged", False),
                              "elapsed_ms": round((time.monotonic() - started) * 1000),
                              "detail": (result or {}).get("detail")}, ensure_ascii=False), flush=True)
            if code != 200 or result.get("acknowledged") is not True:
                raise SystemExit("Physical hardware acknowledgement did not pass")
            time.sleep(1)
    end = time.monotonic() + min(max(args.watch_seconds, 0), 600)
    previous = None
    while True:
        result = json.dumps(status(), default=str, ensure_ascii=False)
        if result != previous:
            print(result, flush=True)
            previous = result
        if time.monotonic() >= end:
            break
        time.sleep(2)
