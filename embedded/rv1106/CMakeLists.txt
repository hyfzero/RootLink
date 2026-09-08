cmake_minimum_required(VERSION 3.18)

if(DEFINED ROOTLINK_TARGET)
  include(cmake/build-target.cmake)
endif()
project(rootlink_rv1106_voice VERSION 0.2.0 LANGUAGES C CXX)

if(ROOTLINK_TARGET STREQUAL "ubuntu")
  if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR CMAKE_CROSSCOMPILING OR
     NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64|i[3-6]86)$")
    message(FATAL_ERROR "The ubuntu target requires native x86 Ubuntu/Linux (Windows: run CMake inside WSL).")
  endif()
endif()

set(ROOTLINK_UI_BACKEND "none" CACHE STRING "none, sdl or fbdev")
set(ROOTLINK_LVGL_SOURCE_DIR "" CACHE PATH "External DeskBot LVGL source directory")
if(NOT ROOTLINK_UI_BACKEND MATCHES "^(none|sdl|fbdev)$")
  message(FATAL_ERROR "Unsupported ROOTLINK_UI_BACKEND")
endif()
add_library(rootlink_main_view src/ui/main_view.cpp)
target_compile_features(rootlink_main_view PUBLIC cxx_std_17)
target_include_directories(rootlink_main_view PUBLIC include)
target_compile_definitions(rootlink_main_view PRIVATE ROOTLINK_UI_BACKEND="${ROOTLINK_UI_BACKEND}")
if(NOT ROOTLINK_UI_BACKEND STREQUAL "none")
  if(NOT EXISTS "${ROOTLINK_LVGL_SOURCE_DIR}/lvgl.h")
    message(FATAL_ERROR "Set ROOTLINK_LVGL_SOURCE_DIR to DeskBot_demo/lvgl")
  endif()
  set(LV_CONF_PATH "${CMAKE_CURRENT_SOURCE_DIR}/config/lv_conf.h" CACHE STRING "" FORCE)
  set(LV_CONF_BUILD_DISABLE_EXAMPLES ON CACHE BOOL "" FORCE)
  set(LV_CONF_BUILD_DISABLE_DEMOS ON CACHE BOOL "" FORCE)
  set(LV_CONF_BUILD_DISABLE_THORVG_INTERNAL ON CACHE BOOL "" FORCE)
  add_subdirectory("${ROOTLINK_LVGL_SOURCE_DIR}" "${CMAKE_BINARY_DIR}/lvgl")
  target_link_libraries(rootlink_main_view PUBLIC lvgl)
  target_compile_definitions(rootlink_main_view PRIVATE ROOTLINK_UI_ENABLED=1)
  if(ROOTLINK_UI_BACKEND STREQUAL "sdl")
    find_package(SDL2 REQUIRED)
    target_link_libraries(lvgl PUBLIC SDL2::SDL2)
    target_compile_definitions(lvgl PUBLIC ROOTLINK_LV_SDL=1)
  else()
    target_compile_definitions(lvgl PUBLIC ROOTLINK_LV_SDL=0)
  endif()
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(MSVC)
  add_compile_options(/utf-8)
endif()

# 音频 API 是互斥选择：同一个 smoke 可执行文件只链接一种后端，避免把板端
# ALSA 依赖带进 Windows/CI 仿真构建。保留旧的 ENABLE_ALSA 开关作为兼容入口。
if(NOT DEFINED ROOTLINK_AUDIO_API)
  if(DEFINED ROOTLINK_AUDIO_ENABLE_ALSA)
    if(ROOTLINK_AUDIO_ENABLE_ALSA)
      set(ROOTLINK_AUDIO_API "alsa")
    else()
      set(ROOTLINK_AUDIO_API "none")
    endif()
  elseif(WIN32)
    set(ROOTLINK_AUDIO_API "simulated")
  else()
    set(ROOTLINK_AUDIO_API "alsa")
  endif()
endif()
set(ROOTLINK_AUDIO_API "${ROOTLINK_AUDIO_API}" CACHE STRING
    "Audio backend: simulated, alsa, or none")
