import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/market_pulse.dart';
import '../models/opportunity_now.dart';
import '../models/signal_analytics.dart';
import '../models/stock.dart';
import '../models/system_status.dart';
import '../models/trade_replay.dart';
import 'auth_session.dart';
import 'api_config.dart';

/// HTTP client for Smart Stock Assistant backend.
class ApiService {
  static String get baseUrl => ApiConfig.baseUrl;

  final http.Client _client;
  final AuthSession authSession;

  ApiService({http.Client? client, AuthSession? authSession})
      : _client = client ?? http.Client(),
        authSession = authSession ?? AuthSession();

  Future<bool> login(String password) async {
    final uri = Uri.parse('$baseUrl/auth/login');
    final response = await _client.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({'password': password}),
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final token = data['access_token'] as String?;
      if (token != null && token.isNotEmpty) {
        await authSession.setToken(token);
        return true;
      }
    }
    return false;
  }

  Future<bool> restoreSession() async {
    await authSession.restore();
    if (authSession.accessToken == null) return false;
    final uri = Uri.parse('$baseUrl/auth/session');
    final response = await _client.get(uri, headers: authSession.authHeaders());
    if (response.statusCode == 200) return true;
    await authSession.clear();
    return false;
  }

  Future<void> logout() async {
    await authSession.clear();
  }

  Future<http.Response> _get(String path, {Duration? timeout}) async {
    if (authSession.accessToken == null) {
      await authSession.restore();
    }
    final uri = Uri.parse('$baseUrl$path');
    final future = _client.get(uri, headers: authSession.authHeaders());
    if (timeout != null) return future.timeout(timeout);
    return future;
  }

  Future<List<StockOpportunity>> getOpportunities({int limit = 5}) async {
    final dashboard = await fetchOpportunitiesDashboard(limit: limit);
    return dashboard.displayItems;
  }

  Future<OpportunitiesDashboard> fetchOpportunitiesDashboard({int limit = 20}) async {
    final response = await _get('/stocks/opportunities?limit=$limit');
    if (response.statusCode == 401) {
      throw Exception('انتهت الجلسة — سجّل الدخول مجددًا');
    }
    if (response.statusCode != 200) {
      throw Exception('فشل تحميل الفرص');
    }
    final body = jsonDecode(response.body);
    if (body is List) {
      final items = body
          .map((e) => StockOpportunity.fromJson(e as Map<String, dynamic>))
          .toList();
      return OpportunitiesDashboard(
        marketStatus: 'REGULAR',
        opportunities: items,
        watchlistCandidates: const [],
        explanation: '',
        noSignalReason: '',
        debug: ScannerStageCounts.fromJson(null),
      );
    }
    return OpportunitiesDashboard.fromJson(body as Map<String, dynamic>);
  }

  Future<List<SearchResult>> searchStocks(String query) async {
    final response = await _get('/stocks/search?q=${Uri.encodeQueryComponent(query)}');
    if (response.statusCode != 200) {
      throw Exception('فشل البحث');
    }
    final list = jsonDecode(response.body) as List;
    return list
        .map((e) => SearchResult.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<StockAnalysis> getAnalysis(String symbol) async {
    final response = await _get('/stocks/${symbol.toUpperCase()}/analysis');
    if (response.statusCode == 404) {
      throw Exception('السهم غير موجود');
    }
    if (response.statusCode != 200) {
      throw Exception('فشل تحميل التحليل');
    }
    return StockAnalysis.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<Map<String, dynamic>> getHealth() async {
    final uri = Uri.parse('$baseUrl/health');
    final response = await _client.get(uri).timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('فشل فحص الخادم (${response.statusCode})');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getConnectionStatus() async {
    final response = await _get('/status').timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('فشل فحص الحالة (${response.statusCode})');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getScannerState() async {
    final response = await _get('/scanner/state').timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('فشل حالة الماسح (${response.statusCode})');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<AnalyticsDashboard> fetchAnalyticsDashboard() async {
    final response = await _get('/analytics/dashboard').timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('فشل لوحة التحليلات (${response.statusCode})');
    }
    return AnalyticsDashboard.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<RankedSignalsResponse> fetchRankedSignals({int limit = 50}) async {
    final response = await _get('/analytics/signals?limit=$limit').timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('فشل تحميل الإشارات (${response.statusCode})');
    }
    return RankedSignalsResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<PerformanceReport> fetchPerformanceReport() async {
    final response = await _get('/analytics/performance').timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('فشل تقرير الأداء (${response.statusCode})');
    }
    return PerformanceReport.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<TradeReplayListResponse> fetchTradeReplayList({int limit = 50, String? symbol}) async {
    var path = '/analytics/replay?limit=$limit';
    if (symbol != null && symbol.isNotEmpty) {
      path = '/analytics/replay?limit=$limit&symbol=${symbol.toUpperCase()}';
    }
    final response = await _get(path).timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('فشل إعادة الصفقة (${response.statusCode})');
    }
    return TradeReplayListResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<TradeReplayDetail> fetchTradeReplayDetail(int signalId) async {
    final response = await _get('/analytics/replay/$signalId').timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('فشل تفاصيل إعادة الصفقة (${response.statusCode})');
    }
    return TradeReplayDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<PerformanceInsights> fetchPerformanceInsights() async {
    final response = await _get('/analytics/insights').timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('فشل رؤى الأداء (${response.statusCode})');
    }
    return PerformanceInsights.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<MarketPulseHealth> fetchMarketPulseHealth() async {
    final response = await _get('/market-pulse/health').timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('فشل حالة نبض السوق');
    }
    return MarketPulseHealth.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<MarketPulseListResponse> fetchMarketPulseAlerts() async {
    final response = await _get('/market-pulse').timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('فشل تحميل نبض السوق');
    }
    return MarketPulseListResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<OpportunityNowResponse> fetchOpportunityNow() async {
    final response = await _get('/stocks/opportunity-now').timeout(const Duration(seconds: 12));
    if (response.statusCode == 401) {
      throw Exception('انتهت الجلسة — سجّل الدخول مجددًا');
    }
    if (response.statusCode != 200) {
      throw Exception('فشل تحميل فرصة الآن');
    }
    return OpportunityNowResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<SystemStatus> fetchSystemStatus() async {
    final health = await getHealth();
    final connection = await getConnectionStatus();
    Map<String, dynamic>? scanner;
    try {
      scanner = await getScannerState();
    } catch (_) {
      scanner = null;
    }
    connection['stream_mode'] ??= health['stream_mode'];
    return SystemStatus.fromApi(
      health: health,
      connection: connection,
      scanner: scanner,
    );
  }
}
