"""Figma-derived visual tokens for the mobile companion UI."""

from __future__ import annotations

import flet as ft

MOBILE_WIDTH = 428

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
    colors = ["#1A1625", "#1E1A2E", "#2A2438"] if is_dark else ["#E8E6F0", "#EBE9F3", "#EFEDF7"]
    return ft.LinearGradient(colors=colors, begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1))


def animation(name: str = "normal", curve: ft.AnimationCurve | None = None, phase: str = "enter") -> ft.Animation:
    return ft.Animation(MOTION.get(name, MOTION["normal"]), curve or MOTION_CURVES.get(phase, ft.AnimationCurve.EASE_OUT))


def character_chat_gradient(role_id: str, is_dark: bool) -> ft.LinearGradient:
    if not is_dark:
        if role_id == "shinji":
            colors = ["#DFE3E9", "#E3E7ED", "#E8ECF2"]
        elif role_id == "asuka":
            colors = ["#F0E6E8", "#F3E9EB", "#F7EDEF"]
        else:
            colors = ["#E8E6F0", "#EBE9F3", "#EFEDF7"]
    else:
        if role_id == "shinji":
            colors = ["#1E2430", "#1A1E28", "#16181F"]
        elif role_id == "asuka":
            colors = ["#2E2228", "#251E22", "#1D181C"]
        else:
            colors = ["#2A2438", "#1E1A2E", "#1A1625"]
    return ft.LinearGradient(colors=colors, begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1))


def palette(is_dark: bool) -> dict[str, str]:
    if is_dark:
        return {
            "text": "#FFFFFF",
            "text_soft": hex_with_alpha("#FFFFFF", 0xE6),
            "text_secondary": hex_with_alpha("#FFFFFF", 0x80),
            "text_tertiary": hex_with_alpha("#FFFFFF", 0x66),
            "card": hex_with_alpha("#FFFFFF", 0x0D),
            "card_strong": hex_with_alpha("#FFFFFF", 0x14),
            "card_border": hex_with_alpha("#FFFFFF", 0x0D),
            "input": hex_with_alpha("#FFFFFF", 0x14),
            "input_border": hex_with_alpha("#FFFFFF", 0x1A),
            "muted": hex_with_alpha("#FFFFFF", 0x0D),
            "message": hex_with_alpha("#FFFFFF", 0x14),
            "message_border": hex_with_alpha("#FFFFFF", 0x0D),
            "button_text_dark": "#1A1625",
        }
    return {
        "text": "#1F1B2E",
        "text_soft": hex_with_alpha("#1F1B2E", 0xE6),
        "text_secondary": hex_with_alpha("#1F1B2E", 0xA6),
        "text_tertiary": hex_with_alpha("#1F1B2E", 0x73),
        "card": hex_with_alpha("#FFFFFF", 0xCC),
        "card_strong": hex_with_alpha("#FFFFFF", 0xE6),
        "card_border": hex_with_alpha("#1F1B2E", 0x14),
        "input": hex_with_alpha("#FFFFFF", 0xE6),
        "input_border": hex_with_alpha("#1F1B2E", 0x26),
        "muted": hex_with_alpha("#1F1B2E", 0x0D),
        "message": hex_with_alpha("#FFFFFF", 0xE6),
        "message_border": hex_with_alpha("#1F1B2E", 0x1A),
        "button_text_dark": "#FFFFFF",
    }


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
        color = hex_with_alpha(accent_color, 0x24 if is_dark else 0x34)
    else:
        color = hex_with_alpha("#000000", 0x33) if is_dark else hex_with_alpha("#1F1B2E", 0x1A)
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
