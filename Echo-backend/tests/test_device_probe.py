import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from features.devices.application.device_probe import DeviceProbe


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_matching_session_and_reply(self):
        probe, socket = DeviceProbe(), AsyncMock()
        task = asyncio.create_task(probe.check("test", socket))
        await asyncio.sleep(0)
        sent = socket.send_json.call_args.args[0]
        reply = {"jsonrpc": "2.0", "id": sent["payload"]["id"], "result": {"content": [{"type": "text", "text": "{}"}]}}
        probe.receive("test", object(), reply)
        self.assertFalse(task.done())
        probe.receive("test", socket, reply)
        await task
        self.assertFalse(probe.pending)

    async def test_timeout_is_not_success(self):
        probe = DeviceProbe()
        with self.assertRaises(TimeoutError):
            await probe.check("test", AsyncMock(), timeout=0.01)
        self.assertFalse(probe.pending)

    async def test_duplicate_request_and_disconnect(self):
        probe, socket = DeviceProbe(), AsyncMock()
        task = asyncio.create_task(probe.check("test", socket))
        await asyncio.sleep(0)
        with self.assertRaises(RuntimeError):
            await probe.check("test", socket)
        probe.disconnect("test", socket)
        with self.assertRaises(ConnectionError):
            await task
        self.assertFalse(probe.pending)

    async def test_mcp_error_cannot_acknowledge(self):
        probe, socket = DeviceProbe(), AsyncMock()
        task = asyncio.create_task(probe.check("test", socket))
        await asyncio.sleep(0)
        probe.receive("test", socket, {
            "jsonrpc": "2.0",
            "id": socket.send_json.call_args.args[0]["payload"]["id"],
            "result": {"isError": True, "content": [{"type": "text"}]},
        })
        with self.assertRaises(RuntimeError):
            await task

    async def test_empty_status_is_not_acknowledgement(self):
        probe, socket = DeviceProbe(), AsyncMock()
        task = asyncio.create_task(probe.check("test", socket))
        await asyncio.sleep(0)
        probe.receive("test", socket, {
            "jsonrpc": "2.0", "id": socket.send_json.call_args.args[0]["payload"]["id"],
            "result": {"content": [{"type": "text", "text": ""}]},
        })
        with self.assertRaises(RuntimeError):
            await task


if __name__ == "__main__":
    unittest.main()
