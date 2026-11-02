from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from echo_desktop.config import DesktopConfig, load_config, save_config


class ConfigTests(unittest.TestCase):
    def test_round_trips_auto_approve_and_defaults_missing_field(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {"APPDATA": temporary}),
        ):
            config = DesktopConfig(
                server_url="https://api.echoaiforever.cn",
                node_id="dnode_1",
                node_name="测试电脑",
                token="token",
                auto_approve=False,
            )
            save_config(config)
            loaded = load_config()
            self.assertIsNotNone(loaded)
            self.assertFalse(loaded.auto_approve)

            path = Path(temporary) / "EchoDesktop" / "config.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.pop("auto_approve")
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(load_config().auto_approve)


if __name__ == "__main__":
    unittest.main()
