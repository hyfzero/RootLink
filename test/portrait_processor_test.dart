import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'dart:typed_data';

import 'package:rootlink/data/image_portrait_processor.dart';

void main() {
  test('portrait processor applies the compatible pixel crop box', () async {
    final source = img.Image(width: 4, height: 2, numChannels: 4);
    source.clear(img.ColorRgba8(255, 0, 0, 255));
    for (var y = 0; y < source.height; y++) {
      source.setPixelRgba(1, y, 0, 255, 0, 255);
      source.setPixelRgba(2, y, 0, 0, 255, 255);
    }

    final output = await const ImagePortraitProcessor().process(
      source: img.encodePng(source),
      renderMode: 'original',
      backgroundColor: const <int>[255, 255, 255],
      tolerance: 0,
      feather: 0,
      cropBox: const <int>[1, 0, 3, 2],
      scale: 1,
      offsetX: 0,
      offsetY: 0,
      canvasWidth: 2,
      canvasHeight: 2,
    );

    final decoded = img.decodePng(Uint8List.fromList(output))!;
    expect(decoded.width, 2);
    expect(decoded.getPixel(0, 0).g, 255);
    expect(decoded.getPixel(1, 0).b, 255);
  });
}
