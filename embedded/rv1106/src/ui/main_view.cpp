#include "rootlink/ui/main_view.h"
#include <chrono>
#include <cstring>
#include <vector>
#if defined(ROOTLINK_UI_ENABLED)
#include "lvgl.h"
#if ROOTLINK_LV_SDL
#include <SDL2/SDL.h>
#else
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#endif
#endif

namespace rootlink::ui {
using audio::Status;
using audio::AudioError;
struct MainView::Impl {
  std::atomic<bool> closed{false};
  std::atomic<bool> reset_requested{false};
  bool initialized{false};
#if defined(ROOTLINK_UI_ENABLED)
  lv_display_t* display{nullptr};
  lv_obj_t* label{nullptr};
  lv_obj_t* mark{nullptr};
  DisplayState shown{DisplayState::Error};
#if !ROOTLINK_LV_SDL
  int fd{-1};
  int input_fd{-1};
  bool touch_down{false};
  void* mapped{MAP_FAILED};
  fb_fix_screeninfo fixed{};
  fb_var_screeninfo variable{};
  std::vector<uint8_t> buffer;
  static void flush(lv_display_t* display, const lv_area_t* area, uint8_t* pixels) {
    auto& self = *static_cast<Impl*>(lv_display_get_user_data(display));
    const size_t bytes = self.variable.bits_per_pixel / 8;
    const size_t row = (area->x2 - area->x1 + 1) * bytes;
    for (int y = area->y1; y <= area->y2; ++y) {
      const size_t offset = (y + self.variable.yoffset) * self.fixed.line_length +
                            (area->x1 + self.variable.xoffset) * bytes;
      std::memcpy(static_cast<uint8_t*>(self.mapped) + offset, pixels, row);
      pixels += row;
    }
    lv_display_flush_ready(display);
  }
#endif
#endif
};
MainView::MainView() : impl_(std::make_unique<Impl>()) {}
MainView::~MainView() {
#if defined(ROOTLINK_UI_ENABLED)
  if (impl_->display) lv_display_delete(impl_->display);
  if (impl_->initialized) lv_deinit();
#if ROOTLINK_LV_SDL
  SDL_SetEventFilter(nullptr, nullptr);
  SDL_Quit();
#else
  if (impl_->mapped != MAP_FAILED) munmap(impl_->mapped, impl_->fixed.smem_len);
  if (impl_->fd >= 0) close(impl_->fd);
  if (impl_->input_fd >= 0) close(impl_->input_fd);
#endif
#endif
}
Status MainView::initialize(const voice::RuntimeConfig& config) {
  if (config.ui_backend != ROOTLINK_UI_BACKEND)
    return {AudioError::kConfigError, "UI backend differs from build; rebuild for selected UI_BACKEND"};
#if !defined(ROOTLINK_UI_ENABLED)
  return {AudioError::kConfigError, "This build has no UI"};
#else
  lv_init();
  impl_->initialized = true;
  lv_tick_set_cb([]() -> uint32_t {
    return static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
  });
#if ROOTLINK_LV_SDL
  if (SDL_Init(SDL_INIT_VIDEO) != 0) return {AudioError::kIoError, "Cannot initialize SDL display"};
  // Intercept close before LVGL's SDL driver deinitializes or exits the process.
  SDL_SetEventFilter([](void* data, SDL_Event* event) -> int {
    if ((event->type == SDL_MOUSEBUTTONUP && event->button.button == SDL_BUTTON_LEFT) ||
        event->type == SDL_FINGERUP)
      static_cast<Impl*>(data)->reset_requested = true;
    if (event->type == SDL_QUIT || (event->type == SDL_WINDOWEVENT &&
                                  event->window.event == SDL_WINDOWEVENT_CLOSE)) {
      static_cast<Impl*>(data)->closed = true;
      return 0;
    }
    return 1;
  }, impl_.get());
  impl_->display = lv_sdl_window_create(config.ui_width, config.ui_height);
#else
  if (!config.ui_input_device.empty()) {
    impl_->input_fd = open(config.ui_input_device.c_str(), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    if (impl_->input_fd < 0)
      return {AudioError::kIoError, "Cannot open UI_INPUT_DEVICE touchscreen"};
  }
  impl_->fd = open(config.ui_device.c_str(), O_RDWR | O_CLOEXEC);
  auto& v = impl_->variable;
  auto& f = impl_->fixed;
  if (impl_->fd < 0 || ioctl(impl_->fd, FBIOGET_FSCREENINFO, &f) < 0 ||
      ioctl(impl_->fd, FBIOGET_VSCREENINFO, &v) < 0)
    return {AudioError::kIoError, "Cannot open framebuffer"};
  const bool rgb565 = v.bits_per_pixel == 16 && v.red.offset == 11 && v.red.length == 5 &&
      v.green.offset == 5 && v.green.length == 6 && v.blue.offset == 0 && v.blue.length == 5;
  const bool rgb888 = v.bits_per_pixel == 32 && v.red.offset == 16 && v.red.length == 8 &&
      v.green.offset == 8 && v.green.length == 8 && v.blue.offset == 0 && v.blue.length == 8;
  const uint64_t row_end = (uint64_t(v.xoffset) + v.xres) * (v.bits_per_pixel / 8);
  const uint64_t end = (uint64_t(v.yoffset) + v.yres) * f.line_length;
  if ((!rgb565 && !rgb888) || f.type != FB_TYPE_PACKED_PIXELS || f.visual != FB_VISUAL_TRUECOLOR ||
      v.xres < 80 || v.yres < 80 || v.xres > 1920 || v.yres > 1080 ||
      row_end > f.line_length || end > f.smem_len)
    return {AudioError::kConfigError, "Framebuffer requires bounded RGB565 or XRGB8888 truecolor"};
  impl_->mapped = mmap(nullptr, f.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, impl_->fd, 0);
  if (impl_->mapped == MAP_FAILED) return {AudioError::kIoError, "Cannot map framebuffer"};
  impl_->display = lv_display_create(v.xres, v.yres);
  if (!impl_->display) return {AudioError::kIoError, "Cannot allocate display"};
  lv_display_set_color_format(impl_->display, rgb565 ? LV_COLOR_FORMAT_RGB565 : LV_COLOR_FORMAT_XRGB8888);
  impl_->buffer.resize(v.xres * 20 * (v.bits_per_pixel / 8));
  lv_display_set_buffers(impl_->display, impl_->buffer.data(), nullptr,
                         impl_->buffer.size(), LV_DISPLAY_RENDER_MODE_PARTIAL);
  lv_display_set_user_data(impl_->display, impl_.get());
  lv_display_set_flush_cb(impl_->display, Impl::flush);
#endif
  if (!impl_->display) return {AudioError::kIoError, "Cannot create display"};
  auto* screen = lv_display_get_screen_active(impl_->display);
  lv_obj_set_style_bg_color(screen, lv_color_black(), 0);
  lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
  lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
  impl_->label = lv_label_create(screen);
  lv_obj_set_style_text_color(impl_->label, lv_color_white(), 0);
  lv_obj_set_style_text_font(impl_->label, &lv_font_montserrat_48, 0);
  // Draw dash/cross ourselves, avoiding a full CJK font dependency for 5 symbols.
  impl_->mark = lv_obj_create(screen);
  lv_obj_remove_style_all(impl_->mark);
  lv_obj_set_size(impl_->mark, 64, 64);
  lv_obj_center(impl_->mark);
  lv_obj_add_event_cb(impl_->mark, [](lv_event_t* event) {
    auto* self = static_cast<Impl*>(lv_event_get_user_data(event));
    lv_area_t area;
    lv_obj_get_coords(self->mark, &area);
    lv_draw_line_dsc_t line;
    lv_draw_line_dsc_init(&line);
    line.color = lv_color_white(); line.width = 5; line.round_start = line.round_end = 1;
    const bool error = self->shown == DisplayState::Error;
    line.p1 = {area.x1 + 8, area.y1 + (error ? 8 : 32)};
    line.p2 = {area.x1 + 56, area.y1 + (error ? 56 : 32)};
    lv_draw_line(lv_event_get_layer(event), &line);
    if (error) {
      line.p1.y = area.y1 + 56; line.p2.y = area.y1 + 8;
      lv_draw_line(lv_event_get_layer(event), &line);
    }
  }, LV_EVENT_DRAW_MAIN, impl_.get());
  tick(DisplayState::Idle);
  return {};
#endif
}
bool MainView::tick(DisplayState state) {
#if defined(ROOTLINK_UI_ENABLED)
  if (impl_->closed) return false;
#if !ROOTLINK_LV_SDL
  // Only a whole-screen tap is needed; no coordinate calibration or LVGL pointer.
  input_event event{};
  for (int n = 0; n < 256 && impl_->input_fd >= 0 &&
       read(impl_->input_fd, &event, sizeof(event)) == sizeof(event); ++n) {
    if (event.type == EV_KEY && event.code == BTN_TOUCH) {
      if (event.value == 0 && impl_->touch_down) impl_->reset_requested = true;
      impl_->touch_down = event.value != 0;
    }
  }
#endif
  if (state != impl_->shown) {
    impl_->shown = state;
    const bool mark = state == DisplayState::Idle || state == DisplayState::Error;
    if (mark) {
      lv_obj_add_flag(impl_->label, LV_OBJ_FLAG_HIDDEN);
      lv_obj_remove_flag(impl_->mark, LV_OBJ_FLAG_HIDDEN);
      lv_obj_invalidate(impl_->mark);
    } else {
      lv_obj_add_flag(impl_->mark, LV_OBJ_FLAG_HIDDEN);
      lv_obj_remove_flag(impl_->label, LV_OBJ_FLAG_HIDDEN);
      lv_label_set_text(impl_->label, state == DisplayState::Listening ? "?" :
                       state == DisplayState::Thinking ? "...." : "!");
      lv_obj_center(impl_->label);
      if (state == DisplayState::Thinking) lv_obj_set_y(impl_->label, -14);
    }
  }
  lv_timer_handler();
#else
  (void)state;
#endif
  return !impl_->closed;
}
bool MainView::takeResetRequest() { return impl_->reset_requested.exchange(false); }
}
