import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/spx_signal.dart';
import 'api_config.dart';
import 'auth_session.dart';

class SpxApiService {
  static String get baseUrl => ApiConfig.baseUrl;

  final http.Client _client;
  final AuthSession authSession;

  SpxApiService({http.Client? client, AuthSession? authSession})
      : _client = client ?? http.Client(),
        authSession = authSession ?? AuthSession();

  Future<SpxSignal> fetchSignal({bool refresh = false}) async {
    await authSession.restore();
    final path = refresh ? '/spx/signal/refresh' : '/spx/signal';
    final uri = Uri.parse('$baseUrl$path');
    final response = refresh
        ? await _client.post(
            uri,
            headers: authSession.authHeaders(),
          ).timeout(const Duration(seconds: 20))
        : await _client.get(
            uri,
            headers: authSession.authHeaders(),
          ).timeout(const Duration(seconds: 20));

    _ensureJsonResponse(response, path);

    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('SPX API returned a non-object JSON payload');
      }
      return SpxSignal.fromJson(decoded);
    } on FormatException catch (error) {
      throw Exception('استجابة SPX غير صالحة من $path: ${error.message}');
    } on TypeError catch (error) {
      throw Exception('بيانات SPX غير متوافقة مع النموذج: $error');
    }
  }

  void _ensureJsonResponse(http.Response response, String path) {
    final contentType = response.headers['content-type'] ?? '';
    final isJson = contentType.toLowerCase().contains('application/json');
    if (response.statusCode != 200 || !isJson) {
      final preview = response.body
          .replaceAll(RegExp(r'\s+'), ' ')
          .trim();
      final safePreview = preview.length > 180 ? preview.substring(0, 180) : preview;
      throw Exception(
        'فشل API الخاص بـ SPX: ${response.statusCode} ${response.reasonPhrase ?? ''} '
        '| Content-Type: ${contentType.isEmpty ? 'غير موجود' : contentType} '
        '| $path | body: $safePreview',
      );
    }
  }
}
