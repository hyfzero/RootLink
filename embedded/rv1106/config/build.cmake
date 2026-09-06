# 在 Ubuntu / WSL 中使用：cmake -S . -B build/ubuntu -C config/build.cmake
# 切换为 rv1106 后使用另一个构建目录：build/rv1106。
set(ROOTLINK_TARGET "ubuntu" CACHE STRING "ubuntu or rv1106" FORCE)

# 外部源码默认沿用当前工作区布局；换机器时在这里修改路径。
get_filename_component(_workspace "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
set(ROOTLINK_LVGL_SOURCE_DIR
    "${_workspace}/Amadues_chatRobo/Demo/DeskBot_demo/lvgl"
    CACHE PATH "External LVGL source" FORCE)
set(RV1106_SDK_ROOT "${_workspace}/Amadues_chatRobo/SDK/rv1106-sdk"
    CACHE PATH "External RV1106 SDK" FORCE)
set(RV1106_CA_BUNDLE "/etc/ssl/certs/ca-certificates.crt"
    CACHE FILEPATH "Trusted CA bundle to stage for RV1106" FORCE)
set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
