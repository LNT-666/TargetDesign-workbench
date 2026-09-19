#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the shared GUI workspace and common mixin."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
sys.path.insert(0, ROOT)
sys.path.insert(0, SHARED)

from gui.gui_common import CommonGUIMixin, Workspace  # noqa: E402


class WorkspaceTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "workspace.json")
            ws = Workspace(tmp, path)
            ws.set("genome", "genome.fa")
            ws.set("engine", "indexed")
            self.assertTrue(ws.save())

            loaded = Workspace(tmp, path)
            self.assertEqual(loaded.get("genome"), "genome.fa")
            self.assertEqual(loaded.get("engine"), "indexed")

    def test_load_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp, os.path.join(tmp, "missing.json"))
            self.assertEqual(ws.values(), {})


class CommonGUIMixinTests(unittest.TestCase):
    def test_collect_and_apply_workspace(self):
        class FakeVar:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class FakeEntry:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def delete(self, *_):
                self.value = ""

            def insert(self, _, value):
                self.value = value

        app = CommonGUIMixin()
        app.entry_genome = FakeEntry("genome.fa")
        app.combo_engine = FakeVar("exact")
        collected = app.collect_workspace({
            "entry_genome": "genome",
            "combo_engine": "engine",
        })
        self.assertEqual(collected["genome"], "genome.fa")
        self.assertEqual(collected["engine"], "exact")

        app.workspace = Workspace(tempfile.gettempdir())
        app.workspace.data = {"genome": "new.fa", "engine": "blast"}
        app.apply_workspace({
            "entry_genome": "genome",
            "combo_engine": "engine",
        })
        self.assertEqual(app.entry_genome.get(), "new.fa")
        self.assertEqual(app.combo_engine.get(), "blast")


class MainAppWorkspaceMappingTests(unittest.TestCase):
    """The legacy GUI mapping must name the widgets that really exist."""

    def test_library_engine_key_matches_the_real_widget(self):
        from main import MainApp

        class FakeVar:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        app = MainApp.__new__(MainApp)
        app.workspace = Workspace(tempfile.gettempdir())
        app.combo_library_search = FakeVar("blast")
        app.combo_library_memory_mode = FakeVar("Auto (50% RAM)")

        mapping = MainApp._workspace_mapping(app)
        self.assertEqual(mapping.get("combo_library_search"), "engine")
        self.assertNotIn("combo_library_engine", mapping)

        collected = MainApp.collect_workspace(app, mapping)
        self.assertEqual(collected.get("engine"), "blast")


if __name__ == "__main__":
    unittest.main()
