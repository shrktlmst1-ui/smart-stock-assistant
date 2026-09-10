import 'dart:convert';
import 'package:http/http.dart' as http;
import 'api_config.dart';

class FacilityApiService {
  String? token;
  String get baseUrl => ApiConfig.baseUrl;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  Future<void> login(String email, String password) async {
    final r = await http.post(Uri.parse('$baseUrl/api/auth/login'), headers: _headers, body: jsonEncode({'email': email, 'password': password}));
    if (r.statusCode != 200) throw Exception(_message(r));
    token = jsonDecode(r.body)['access_token'] as String;
  }

  Future<void> setup(String facilityName, String email, String password) async {
    final r = await http.post(Uri.parse('$baseUrl/api/auth/setup'), headers: _headers, body: jsonEncode({'facility_name': facilityName, 'admin_email': email, 'admin_password': password}));
    if (r.statusCode != 200) throw Exception(_message(r));
    token = jsonDecode(r.body)['access_token'] as String;
  }

  Future<Map<String, dynamic>> me() async => _get('/api/me');
  Future<List<dynamic>> branches() async => _getList('/api/branches');
  Future<List<dynamic>> employees() async => _getList('/api/employees');

  Future<Map<String, dynamic>> createBranch(String name, String address) async => _post('/api/branches', {'name': name, 'address': address});
  Future<Map<String, dynamic>> createEmployee(Map<String, dynamic> data) async => _post('/api/employees', data);

  Future<Map<String, dynamic>> _get(String path) async {
    final r = await http.get(Uri.parse('$baseUrl$path'), headers: _headers);
    if (r.statusCode != 200) throw Exception(_message(r));
    return Map<String, dynamic>.from(jsonDecode(r.body));
  }

  Future<List<dynamic>> _getList(String path) async {
    final r = await http.get(Uri.parse('$baseUrl$path'), headers: _headers);
    if (r.statusCode != 200) throw Exception(_message(r));
    return List<dynamic>.from(jsonDecode(r.body));
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final r = await http.post(Uri.parse('$baseUrl$path'), headers: _headers, body: jsonEncode(body));
    if (r.statusCode < 200 || r.statusCode >= 300) throw Exception(_message(r));
    return Map<String, dynamic>.from(jsonDecode(r.body));
  }

  String _message(http.Response r) {
    try { return Map<String, dynamic>.from(jsonDecode(r.body))['detail']?.toString() ?? 'حدث خطأ في الخادم'; } catch (_) { return 'تعذر الاتصال بالخادم (${r.statusCode})'; }
  }
}
