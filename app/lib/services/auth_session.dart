import 'token_storage_io.dart' if (dart.library.html) 'token_storage_web.dart';

/// Holds JWT in memory + sessionStorage (web). Never stores password.
class AuthSession {
  AuthSession({TokenStorage? storage}) : _storage = storage ?? TokenStorage();

  final TokenStorage _storage;
  String? _memoryToken;

  String? get accessToken => _memoryToken;

  Future<void> restore() async {
    _memoryToken = await _storage.read();
  }

  Future<void> setToken(String token) async {
    _memoryToken = token;
    await _storage.write(token);
  }

  Future<void> clear() async {
    _memoryToken = null;
    await _storage.clear();
  }

  Map<String, String> authHeaders({Map<String, String>? extra}) {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      ...?extra,
    };
    final token = _memoryToken;
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }
}
