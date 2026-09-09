#!/usr/bin/env python3
"""Regenerate the checked-in 16px/2bpp Noto Sans SC dialogue font.

Requires lv_font_conv on the development host. Targets use only the generated C;
they do not need Node.js, Python or a font engine to render the dialogue.
"""
import argparse
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--font", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--converter", default="lv_font_conv")
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
# Common CJK unified ideographs, punctuation, kana, ASCII and replacement glyph.
# Extension-plane ideographs and emoji are not included.
subprocess.run([
    args.converter, "--bpp", "2", "--size", "16", "--font", str(args.font),
    "--format", "lvgl", "-r",
    "0x20-0x7f,0x3000-0x303f,0x3040-0x30ff,0xff01-0xff60,0x4e00-0x9fff",
    "--symbols", "牧瀬紅莉栖�", "-o", str(args.output),
    "--force-fast-kern-format",
], check=True)
