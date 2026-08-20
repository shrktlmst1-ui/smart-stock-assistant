/// فرصة الآن — sub-\$10 momentum signals from scanner cache.
library;

class OpportunityNowSignal {
  final String symbol;
  final String name;
  final double price;
  final double changePercent;
  final double score;
  final String status;
  final String appearedAt;
  final String expiresAt;
  final double entryZone;
  final double stopLoss;
  final double target1;
  final double target2;
  final String riskLevel;
  final List<String> reasonsAr;
  final bool lateEntryWarning;
  final bool hasNewsCatalyst;
  final bool movementWithoutNews;
  final String dataTimestamp;

  const OpportunityNowSignal({
    required this.symbol,
    required this.name,
    required this.price,
    required this.changePercent,
    required this.score,
    required this.status,
    required this.appearedAt,
    required this.expiresAt,
    required this.entryZone,
    required this.stopLoss,
    required this.target1,
    required this.target2,
    required this.riskLevel,
    required this.reasonsAr,
    required this.lateEntryWarning,
    required this.hasNewsCatalyst,
    required this.movementWithoutNews,
    required this.dataTimestamp,
  });

  factory OpportunityNowSignal.fromJson(Map<String, dynamic> json) {
    return OpportunityNowSignal(
      symbol: json['symbol'] as String? ?? '',
      name: json['name'] as String? ?? '',
      price: (json['price'] as num?)?.toDouble() ?? 0,
      changePercent: (json['change_percent'] as num?)?.toDouble() ?? 0,
      score: (json['score'] as num?)?.toDouble() ?? 0,
      status: json['status'] as String? ?? 'تجنب',
      appearedAt: json['appeared_at'] as String? ?? '',
      expiresAt: json['expires_at'] as String? ?? '',
      entryZone: (json['entry_zone'] as num?)?.toDouble() ?? 0,
      stopLoss: (json['stop_loss'] as num?)?.toDouble() ?? 0,
      target1: (json['target_1'] as num?)?.toDouble() ?? 0,
      target2: (json['target_2'] as num?)?.toDouble() ?? 0,
      riskLevel: json['risk_level'] as String? ?? 'مرتفع',
      reasonsAr: (json['reasons_ar'] as List?)?.map((e) => e.toString()).toList() ?? [],
      lateEntryWarning: json['late_entry_warning'] as bool? ?? false,
      hasNewsCatalyst: json['has_news_catalyst'] as bool? ?? false,
      movementWithoutNews: json['movement_without_news'] as bool? ?? false,
      dataTimestamp: json['data_timestamp'] as String? ?? '',
    );
  }

  bool get isValid => price > 0 && score > 0;

  bool get isOpportunityNow => status == 'فرصة الآن';

  bool get isMarketClosedOnly => status != 'فرصة الآن' && score >= 85;
}

class OpportunityNowResponse {
  final String marketStatus;
  final bool marketOpen;
  final int scanIntervalSeconds;
  final String message;
  final List<OpportunityNowSignal> signals;
  final OpportunityNowSignal? topSignal;

  const OpportunityNowResponse({
    required this.marketStatus,
    required this.marketOpen,
    required this.scanIntervalSeconds,
    required this.message,
    required this.signals,
    required this.topSignal,
  });

  factory OpportunityNowResponse.fromJson(Map<String, dynamic> json) {
    OpportunityNowSignal? top;
    final rawTop = json['top_signal'];
    if (rawTop is Map<String, dynamic>) {
      top = OpportunityNowSignal.fromJson(rawTop);
      if (!top.isValid) top = null;
    }

    final rawSignals = json['signals'] as List? ?? [];
    final signals = rawSignals
        .map((e) => OpportunityNowSignal.fromJson(e as Map<String, dynamic>))
        .where((s) => s.isValid)
        .toList();

    return OpportunityNowResponse(
      marketStatus: json['market_status'] as String? ?? 'CLOSED',
      marketOpen: json['market_open'] as bool? ?? false,
      scanIntervalSeconds: json['scan_interval_seconds'] as int? ?? 15,
      message: json['message'] as String? ?? '',
      signals: signals,
      topSignal: top,
    );
  }

  OpportunityNowSignal? get displayTop {
    if (topSignal != null && topSignal!.isValid) return topSignal;
    for (final s in signals) {
      if (s.isOpportunityNow) return s;
    }
    return null;
  }
}
