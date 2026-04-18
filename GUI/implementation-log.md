# Figma Mobile UI Implementation Log

## Source

- Figma Make file key: `g7EB8aqSZGjbIQO0j42Ax0`
- Target: mobile-first Flet UI in root `GUI/`
- Scope: UI layer and demo harness only. No `SessionManager`, LLM, Brain storage, or API-key persistence calls.

## Resource Mapping

- Amadeus avatar: `resource/amadues.png`
- Amadeus standing image: `resource/amadues_Full_profile.png`
- Shinji avatar: `resource/Shinji.png`
- Shinji standing image: `resource/Shinji_Ikari_full_profile.png`
- Asuka avatar: `resource/Asuka.png`
- Asuka standing image: `resource/Asuka_full_profile.png`

## Implementation Notes

- Created root package `GUI/` and left existing `src/GUI` untouched.
- Implemented a centered 428px mobile canvas for desktop compatibility.
- Implemented home, normal chat, immersive chat, settings, and create-character wizard screens.
- Added callback/provider interfaces so the control layer can drive UI without UI code importing core runtime modules.
- Added a voice-button callback (`on_voice_requested`) for the Figma chat input microphone action.
- Flet approximates Figma CSS blur, Tailwind gradients, and motion animations with native gradients, cards, and state transitions.

## Color and Motion Revision

- Source check: `https://alike-board-73939924.figma.site/` resolves to a Figma Make generated bundle for the same design source.
- Reworked visual tokens toward the Figma mobile source: dark gradient `#1A1625 -> #1E1A2E -> #2A2438`, light gradient `#E8E6F0 -> #EBE9F3 -> #EFEDF7`, lower-opacity card/message/input layers, soft borders, and subtle shadows.
- Reduced saturated role-color surfaces by using low-alpha accent glass gradients for role cards, selector cards, dialogue cards, and message bubbles.
- Added motion tokens (`fast=180ms`, `normal=300ms`, `page=560ms`) and reused them across tap feedback, page switching, role selection, chat mode switching, message refresh, immersive portrait/dialogue entry, typing dots, and create-wizard step transitions.
- Kept `CompanionUICallback` and `CompanionUIView` semantics unchanged. All control-layer integration still flows through callbacks/provider methods.

## Color Root Cause and Fix

- Root cause: many colors were written as `#RRGGBBAA`, but Flet 8-digit hex follows `#AARRGGBB`. This made transparency and channels parse incorrectly, causing obvious hue/brightness drift from Figma.
- Fix: switched alpha handling to `ft.Colors.with_opacity(...)` through `hex_with_alpha()` and removed remaining `#RRGGBBAA` usages in theme/component/view code.
- Updated immersive and overlay color concatenations (e.g. `${accent}33`) to use the same safe alpha conversion path.

## Test Runs

- 2026-04-17 23:20:25 +08:00: `python -m compileall -q GUI` passed.
- 2026-04-17 23:20:25 +08:00: `python -m compileall -q GUI src` passed.
- 2026-04-17 23:20:25 +08:00: import and construction smoke test passed.
- 2026-04-17 23:20:25 +08:00: page switch smoke test passed for settings, create wizard steps 1-5, chat, immersive mode, normal mode, send, and clear chat.
- 2026-04-17 23:20:25 +08:00: `git diff --check` passed.
- 2026-04-17 23:20:25 +08:00: final `python -B -` smoke test passed without writing bytecode.
- 2026-04-17 23:48:31 +08:00: `.\.venv\Scripts\python.exe -m compileall -q GUI` passed.
- 2026-04-17 23:48:31 +08:00: `.\.venv\Scripts\python.exe -m compileall -q GUI src` passed.
- 2026-04-17 23:48:31 +08:00: import and construction smoke test passed.
- 2026-04-17 23:48:31 +08:00: direct script-path import smoke test passed with `runpy.run_path('GUI/app.py', run_name='not_main')`.
- 2026-04-17 23:48:31 +08:00: page, chat mode, typing indicator, send, clear-chat, settings, and create-wizard smoke test passed.
- 2026-04-17 23:48:31 +08:00: `git diff --check -- GUI` passed.
- 2026-04-17 23:49:17 +08:00: final compile tests were rerun serially after a parallel `compileall` pycache write race on Windows; serial `compileall` for `GUI` and `GUI src` passed.
- 2026-04-17 23:55:41 +08:00: alpha-format correction completed (`#RRGGBBAA` -> Flet-compatible opacity), then reran `compileall`, import smoke, script-path smoke, chat-mode/typing smoke, and `git diff --check -- GUI`; all passed.

## Manual Run

