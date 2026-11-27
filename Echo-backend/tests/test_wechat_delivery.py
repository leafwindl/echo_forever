# ruff: noqa: ARG002
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.agent.domain.entities import ContentPart
from features.chat.public import build_chat_delivery_items
from features.desktop.application import wechat_events
from features.desktop.application.remote_command import RemoteCommandResult


def _sticker_part(
    sticker_id: str = "stk_a",
    url: str = "https://api.example.com/static/stickers/a.png",
    index: int = 0,
) -> ContentPart:
    return ContentPart(
        type="sticker",
        sticker_id=sticker_id,
        url=url,
        after_text_index=index,
    )


def _sequence_body(command: str) -> dict:
    body = command.split("-Body '", 1)[1].rsplit("' -TimeoutSec", 1)[0]
    return json.loads(body)


class WechatDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def test_build_chat_delivery_items_interleaves_text_and_sticker(self):
        items = build_chat_delivery_items(
            ("第一句", "第二句"),
            (_sticker_part(index=0),),
            "after_text",
        )

        self.assertEqual([item.message_type for item in items], ["text", "sticker", "text"])
        self.assertEqual(items[1].parts[0].sticker_id, "stk_a")

    def test_sticker_suffix_ignores_signed_query(self):
        url = (
            "https://bucket.cos.ap-guangzhou.myqcloud.com/echo/a.JPG"
            "?sign=q-sign-algorithm%3Dsha1"
        )

        self.assertEqual(wechat_events._sticker_suffix(url), ".jpg")

    def test_sticker_filename_is_ascii_and_stable(self):
        first = wechat_events._sticker_filename("stk_a", "https://x/a.png")
        second = wechat_events._sticker_filename("stk_a", "https://x/a.png?sign=1")

        self.assertEqual(first, second)
        self.assertRegex(first, r"^stk_[0-9a-f]{16}\.png$")

    def test_sticker_download_command_uses_vm_images_dir(self):
        command = wechat_events._sticker_download_command(
            "https://x/a.png",
            "stk_0123456789abcdef.png",
        )

        self.assertIn("C:\\EchoComputer\\images\\stk_0123456789abcdef.png", command)
        self.assertIn("$ErrorActionPreference='Stop'", command)

    async def test_delivery_sends_text_and_image_in_order(self):
        remote = AsyncMock(
            side_effect=[
                RemoteCommandResult(True, "1234"),
                RemoteCommandResult(True, '{"ok": true, "results": []}'),
            ]
        )
        items = build_chat_delivery_items(("图来了",), (_sticker_part(),), "after_text")

        with patch.object(wechat_events, "run_remote_command", remote):
            ok = await wechat_events.send_wechat_delivery(
                service=object(),
                user_id="user_1",
                items=items,
            )

        self.assertTrue(ok)
        self.assertEqual(remote.await_count, 2)
        body = _sequence_body(remote.await_args_list[-1].kwargs["command"])
        self.assertEqual(body["items"][0], {"type": "text", "text": "图来了"})
        self.assertEqual(body["items"][1]["type"], "image")
        self.assertTrue(body["items"][1]["path"].startswith("stk_"))

    async def test_download_failure_degrades_to_text(self):
        remote = AsyncMock(
            side_effect=[
                RemoteCommandResult(False, "boom"),
                RemoteCommandResult(True, '{"ok": true, "results": []}'),
            ]
        )
        items = build_chat_delivery_items(("先说话",), (_sticker_part(),), "after_text")

        with patch.object(wechat_events, "run_remote_command", remote):
            ok = await wechat_events.send_wechat_delivery(
                service=object(),
                user_id="user_1",
                items=items,
            )

        self.assertTrue(ok)
        body = _sequence_body(remote.await_args_list[-1].kwargs["command"])
        self.assertEqual(body["items"], [{"type": "text", "text": "先说话"}])

    async def test_only_first_sticker_is_sent(self):
        remote = AsyncMock(
            side_effect=[
                RemoteCommandResult(True, "1234"),
                RemoteCommandResult(True, '{"ok": true, "results": []}'),
            ]
        )
        parts = (
            _sticker_part("stk_a", "https://x/a.png", index=0),
            _sticker_part("stk_b", "https://x/b.png", index=1),
        )
        items = build_chat_delivery_items(("第一句", "第二句"), parts, "after_text")

        with patch.object(wechat_events, "run_remote_command", remote):
            ok = await wechat_events.send_wechat_delivery(
                service=object(),
                user_id="user_1",
                items=items,
            )

        self.assertTrue(ok)
        self.assertEqual(remote.await_count, 2)
        body = _sequence_body(remote.await_args_list[-1].kwargs["command"])
        images = [item for item in body["items"] if item["type"] == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(
            images[0]["path"],
            wechat_events._sticker_filename("stk_a", "https://x/a.png"),
        )

    async def test_gif_is_skipped(self):
        remote = AsyncMock(return_value=RemoteCommandResult(True, '{"ok": true}'))
        items = build_chat_delivery_items(
            ("嗨",),
            (_sticker_part(url="https://x/a.gif"),),
            "after_text",
        )

        with patch.object(wechat_events, "run_remote_command", remote):
            ok = await wechat_events.send_wechat_delivery(
                service=object(),
                user_id="user_1",
                items=items,
            )

        self.assertTrue(ok)
        self.assertEqual(remote.await_count, 1)
        body = _sequence_body(remote.await_args.kwargs["command"])
        self.assertEqual(body["items"], [{"type": "text", "text": "嗨"}])

    async def test_gif_only_delivery_is_not_sent(self):
        remote = AsyncMock()
        items = build_chat_delivery_items(
            (),
            (_sticker_part(url="https://x/a.gif"),),
            "after_text",
        )

        with patch.object(wechat_events, "run_remote_command", remote):
            ok = await wechat_events.send_wechat_delivery(
                service=object(),
                user_id="user_1",
                items=items,
            )

        self.assertFalse(ok)
        remote.assert_not_awaited()

    async def test_bridge_rejection_is_failure(self):
        remote = AsyncMock(return_value=RemoteCommandResult(True, '{"ok": false}'))
        items = build_chat_delivery_items(("嗨",), (), "after_text")

        with patch.object(wechat_events, "run_remote_command", remote):
            ok = await wechat_events.send_wechat_delivery(
                service=object(),
                user_id="user_1",
                items=items,
            )

        self.assertFalse(ok)

    def test_bridge_sequence_command_carries_items(self):
        command = wechat_events._bridge_send_sequence_command(
            [
                {"type": "text", "text": "嗨"},
                {"type": "image", "path": "stk_0123456789abcdef.png"},
            ]
        )

        self.assertIn("/send_sequence", command)
        self.assertEqual(
            _sequence_body(command)["items"],
            [
                {"type": "text", "text": "嗨"},
                {"type": "image", "path": "stk_0123456789abcdef.png"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
