#include <csignal>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/audio_session.h"
#include "rootlink/platform/process_memory.h"

// 后端由 CMake 的 ROOTLINK_AUDIO_API 互斥选择。main 保持同一套命令行和业务流程，
// 这样仿真验证与板端验收不会逐渐演变成两份行为不同的程序。
#if defined(ROOTLINK_AUDIO_API_ALSA)
#include "rootlink/audio/alsa_audio_capture.h"
#include "rootlink/audio/alsa_audio_playback.h"
#elif defined(ROOTLINK_AUDIO_API_SIMULATED)
#include "rootlink/audio/simulated_audio_capture.h"
#include "rootlink/audio/simulated_audio_playback.h"
#else
#error "No RootLink audio API was selected"
#endif

namespace {

volatile std::sig_atomic_t g_stop_requested = 0;

// POSIX/CRT 信号处理器只写 sig_atomic_t，避免在异步信号上下文调用非安全函数。
// 真正的 stop、缓冲区 close 和线程 join 都在普通控制流中完成。
void handleSignal(int) { g_stop_requested = 1; }

#if defined(ROOTLINK_AUDIO_API_ALSA)
using CaptureBackend = rootlink::audio::AlsaAudioCapture;
using PlaybackBackend = rootlink::audio::AlsaAudioPlayback;
#else
using CaptureBackend = rootlink::audio::SimulatedAudioCapture;
using PlaybackBackend = rootlink::audio::SimulatedAudioPlayback;
#endif

struct Options {
  std::string command;
  std::string input;
  std::string output;
  // 下列默认值来自 rootlink-audio.conf，经 CMake 固化进当前产物；命令行优先级更高。
  std::string capture_device{ROOTLINK_DEFAULT_CAPTURE_DEVICE};
  std::string playback_device{ROOTLINK_DEFAULT_PLAYBACK_DEVICE};
  std::size_t buffer_frames{ROOTLINK_DEFAULT_BUFFER_FRAMES};
  double duration_seconds{0.0};
  bool duration_set{false};
};

void printUsage() {
  std::cerr
      << "Usage:\n"
      << "  rootlink-audio-smoke record --output <wav> --duration <seconds> [options]\n"
      << "  rootlink-audio-smoke play --input <wav> [options]\n"
      << "  rootlink-audio-smoke loopback [--duration <seconds>] [options]\n\n"
      << "Compiled audio API: " << ROOTLINK_AUDIO_API_NAME << "\n\n"
      << "Options:\n"
      << "  --capture-device <name>   Capture device; used by ALSA (default: "
      << ROOTLINK_DEFAULT_CAPTURE_DEVICE << ")\n"
      << "  --playback-device <name>  Playback device; used by ALSA (default: "
      << ROOTLINK_DEFAULT_PLAYBACK_DEVICE << ")\n"
      << "  --buffer-frames <count>   Loopback capacity (default: "
      << ROOTLINK_DEFAULT_BUFFER_FRAMES << ")\n";
}

bool nextValue(int argc, char** argv, int& index, std::string& value, std::string& error) {
  if (index + 1 >= argc) {
    error = std::string("missing value for ") + argv[index];
    return false;
  }
  value = argv[++index];
  return true;
}

bool parseOptions(int argc, char** argv, Options& options, std::string& error) {
  if (argc < 2) {
    error = "missing command";
    return false;
  }
  options.command = argv[1];
  for (int index = 2; index < argc; ++index) {
    const std::string argument = argv[index];
    std::string value;
    if (argument == "--input") {
      if (!nextValue(argc, argv, index, options.input, error)) return false;
    } else if (argument == "--output") {
      if (!nextValue(argc, argv, index, options.output, error)) return false;
    } else if (argument == "--capture-device") {
      if (!nextValue(argc, argv, index, options.capture_device, error)) return false;
    } else if (argument == "--playback-device") {
      if (!nextValue(argc, argv, index, options.playback_device, error)) return false;
    } else if (argument == "--duration") {
      if (!nextValue(argc, argv, index, value, error)) return false;
      try {
        std::size_t consumed = 0;
        options.duration_seconds = std::stod(value, &consumed);
        if (consumed != value.size() || !std::isfinite(options.duration_seconds) ||
            options.duration_seconds >
                static_cast<double>(std::numeric_limits<std::int64_t>::max()) / 1000.0) {
          throw std::out_of_range("duration");
        }
        options.duration_set = true;
      } catch (...) {
        error = "invalid duration: " + value;
        return false;
      }
    } else if (argument == "--buffer-frames") {
      if (!nextValue(argc, argv, index, value, error)) return false;
      try {
        std::size_t consumed = 0;
        const unsigned long long parsed = std::stoull(value, &consumed);
        if (value.empty() || value.front() == '-' || consumed != value.size() || parsed == 0 ||
            parsed > std::numeric_limits<std::size_t>::max()) {
          throw std::out_of_range("size");
        }
        options.buffer_frames = static_cast<std::size_t>(parsed);
      } catch (...) {
        error = "invalid buffer frame count: " + value;
        return false;
      }
    } else {
      error = "unknown argument: " + argument;
      return false;
    }
  }

  if (options.command == "record") {
    if (options.output.empty() || !options.duration_set || options.duration_seconds <= 0) {
      error = "record requires --output and a positive --duration";
      return false;
    }
  } else if (options.command == "play") {
    if (options.input.empty()) {
      error = "play requires --input";
      return false;
    }
  } else if (options.command == "loopback") {
    if (options.duration_set && options.duration_seconds <= 0) {
      error = "loopback duration must be positive when supplied";
      return false;
    }
  } else {
    error = "unknown command: " + options.command;
    return false;
  }
  return true;
}

std::chrono::milliseconds duration(const Options& options) {
  return std::chrono::milliseconds(static_cast<std::int64_t>(options.duration_seconds * 1000.0));
}

void printDeviceStats(const rootlink::audio::AudioDeviceStats& capture,
                      const rootlink::audio::AudioDeviceStats& playback) {
  std::cout << "audio_api=" << ROOTLINK_AUDIO_API_NAME << '\n'
            << "capture_recoveries=" << capture.recoveries << '\n'
            << "playback_recoveries=" << playback.recoveries << '\n';
  const auto rss = rootlink::platform::residentMemoryKiB();
  if (rss) std::cout << "rss_kib=" << *rss << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  if (argc == 2 && (std::string(argv[1]) == "--help" || std::string(argv[1]) == "-h")) {
    printUsage();
    return 0;
  }

  Options options;
  std::string error;
  if (!parseOptions(argc, argv, options, error)) {
    std::cerr << "error: " << error << "\n\n";
    printUsage();
    return 2;
  }

  std::signal(SIGINT, handleSignal);
  std::signal(SIGTERM, handleSignal);
  const auto stopped = [] { return g_stop_requested != 0; };

  rootlink::audio::AudioConfig capture_config;
  capture_config.device = options.capture_device;
  rootlink::audio::AudioConfig playback_config;
  playback_config.device = options.playback_device;
  rootlink::audio::Status status;

  if (options.command == "record") {
    CaptureBackend capture(capture_config);
    status = rootlink::audio::recordToWav(capture, capture_config, options.output,
                                         duration(options), stopped);
    printDeviceStats(capture.stats(), {});
  } else if (options.command == "play") {
    PlaybackBackend playback(playback_config);
    status = rootlink::audio::playWav(playback, options.input, stopped);
    printDeviceStats({}, playback.stats());
  } else {
    CaptureBackend capture(capture_config);
    PlaybackBackend playback(playback_config);
    rootlink::audio::AudioSessionReport report;
    status = rootlink::audio::runLoopback(capture, playback, capture_config,
                                         options.buffer_frames, duration(options), stopped,
                                         &report);
    std::cout << "buffer_capacity_frames=" << report.buffer.capacity_frames << '\n'
              << "buffer_high_watermark_frames=" << report.buffer.high_watermark_frames << '\n'
              << "buffer_dropped_frames=" << report.buffer.dropped_frames << '\n';
    printDeviceStats(report.capture, report.playback);
  }

  if (!status.ok()) {
    std::cerr << "audio error (" << static_cast<int>(status.code()) << "): "
              << status.message() << '\n';
    return 1;
  }
  return 0;
}
