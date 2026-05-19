"""Lightweight local portrait cutout and alignment helpers."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from PIL import Image, ImageFilter

from .interfaces import PortraitEditDraft, PortraitLayoutDraft


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_CANVAS_SIZE = (390, 520)
PORTRAIT_RENDER_MODE_CUTOUT = "cutout"
PORTRAIT_RENDER_MODE_ORIGINAL = "original"
PORTRAIT_RENDER_MODES = {PORTRAIT_RENDER_MODE_CUTOUT, PORTRAIT_RENDER_MODE_ORIGINAL}


class PortraitProcessingError(ValueError):
    """Raised when a portrait cannot be processed."""


def validate_image_path(path: str) -> Path:
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise PortraitProcessingError(f"Image file not found: {path}")
    if source.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise PortraitProcessingError("Images must be PNG, JPG, JPEG, or WebP.")
    return source


def sample_background_color(path: str, preset: str = "top_left") -> tuple[int, int, int]:
    source = validate_image_path(path)
    with Image.open(source) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        points = {
            "top_left": (0, 0),
            "top_right": (max(0, width - 1), 0),
            "bottom_left": (0, max(0, height - 1)),
            "bottom_right": (max(0, width - 1), max(0, height - 1)),
            "center": (width // 2, height // 2),
        }
        return tuple(int(value) for value in rgb.getpixel(points.get(preset, (0, 0))))


def sample_background_color_auto(path: str) -> tuple[int, int, int]:
    source = validate_image_path(path)
    with Image.open(source) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        corners = [
            (0, 0),
            (max(0, width - 1), 0),
            (0, max(0, height - 1)),
            (max(0, width - 1), max(0, height - 1)),
            (width // 2, height // 2),
        ]
        colors = [rgb.getpixel(p) for p in corners]
    from collections import Counter
    most_common = Counter(colors).most_common(1)[0][0]
    return tuple(int(v) for v in most_common)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _normalized_crop_box(crop_box: tuple[int, int, int, int] | None, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    if crop_box is None:
        return (0, 0, width, height)
    left, top, right, bottom = crop_box
    left = _clamp(int(left), 0, width - 1)
    top = _clamp(int(top), 0, height - 1)
    right = _clamp(int(right), left + 1, width)
    bottom = _clamp(int(bottom), top + 1, height)
    return (left, top, right, bottom)


def create_cutout_image(edit: PortraitEditDraft) -> Image.Image:
    source = validate_image_path(edit.source_path)
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
    rgba = rgba.crop(_normalized_crop_box(edit.crop_box, rgba.size))
    if edit.render_mode == PORTRAIT_RENDER_MODE_ORIGINAL:
        return rgba

    bg_r, bg_g, bg_b = edit.background_color
    tolerance = max(0, int(edit.tolerance))
    tolerance_sq = tolerance * tolerance
    alpha_values = []
    pixel_data = rgba.get_flattened_data() if hasattr(rgba, "get_flattened_data") else rgba.getdata()
    for red, green, blue, alpha in pixel_data:
        distance_sq = (red - bg_r) ** 2 + (green - bg_g) ** 2 + (blue - bg_b) ** 2
        alpha_values.append(0 if distance_sq <= tolerance_sq else alpha)

    alpha_mask = Image.new("L", rgba.size)
    alpha_mask.putdata(alpha_values)
    feather = max(0, int(edit.feather))
    if feather:
        alpha_mask = alpha_mask.filter(ImageFilter.GaussianBlur(radius=feather))
    rgba.putalpha(alpha_mask)
    return rgba


def foreground_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    alpha = image.getchannel("A")
    return alpha.getbbox()


def _fit_size(source_size: tuple[int, int], target_size: tuple[int, int], scale: float) -> tuple[int, int]:
    source_width, source_height = source_size
    target_width, target_height = target_size
    if source_width <= 0 or source_height <= 0:
        return (1, 1)
    ratio = min(target_width / source_width, target_height / source_height) * max(0.05, float(scale))
    return (max(1, int(source_width * ratio)), max(1, int(source_height * ratio)))


def export_aligned_portrait(
    edit: PortraitEditDraft,
    layout: PortraitLayoutDraft | None = None,
    *,
    output_path: str | Path | None = None,
) -> tuple[Path, PortraitLayoutDraft, str]:
    cutout = create_cutout_image(edit)
    bbox = foreground_bbox(cutout)
    if bbox is None:
        raise PortraitProcessingError("No foreground pixels were found. Try lowering tolerance or changing the background sample.")

    foreground = cutout.crop(bbox)
    warning = ""
    if layout is None or layout.canvas_width <= 0 or layout.canvas_height <= 0 or layout.anchor_bbox is None:
        canvas_width, canvas_height = DEFAULT_CANVAS_SIZE
        anchor_bbox = _centered_anchor_bbox(bbox, cutout.size, (canvas_width, canvas_height))
        layout = PortraitLayoutDraft(canvas_width=canvas_width, canvas_height=canvas_height, anchor_bbox=anchor_bbox)
    else:
        canvas_width, canvas_height = int(layout.canvas_width), int(layout.canvas_height)
        anchor_bbox = layout.anchor_bbox
        if _bbox_area(bbox) > _bbox_area(anchor_bbox) * 1.1:
            warning = "当前立绘前景大于 neutral 基准，可能被压缩以保持同一范围。"

    anchor_left, anchor_top, anchor_right, anchor_bottom = anchor_bbox
    target_size = (max(1, anchor_right - anchor_left), max(1, anchor_bottom - anchor_top))
    fitted_size = _fit_size(foreground.size, target_size, edit.scale)
    foreground = foreground.resize(fitted_size, Image.Resampling.LANCZOS)

    paste_x = anchor_left + (target_size[0] - fitted_size[0]) // 2 + int(edit.offset_x)
    paste_y = anchor_top + (target_size[1] - fitted_size[1]) // 2 + int(edit.offset_y)
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    _alpha_composite_clipped(canvas, foreground, paste_x, paste_y)

    output = Path(output_path) if output_path is not None else _temp_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    return output, layout, warning


def _centered_anchor_bbox(
    source_bbox: tuple[int, int, int, int],
    source_size: tuple[int, int],
    canvas_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    left, top, right, bottom = source_bbox
    source_width, source_height = source_size
    canvas_width, canvas_height = canvas_size
    bbox_width = max(1, right - left)
    bbox_height = max(1, bottom - top)
    ratio = min(canvas_width / max(1, source_width), canvas_height / max(1, source_height))
    width = max(1, int(bbox_width * ratio))
    height = max(1, int(bbox_height * ratio))
    center_x = canvas_width // 2
    center_y = int((top + bbox_height / 2) * ratio + (canvas_height - source_height * ratio) / 2)
    anchor_left = _clamp(center_x - width // 2, 0, canvas_width - 1)
    anchor_top = _clamp(center_y - height // 2, 0, canvas_height - 1)
    anchor_right = _clamp(anchor_left + width, anchor_left + 1, canvas_width)
    anchor_bottom = _clamp(anchor_top + height, anchor_top + 1, canvas_height)
    return (anchor_left, anchor_top, anchor_right, anchor_bottom)


def _bbox_area(bbox: tuple[int, int, int, int]) -> int:
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _alpha_composite_clipped(canvas: Image.Image, foreground: Image.Image, x: int, y: int) -> None:
    left = max(0, x)
    top = max(0, y)
    right = min(canvas.width, x + foreground.width)
    bottom = min(canvas.height, y + foreground.height)
    if right <= left or bottom <= top:
        return

    source_left = max(0, -x)
    source_top = max(0, -y)
    clipped = foreground.crop(
        (
            source_left,
            source_top,
            source_left + (right - left),
            source_top + (bottom - top),
        )
    )
    canvas.alpha_composite(clipped, dest=(left, top))


def _temp_output_path() -> Path:
    root = Path(tempfile.gettempdir()) / "amadues_portraits"
    return root / f"portrait-{uuid.uuid4().hex}.png"
