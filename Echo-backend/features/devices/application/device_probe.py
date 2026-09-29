import asyncio
import secrets


class DeviceProbe:
    """Bounded, session-scoped MCP requests; a send is not an acknowledgement."""

    def __init__(self):
        self.pending = {}

    async def check(self, device_id, websocket, timeout=5.0):
        if device_id in self.pending:
            raise RuntimeError("Device check already running")
        request_id = secrets.randbelow(2**30)
        future = asyncio.get_running_loop().create_future()
        entry = (websocket, request_id, future)
        self.pending[device_id] = entry
        try:
            async with asyncio.timeout(timeout):
                await websocket.send_json({
                    "type": "mcp",
                    "payload": {
                        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                        "params": {"name": "self.get_device_status", "arguments": {}},
                    },
                })
                await future
        finally:
            if self.pending.get(device_id) is entry:
                self.pending.pop(device_id, None)
            if not future.done():
                future.cancel()

    def receive(self, device_id, websocket, payload):
        entry = self.pending.get(device_id)
        if not entry or entry[0] is not websocket or not isinstance(payload, dict):
            return
        _, request_id, future = entry
        if payload.get("id") != request_id or future.done():
            return
        result = payload.get("result")
        if (payload.get("jsonrpc") != "2.0" or "error" in payload
                or not isinstance(result, dict) or result.get("isError")):
            future.set_exception(RuntimeError("Device check was rejected"))
            return
        content = result.get("content")
        if not isinstance(content, list) or not any(
            isinstance(item, dict) and item.get("type") == "text"
            and isinstance(item.get("text"), str) and item["text"].strip()
            for item in content
        ):
            future.set_exception(RuntimeError("Device returned no status"))
        else:
            future.set_result(None)

    def disconnect(self, device_id, websocket):
        entry = self.pending.get(device_id)
        if entry and entry[0] is websocket and not entry[2].done():
            entry[2].set_exception(ConnectionError("Device disconnected during check"))
