#include "rootlink/ui/main_view.h"
#include <SDL2/SDL.h>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <thread>
#include <vector>
#include <cstring>
int main(int argc, char** argv) {
  rootlink::voice::RuntimeConfig config;
  config.ui_backend = "sdl";
  rootlink::ui::MainView view;
  if (!view.initialize(config).ok()) return 1;
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
  close.type = SDL_QUIT;
  SDL_PushEvent(&close);
  if (view.tick(DisplayState::Error)) return 5;
  std::cout << "Five symbols and graceful SDL close passed\n";
}
