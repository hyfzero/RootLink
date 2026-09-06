set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

# SDK 始终来自显式 CMake 参数或同名环境变量，绝不把开发机绝对路径写入仓库。
if(NOT RV1106_SDK_ROOT AND DEFINED ENV{RV1106_SDK_ROOT})
  set(RV1106_SDK_ROOT "$ENV{RV1106_SDK_ROOT}")
endif()

if(NOT RV1106_SDK_ROOT)
  message(FATAL_ERROR
    "RV1106_SDK_ROOT is required. Point it at the external Echo-Mate rv1106-sdk checkout."
  )
endif()

file(TO_CMAKE_PATH "${RV1106_SDK_ROOT}" RV1106_SDK_ROOT)
set(RV1106_SDK_ROOT "${RV1106_SDK_ROOT}" CACHE PATH "External RV1106 SDK root" FORCE)
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES RV1106_SDK_ROOT)
set(_tool_prefix "arm-rockchip830-linux-uclibcgnueabihf")
get_filename_component(_buildroot_output
  "${RV1106_SDK_ROOT}/sysdrv/source/buildroot/buildroot-2023.02.6/output"
  REALPATH
)
set(_buildroot_tool_bin "${_buildroot_output}/host/bin")
set(RV1106_TARGET_ROOT "${_buildroot_output}/target" CACHE PATH "Buildroot target rootfs")

# 使用 Buildroot 生成的 wrapper，而不是 SDK 的裸编译器。wrapper 会携带该次 rootfs
# 的 include/lib/sysroot 配置，因此找到的 ALSA 必然与最终板端根文件系统匹配。
if(NOT EXISTS "${_buildroot_tool_bin}/${_tool_prefix}-gcc")
  message(FATAL_ERROR
    "Buildroot C compiler wrapper not found under ${_buildroot_tool_bin}. Rebuild the rootfs first."
  )
endif()
if(NOT EXISTS "${_buildroot_tool_bin}/${_tool_prefix}-g++")
  message(FATAL_ERROR
    "Buildroot C++ compiler wrapper not found under ${_buildroot_tool_bin}. Rebuild the rootfs first."
  )
endif()
set(CMAKE_C_COMPILER "${_buildroot_tool_bin}/${_tool_prefix}-gcc")
set(CMAKE_CXX_COMPILER "${_buildroot_tool_bin}/${_tool_prefix}-g++")
execute_process(
  COMMAND "${CMAKE_CXX_COMPILER}" -print-sysroot
  OUTPUT_VARIABLE _buildroot_sysroot
  OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE _sysroot_result
)
# output 目录在 Echo-Mate SDK 中可能是符号链接，向编译器查询 sysroot 比硬编码
# arm-buildroot-* 子目录更可靠。
if(NOT _sysroot_result EQUAL 0 OR NOT IS_DIRECTORY "${_buildroot_sysroot}")
  message(FATAL_ERROR
    "The Buildroot compiler did not report a usable sysroot. Run './build.sh rootfs' first."
  )
endif()
set(RV1106_SYSROOT "${_buildroot_sysroot}" CACHE PATH "RV1106 Buildroot sysroot" FORCE)
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES RV1106_SYSROOT)
# Buildroot's compiler wrapper injects its relocatable sysroot. Passing a second
# --sysroot overrides that wrapper configuration and breaks the C runtime lookup.
set(CMAKE_FIND_ROOT_PATH "${RV1106_SYSROOT}")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
