import 'dart:isolate';
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import '../domain/repositories.dart';

class ImagePortraitProcessor implements PortraitProcessor {
  const ImagePortraitProcessor();

  @override
  Future<List<int>> process({
    required List<int> source,
    required String renderMode,
    required List<int> backgroundColor,
    required int tolerance,
    required int feather,
    required List<int>? cropBox,
    required double scale,
    required int offsetX,
    required int offsetY,
    required int canvasWidth,
    required int canvasHeight,
  }) => Isolate.run(
    () => _process(<String, Object?>{
      'source': source,
      'renderMode': renderMode,
      'backgroundColor': backgroundColor,
      'tolerance': tolerance,
      'feather': feather,
      'cropBox': cropBox,
      'scale': scale,
      'offsetX': offsetX,
      'offsetY': offsetY,
      'canvasWidth': canvasWidth,
      'canvasHeight': canvasHeight,
    }),
  );

  static List<int> _process(Map<String, Object?> input) {
    final decoded = img.decodeImage(
      Uint8List.fromList(input['source']! as List<int>),
    );
    if (decoded == null) throw const FormatException('不支持的立绘图片格式');
    var foreground = decoded.convert(numChannels: 4);
    final cropBox = input['cropBox'] as List<int>?;
    if (cropBox != null && cropBox.length == 4) {
      final left = cropBox[0].clamp(0, foreground.width - 1);
      final top = cropBox[1].clamp(0, foreground.height - 1);
      final right = cropBox[2].clamp(left + 1, foreground.width);
      final bottom = cropBox[3].clamp(top + 1, foreground.height);
      foreground = img.copyCrop(
        foreground,
        x: left,
        y: top,
        width: right - left,
        height: bottom - top,
      );
    }
    if (input['renderMode'] == 'cutout') {
      final background = input['backgroundColor']! as List<int>;
      final tolerance = input['tolerance']! as int;
      final feather = input['feather']! as int;
      final edge = (tolerance + feather).clamp(0, 441);
      for (final pixel in foreground) {
        final dr = pixel.r.toInt() - background[0];
        final dg = pixel.g.toInt() - background[1];
        final db = pixel.b.toInt() - background[2];
        final distance = (dr * dr + dg * dg + db * db).sqrt();
        if (distance <= tolerance) {
          pixel.a = 0;
        } else if (feather > 0 && distance < edge) {
          pixel.a = (((distance - tolerance) / feather) * 255).round().clamp(
            0,
            255,
          );
        }
      }
    }
    final scale = input['scale']! as double;
    if (scale != 1) {
      foreground = img.copyResize(
        foreground,
        width: (foreground.width * scale).round().clamp(1, 8192),
        height: (foreground.height * scale).round().clamp(1, 8192),
        interpolation: img.Interpolation.cubic,
      );
    }
    final width = input['canvasWidth']! as int;
    final height = input['canvasHeight']! as int;
    final canvas = img.Image(width: width, height: height, numChannels: 4);
    canvas.clear(img.ColorRgba8(0, 0, 0, 0));
    final x = ((width - foreground.width) ~/ 2) + (input['offsetX']! as int);
    final y = ((height - foreground.height) ~/ 2) + (input['offsetY']! as int);
    img.compositeImage(canvas, foreground, dstX: x, dstY: y);
    return img.encodePng(canvas);
  }
}

extension on int {
  double sqrt() {
    if (this <= 0) return 0;
    var estimate = toDouble();
    for (var i = 0; i < 8; i++) {
      estimate = (estimate + this / estimate) / 2;
    }
    return estimate;
  }
}
