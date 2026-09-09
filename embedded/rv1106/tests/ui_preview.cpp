#include "rootlink/ui/main_view.h"
#include <SDL2/SDL.h>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <thread>
#include <vector>
#include <cstring>
#include "lvgl.h"
LV_FONT_DECLARE(ui_font_dialogue16);
int main(int argc, char** argv) {
  rootlink::voice::RuntimeConfig config;
  config.ui_backend = "sdl";
  rootlink::ui::MainView view;
  if (!view.initialize(config).ok()) return 1;
  // A cmap match alone is insufficient: disabled compressed-font support can
  // leave every character rendered as a box despite successful layout tests.
  for (const auto codepoint : {0x4e2dU, 0x6587U, 0x7267U, 0x6fd1U, 0x3042U, 0x41U}) {
    lv_font_glyph_dsc_t glyph{};
    if (!lv_font_get_glyph_dsc(&ui_font_dialogue16, &glyph, codepoint, 0) ||
        glyph.is_placeholder || !glyph.box_w || !glyph.box_h) return 17;
    auto* buffer = lv_draw_buf_create(glyph.box_w, glyph.box_h, LV_COLOR_FORMAT_A8, 0);
    if (!buffer) return 18;
    const bool decoded = lv_font_get_glyph_bitmap(&glyph, buffer) != nullptr;
    lv_draw_buf_destroy(buffer);
    if (!decoded) return 19;
  }
  view.setDialogue("牧瀬紅莉栖：こんにちは。中文对白测试。\n这是第二行。");
  for (int tick = 0; tick < 8; ++tick) {
    if (!view.tick(rootlink::ui::DisplayState::Idle)) return 9;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  auto* dialogue_window = SDL_GetWindowFromID(1);
  auto* dialogue_renderer = SDL_GetRenderer(dialogue_window);
  auto* dialogue_surface = SDL_CreateRGBSurfaceWithFormat(0, 320, 240, 32,
                                                           SDL_PIXELFORMAT_ARGB8888);
  if (!dialogue_surface || SDL_RenderReadPixels(dialogue_renderer, nullptr,
      dialogue_surface->format->format, dialogue_surface->pixels,
      dialogue_surface->pitch) != 0) return 10;
  std::vector<unsigned char> dialogue_pixels(
      static_cast<unsigned char*>(dialogue_surface->pixels),
      static_cast<unsigned char*>(dialogue_surface->pixels) +
      dialogue_surface->pitch * dialogue_surface->h);
  if (argc == 2) {
    std::filesystem::create_directories(argv[1]);
    if (SDL_SaveBMP(dialogue_surface,
        (std::filesystem::path(argv[1]) / "dialogue.bmp").string().c_str()) != 0) return 11;
  }
  view.setDialogue("这是一段较长的中文对白，用于确认固定对话框会自动滚动到最新内容，且不会破坏 UTF-8 字符。ABCDEFGHIJKLMNOPQRSTUVWXYZ。这里继续追加内容以覆盖多行并触发纵向滚动。重复测试中文显示和滚动行为，确保每次更新都安全。再追加一段文本，验证长句不会越界。最后保留足够的行数让对话框滚动到底部。");
  for (int tick = 0; tick < 12; ++tick) {
    view.tick(rootlink::ui::DisplayState::Speaking);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  if (SDL_RenderReadPixels(dialogue_renderer, nullptr, dialogue_surface->format->format,
                          dialogue_surface->pixels, dialogue_surface->pitch) != 0) return 16;
  if (argc == 2 && SDL_SaveBMP(dialogue_surface,
      (std::filesystem::path(argv[1]) / "dialogue-long.bmp").string().c_str()) != 0) return 15;
  view.setDialogue("");
  for (int tick = 0; tick < 5; ++tick) {
    view.tick(rootlink::ui::DisplayState::Speaking);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  if (SDL_RenderReadPixels(dialogue_renderer, nullptr, dialogue_surface->format->format,
                           dialogue_surface->pixels, dialogue_surface->pitch) != 0) return 12;
  const auto lower_offset = dialogue_surface->pitch * (dialogue_surface->h / 2);
  if (std::memcmp(static_cast<unsigned char*>(dialogue_surface->pixels) + lower_offset,
                  dialogue_pixels.data() + lower_offset,
                  dialogue_pixels.size() - lower_offset) == 0)
    return 13;
  if (argc == 2 && SDL_SaveBMP(dialogue_surface,
      (std::filesystem::path(argv[1]) / "dialogue-cleared.bmp").string().c_str()) != 0) return 14;
  SDL_FreeSurface(dialogue_surface);
  using rootlink::ui::DisplayState;
  const DisplayState states[] = {DisplayState::Idle, DisplayState::Listening,
      DisplayState::Thinking, DisplayState::Speaking, DisplayState::Error};
  const char* names[] = {"idle", "listening", "thinking", "speaking", "error"};
  std::vector<unsigned char> idle_pixels;
  for (int index = 0; index < 5; ++index) {
    for (int tick = 0; tick < 25; ++tick) {
      if (!view.tick(states[index])) return 2;
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    {
      auto* window = SDL_GetWindowFromID(1);
      auto* renderer = SDL_GetRenderer(window);
      auto* surface = SDL_CreateRGBSurfaceWithFormat(0, 320, 240, 32, SDL_PIXELFORMAT_ARGB8888);
      if (!surface || SDL_RenderReadPixels(renderer, nullptr, surface->format->format,
                                           surface->pixels, surface->pitch) != 0) return 3;
      if (index == 0) {
        auto* bytes = static_cast<unsigned char*>(surface->pixels);
        idle_pixels.assign(bytes, bytes + surface->pitch * surface->h);
      }
      int result = 0;
      if (argc == 2) {
        std::filesystem::create_directories(argv[1]);
        const auto path = std::filesystem::path(argv[1]) / (std::string(names[index]) + ".bmp");
        result = SDL_SaveBMP(surface, path.string().c_str());
      }
      for (int tick = 0; tick < 5; ++tick) {
        view.tick(DisplayState::Idle);
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
      if (SDL_RenderReadPixels(renderer, nullptr, surface->format->format,
                               surface->pixels, surface->pitch) != 0 ||
          std::memcmp(surface->pixels, idle_pixels.data(), idle_pixels.size()) != 0) return 6;
      SDL_FreeSurface(surface);
      if (result != 0) return 4;
    }
  }
  SDL_Event close{};
  SDL_Event tap{};
  tap.type = SDL_MOUSEBUTTONUP;
  tap.button.button = SDL_BUTTON_LEFT;
  for (auto state : states) {
    if (view.takeResetRequest()) return 7;
    SDL_PushEvent(&tap);
    SDL_PushEvent(&tap); // duplicate events coalesce to one reset
    if (!view.tick(state) || !view.takeResetRequest() || view.takeResetRequest()) return 8;
  }
  close.type = SDL_QUIT;
  SDL_PushEvent(&close);
  if (view.tick(DisplayState::Error)) return 5;
  std::cout << "Five symbols and graceful SDL close passed\n";
}
