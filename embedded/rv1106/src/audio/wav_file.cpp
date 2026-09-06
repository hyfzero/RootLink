#include "rootlink/audio/wav_file.h"

#include <array>
#include <cstring>
#include <limits>

namespace rootlink::audio {
namespace {

// WAV 明确规定多字节整数为 little-endian。逐字节编码避免依赖主机端序，也让
// x86 主机测试与 little-endian ARM 板端生成完全相同的文件头。
void writeLe16(std::ostream& output, std::uint16_t value) {
  const std::array<char, 2> bytes{static_cast<char>(value & 0xffU),
                                  static_cast<char>((value >> 8U) & 0xffU)};
  output.write(bytes.data(), bytes.size());
}

void writeLe32(std::ostream& output, std::uint32_t value) {
  const std::array<char, 4> bytes{static_cast<char>(value & 0xffU),
                                  static_cast<char>((value >> 8U) & 0xffU),
                                  static_cast<char>((value >> 16U) & 0xffU),
                                  static_cast<char>((value >> 24U) & 0xffU)};
  output.write(bytes.data(), bytes.size());
}

bool readBytes(std::istream& input, char* data, std::size_t size) {
  input.read(data, static_cast<std::streamsize>(size));
  return input.good();
}

bool readLe16(std::istream& input, std::uint16_t& value) {
  std::array<unsigned char, 2> bytes{};
  if (!readBytes(input, reinterpret_cast<char*>(bytes.data()), bytes.size())) return false;
  value = static_cast<std::uint16_t>(bytes[0]) |
          static_cast<std::uint16_t>(bytes[1] << 8U);
  return true;
}

bool readLe32(std::istream& input, std::uint32_t& value) {
  std::array<unsigned char, 4> bytes{};
  if (!readBytes(input, reinterpret_cast<char*>(bytes.data()), bytes.size())) return false;
  value = static_cast<std::uint32_t>(bytes[0]) |
          (static_cast<std::uint32_t>(bytes[1]) << 8U) |
          (static_cast<std::uint32_t>(bytes[2]) << 16U) |
          (static_cast<std::uint32_t>(bytes[3]) << 24U);
  return true;
}

bool tagEquals(const std::array<char, 4>& tag, const char* expected) {
  return std::memcmp(tag.data(), expected, tag.size()) == 0;
}

Status malformed(const std::string& detail) {
  return {AudioError::kUnsupportedFormat, "invalid WAV file: " + detail};
}

}  // namespace

WavWriter::~WavWriter() { (void)close(); }

Status WavWriter::open(const std::string& path, const AudioConfig& config) {
  if (stream_.is_open()) return {AudioError::kInvalidState, "WAV writer is already open"};
  const Status valid = config.validate();
  if (!valid.ok()) return valid;
  stream_.open(path, std::ios::binary | std::ios::trunc);
  if (!stream_) return {AudioError::kIoError, "cannot open WAV output: " + path};
  config_ = config;
  data_bytes_ = 0;
  return writeHeader(0);
}

Status WavWriter::writeHeader(std::uint32_t data_bytes) {
  // 标准 PCM WAV 头固定为 44 字节：RIFF(12) + fmt(24) + data header(8)。
  // open 时 data_bytes=0 写占位头，close 时回到文件开头修正两个长度字段。
  stream_.seekp(0, std::ios::beg);
  stream_.write("RIFF", 4);
  writeLe32(stream_, 36U + data_bytes);
  stream_.write("WAVEfmt ", 8);
  writeLe32(stream_, 16);
  writeLe16(stream_, 1);
  writeLe16(stream_, config_.channels);
  writeLe32(stream_, config_.sample_rate);
  const std::uint32_t byte_rate =
      config_.sample_rate * config_.channels * config_.bits_per_sample / 8U;
  writeLe32(stream_, byte_rate);
  writeLe16(stream_, static_cast<std::uint16_t>(config_.channels * config_.bits_per_sample / 8U));
  writeLe16(stream_, config_.bits_per_sample);
  stream_.write("data", 4);
  writeLe32(stream_, data_bytes);
  if (!stream_) return {AudioError::kIoError, "failed to write WAV header"};
  return Status::okStatus();
}

Status WavWriter::writeFrame(const std::vector<std::int16_t>& frame) {
  if (!stream_.is_open()) return {AudioError::kInvalidState, "WAV writer is not open"};
  if (frame.size() != config_.samplesPerFrame()) {
    return {AudioError::kInvalidArgument, "WAV frame must contain exactly 320 samples"};
  }
  if (data_bytes_ + config_.bytesPerFrame() >
      std::numeric_limits<std::uint32_t>::max() - 36U) {
    return {AudioError::kIoError, "WAV data exceeds the 4 GiB RIFF limit"};
  }
  stream_.write(reinterpret_cast<const char*>(frame.data()),
                static_cast<std::streamsize>(config_.bytesPerFrame()));
  if (!stream_) return {AudioError::kIoError, "failed to write WAV audio data"};
  data_bytes_ += config_.bytesPerFrame();
  return Status::okStatus();
}

Status WavWriter::close() {
  if (!stream_.is_open()) return Status::okStatus();
  Status result = writeHeader(static_cast<std::uint32_t>(data_bytes_));
  stream_.flush();
  if (!stream_ && result.ok()) result = {AudioError::kIoError, "failed to finalize WAV file"};
  stream_.close();
  return result;
}

WavReader::~WavReader() { close(); }

Status WavReader::open(const std::string& path) {
  if (stream_.is_open()) return {AudioError::kInvalidState, "WAV reader is already open"};
  stream_.open(path, std::ios::binary);
  if (!stream_) return {AudioError::kIoError, "cannot open WAV input: " + path};

  std::array<char, 4> tag{};
  std::uint32_t riff_size = 0;
  if (!readBytes(stream_, tag.data(), 4) || !tagEquals(tag, "RIFF") ||
      !readLe32(stream_, riff_size) || !readBytes(stream_, tag.data(), 4) ||
      !tagEquals(tag, "WAVE")) {
    close();
    return malformed("missing RIFF/WAVE header");
  }

  bool have_fmt = false;
  bool have_data = false;
  std::uint16_t format = 0, channels = 0, block_align = 0, bits = 0;
  std::uint32_t rate = 0, byte_rate = 0;
  while (stream_ && !have_data) {
    // RIFF 允许在 fmt/data 之间插入 LIST、JUNK 等未知块；安全跳过它们，而不是
    // 错误地假设 data 一定从第 44 字节开始。奇数大小块还包含一个对齐填充字节。
    std::uint32_t chunk_size = 0;
    if (!readBytes(stream_, tag.data(), 4) || !readLe32(stream_, chunk_size)) break;
    if (tagEquals(tag, "fmt ")) {
      if (chunk_size < 16 || !readLe16(stream_, format) || !readLe16(stream_, channels) ||
          !readLe32(stream_, rate) || !readLe32(stream_, byte_rate) ||
          !readLe16(stream_, block_align) || !readLe16(stream_, bits)) {
        close();
        return malformed("truncated fmt chunk");
      }
      if (chunk_size > 16) stream_.seekg(static_cast<std::streamoff>(chunk_size - 16), std::ios::cur);
      have_fmt = true;
    } else if (tagEquals(tag, "data")) {
      data_start_ = static_cast<std::uint64_t>(stream_.tellg());
      data_bytes_ = chunk_size;
      have_data = true;
    } else {
      stream_.seekg(static_cast<std::streamoff>(chunk_size), std::ios::cur);
    }
    if (!have_data && (chunk_size & 1U)) stream_.seekg(1, std::ios::cur);
  }

  config_ = {};
  config_.device = "wav";
  config_.sample_rate = rate;
  config_.channels = channels;
  config_.bits_per_sample = bits;
  // format=1 表示无压缩 PCM；block_align/byte_rate 的交叉检查能捕获表面采样率正确、
  // 实际布局却不一致的损坏文件。
  if (!have_fmt || !have_data || format != 1 || block_align != 2 || byte_rate != 32000 ||
      !config_.validate().ok()) {
    close();
    return malformed("only 16000 Hz mono PCM16 is supported");
  }
  if (data_bytes_ % config_.bytesPerFrame() != 0) {
    close();
    return malformed("data length is not a whole 20 ms frame");
  }

  // data chunk 声明长度可能超出实际文件；在开始播放前一次性拒绝，避免中途才出声后报错。
  stream_.seekg(0, std::ios::end);
  const auto file_size = stream_.tellg();
  if (file_size < 0 || data_start_ + data_bytes_ > static_cast<std::uint64_t>(file_size)) {
    close();
    return malformed("declared audio data is truncated");
  }
  stream_.clear();
  stream_.seekg(static_cast<std::streamoff>(data_start_), std::ios::beg);
  bytes_read_ = 0;
  return Status::okStatus();
}

Status WavReader::readFrame(std::vector<std::int16_t>& frame) {
  if (!stream_.is_open()) return {AudioError::kInvalidState, "WAV reader is not open"};
  if (bytes_read_ == data_bytes_) return {AudioError::kEndOfStream, "end of WAV audio data"};
  frame.resize(config_.samplesPerFrame());
  stream_.read(reinterpret_cast<char*>(frame.data()),
               static_cast<std::streamsize>(config_.bytesPerFrame()));
  if (!stream_) return {AudioError::kIoError, "WAV audio data is truncated"};
  bytes_read_ += config_.bytesPerFrame();
  return Status::okStatus();
}

void WavReader::close() noexcept {
  if (stream_.is_open()) stream_.close();
  data_start_ = data_bytes_ = bytes_read_ = 0;
}

}  // namespace rootlink::audio
