# 对话字体

`ui_font_dialogue16.c` 是 Noto Sans SC 的 16 px、2 bpp LVGL 位图字体。仅在 SDL/framebuffer 构建中链接，板端无需字体引擎或源 TTF。源码体积不等于目标运行内存，实际资源占用仍需实板测量。

来源：参考工程 `Amadues_chatRobo/Demo/DeskBot_demo/lvgl/tests/src/test_files/fonts/noto/NotoSansSC-Regular.ttf`。源文件 SHA-256：`ae82f4e2a55e1316a55bcc1d05e9555ce08d8bda07e893b486896b626fd852ff`。版权与 SIL OFL 1.1 许可全文见同目录 `OFL.txt`，分发字体时须一并保留。

生成范围包含 ASCII、中文标点、假名、全角标点、U+4E00–U+9FFF 常用统一汉字区，以及替换符 U+FFFD。具体字形以源字体为准；未包含扩展平面汉字及 emoji，不承诺任意 Unicode 都能显示。

普通编译直接使用已生成的 C 文件，无需安装生成工具。需要修改字号或字符集时，在开发机安装 `lv_font_conv`，从 `embedded/rv1106` 运行：

```sh
../../.venv/bin/python scripts/generate_dialogue_font.py \
  --font ../../../Amadues_chatRobo/Demo/DeskBot_demo/lvgl/tests/src/test_files/fonts/noto/NotoSansSC-Regular.ttf \
  --output src/ui/fonts/ui_font_dialogue16.c
```

可用 `--converter /path/to/lv_font_conv` 指定工具。`LV_FONT_FMT_TXT_LARGE=1` 用于容纳该字库的位图偏移，`LV_USE_FONT_COMPRESSED=1` 启用压缩字形解码；变更后需重新构建 LVGL 与界面目标。预览测试检查中、文、牧、濑、あ和 A 的实际位图可解码，避免只有字符映射而显示为方框。
