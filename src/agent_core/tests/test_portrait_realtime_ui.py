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

from GUI.interfaces import CompanionRole, PortraitEditDraft, PortraitLayoutDraft
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
            self.assertEqual(edit.feather, 0)
            self.assertIn("neutral", view._draft.portraits)
            self.assertNotEqual(view._draft.portraits["neutral"], initial_preview)
            self.assertTrue(Path(view._draft.portraits["neutral"]).exists())

    def test_render_mode_toggle_updates_draft_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            make_portrait(source)
            view = CompanionAppView(roles=[make_role()])
            queued_previews: list[dict[str, bool]] = []
            view._queue_portrait_preview = lambda **kwargs: queued_previews.append(kwargs)  # type: ignore[method-assign]
            edit = PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255))
            view._draft.portrait_edits["neutral"] = edit
            view._draft.portrait_layout = PortraitLayoutDraft(canvas_width=390, canvas_height=520, anchor_bbox=(10, 10, 100, 200))
            view._portrait_processing_panel(view._colors())

            view._set_portrait_render_mode("original")

            self.assertEqual(edit.render_mode, "original")
            self.assertIsNone(view._draft.portrait_layout)
            self.assertEqual(queued_previews[-1], {})

            view._draft.portrait_layout = PortraitLayoutDraft(canvas_width=390, canvas_height=520, anchor_bbox=(10, 10, 100, 200))
            view._set_portrait_preset("strong")

            self.assertEqual(edit.render_mode, "cutout")
            self.assertIsNone(view._draft.portrait_layout)
            self.assertEqual(edit.tolerance, 55)

    def test_portrait_step_generates_initial_preview_when_saved_cache_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            make_portrait(source)
            view = CompanionAppView(roles=[make_role()])
            view._draft.portrait_edits["neutral"] = PortraitEditDraft(
                source_path=str(source),
                processed_path=str(Path(temp_dir) / "missing-preview.png"),
                background_color=(255, 255, 255),
            )

            view._portrait_step(view._colors())

            preview_path = view._draft.portraits["neutral"]
            self.assertTrue(Path(preview_path).exists())
            self.assertNotEqual(preview_path, str(source))

    def test_replacing_neutral_portrait_rebuilds_layout_and_refreshes_preview_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.png"
            second = Path(temp_dir) / "second.png"
            make_portrait(first)
            image = Image.new("RGB", (160, 160), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((8, 8, 152, 152), fill=(210, 50, 50))
            image.save(second)

            view = CompanionAppView(roles=[make_role()])
            view._draft.portrait_edits["neutral"] = PortraitEditDraft(
                source_path=str(first),
                background_color=(255, 255, 255),
            )
            self.assertTrue(view._process_portrait("neutral", refresh=False))
            first_preview = view._draft.portraits["neutral"]
            stale_layout = PortraitLayoutDraft(canvas_width=390, canvas_height=520, anchor_bbox=(10, 10, 40, 40))
            view._draft.portrait_layout = stale_layout

            view._replace_portrait_image("neutral", str(second))

            edit = view._draft.portrait_edits["neutral"]
            self.assertEqual(edit.warning, "")
            self.assertNotEqual(view._draft.portrait_layout, stale_layout)
            self.assertNotEqual(view._draft.portraits["neutral"], first_preview)
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
            self.assertIn("1.25", text_values)
            self.assertIn("-12", text_values)
            self.assertIn("8", text_values)

            view._portrait_scale_slider.value = 0.75
            view._portrait_scale_slider.on_change(None)

            self.assertEqual(view._portrait_value_labels["scale"].value, "0.75")
            self.assertEqual(queued_previews[-1], {"refresh_page": False})

    def test_advanced_slider_rows_use_stacked_mobile_layout(self) -> None:
        view = CompanionAppView(roles=[make_role()])
        slider = view._portrait_slider(0, 100, 10, 50)

        row = view._portrait_slider_row("Scale", slider, view._colors(), "scale", "int")

        self.assertIsInstance(row, ft.Container)
        self.assertIsInstance(row.content, ft.Column)
        self.assertEqual(len(row.content.controls), 2)
        self.assertIsInstance(row.content.controls[0], ft.Row)
        self.assertIsInstance(row.content.controls[1], ft.Container)
        self.assertEqual(row.content.controls[1].height, 36)
        self.assertIs(row.content.controls[1].content, slider)

    def test_persist_current_step_saves_latest_advanced_slider_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            make_portrait(source)
            view = CompanionAppView(roles=[make_role()])
            view._portrait_advanced_open = True
            edit = PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255))
            view._draft.portrait_edits["neutral"] = edit
            view._portrait_processing_panel(view._colors())

            view._portrait_tolerance_slider.value = 88
            view._portrait_scale_slider.value = 0.65
            view._portrait_offset_x_slider.value = 24
            view._portrait_offset_y_slider.value = -12
            view._persist_current_step()

            self.assertEqual(edit.tolerance, 88)
            self.assertEqual(edit.scale, 0.65)
            self.assertEqual(edit.offset_x, 24)
            self.assertEqual(edit.offset_y, -12)


if __name__ == "__main__":
    unittest.main()
