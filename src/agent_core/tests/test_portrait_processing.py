#!/usr/bin/env python3
"""Tests for local portrait cutout and alignment helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
SRC_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[3]

for path in (str(REPO_ROOT), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from PIL import Image

from GUI.interfaces import PortraitEditDraft
from GUI.portrait_processing import create_cutout_image, export_aligned_portrait


class PortraitProcessingTests(unittest.TestCase):
    def test_cutout_exports_transparent_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            output = Path(temp_dir) / "aligned.png"
            self._write_sample(source, size=(32, 32), foreground_box=(9, 6, 24, 28))

            edit = PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255), tolerance=2, feather=0)
            exported, layout, warning = export_aligned_portrait(edit, output_path=output)

            self.assertEqual(exported, output)
            self.assertEqual(warning, "")
            self.assertEqual((layout.canvas_width, layout.canvas_height), (390, 520))
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.size, (390, 520))
                self.assertIsNotNone(image.getchannel("A").getbbox())
                self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_tolerance_changes_transparent_area(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            self._write_sample(source, background=(250, 250, 250), foreground_box=(3, 3, 8, 8))

            strict = create_cutout_image(PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255), tolerance=0, feather=0))
            loose = create_cutout_image(PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255), tolerance=10, feather=0))

            self.assertEqual(strict.getpixel((0, 0))[3], 255)
            self.assertEqual(loose.getpixel((0, 0))[3], 0)

    def test_original_mode_preserves_source_background(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.png"
            self._write_sample(source, background=(250, 250, 250), foreground_box=(3, 3, 8, 8))

            original = create_cutout_image(
                PortraitEditDraft(
                    source_path=str(source),
                    render_mode="original",
                    background_color=(255, 255, 255),
                    tolerance=10,
                    feather=0,
                )
            )

            self.assertEqual(original.getpixel((0, 0)), (250, 250, 250, 255))

    def test_expression_reuses_neutral_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            neutral = Path(temp_dir) / "neutral.png"
            happy = Path(temp_dir) / "happy.webp"
            neutral_out = Path(temp_dir) / "neutral_out.png"
            happy_out = Path(temp_dir) / "happy_out.png"
            self._write_sample(neutral, size=(40, 60), foreground_box=(12, 8, 30, 54))
            self._write_sample(happy, size=(54, 64), foreground=(0, 90, 255), foreground_box=(8, 4, 48, 60))

            _, layout, _ = export_aligned_portrait(
                PortraitEditDraft(source_path=str(neutral), background_color=(255, 255, 255), tolerance=2, feather=0),
                output_path=neutral_out,
            )
            _, reused_layout, _ = export_aligned_portrait(
                PortraitEditDraft(source_path=str(happy), background_color=(255, 255, 255), tolerance=2, feather=0),
                layout,
                output_path=happy_out,
            )

            self.assertEqual(reused_layout, layout)
            with Image.open(neutral_out) as neutral_image, Image.open(happy_out) as happy_image:
                self.assertEqual(neutral_image.size, happy_image.size)
                self.assertEqual(happy_image.size, (390, 520))

    def test_jpg_input_outputs_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "portrait.jpg"
            output = Path(temp_dir) / "portrait.png"
            self._write_sample(source, foreground_box=(6, 6, 20, 26))

            exported, _, _ = export_aligned_portrait(
                PortraitEditDraft(source_path=str(source), background_color=(255, 255, 255), tolerance=35, feather=0),
                output_path=output,
            )

            self.assertEqual(exported.suffix, ".png")
            with Image.open(output) as image:
                self.assertEqual(image.format, "PNG")

    def _write_sample(
        self,
        path: Path,
        *,
        size: tuple[int, int] = (32, 32),
        background: tuple[int, int, int] = (255, 255, 255),
        foreground: tuple[int, int, int] = (220, 30, 30),
        foreground_box: tuple[int, int, int, int] = (8, 8, 24, 24),
    ) -> None:
        image = Image.new("RGB", size, background)
        for x in range(foreground_box[0], foreground_box[2]):
            for y in range(foreground_box[1], foreground_box[3]):
                image.putpixel((x, y), foreground)
        image.save(path)


if __name__ == "__main__":
    unittest.main()
