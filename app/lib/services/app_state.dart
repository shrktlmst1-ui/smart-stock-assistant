import 'package:flutter/foundation.dart';

import '../models/alert.dart';
import '../models/stock.dart';
import '../models/system_status.dart';
import 'api_service.dart';
import 'local_storage_service.dart';

/// Live API only — no mock or random fallback data.
class StockDataService {
  final ApiService _api;

  StockDataService({ApiService? api}) : _api = api ?? ApiService();

  Future<OpportunitiesDashboard> getOpportunitiesDashboard({int limit = 20}) async {
    return _api.fetchOpportunitiesDashboard(limit: limit);
  }

  Future<List<StockOpportunity>> getOpportunities({int limit = 20}) async {
    final dashboard = await getOpportunitiesDashboard(limit: limit);
    return dashboard.displayItems;
  }

  Future<List<SearchResult>> search(String query) async {
    return _api.searchStocks(query);
  }

  Future<StockAnalysis> getAnalysis(String symbol) async {
    return _api.getAnalysis(symbol);
  }

  Future<SystemStatus> getSystemStatus() async {
    return _api.fetchSystemStatus();
  }
}

class AppState extends ChangeNotifier {
  final LocalStorageService storage;
  final StockDataService stockData;
  final ApiService api;

  bool _isLoggedIn = false;
  bool _isLoading = false;
  List<WatchlistItem> _watchlist = [];
  List<StockAlert> _alerts = [];

  AppState({
    LocalStorageService? storage,
    StockDataService? stockData,
    ApiService? api,
  })  : storage = storage ?? LocalStorageService(),
        api = api ?? ApiService(),
        stockData = stockData ?? StockDataService();

  bool get isLoggedIn => _isLoggedIn;
  bool get isLoading => _isLoading;
  List<WatchlistItem> get watchlist => List.unmodifiable(_watchlist);
  List<StockAlert> get alerts => List.unmodifiable(_alerts);

  Future<void> init() async {
    _isLoggedIn = await storage.isLoggedIn();
    _watchlist = await storage.getWatchlist();
    _alerts = await storage.getAlerts();
    notifyListeners();
  }

  Future<bool> login(String password) async {
    _isLoading = true;
    notifyListeners();

    await Future.delayed(const Duration(milliseconds: 400));

    final success = password == ApiService.appPassword;
    if (success) {
      _isLoggedIn = true;
      await storage.setLoggedIn(true);
    }

    _isLoading = false;
    notifyListeners();
    return success;
  }

  Future<void> logout() async {
    _isLoggedIn = false;
    await storage.setLoggedIn(false);
    notifyListeners();
  }

  Future<void> refreshWatchlist() async {
    _watchlist = await storage.getWatchlist();
    notifyListeners();
  }

  Future<void> refreshAlerts() async {
    _alerts = await storage.getAlerts();
    notifyListeners();
  }

  Future<void> addToWatchlist(String symbol, String name) async {
    await storage.addToWatchlist(
      WatchlistItem(symbol: symbol, name: name, addedAt: DateTime.now()),
    );
    await refreshWatchlist();
  }

  Future<void> removeFromWatchlist(String symbol) async {
    await storage.removeFromWatchlist(symbol);
    await refreshWatchlist();
  }

  Future<bool> isInWatchlist(String symbol) {
    return storage.isInWatchlist(symbol);
  }

  Future<void> addAlert(StockAlert alert) async {
    await storage.addAlert(alert);
    await refreshAlerts();
  }

  Future<void> removeAlert(String id) async {
    await storage.removeAlert(id);
    await refreshAlerts();
  }

  Future<void> toggleAlert(String id, bool active) async {
    await storage.toggleAlert(id, active);
    await refreshAlerts();
  }
}
