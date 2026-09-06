#pragma once

#include <cstdint>
#include <fstream>
#include <string>
#include <vector>

#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/status.h"

namespace rootlink::audio {

/**
 * @brief 只写 Phase 1 PCM WAV 的流式写入器。
 *
 * open 先写 44 字节占位头；close 或析构时回填 RIFF/data 长度。由此即使调用方走
 * Ctrl+C 的正常清理路径，得到的文件也仍可被标准播放器解析。
 */
class WavWriter {
 public:
  WavWriter() = default;
  ~WavWriter();

  WavWriter(const WavWriter&) = delete;
  WavWriter& operator=(const WavWriter&) = delete;

  Status open(const std::string& path, const AudioConfig& config);
  Status writeFrame(const std::vector<std::int16_t>& frame);
  Status close();
  bool isOpen() const noexcept { return stream_.is_open(); }

 private:
  Status writeHeader(std::uint32_t data_bytes);

  std::ofstream stream_;
  AudioConfig config_;
  std::uint64_t data_bytes_{0};
};

/**
 * @brief 严格 WAV 读取器。
 *
 * 支持遍历未知 RIFF chunk，但仅接受 PCM、16 kHz、单声道、16 bit，且 data 大小
 * 必须由 640 字节整帧组成；截断或格式不符会明确拒绝。
 */
class WavReader {
 public:
  WavReader() = default;
  ~WavReader();

  WavReader(const WavReader&) = delete;
  WavReader& operator=(const WavReader&) = delete;

  Status open(const std::string& path);
  Status readFrame(std::vector<std::int16_t>& frame);
  void close() noexcept;
  bool isOpen() const noexcept { return stream_.is_open(); }
  const AudioConfig& config() const noexcept { return config_; }

 private:
  std::ifstream stream_;
  AudioConfig config_;
  std::uint64_t data_start_{0};
  std::uint64_t data_bytes_{0};
  std::uint64_t bytes_read_{0};
};

}  // namespace rootlink::audio
