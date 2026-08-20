import 'dart:html' as html;

/// Web sessionStorage — cleared when browser tab closes.
class TokenStorage {
  static const _key = 'ssa_access_token';

  Future<String?> read() async => html.window.sessionStorage[_key];

  Future<void> write(String token) async {
    html.window.sessionStorage[_key] = token;
  }

  Future<void> clear() async {
    html.window.sessionStorage.remove(_key);
  }
}
