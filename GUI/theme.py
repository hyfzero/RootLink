"""Figma-derived visual tokens for the mobile companion UI."""

from __future__ import annotations

import flet as ft

MOBILE_WIDTH = 428
UI_FONT_FAMILY = "Microsoft YaHei UI"

MOTION = {
    "fast": 180,
    "normal": 300,
    "medium": 500,
    "slow": 600,
    "page": 560,
    "message": 260,
    "stagger": 80,
}

MOTION_CURVES = {
    "enter": ft.AnimationCurve.FAST_OUT_SLOWIN,
    "exit": ft.AnimationCurve.EASE_IN_OUT,
    "press": ft.AnimationCurve.EASE_OUT,
}


def hex_with_alpha(hex_color: str, alpha: int) -> str:
    opacity = max(0.0, min(1.0, alpha / 255))
    return ft.Colors.with_opacity(opacity, hex_color)


def app_gradient(is_dark: bool) -> ft.LinearGradient:
    colors = ["#302B39", "#352F40", "#3B3548"] if is_dark else ["#E9E6EF", "#EDEAF2", "#F1EEF5"]
    return ft.LinearGradient(colors=colors, begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1))


def animation(name: str = "normal", curve: ft.AnimationCurve | None = None, phase: str = "enter") -> ft.Animation:
    return ft.Animation(MOTION.get(name, MOTION["normal"]), curve or MOTION_CURVES.get(phase, ft.AnimationCurve.EASE_OUT))


def character_chat_gradient(role_id: str, is_dark: bool) -> ft.LinearGradient:
    if not is_dark:
        if role_id == "shinji":
            colors = ["#E3E7ED", "#E8EBF1", "#EEF1F5"]
        elif role_id == "asuka":
            colors = ["#F0E6EA", "#F4ECEF", "#F7F1F3"]
        else:
            colors = ["#E9E6EF", "#EDEAF2", "#F1EEF5"]
    else:
        if role_id == "shinji":
            colors = ["#38404C", "#333B47", "#2F3642"]
        elif role_id == "asuka":
            colors = ["#453941", "#3F343B", "#383038"]
        else:
            colors = ["#3B3548", "#352F40", "#302B39"]
    return ft.LinearGradient(colors=colors, begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1))


def palette(is_dark: bool) -> dict[str, str]:
    if is_dark:
        return {
            "text": "#F0EAF5",
            "text_soft": hex_with_alpha("#F0EAF5", 0xDC),
            "text_secondary": hex_with_alpha("#F0EAF5", 0x8A),
            "text_tertiary": hex_with_alpha("#F0EAF5", 0x6C),
            "card": hex_with_alpha("#FFFFFF", 0x12),
            "card_strong": hex_with_alpha("#FFFFFF", 0x1A),
            "card_border": hex_with_alpha("#FFFFFF", 0x16),
            "input": hex_with_alpha("#FFFFFF", 0x1A),
            "input_bar": hex_with_alpha("#26212F", 0x8A),
            "input_button": hex_with_alpha("#FFFFFF", 0x18),
            "input_border": hex_with_alpha("#FFFFFF", 0x20),
            "muted": hex_with_alpha("#FFFFFF", 0x12),
            "message": hex_with_alpha("#FFFFFF", 0x18),
            "message_border": hex_with_alpha("#FFFFFF", 0x12),
            "button_text_dark": "#1A1625",
        }
    return {
        "text": "#363040",
        "text_soft": hex_with_alpha("#363040", 0xDC),
        "text_secondary": hex_with_alpha("#363040", 0x92),
        "text_tertiary": hex_with_alpha("#363040", 0x70),
        "card": hex_with_alpha("#FFFFFF", 0xA8),
        "card_strong": hex_with_alpha("#FFFFFF", 0xC8),
        "card_border": hex_with_alpha("#3B334A", 0x14),
        "input": hex_with_alpha("#FFFFFF", 0xC8),
        "input_bar": hex_with_alpha("#EDEAF2", 0xD8),
        "input_button": hex_with_alpha("#FFFFFF", 0xC8),
        "input_border": hex_with_alpha("#3B334A", 0x18),
        "muted": hex_with_alpha("#3B334A", 0x0E),
        "message": hex_with_alpha("#FFFFFF", 0xC8),
        "message_border": hex_with_alpha("#3B334A", 0x16),
        "button_text_dark": "#FFFFFF",
    }


def is_dark_palette(colors: dict[str, str]) -> bool:
    return colors.get("button_text_dark") == "#1A1625"


def glass_gradient(accent_color: str, is_dark: bool, strong: bool = False) -> ft.LinearGradient:
    if is_dark:
        a1, a2 = (0x20, 0x10) if strong else (0x15, 0x08)
    else:
        a1, a2 = (0x30, 0x15) if strong else (0x25, 0x12)
    return ft.LinearGradient(
        colors=[hex_with_alpha(accent_color, a1), hex_with_alpha(accent_color, a2)],
        begin=ft.Alignment(-1, -1),
        end=ft.Alignment(1, 1),
    )


def soft_shadow(is_dark: bool, accent_color: str | None = None, level: str = "card") -> list[ft.BoxShadow]:
    if accent_color:
        color = hex_with_alpha(accent_color, 0x20 if is_dark else 0x2A)
    else:
        color = hex_with_alpha("#000000", 0x24) if is_dark else hex_with_alpha("#2E2938", 0x12)
    blur = 24 if level == "button" else 18
    y = 8 if level == "button" else 5
    return [ft.BoxShadow(spread_radius=0, blur_radius=blur, color=color, offset=ft.Offset(0, y))]


PROVIDERS = [
    ("openai", "OpenAI", "GPT 系列"),
    ("anthropic", "Anthropic", "Claude 系列"),
    ("google", "Google", "Gemini 系列"),
    ("deepseek", "DeepSeek", "DeepSeek 系列"),
    ("custom", "自定义", "自定义 API 地址"),
]

EMOTIONS = [
    ("neutral", "平静", "."),
    ("happy", "开心", "+"),
    ("sad", "难过", "-"),
    ("angry", "生气", "!"),
    ("surprised", "惊讶", "?"),
    ("thinking", "思考", "..."),
    ("scared", "害怕", "~"),
    ("embarrassed", "害羞", "*"),
    ("confused", "困惑", "?"),
]
