#include "rootlink/voice/python_persona.h"
#include <iostream>
#include <cstdlib>
int main(int argc, char** argv) {
  if (argc != 5) return 2;
  rootlink::voice::RuntimeConfig c;
  c.python_executable=argv[1]; c.python_core_entry=argv[2];
  c.role_dir=argv[3]; c.python_data_dir=argv[4];
  if (const auto* timeout = std::getenv("TEST_TIMEOUT"))
    c.persona_start_timeout_ms = c.persona_turn_timeout_ms = std::stol(timeout);
  rootlink::voice::PythonPersonaProvider core(c);
  auto status=core.start();
  if (!status.ok()) { std::cerr << status.message(); return 1; }
  if (!core.health().ok()) return 1;
  std::string text;
  while (std::getline(std::cin, text)) {
    auto answer=core.complete({{"user",text,0}}, {}, {});
    if (!answer.ok()) { std::cerr << answer.status().message(); return 1; }
    std::cout << answer.value() << std::endl;
  }
  return 0;
}
