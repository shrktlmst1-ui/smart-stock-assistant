import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Ensures legacy hardcoded credentials are not present in source or web build.
void main() {
  const forbidden = ['SmartStock2026', 'appPassword', 'APP_PASSWORD_HASH'];

  test('Flutter lib has no hardcoded secrets', () {
    final libDir = Directory('lib');
    expect(libDir.existsSync(), isTrue);
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final text = entity.readAsStringSync();
      for (final needle in forbidden) {
        expect(
          text.contains(needle),
          isFalse,
          reason: '${entity.path} must not contain $needle',
        );
      }
    }
  });

  test('web build has no hardcoded secrets when present', () {
    final buildDir = Directory('build/web');
    if (!buildDir.existsSync()) return;
    for (final entity in buildDir.listSync(recursive: true)) {
      if (entity is! File) continue;
      if (!entity.path.endsWith('.js') &&
          !entity.path.endsWith('.html') &&
          !entity.path.endsWith('.json')) {
        continue;
      }
      final text = entity.readAsStringSync();
      for (final needle in forbidden) {
        expect(
          text.contains(needle),
          isFalse,
          reason: '${entity.path} must not contain $needle',
        );
      }
    }
  });
}