set_property(CACHE ROOTLINK_AUDIO_API PROPERTY STRINGS simulated alsa none)
string(TOLOWER "${ROOTLINK_AUDIO_API}" ROOTLINK_AUDIO_API)
if(NOT ROOTLINK_AUDIO_API MATCHES "^(simulated|alsa|none)$")
  message(FATAL_ERROR
    "ROOTLINK_AUDIO_API must be one of: simulated, alsa, none (got '${ROOTLINK_AUDIO_API}')")
endif()

if(ROOTLINK_AUDIO_API STREQUAL "none")
  set(_rootlink_cli_default OFF)
else()
  set(_rootlink_cli_default ON)
endif()
option(ROOTLINK_AUDIO_BUILD_CLI "Build the audio smoke-test CLI" ${_rootlink_cli_default})
option(ROOTLINK_VOICE_BUILD_CLI "Build the Stage 2 voice CLI" ${_rootlink_cli_default})

# 服务后端也在编译期互斥选择。mock 不依赖网络库，适合 Windows/CI；curl 是
# 开发板和 Linux 真云端构建，避免把不需要的 TLS 依赖带入纯逻辑测试。
set(ROOTLINK_SERVICE_API "mock" CACHE STRING "Service backend: mock or curl")
set_property(CACHE ROOTLINK_SERVICE_API PROPERTY STRINGS mock curl)
string(TOLOWER "${ROOTLINK_SERVICE_API}" ROOTLINK_SERVICE_API)
if(NOT ROOTLINK_SERVICE_API MATCHES "^(mock|curl)$")
  message(FATAL_ERROR "ROOTLINK_SERVICE_API must be mock or curl")
endif()

# 这些值只决定 CLI 的初始值；用户仍可用命令行参数逐次覆盖。协议格式本身不可配置。
set(ROOTLINK_DEFAULT_CAPTURE_DEVICE "default" CACHE STRING "Default ALSA capture device")
set(ROOTLINK_DEFAULT_PLAYBACK_DEVICE "default" CACHE STRING "Default ALSA playback device")
set(ROOTLINK_DEFAULT_BUFFER_FRAMES "100" CACHE STRING "Default loopback capacity in frames")
if(ROOTLINK_DEFAULT_CAPTURE_DEVICE MATCHES "[\";]" OR
   ROOTLINK_DEFAULT_PLAYBACK_DEVICE MATCHES "[\";]")
  message(FATAL_ERROR "Default audio device names cannot contain a quote or semicolon")
endif()
if(NOT ROOTLINK_DEFAULT_BUFFER_FRAMES MATCHES "^[1-9][0-9]*$")
  message(FATAL_ERROR "ROOTLINK_DEFAULT_BUFFER_FRAMES must be a positive integer")
endif()

if(CMAKE_CROSSCOMPILING AND NOT DEFINED BUILD_TESTING)
  set(BUILD_TESTING OFF CACHE BOOL "Build tests" FORCE)
endif()
include(CTest)

find_package(Threads REQUIRED)

add_library(rootlink_audio_core STATIC
  src/audio/audio_config.cpp
  src/audio/audio_session.cpp
  src/audio/pcm_ring_buffer.cpp
  src/audio/wav_file.cpp
  src/platform/process_memory.cpp
)

target_include_directories(rootlink_audio_core PUBLIC include)
target_link_libraries(rootlink_audio_core PUBLIC Threads::Threads)

if(MSVC)
  target_compile_options(rootlink_audio_core PRIVATE /W4 /permissive-)
