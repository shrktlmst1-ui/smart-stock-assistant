import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/market_pulse.dart';
import '../models/opportunity_now.dart';

/// Persists last successful home-screen payload so Safari/Web resume shows data instantly.
class HomeCachedSnapshot {
  final DateTime fetchedAt;
  final Map<String, dynamic>? opportunityRaw;
  final Map<String, dynamic>? pulseListRaw;
  final Map<String, dynamic>? pulseHealthRaw;

  const HomeCachedSnapshot({
    required this.fetchedAt,
    this.opportunityRaw,
    this.pulseListRaw,
    this.pulseHealthRaw,
  });

  OpportunityNowResponse? get opportunity {
    final raw = opportunityRaw;
    if (raw == null) return null;
    try {
      return OpportunityNowResponse.fromJson(raw);
    } catch (_) {
      return null;
    }
  }

  MarketPulseListResponse? get pulseList {
    final raw = pulseListRaw;
    if (raw == null) return null;
    try {
      return MarketPulseListResponse.fromJson(raw);
    } catch (_) {
      return null;
    }
  }

  MarketPulseHealth? get pulseHealth {
    final raw = pulseHealthRaw;
    if (raw == null) return null;
    try {
      return MarketPulseHealth.fromJson(raw);
    } catch (_) {
      return null;
    }
  }

  bool get hasDisplayableOpportunity {
    final opp = opportunity;
    if (opp == null) return false;
    return opp.confirmedJumps().isNotEmpty || opp.displayTop != null;
  }

  Map<String, dynamic> toJson() => {
        'fetched_at_ms': fetchedAt.millisecondsSinceEpoch,
        if (opportunityRaw != null) 'opportunity_raw': opportunityRaw,
        if (pulseListRaw != null) 'pulse_list_raw': pulseListRaw,
        if (pulseHealthRaw != null) 'pulse_health_raw': pulseHealthRaw,
      };

  factory HomeCachedSnapshot.fromJson(Map<String, dynamic> json) {
    return HomeCachedSnapshot(
      fetchedAt: DateTime.fromMillisecondsSinceEpoch(
        readJsonInt(json, ['fetched_at_ms', 'fetchedAtMs']),
      ),
      opportunityRaw: json['opportunity_raw'] as Map<String, dynamic>? ??
          json['opportunityRaw'] as Map<String, dynamic>?,
      pulseListRaw: json['pulse_list_raw'] as Map<String, dynamic>? ??
          json['pulseListRaw'] as Map<String, dynamic>?,
      pulseHealthRaw: json['pulse_health_raw'] as Map<String, dynamic>? ??
          json['pulseHealthRaw'] as Map<String, dynamic>?,
    );
  }
}

int readJsonInt(Map<String, dynamic> json, List<String> keys, {int defaultValue = 0}) {
  for (final key in keys) {
    final value = json[key];
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) {
      final parsed = int.tryParse(value);
      if (parsed != null) return parsed;
    }
  }
  return defaultValue;
}

class HomeScreenCache {
  static const _prefsKey = 'home_screen_snapshot_v1';

  static HomeCachedSnapshot? _memory;

  static HomeCachedSnapshot? get memorySnapshot => _memory;

  static void seedMemory(HomeCachedSnapshot snapshot) {
    if (_memory != null && snapshot.fetchedAt.isBefore(_memory!.fetchedAt)) {
      return;
    }
    _memory = snapshot;
  }

  static Future<HomeCachedSnapshot?> load() async {
    if (_memory != null) return _memory;
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_prefsKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      final snapshot = HomeCachedSnapshot.fromJson(decoded);
      _memory = snapshot;
      return snapshot;
    } catch (_) {
      return null;
    }
  }

  static Future<void> save(HomeCachedSnapshot snapshot) async {
    if (_memory != null && snapshot.fetchedAt.isBefore(_memory!.fetchedAt)) {
      return;
    }
    _memory = snapshot;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefsKey, jsonEncode(snapshot.toJson()));
    } catch (_) {
      // Keep in-memory cache even if persistence fails.
    }
  }

  static Future<void> clear() async {
    _memory = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_prefsKey);
  }
}
