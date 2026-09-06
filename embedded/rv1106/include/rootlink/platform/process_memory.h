#pragma once

#include <cstdint>
#include <optional>

namespace rootlink::platform {

/// 读取当前进程常驻内存（KiB）；非 Linux 或 /proc 不可用时返回 std::nullopt。
std::optional<std::uint64_t> residentMemoryKiB();
/// 读取 Linux VmHWM 峰值常驻内存；不支持的平台返回 std::nullopt。
std::optional<std::uint64_t> peakResidentMemoryKiB();

}  // namespace rootlink::platform
