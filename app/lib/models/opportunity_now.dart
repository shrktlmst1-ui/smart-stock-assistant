/// فرصة الآن — live confirmation engine signals.
library;

import '../utils/json_parse.dart';

class OpportunityNowSignal {
  final String symbol;
  final String name;
  final double price;
  final double changePercent;
  final double score;
  final String status;
  final String statusAr;
  final String opportunityType;
  final String appearedAt;
  final String expiresAt;
  final double entryZone;
  final double entryZoneLow;
  final double entryZoneHigh;
  final double stopLoss;
  final double target1;
  final double target2;
  final String riskLevel;
  final double riskRewardRatio;
  final int confirmedFactors;
  final int totalFactors;
  final int consecutiveConfirmations;
  final List<String> reasonsAr;
  final List<String> cancellationReasonsAr;
  final bool lateEntryWarning;
  final bool hasNewsCatalyst;
  final bool movementWithoutNews;
  final String dataTimestamp;
  final double dataAgeSeconds;
  // Extended-hours gap fields
  final String session;
  final double previousClose;
  final double extendedPrice;
  final double extendedGapPct;
  final int extendedVolume;
  final double relativeVolume;
  final String catalystType;
  final String catalystTitleAr;
  final String catalystSource;
  final String catalystPublishedAt;
  final String detectionStage;
  final List<String> riskFlagsAr;
  final String detectedAt;
  final bool hasConfirmedNews;
  final String volumeStatus;

  const OpportunityNowSignal({
    required this.symbol,
    required this.name,
    required this.price,
    required this.changePercent,
    required this.score,
    required this.status,
    required this.statusAr,
    required this.opportunityType,
    required this.appearedAt,
    required this.expiresAt,
    required this.entryZone,
    required this.entryZoneLow,
    required this.entryZoneHigh,
    required this.stopLoss,
    required this.target1,
    required this.target2,
    required this.riskLevel,
    required this.riskRewardRatio,
    required this.confirmedFactors,
    required this.totalFactors,
    required this.consecutiveConfirmations,
    required this.reasonsAr,
    required this.cancellationReasonsAr,
    required this.lateEntryWarning,
    required this.hasNewsCatalyst,
    required this.movementWithoutNews,
    required this.dataTimestamp,
    required this.dataAgeSeconds,
    this.session = '',
    this.previousClose = 0,
    this.extendedPrice = 0,
    this.extendedGapPct = 0,
    this.extendedVolume = 0,
    this.relativeVolume = 0,
    this.catalystType = '',
    this.catalystTitleAr = '',
    this.catalystSource = '',
    this.catalystPublishedAt = '',
    this.detectionStage = '',
    this.riskFlagsAr = const [],
    this.detectedAt = '',
    this.hasConfirmedNews = false,
    this.volumeStatus = 'KNOWN',
  });

  factory OpportunityNowSignal.fromJson(Map<String, dynamic> json) {
    final statusAr = readJsonString(json, ['status_ar', 'statusAr']);
    final status = readJsonString(json, ['status'], defaultValue: 'NONE');
    return OpportunityNowSignal(
      symbol: json['symbol'] as String? ?? '',
      name: json['name'] as String? ?? '',
      price: (json['price'] as num?)?.toDouble() ?? 0,
      changePercent: (json['change_percent'] as num?)?.toDouble() ?? 0,
      score: (json['score'] as num?)?.toDouble() ?? 0,
      status: status,
      statusAr: statusAr.isNotEmpty ? statusAr : _statusArFromCode(status),
      opportunityType: readJsonString(json, ['opportunity_type', 'opportunityType'], defaultValue: status),
      appearedAt: json['appeared_at'] as String? ?? '',
      expiresAt: json['expires_at'] as String? ?? '',
      entryZone: (json['entry_zone'] as num?)?.toDouble() ?? 0,
      entryZoneLow: (json['entry_zone_low'] as num?)?.toDouble() ?? 0,
      entryZoneHigh: (json['entry_zone_high'] as num?)?.toDouble() ?? 0,
      stopLoss: (json['stop_loss'] as num?)?.toDouble() ?? 0,
      target1: (json['target_1'] as num?)?.toDouble() ?? 0,
      target2: (json['target_2'] as num?)?.toDouble() ?? 0,
      riskLevel: json['risk_level'] as String? ?? 'مرتفع',
      riskRewardRatio: (json['risk_reward_ratio'] as num?)?.toDouble() ?? 0,
      confirmedFactors: readJsonInt(json, ['confirmed_factors', 'confirmedFactors']),
      totalFactors: readJsonInt(json, ['total_factors', 'totalFactors'], defaultValue: 17),
      consecutiveConfirmations: readJsonInt(json, ['consecutive_confirmations', 'consecutiveConfirmations']),
      reasonsAr: (json['reasons_ar'] as List?)?.map((e) => e.toString()).toList() ?? [],
      cancellationReasonsAr: (json['cancellation_reasons_ar'] as List?)?.map((e) => e.toString()).toList() ?? [],
      lateEntryWarning: readJsonBool(json, ['late_entry_warning', 'lateEntryWarning']),
      hasNewsCatalyst: readJsonBool(json, ['has_news_catalyst', 'hasNewsCatalyst']),
      movementWithoutNews: readJsonBool(json, ['movement_without_news', 'movementWithoutNews']),
      dataTimestamp: readJsonString(json, ['data_timestamp', 'dataTimestamp']),
      dataAgeSeconds: (json['data_age_seconds'] as num?)?.toDouble() ?? 0,
      session: readJsonString(json, ['session']),
      previousClose: (json['previous_close'] as num?)?.toDouble() ?? 0,
      extendedPrice: (json['extended_price'] as num?)?.toDouble() ?? 0,
      extendedGapPct: (json['extended_gap_pct'] as num?)?.toDouble() ?? 0,
      extendedVolume: readJsonInt(json, ['extended_volume', 'extendedVolume']),
      relativeVolume: (json['relative_volume'] as num?)?.toDouble() ?? 0,
      catalystType: readJsonString(json, ['catalyst_type', 'catalystType']),
      catalystTitleAr: readJsonString(json, ['catalyst_title_ar', 'catalystTitleAr']),
      catalystSource: readJsonString(json, ['catalyst_source', 'catalystSource']),
      catalystPublishedAt: readJsonString(json, ['catalyst_published_at', 'catalystPublishedAt']),
      detectionStage: readJsonString(json, ['detection_stage', 'detectionStage']),
      riskFlagsAr: (json['risk_flags_ar'] as List?)?.map((e) => e.toString()).toList() ?? [],
      detectedAt: readJsonString(json, ['detected_at', 'detectedAt']),
      hasConfirmedNews: readJsonBool(json, ['has_confirmed_news', 'hasConfirmedNews']),
      volumeStatus: readJsonString(json, ['volume_status', 'volumeStatus'], defaultValue: 'KNOWN'),
    );
  }

