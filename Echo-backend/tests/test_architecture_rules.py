"""Regression checks for actual dependency boundaries and empty API handlers."""

import ast
import runpy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

CHECKS = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/check_architecture.py"))


class ArchitectureRulesTests(unittest.TestCase):
    def test_routes_cannot_be_future_placeholders(self):
        source = "@router.post('/future')\ndef future():\n    raise NotImplementedError('later')\n"
        errors = CHECKS["check_implemented_routes"](ast.parse(source), "example.py")
        self.assertEqual(len(errors), 1)

    def test_empty_async_route_is_rejected(self):
        source = "@router.websocket('/future')\nasync def future():\n    ...\n"
        self.assertTrue(CHECKS["check_implemented_routes"](ast.parse(source), "example.py"))

    def test_consumed_contracts_and_real_routes_are_allowed(self):
        source = (
            "class Gateway(Protocol):\n    def execute(self): ...\n"
            "@router.post('/current')\ndef current():\n    return use_case.execute()\n"
        )
        self.assertEqual(CHECKS["check_implemented_routes"](ast.parse(source), "example.py"), [])

    def test_shared_prompting_cannot_import_business_or_database(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "renderer.py"
            source.write_text("from features.persona.public import get_persona\nimport db\n")
            function = CHECKS["check_shared_prompt_file"]
            with patch.dict(function.__globals__, {"PROJECT_ROOT": root}):
                self.assertEqual(len(function(source)), 2)

    def test_neutral_prompt_contracts_are_allowed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "contracts.py"
            source.write_text("from typing import Protocol\nclass Input(Protocol): ...\n")
            function = CHECKS["check_shared_prompt_file"]
            with patch.dict(function.__globals__, {"PROJECT_ROOT": root}):
                self.assertEqual(function(source), [])

    def test_prompt_assets_require_current_consumers_and_nonempty_content(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            renderer = root / "renderer.py"
            renderer.write_text("POLICY = _load_rule('active.md')\n")
            (root / "active.md").write_text("Current rule")
            (root / "future.md").write_text("Unwired future rule")
            function = CHECKS["check_prompt_assets"]
            self.assertEqual(len(function(renderer, root)), 1)
            (root / "future.md").unlink()
            self.assertEqual(function(renderer, root), [])
            (root / "active.md").write_text("")
            self.assertEqual(len(function(renderer, root)), 1)
