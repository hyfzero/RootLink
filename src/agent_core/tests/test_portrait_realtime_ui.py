#!/usr/bin/env python3
"""Tests for realtime portrait preview behavior in the create flow."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import flet as ft
from PIL import Image, ImageDraw

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from GUI.interfaces import CompanionRole, PortraitEditDraft
from GUI.views import CompanionAppView


def make_role() -> CompanionRole:
    return CompanionRole(
        id="amadeus",
        name="Amadeus",
        type="Test",
        tags=[],
        intro="intro",
        status_text="status",
        accent_color="#FF6600",
        avatar_path="",
        standing_image_path="",
    )


def make_portrait(path: Path) -> None:
    image = Image.new("RGB", (80, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((25, 24, 55, 108), fill=(210, 50, 50))
    image.save(path)


def collect_text_values(control) -> list[str]:
    values: list[str] = []
    seen: set[int] = set()

    def visit(item) -> None:
        if item is None or id(item) in seen:
            return
        seen.add(id(item))
        if isinstance(item, ft.Text):
            values.append(item.value)
        visit(getattr(item, "content", None))
        for child in getattr(item, "controls", []) or []:
            visit(child)

    visit(control)
    return values


class PortraitRealtimeUiTests(unittest.TestCase):
    def test_preset_updates_parameters_and_preview_without_manual_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            make_portrait(source)
            view = CompanionAppView(roles=[make_role()])
            edit = PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255))
            view._draft.portrait_edits["neutral"] = edit

            view._process_portrait("neutral", refresh=False)
            initial_preview = view._draft.portraits["neutral"]
            view._portrait_processing_panel(view._colors())

            view._set_portrait_preset("strong")

            self.assertEqual(edit.tolerance, 55)
            self.assertEqual(edit.feather, 3)
            self.assertIn("neutral", view._draft.portraits)
            self.assertNotEqual(view._draft.portraits["neutral"], initial_preview)
            self.assertTrue(Path(view._draft.portraits["neutral"]).exists())

    def test_failed_preview_keeps_previous_valid_portrait(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            make_portrait(source)
            view = CompanionAppView(roles=[make_role()])
            edit = PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255))
            view._draft.portrait_edits["neutral"] = edit
            self.assertTrue(view._process_portrait("neutral", refresh=False))
            valid_preview = view._draft.portraits["neutral"]

            edit.source_path = str(Path(temp_dir) / "missing.png")
            self.assertFalse(view._process_portrait("neutral", refresh=False))

            self.assertEqual(view._draft.portraits["neutral"], valid_preview)
            self.assertTrue(Path(valid_preview).exists())

    def test_advanced_sliders_show_and_refresh_numeric_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            make_portrait(source)
            view = CompanionAppView(roles=[make_role()])
            queued_previews: list[dict[str, bool]] = []
            view._queue_portrait_preview = lambda **kwargs: queued_previews.append(kwargs)  # type: ignore[method-assign]
            view._portrait_advanced_open = True
            edit = PortraitEditDraft(
                source_path=str(source),
                background_color=(255, 255, 255),
                tolerance=32,
                feather=2,
                scale=1.25,
                offset_x=-12,
                offset_y=8,
            )
            view._draft.portrait_edits["neutral"] = edit

            panel = view._portrait_processing_panel(view._colors())

            text_values = collect_text_values(panel)
            self.assertIn("32", text_values)
            self.assertIn("2", text_values)
            self.assertIn("1.25", text_values)
            self.assertIn("-12", text_values)
            self.assertIn("8", text_values)

            view._portrait_scale_slider.value = 0.75
            view._portrait_scale_slider.on_change(None)

            self.assertEqual(view._portrait_value_labels["scale"].value, "0.75")
            self.assertEqual(queued_previews[-1], {"refresh_page": False})


if __name__ == "__main__":
    unittest.main()
