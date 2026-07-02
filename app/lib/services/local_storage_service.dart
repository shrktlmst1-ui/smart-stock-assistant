import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/alert.dart';

class LocalStorageService {
  static const _watchlistKey = 'watchlist';
  static const _alertsKey = 'alerts';
  static const _loggedInKey = 'is_logged_in';

  Future<bool> isLoggedIn() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_loggedInKey) ?? false;
  }

  Future<void> setLoggedIn(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_loggedInKey, value);
  }

  Future<List<WatchlistItem>> getWatchlist() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_watchlistKey);
    if (raw == null) return [];

    final list = jsonDecode(raw) as List;
    return list
        .map((e) => WatchlistItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> saveWatchlist(List<WatchlistItem> items) async {
    final prefs = await SharedPreferences.getInstance();
    final encoded = jsonEncode(items.map((e) => e.toJson()).toList());
    await prefs.setString(_watchlistKey, encoded);
  }

  Future<void> addToWatchlist(WatchlistItem item) async {
    final items = await getWatchlist();
    if (items.any((i) => i.symbol == item.symbol)) return;
    items.add(item);
    await saveWatchlist(items);
  }

  Future<void> removeFromWatchlist(String symbol) async {
    final items = await getWatchlist();
    items.removeWhere((i) => i.symbol == symbol);
    await saveWatchlist(items);
  }

  Future<bool> isInWatchlist(String symbol) async {
    final items = await getWatchlist();
    return items.any((i) => i.symbol == symbol);
  }

  Future<List<StockAlert>> getAlerts() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_alertsKey);
    if (raw == null) return [];

    final list = jsonDecode(raw) as List;
    return list
        .map((e) => StockAlert.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> saveAlerts(List<StockAlert> alerts) async {
    final prefs = await SharedPreferences.getInstance();
    final encoded = jsonEncode(alerts.map((e) => e.toJson()).toList());
    await prefs.setString(_alertsKey, encoded);
  }

  Future<void> addAlert(StockAlert alert) async {
    final alerts = await getAlerts();
    alerts.add(alert);
    await saveAlerts(alerts);
  }

  Future<void> removeAlert(String id) async {
    final alerts = await getAlerts();
    alerts.removeWhere((a) => a.id == id);
    await saveAlerts(alerts);
  }

  Future<void> toggleAlert(String id, bool isActive) async {
    final alerts = await getAlerts();
    final index = alerts.indexWhere((a) => a.id == id);
    if (index == -1) return;
    alerts[index] = alerts[index].copyWith(isActive: isActive);
    await saveAlerts(alerts);
  }
}
