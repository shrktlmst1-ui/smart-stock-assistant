/// Market Pulse models — نبض السوق الذكي.
library;

import '../utils/json_parse.dart';
class MarketPulseHealth {
  final bool enabled;
  final String status;
  final bool hasApiKey;
  final int subscribedSymbols;
  final int maxSymbols;
  final bool streamConnected;
  final String? lastNewsFetch;
  final String message;

  const MarketPulseHealth({
    required this.enabled,
    required this.status,
    required this.hasApiKey,
    required this.subscribedSymbols,
    required this.maxSymbols,
    required this.streamConnected,
    this.lastNewsFetch,
    required this.message,
  });

  factory MarketPulseHealth.fromJson(Map<String, dynamic> json) {
    return MarketPulseHealth(
      enabled: readJsonBool(json, ['enabled', 'is_enabled', 'market_pulse_enabled']),
      status: readJsonString(json, ['status'], defaultValue: 'disabled'),
      hasApiKey: readJsonBool(json, ['has_api_key', 'hasApiKey', 'has_api_key_configured']),
      subscribedSymbols: readJsonInt(json, ['subscribed_symbols', 'subscribedSymbols']),
      maxSymbols: readJsonInt(json, ['max_symbols', 'maxSymbols'], defaultValue: 50),
      streamConnected: readJsonBool(json, ['stream_connected', 'streamConnected']),
      lastNewsFetch: json['last_news_fetch'] as String? ?? json['lastNewsFetch'] as String?,
      message: readJsonString(json, ['message']),
    );
  }

  bool get isActive => enabled || (status != 'disabled' && status.isNotEmpty);
}

class CatalystInfo {
  final String headline;
  final String sentiment;
  final String triggerType;
  final double newsAgeSeconds;
  final List<String> symbols;
  final String providerId;

  const CatalystInfo({
    required this.headline,
    required this.sentiment,
    required this.triggerType,
    required this.newsAgeSeconds,
    required this.symbols,
    required this.providerId,
  });

  factory CatalystInfo.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const CatalystInfo(
        headline: '',
        sentiment: 'neutral',
        triggerType: '',
        newsAgeSeconds: 0,
        symbols: [],
        providerId: '',
      );
    }
    return CatalystInfo(
      headline: json['headline'] as String? ?? '',
      sentiment: json['sentiment'] as String? ?? 'neutral',
      triggerType: json['trigger_type'] as String? ?? '',
      newsAgeSeconds: (json['news_age_seconds'] as num?)?.toDouble() ?? 0,
      symbols: (json['symbols'] as List?)?.map((e) => e.toString()).toList() ?? [],
      providerId: json['provider_id'] as String? ?? '',
    );
  }
}

class MarketPulseAlert {
  final String symbol;
  final double score;
  final String decision;
  final CatalystInfo catalyst;
  final String headline;
  final double newsAgeSeconds;
  final double estimatedBuyPressure;
  final double rvol;
  final double dollarVolumeAcceleration;
  final double spreadBps;
  final double price;
  final double vwap;
  final double entry;
  final double stopLoss;
  final List<double> targets;
  final List<String> riskFlags;
  final String dataTimestamp;
  final bool isLive;
  final String expiresAt;
  final List<String> reasonsAr;
  final double catalystScore;
  final double liquidityScore;
  final double priceConfirmationScore;
  final double riskPenalty;
  final bool isHalted;

  const MarketPulseAlert({
    required this.symbol,
    required this.score,
    required this.decision,
    required this.catalyst,
    required this.headline,
    required this.newsAgeSeconds,
    required this.estimatedBuyPressure,
    required this.rvol,
    required this.dollarVolumeAcceleration,
    required this.spreadBps,
    required this.price,
    required this.vwap,
    required this.entry,
    required this.stopLoss,
    required this.targets,
    required this.riskFlags,
    required this.dataTimestamp,
    required this.isLive,
    required this.expiresAt,
    required this.reasonsAr,
    required this.catalystScore,
    required this.liquidityScore,
    required this.priceConfirmationScore,
    required this.riskPenalty,
    required this.isHalted,
  });

