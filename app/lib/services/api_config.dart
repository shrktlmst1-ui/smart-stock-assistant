import 'package:flutter/foundation.dart';

/// Resolves API base URL for REST and WebSocket clients.
///
/// - Web production (Render): same origin as the served Flutter app.
/// - Web local dev (`flutter run -d chrome`): backend on localhost:8000.
/// - Mobile/desktop: `API_BASE_URL` dart-define or localhost:8000.
class ApiConfig {
  static String get baseUrl {
    if (kIsWeb) {
      final uri = Uri.base;
      final host = uri.host;
      if (host == 'localhost' || host == '127.0.0.1') {
        return 'http://localhost:8000';
      }
      return uri.origin;
    }
    return const String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://localhost:8000',
    );
  }
}
