import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/stock.dart';
import '../models/signal_analytics.dart';
import '../models/system_status.dart';
import '../models/trade_replay.dart';

/// HTTP client for Smart Stock Assistant backend.
///
/// Production backend: https://smart-stock-assistant.onrender.com
class ApiService {
  static const String baseUrl = 'https://smart-stock-assistant.onrender.com';
  static const String baseUrl1 = 'https://smart-stock-assistant.onrender.com';
  static const String appPassword = 'SmartStock2026!';

  final http.Client _client;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Future<bool> login(String password) async {
    final uri = Uri.parse('$baseUrl/auth/login?password=$password');
    final response = await _client.post(uri);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['success'] == true;
    }
    return false;
  }

  Future<List<StockOpportunity>> getOpportunities({int limit = 5}) async {
    final dashboard = await fetchOpportunitiesDashboard(limit: limit);
    return dashboard.displayItems;
  }

  Future<OpportunitiesDashboard> fetchOpportunitiesDashboard({int limit = 20}) async {
    final uri = Uri.parse('$baseUrl/stocks/opportunities?limit=$limit');
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Failed to load opportunities');
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
    final uri = Uri.parse('$baseUrl/stocks/search?q=${Uri.encodeQueryComponent(query)}');
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('Search failed');
    }
    final list = jsonDecode(response.body) as List;
    return list
        .map((e) => SearchResult.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<StockAnalysis> getAnalysis(String symbol) async {
    final uri = Uri.parse('$baseUrl/stocks/${symbol.toUpperCase()}/analysis');
    final response = await _client.get(uri);
    if (response.statusCode == 404) {
      throw Exception('السهم غير موجود');
    }
    if (response.statusCode != 200) {
      throw Exception('Failed to load analysis');
    }
    return StockAnalysis.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<Map<String, dynamic>> getHealth() async {
    final uri = Uri.parse('$baseUrl/health');
    final response = await _client.get(uri).timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('Health check failed (${response.statusCode})');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getConnectionStatus() async {
    final uri = Uri.parse('$baseUrl/status');
    final response = await _client.get(uri).timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('Status check failed (${response.statusCode})');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getScannerState() async {
    final uri = Uri.parse('$baseUrl/scanner/state');
    final response = await _client.get(uri).timeout(const Duration(seconds: 12));
    if (response.statusCode != 200) {
      throw Exception('Scanner state failed (${response.statusCode})');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<AnalyticsDashboard> fetchAnalyticsDashboard() async {
    final uri = Uri.parse('$baseUrl/analytics/dashboard');
    final response = await _client.get(uri).timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('Analytics dashboard failed (${response.statusCode})');
    }
    return AnalyticsDashboard.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<RankedSignalsResponse> fetchRankedSignals({int limit = 50}) async {
    final uri = Uri.parse('$baseUrl/analytics/signals?limit=$limit');
    final response = await _client.get(uri).timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('Ranked signals failed (${response.statusCode})');
    }
    return RankedSignalsResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<PerformanceReport> fetchPerformanceReport() async {
    final uri = Uri.parse('$baseUrl/analytics/performance');
    final response = await _client.get(uri).timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('Performance report failed (${response.statusCode})');
    }
    return PerformanceReport.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<TradeReplayListResponse> fetchTradeReplayList({int limit = 50, String? symbol}) async {
    var uri = Uri.parse('$baseUrl/analytics/replay?limit=$limit');
    if (symbol != null && symbol.isNotEmpty) {
      uri = uri.replace(queryParameters: {'limit': '$limit', 'symbol': symbol.toUpperCase()});
    }
    final response = await _client.get(uri).timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('Trade replay failed (${response.statusCode})');
    }
    return TradeReplayListResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<TradeReplayDetail> fetchTradeReplayDetail(int signalId) async {
    final uri = Uri.parse('$baseUrl/analytics/replay/$signalId');
    final response = await _client.get(uri).timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('Trade replay detail failed (${response.statusCode})');
    }
    return TradeReplayDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<PerformanceInsights> fetchPerformanceInsights() async {
    final uri = Uri.parse('$baseUrl/analytics/insights');
    final response = await _client.get(uri).timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw Exception('Performance insights failed (${response.statusCode})');
    }
    return PerformanceInsights.fromJson(
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

  /// Placeholder for future Finnhub direct integration from the app.
  /// Prefer routing through backend to keep API keys server-side.
  Future<void> connectFinnhub(String apiKey) async {
    // TODO: optional direct Finnhub calls
    throw UnimplementedError('Use backend Finnhub integration');
  }

  /// Placeholder for future Alpha Vantage direct integration.
  Future<void> connectAlphaVantage(String apiKey) async {
    // TODO: optional direct Alpha Vantage calls
    throw UnimplementedError('Use backend Alpha Vantage integration');
  }
}