  factory MarketPulseAlert.fromJson(Map<String, dynamic> json) {
    return MarketPulseAlert(
      symbol: json['symbol'] as String? ?? '',
      score: (json['score'] as num?)?.toDouble() ?? 0,
      decision: json['decision'] as String? ?? 'AVOID',
      catalyst: CatalystInfo.fromJson(json['catalyst'] as Map<String, dynamic>?),
      headline: json['headline'] as String? ?? '',
      newsAgeSeconds: (json['news_age_seconds'] as num?)?.toDouble() ?? 0,
      estimatedBuyPressure: (json['estimated_buy_pressure'] as num?)?.toDouble() ?? 0,
      rvol: (json['rvol'] as num?)?.toDouble() ?? 0,
      dollarVolumeAcceleration: (json['dollar_volume_acceleration'] as num?)?.toDouble() ?? 0,
      spreadBps: (json['spread_bps'] as num?)?.toDouble() ?? 0,
      price: (json['price'] as num?)?.toDouble() ?? 0,
      vwap: (json['vwap'] as num?)?.toDouble() ?? 0,
      entry: (json['entry'] as num?)?.toDouble() ?? 0,
      stopLoss: (json['stop_loss'] as num?)?.toDouble() ?? 0,
      targets: (json['targets'] as List?)?.map((e) => (e as num).toDouble()).toList() ?? [],
      riskFlags: (json['risk_flags'] as List?)?.map((e) => e.toString()).toList() ?? [],
      dataTimestamp: readJsonString(json, ['data_timestamp', 'dataTimestamp']),
      isLive: readJsonBool(json, ['is_live', 'isLive']),
      expiresAt: readJsonString(json, ['expires_at', 'expiresAt']),
      reasonsAr: (json['reasons_ar'] as List?)?.map((e) => e.toString()).toList() ?? [],
      catalystScore: (json['catalyst_score'] as num?)?.toDouble() ?? 0,
      liquidityScore: (json['liquidity_score'] as num?)?.toDouble() ?? 0,
      priceConfirmationScore: (json['price_confirmation_score'] as num?)?.toDouble() ?? 0,
      riskPenalty: (json['risk_penalty'] as num?)?.toDouble() ?? 0,
      isHalted: readJsonBool(json, ['is_halted', 'isHalted']),
    );
  }

  bool get isExpired => decision == 'EXPIRED';

  bool get isStale => !isLive || decision == 'EXPIRED';

  /// UI-safe decision — downgrade ENTER_NOW when stale/expired.
  String get displayDecision {
    if (isExpired) return 'EXPIRED';
    if (!isLive && decision == 'ENTER_NOW') return 'WAIT';
    return decision;
  }

  double? get riskRewardRatio {
    if (entry <= 0 || stopLoss <= 0 || targets.isEmpty) return null;
    final risk = (entry - stopLoss).abs();
    if (risk <= 0) return null;
    return ((targets.first - entry).abs()) / risk;
  }
}

class MarketPulseListResponse {
  final bool enabled;
  final List<MarketPulseAlert> alerts;
  final int count;

  const MarketPulseListResponse({
    required this.enabled,
    required this.alerts,
    required this.count,
  });

  factory MarketPulseListResponse.fromJson(Map<String, dynamic> json) {
    final raw = json['alerts'] as List? ?? [];
    return MarketPulseListResponse(
      enabled: readJsonBool(json, ['enabled', 'is_enabled', 'market_pulse_enabled']),
      alerts: raw.map((e) => MarketPulseAlert.fromJson(e as Map<String, dynamic>)).toList(),
      count: readJsonInt(json, ['count'], defaultValue: raw.length),
    );
  }
}

enum PulseServiceState {
  loading,
  live,
  delayed,
  stopped,
  stale,
  disabled,
  error,
  empty,
}