else()
  target_compile_options(rootlink_audio_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_library(rootlink_voice_core STATIC
  src/voice/codec.cpp
  src/voice/json_value.cpp
  src/voice/python_persona.cpp
  src/voice/role.cpp
  src/voice/runtime_config.cpp
  src/voice/tts_translation.cpp
  src/voice/vad.cpp
  src/voice/voice_runtime.cpp
)
target_include_directories(rootlink_voice_core PUBLIC include)
target_link_libraries(rootlink_voice_core PUBLIC rootlink_audio_core)
# Echo-Mate GCC 8.3 的 C++17 filesystem 仍放在独立库；GCC 9+ 已并入标准库。
# 让链接器从目标 wrapper 的搜索路径取库，绝不引用主机 libstdc++fs。
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
  target_link_libraries(rootlink_voice_core PUBLIC stdc++fs)
endif()
if(MSVC)
  target_compile_options(rootlink_voice_core PRIVATE /W4 /permissive-)
else()
  target_compile_options(rootlink_voice_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_library(rootlink_voice_mock STATIC src/voice/mock_providers.cpp)
target_include_directories(rootlink_voice_mock PUBLIC include)
target_link_libraries(rootlink_voice_mock PUBLIC rootlink_voice_core)

if(ROOTLINK_SERVICE_API STREQUAL "curl")
  if(CMAKE_CROSSCOMPILING)
    find_path(CURL_INCLUDE_DIR NAMES curl/curl.h
      PATHS "${RV1106_SYSROOT}/usr/include" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    find_library(CURL_LIBRARY NAMES curl
      PATHS "${RV1106_SYSROOT}/usr/lib" "${RV1106_SYSROOT}/lib"
      NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    find_path(JSON_C_INCLUDE_DIR NAMES json-c/json.h
      PATHS "${RV1106_SYSROOT}/usr/include" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    find_library(JSON_C_LIBRARY NAMES json-c
      PATHS "${RV1106_SYSROOT}/usr/lib" "${RV1106_SYSROOT}/lib"
      NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    find_library(OPENSSL_SSL_LIBRARY NAMES ssl
      PATHS "${RV1106_SYSROOT}/usr/lib" "${RV1106_SYSROOT}/lib"
      NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    find_library(OPENSSL_CRYPTO_LIBRARY NAMES crypto
      PATHS "${RV1106_SYSROOT}/usr/lib" "${RV1106_SYSROOT}/lib"
      NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    if(NOT CURL_INCLUDE_DIR OR NOT CURL_LIBRARY OR NOT JSON_C_INCLUDE_DIR OR
       NOT JSON_C_LIBRARY OR NOT OPENSSL_SSL_LIBRARY OR NOT OPENSSL_CRYPTO_LIBRARY)
      message(FATAL_ERROR
        "Stage 2 cloud dependencies are missing from ${RV1106_SYSROOT}. Enable "
        "BR2_PACKAGE_LIBCURL, BR2_PACKAGE_JSON_C and BR2_PACKAGE_OPENSSL in the "
        "Echo-Mate Buildroot config, rebuild rootfs, then configure again.")
    endif()
    set(RV1106_CA_BUNDLE "" CACHE FILEPATH "Explicit trusted CA bundle to deploy with the board binary")
    if(RV1106_CA_BUNDLE)
      if(NOT EXISTS "${RV1106_CA_BUNDLE}")
        message(FATAL_ERROR "RV1106_CA_BUNDLE must be an existing PEM CA bundle")
      endif()
      file(STRINGS "${RV1106_CA_BUNDLE}" _rootlink_ca_marker REGEX "^-----BEGIN CERTIFICATE-----$" LIMIT_COUNT 1)
      if(NOT _rootlink_ca_marker)
        message(FATAL_ERROR "RV1106_CA_BUNDLE does not contain a PEM certificate")
      endif()
      # CA 是与 CPU 架构无关的数据。允许显式提供受信任系统的证书包，但必须随板端
      # 程序部署；不能用主机证书的存在来假装目标 rootfs 已经包含证书。
      configure_file("${RV1106_CA_BUNDLE}" "${CMAKE_BINARY_DIR}/deployment/etc/ssl/certs/ca-certificates.crt" COPYONLY)
      install(FILES "${RV1106_CA_BUNDLE}" DESTINATION etc/ssl/certs RENAME ca-certificates.crt)
      message(STATUS "Explicit CA bundle staged in deployment/etc/ssl/certs; deploy it to the board before cloud use")
    elseif(NOT EXISTS "${RV1106_SYSROOT}/etc/ssl/certs/ca-certificates.crt" AND
           NOT EXISTS "${RV1106_TARGET_ROOT}/etc/ssl/certs/ca-certificates.crt")
      message(FATAL_ERROR
        "CA certificate bundle is missing. Enable BR2_PACKAGE_CA_CERTIFICATES and rebuild rootfs, "
        "or supply -DRV1106_CA_BUNDLE=/trusted/ca-certificates.crt and deploy the staged bundle with the binary.")
    endif()
    set(_rootlink_cloud_libraries "${CURL_LIBRARY}" "${JSON_C_LIBRARY}"
                                  "${OPENSSL_SSL_LIBRARY}" "${OPENSSL_CRYPTO_LIBRARY}")
  else()
    find_package(CURL REQUIRED)
    find_path(JSON_C_INCLUDE_DIR NAMES json-c/json.h REQUIRED)
    find_library(JSON_C_LIBRARY NAMES json-c REQUIRED)
    set(CURL_INCLUDE_DIR "")
    set(_rootlink_cloud_libraries CURL::libcurl "${JSON_C_LIBRARY}")
  endif()
  add_library(rootlink_voice_cloud STATIC
    src/voice/curl_http_client.cpp
    src/voice/cloud_providers.cpp
  )
  target_include_directories(rootlink_voice_cloud PUBLIC include
    PRIVATE "${CURL_INCLUDE_DIR}" "${JSON_C_INCLUDE_DIR}")
  target_compile_definitions(rootlink_voice_cloud PUBLIC ROOTLINK_SERVICE_API_CURL=1)
  target_link_libraries(rootlink_voice_cloud PUBLIC rootlink_voice_core ${_rootlink_cloud_libraries})
  if(MSVC)
    target_compile_options(rootlink_voice_cloud PRIVATE /W4 /permissive-)
  else()
    target_compile_options(rootlink_voice_cloud PRIVATE -Wall -Wextra -Wpedantic)
  endif()
endif()

if(ROOTLINK_AUDIO_API STREQUAL "alsa")
  if(CMAKE_CROSSCOMPILING)
    if(NOT RV1106_SYSROOT)
      message(FATAL_ERROR "RV1106_SYSROOT was not supplied by the RV1106 toolchain file")
    endif()
    find_path(ALSA_INCLUDE_DIR
      NAMES alsa/asoundlib.h
      PATHS "${RV1106_SYSROOT}/usr/include"
      NO_DEFAULT_PATH
      NO_CMAKE_FIND_ROOT_PATH
    )
    find_library(ALSA_LIBRARY
      NAMES asound
      PATHS "${RV1106_SYSROOT}/usr/lib" "${RV1106_SYSROOT}/lib"
      NO_DEFAULT_PATH
      NO_CMAKE_FIND_ROOT_PATH
    )
    if(NOT ALSA_INCLUDE_DIR OR NOT ALSA_LIBRARY)
      message(FATAL_ERROR
        "ALSA was not found in the RV1106 Buildroot sysroot (${RV1106_SYSROOT}). "
        "Run './build.sh rootfs' in RV1106_SDK_ROOT, verify that the echo_mate_defconfig "
        "enables ALSA development files, then configure again."
      )
    endif()
  else()
    find_package(ALSA REQUIRED)
  endif()

  add_library(rootlink_audio_alsa STATIC
    src/audio/alsa_audio_capture.cpp
    src/audio/alsa_audio_playback.cpp
  )
  target_include_directories(rootlink_audio_alsa
    PUBLIC include
    PRIVATE "${ALSA_INCLUDE_DIR}"
  )
  target_link_libraries(rootlink_audio_alsa PUBLIC rootlink_audio_core "${ALSA_LIBRARY}")
  if(MSVC)
    target_compile_options(rootlink_audio_alsa PRIVATE /W4 /permissive-)
  else()
    target_compile_options(rootlink_audio_alsa PRIVATE -Wall -Wextra -Wpedantic)
  endif()
endif()

if(ROOTLINK_AUDIO_API STREQUAL "simulated")
  add_library(rootlink_audio_simulated STATIC
    src/audio/simulated_audio_capture.cpp
    src/audio/simulated_audio_playback.cpp
  )
  target_include_directories(rootlink_audio_simulated PUBLIC include)
  target_link_libraries(rootlink_audio_simulated PUBLIC rootlink_audio_core)
  if(MSVC)
    target_compile_options(rootlink_audio_simulated PRIVATE /W4 /permissive-)
  else()
    target_compile_options(rootlink_audio_simulated PRIVATE -Wall -Wextra -Wpedantic)
  endif()
endif()

if(ROOTLINK_VOICE_BUILD_CLI)
  if(ROOTLINK_AUDIO_API STREQUAL "none")
    message(FATAL_ERROR "ROOTLINK_VOICE_BUILD_CLI requires simulated or alsa audio")
  endif()
  add_executable(rootlink-voice src/app/voice_main.cpp)
  target_link_libraries(rootlink-voice PRIVATE rootlink_main_view)
  if(ROOTLINK_AUDIO_API STREQUAL "alsa")
    target_link_libraries(rootlink-voice PRIVATE rootlink_audio_alsa)
    target_compile_definitions(rootlink-voice PRIVATE
      ROOTLINK_AUDIO_API_ALSA=1 ROOTLINK_AUDIO_API_NAME="alsa")
  else()
    target_link_libraries(rootlink-voice PRIVATE rootlink_audio_simulated)
    target_compile_definitions(rootlink-voice PRIVATE
      ROOTLINK_AUDIO_API_SIMULATED=1 ROOTLINK_AUDIO_API_NAME="simulated")
  endif()
  if(ROOTLINK_SERVICE_API STREQUAL "curl")
    target_link_libraries(rootlink-voice PRIVATE rootlink_voice_cloud)
    target_compile_definitions(rootlink-voice PRIVATE ROOTLINK_SERVICE_API_NAME="curl")
  else()
    target_link_libraries(rootlink-voice PRIVATE rootlink_voice_mock)
    target_compile_definitions(rootlink-voice PRIVATE ROOTLINK_SERVICE_API_NAME="mock")
  endif()
  target_compile_definitions(rootlink-voice PRIVATE ROOTLINK_DEFAULT_CONFIG_PATH="rootlink.conf")
  install(TARGETS rootlink-voice RUNTIME DESTINATION bin)
  install(FILES config/rootlink.conf config/rootlink-secrets.env.example DESTINATION etc/rootlink)
endif()

if(ROOTLINK_AUDIO_BUILD_CLI)
  if(ROOTLINK_AUDIO_API STREQUAL "none")
    message(FATAL_ERROR "ROOTLINK_AUDIO_BUILD_CLI requires an audio API")
  endif()
  add_executable(rootlink-audio-smoke src/app/main.cpp)
  if(ROOTLINK_AUDIO_API STREQUAL "alsa")
    target_link_libraries(rootlink-audio-smoke PRIVATE rootlink_audio_alsa)
    target_compile_definitions(rootlink-audio-smoke PRIVATE
      ROOTLINK_AUDIO_API_ALSA=1 ROOTLINK_AUDIO_API_NAME="alsa")
  else()
    target_link_libraries(rootlink-audio-smoke PRIVATE rootlink_audio_simulated)
    target_compile_definitions(rootlink-audio-smoke PRIVATE
      ROOTLINK_AUDIO_API_SIMULATED=1 ROOTLINK_AUDIO_API_NAME="simulated")
  endif()
  target_compile_definitions(rootlink-audio-smoke PRIVATE
    ROOTLINK_DEFAULT_CAPTURE_DEVICE="${ROOTLINK_DEFAULT_CAPTURE_DEVICE}"
    ROOTLINK_DEFAULT_PLAYBACK_DEVICE="${ROOTLINK_DEFAULT_PLAYBACK_DEVICE}"
    ROOTLINK_DEFAULT_BUFFER_FRAMES=${ROOTLINK_DEFAULT_BUFFER_FRAMES})
  install(TARGETS rootlink-audio-smoke RUNTIME DESTINATION bin)
endif()

if(BUILD_TESTING)
  add_executable(rootlink_ui_state_tests tests/ui_state_tests.cpp)
  target_include_directories(rootlink_ui_state_tests PRIVATE include)
  add_test(NAME rootlink_ui_state_tests COMMAND rootlink_ui_state_tests)
  if(ROOTLINK_UI_BACKEND STREQUAL "sdl")
    add_executable(rootlink_ui_preview tests/ui_preview.cpp)
    target_link_libraries(rootlink_ui_preview PRIVATE rootlink_main_view)
    add_test(NAME rootlink_ui_preview COMMAND rootlink_ui_preview)
    set_tests_properties(rootlink_ui_preview PROPERTIES ENVIRONMENT "SDL_VIDEODRIVER=dummy" TIMEOUT 10)
    if(ROOTLINK_VOICE_BUILD_CLI)
      add_executable(rootlink_ui_restart_tests tests/ui_restart_tests.cpp)
      get_target_property(voice_links rootlink-voice LINK_LIBRARIES)
      get_target_property(voice_definitions rootlink-voice COMPILE_DEFINITIONS)
      target_link_libraries(rootlink_ui_restart_tests PRIVATE ${voice_links})
      target_compile_definitions(rootlink_ui_restart_tests PRIVATE ${voice_definitions})
      add_test(NAME rootlink_ui_restart_tests COMMAND rootlink_ui_restart_tests)
      set_tests_properties(rootlink_ui_restart_tests PROPERTIES ENVIRONMENT "SDL_VIDEODRIVER=dummy" TIMEOUT 10)
    endif()
  endif()
  if(UNIX AND NOT CMAKE_CROSSCOMPILING)
    add_executable(rootlink_persona_bridge_driver tests/persona_bridge_driver.cpp)
    target_link_libraries(rootlink_persona_bridge_driver PRIVATE rootlink_voice_core)
  endif()
  if(ROOTLINK_SERVICE_API STREQUAL "curl")
    add_executable(rootlink_cloud_protocol_tests tests/cloud_protocol_tests.cpp)
    target_link_libraries(rootlink_cloud_protocol_tests PRIVATE rootlink_voice_cloud)
    add_test(NAME rootlink_cloud_protocol_tests COMMAND rootlink_cloud_protocol_tests)
  endif()
  add_executable(rootlink_audio_core_tests tests/audio_core_tests.cpp)
  target_link_libraries(rootlink_audio_core_tests PRIVATE rootlink_audio_core)
  add_test(NAME rootlink_audio_core_tests COMMAND rootlink_audio_core_tests)

  add_executable(rootlink_voice_core_tests tests/voice_core_tests.cpp)
  target_link_libraries(rootlink_voice_core_tests PRIVATE rootlink_voice_core rootlink_voice_mock)
  add_test(NAME rootlink_voice_core_tests COMMAND rootlink_voice_core_tests)

  if(ROOTLINK_AUDIO_API STREQUAL "simulated")
    add_executable(rootlink_audio_simulated_tests tests/simulated_audio_tests.cpp)
    target_link_libraries(rootlink_audio_simulated_tests PRIVATE rootlink_audio_simulated)
    add_test(NAME rootlink_audio_simulated_tests COMMAND rootlink_audio_simulated_tests)
    # 将完整离线对话纳入常规构建验收，避免只验证组件却遗漏 CLI 配置和信号退出。
    if(UNIX AND NOT CMAKE_CROSSCOMPILING AND ROOTLINK_VOICE_BUILD_CLI
       AND ROOTLINK_SERVICE_API STREQUAL "mock")
      add_test(NAME rootlink_voice_cli_tests
        COMMAND sh "${CMAKE_CURRENT_SOURCE_DIR}/scripts/test-voice-cli.sh"
          $<TARGET_FILE:rootlink-voice> "${CMAKE_CURRENT_SOURCE_DIR}/config/rootlink.conf")
      set_tests_properties(rootlink_voice_cli_tests PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" TIMEOUT 30)
    endif()
  endif()
endif()