  bool get isValidExtendedAlert =>
      price > 0 && (extendedGapPct > 0 || detectionStage.isNotEmpty);

  bool get volumeUnknown => volumeStatus.toUpperCase() == 'UNKNOWN';

  static String _statusArFromCode(String code) {
    switch (code) {
      case 'NOW':
        return 'فرصة الآن';
      case 'READY':
        return 'استعد';
      case 'WATCH':
        return 'مراقبة';
      case 'CANCELLED':
        return 'أُلغيت';
      default:
        return 'لا توجد فرصة مكتملة الآن';
    }
  }

  bool get isValid => price > 0 && score > 0;

  bool get isOpportunityNow => status == 'NOW';

  bool get isReady => status == 'READY';

  bool get isWatch => status == 'WATCH';

  bool get isCancelled => status == 'CANCELLED';

  bool get isExtendedGap => extendedGapPct > 0 || detectionStage.isNotEmpty;

  String get sessionLabelAr {
    switch (session) {
      case 'PRE_MARKET':
        return 'قبل الافتتاح';
      case 'AFTER_HOURS':
        return 'بعد الإغلاق';
      default:
        return '';
    }
  }
}

class OpportunityNowResponse {
  final String status;
  final String statusAr;
  final String marketStatus;
  final bool marketOpen;
  final int scanIntervalSeconds;
  final String message;
  final String liveSource;
  final bool wsConnected;
  final int monitorPoolSize;
  final List<OpportunityNowSignal> signals;
  final OpportunityNowSignal? topSignal;
  final OpportunityNowSignal? extendedAlert;

  const OpportunityNowResponse({
    required this.status,
    required this.statusAr,
    required this.marketStatus,
    required this.marketOpen,
    required this.scanIntervalSeconds,
    required this.message,
    required this.liveSource,
    required this.wsConnected,
    required this.monitorPoolSize,
    required this.signals,
    required this.topSignal,
    this.extendedAlert,
  });

  factory OpportunityNowResponse.fromJson(Map<String, dynamic> json) {
    OpportunityNowSignal? top;
    final rawTop = json['top_signal'];
    if (rawTop is Map<String, dynamic>) {
      top = OpportunityNowSignal.fromJson(rawTop);
      if (!top.isValid) top = null;
    }

    OpportunityNowSignal? extended;
    final rawExtended = json['extended_alert'] ?? json['extendedAlert'];
    if (rawExtended is Map<String, dynamic>) {
      extended = OpportunityNowSignal.fromJson(rawExtended);
      if (!extended.isValidExtendedAlert) extended = null;
    }

    final rawSignals = json['signals'] as List? ?? [];
    final signals = rawSignals
        .map((e) => OpportunityNowSignal.fromJson(e as Map<String, dynamic>))
        .where((s) => s.isValid)
        .toList();

    final status = readJsonString(json, ['status'], defaultValue: 'NONE');
    final statusAr = readJsonString(json, ['status_ar', 'statusAr']);

    return OpportunityNowResponse(
      status: status,
      statusAr: statusAr.isNotEmpty ? statusAr : OpportunityNowSignal._statusArFromCode(status),
      marketStatus: readJsonString(json, ['market_status', 'marketStatus'], defaultValue: 'CLOSED'),
      marketOpen: readJsonBool(json, ['market_open', 'marketOpen']),
      scanIntervalSeconds: readJsonInt(
        json,
        ['scan_interval_seconds', 'scanIntervalSeconds'],
        defaultValue: 15,
      ),
      message: readJsonString(json, ['message']),
      liveSource: readJsonString(json, ['live_source', 'liveSource'], defaultValue: 'rest'),
      wsConnected: readJsonBool(json, ['ws_connected', 'wsConnected']),
      monitorPoolSize: readJsonInt(json, ['monitor_pool_size', 'monitorPoolSize']),
      signals: signals,
      topSignal: top,
      extendedAlert: extended,
    );
  }

  bool get hasExtendedAlert => extendedAlert != null;

  bool get hasNoOpportunity => status == 'NONE' && topSignal == null;

  OpportunityNowSignal? get displayTop {
    if (topSignal != null && topSignal!.isValid) return topSignal;
    for (final s in signals) {
      if (s.isOpportunityNow || s.isReady || s.isWatch) return s;
    }
    return null;
  }
}
