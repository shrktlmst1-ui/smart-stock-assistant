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
    final response = refresh
        ? await _client.post(
            Uri.parse('$baseUrl$path'),
            headers: authSession.authHeaders(),
          ).timeout(const Duration(seconds: 20))
        : await _client.get(
            Uri.parse('$baseUrl$path'),
            headers: authSession.authHeaders(),
          ).timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('فشل تحميل إشارة SPX (${response.statusCode})');
    }
    return SpxSignal.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }
}
