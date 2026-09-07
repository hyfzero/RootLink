// Exercise the real application supervisor without opening audio or cloud APIs.
#define main rootlinkApplicationMain
#include "../src/app/voice_main.cpp"
#undef main
#include <SDL2/SDL.h>
#include <fstream>
#include <sstream>

int main() {
  const auto path = std::filesystem::temp_directory_path() /
      ("rootlink-reset-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".conf");
  {
    std::ofstream config(path);
    // Valid config but incompatible audio backend: fail inside each worker,
    // after UI initialization, before opening any device or personality data.
    config << "TARGET=simulator\nUI_BACKEND=sdl\nSERVICE_MODE=mock\nAUDIO_API="
           << (std::string(ROOTLINK_AUDIO_API_NAME) == "alsa" ? "simulated" : "alsa") << '\n';
  }
  std::ostringstream output;
  auto* old = std::cout.rdbuf(output.rdbuf());
  std::thread taps([] {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (g_display_state.read() != rootlink::ui::DisplayState::Error &&
           std::chrono::steady_clock::now() < deadline)
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    for (int n = 0; n < 3; ++n) {
      SDL_Event tap{};
      tap.type = SDL_MOUSEBUTTONUP;
      tap.button.button = SDL_BUTTON_LEFT;
      SDL_PushEvent(&tap);
      std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    SDL_Event close{}; close.type = SDL_QUIT; SDL_PushEvent(&close);
  });
  std::string executable = "rootlink-voice", command = "voice", option = "--config", file = path.string();
  char* argv[] = {executable.data(), command.data(), option.data(), file.data()};
  const int result = rootlinkApplicationMain(4, argv);
  taps.join();
  std::cout.rdbuf(old);
  std::filesystem::remove(path);
  const auto log = output.str();
  size_t resets = 0, pos = 0;
  while ((pos = log.find("reset=ready;", pos)) != std::string::npos) { ++resets; ++pos; }
  if (result == 0 || resets != 3) {
    std::cerr << "Expected three user-triggered worker restarts; got " << resets << '\n';
    return 1;
  }
  std::cout << "Three failed-runtime resets and window close passed\n";
}
