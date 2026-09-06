#include "rootlink/platform/process_memory.h"

#include <fstream>
#include <sstream>
#include <string>

namespace rootlink::platform {

static std::optional<std::uint64_t> readMemory(const char* key) {
#if defined(__linux__)
  std::ifstream status("/proc/self/status");
  std::string line;
  while (std::getline(status, line)) {
    if (line.rfind(key, 0) == 0) {
      std::istringstream input(line.substr(6));
      std::uint64_t kib = 0;
      input >> kib;
      if (input) {
        return kib;
      }
    }
  }
#else
  (void)key;
#endif
  return std::nullopt;
}

std::optional<std::uint64_t> residentMemoryKiB() { return readMemory("VmRSS:"); }
std::optional<std::uint64_t> peakResidentMemoryKiB() { return readMemory("VmHWM:"); }

}  // namespace rootlink::platform