- Command: `python -m GUI.app`
- Expected behavior: launches a Flet window with a centered 428px mobile canvas. The app remains open until the window is closed.

## Motion Smoothing Revision (Figma-aligned)

- Rebuilt `GUI/views.py` from scratch after file corruption and re-applied the full mobile-first flow: Home, Chat (normal + immersive), Settings, Create wizard.
- Home now uses repeatable stagger entry on every return with `0/80/160/240/320/400ms`.
- Chat updates:
  - `normal`/`immersive` switch keeps `300ms` transition.
  - new appended message bubbles use dedicated entry animation (`opacity + slight Y offset`, `260ms`).
  - immersive portrait uses delayed entry (`600ms`, `200ms delay`) and dialogue box uses delayed entry (`500ms`, `400ms delay`).
  - typing indicator switched to localized animated dots component (`TypingDots`) so only the indicator updates.
- Settings and Create pages now apply section-level staggered entry, and Create step transitions use direction-aware horizontal slide + opacity (`300ms`).
- Unified motion primitives:
  - `MOTION` tokens: `fast=180`, `normal=300`, `medium=500`, `slow=600`, `message=260`, `stagger=80`.
  - curve mapping in `theme.py`: enter `FAST_OUT_SLOWIN`, exit `EASE_IN_OUT`, press `EASE_OUT`.
- Data/text cleanup:
  - rewrote `GUI/theme.py` and `GUI/interfaces.py` to remove corrupted mojibake text and keep stable defaults.
  - rewrote `GUI/app.py` demo callback text and kept direct script-path import compatibility.

## Test Runs (This Revision)

- 2026-04-18 00:29:50 +08:00: `.\.venv\Scripts\python.exe -m compileall -q GUI` passed.
- 2026-04-18 00:29:50 +08:00: `.\.venv\Scripts\python.exe -m compileall -q GUI src` passed.
- 2026-04-18 00:29:50 +08:00: `.\.venv\Scripts\python.exe -B -c "from GUI import CompanionAppView, DemoCallback; CompanionAppView(callback=DemoCallback()); print('ok')"` passed (`ok`).
- 2026-04-18 00:29:50 +08:00: `.\.venv\Scripts\python.exe -B -c "import runpy; runpy.run_path('GUI/app.py', run_name='not_main')"` passed.
- 2026-04-18 00:29:50 +08:00: `git diff --check -- GUI` passed.
- 2026-04-18 00:34:26 +08:00: fixed Flet compatibility in immersive layout (`ft.alignment.bottom_center` -> `ft.Alignment(0, 1)`), then reran `compileall`, import smoke, script-path smoke, and state-transition smoke (`home/settings/create/chat`, mode switches, typing, append, clear) and all passed.

## Chinese UI and Chat Layout Revision

- Source check: Figma Make `g7EB8aqSZGjbIQO0j42Ax0` was used as the primary source for Chinese copy, the compact icon chat-mode switch, and immersive chat layout. The published `figma.site` URL still resolves to the JavaScript shell and is treated as same-source confirmation only.
- Localized visible demo/UI copy across the root `GUI/` package:
  - role data, tags, status text, recent-chat text, settings labels, create-wizard labels, input hints, memory editor labels, and demo reply text are now Chinese.
  - internal ids and public control-layer values remain stable (`normal`, `immersive`, provider ids, template ids, etc.).
- Chat mode switch now uses two icon-only buttons: chat bubble for regular chat and sparkles for immersive mode, with Chinese tooltips.
- Immersive chat now uses a portrait stage plus a fixed lower dialogue area instead of a full-page overlay. The input bar remains separated at the bottom.
- Added start-chat motion:
  - all home chat entry points route through `_begin_open_chat`.
  - selected role card briefly scales/fades before opening chat.
  - chat header, body, and input bar use staggered first-entry motion.
- Tests:
  - 2026-04-18 00:55 +08:00: `.\.venv\Scripts\python.exe -m compileall -q GUI` passed after rerun outside the default sandbox because Windows blocked pycache temp writes.
  - 2026-04-18 00:55 +08:00: `.\.venv\Scripts\python.exe -m compileall -q GUI src` passed.
  - 2026-04-18 00:55 +08:00: import and construction smoke test passed.
  - 2026-04-18 00:55 +08:00: direct script-path smoke test with `runpy.run_path('GUI/app.py', run_name='not_main')` passed.
  - 2026-04-18 00:55 +08:00: state smoke test for settings/create/chat mode/message APIs passed.
  - 2026-04-18 00:55 +08:00: `git diff --check -- GUI` passed.
  - 2026-04-18 01:02 +08:00: after final Chinese label cleanup, `python -B` syntax/import smoke tests and `git diff --check -- GUI` passed.
