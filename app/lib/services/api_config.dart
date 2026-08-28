import 'package:flutter/foundation.dart';

/// Resolves API base URL for REST and WebSocket clients.
class ApiConfig {
  /// Production backend (Render Web Service).
  static const String productionApiBaseUrl =
      'https://smart-stock-assistant.onrender.com';

  static String get baseUrl {
    const fromEnv = String.fromEnvironment('API_BASE_URL');
    if (fromEnv.isNotEmpty) {
      return _normalize(fromEnv);
    }

    if (kIsWeb) {
      final host = Uri.base.host;
      if (host == 'localhost' || host == '127.0.0.1') {
        return 'http://localhost:8000';
      }
      return productionApiBaseUrl;
    }

    return 'http://localhost:8000';
  }

  static String _normalize(String url) {
    var trimmed = url.trim();
    while (trimmed.endsWith('/')) {
      trimmed = trimmed.substring(0, trimmed.length - 1);
    }
    return trimmed;
  }
}
