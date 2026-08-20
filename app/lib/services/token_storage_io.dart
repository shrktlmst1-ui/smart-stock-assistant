/// In-memory token storage for non-web platforms.
class TokenStorage {
  String? _token;

  Future<String?> read() async => _token;

  Future<void> write(String token) async {
    _token = token;
  }

  Future<void> clear() async {
    _token = null;
  }
}
