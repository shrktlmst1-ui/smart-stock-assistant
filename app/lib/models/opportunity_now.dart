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
  final String jumpAlertId;
  final bool jumpQualified;
  final bool jumpAlertCreated;
  final String stageLifecycle;
  final String displayType;
  final double buyPressureScore;
  final int confluenceCount;
  final List<String> confluenceFactors;
  final double rvol;
  final double volumeAcceleration;
  // REAL_JUMP_ALERT wave KPI (display-only)
  final double realJumpMoveStartPrice;
  final String realJumpMoveStartTime;
  final double realJumpCurrentMovePct;
  final double realJumpFirstDetectedPrice;
  final double realJumpFirstDetectedPct;
  final String realJumpFirstDetectedTime;
  final double realJumpWavePeakPrice;
  final double realJumpWavePeakMovePct;
  final double realJumpPeakAfterDetectionPct;

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
    this.jumpAlertId = '',
    this.jumpQualified = false,
    this.jumpAlertCreated = false,
    this.stageLifecycle = '',
    this.displayType = '',
    this.buyPressureScore = 0,
    this.confluenceCount = 0,
    this.confluenceFactors = const [],
    this.rvol = 0,
    this.volumeAcceleration = 0,
    this.realJumpMoveStartPrice = 0,
    this.realJumpMoveStartTime = '',
    this.realJumpCurrentMovePct = 0,
    this.realJumpFirstDetectedPrice = 0,
    this.realJumpFirstDetectedPct = 0,
    this.realJumpFirstDetectedTime = '',
    this.realJumpWavePeakPrice = 0,
    this.realJumpWavePeakMovePct = 0,
    this.realJumpPeakAfterDetectionPct = 0,
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
      jumpAlertId: readJsonString(json, ['jump_alert_id', 'jumpAlertId']),
      jumpQualified: readJsonBool(json, ['jump_qualified', 'jumpQualified']),
      jumpAlertCreated: readJsonBool(json, ['jump_alert_created', 'jumpAlertCreated']),
      stageLifecycle: readJsonString(json, ['stage_lifecycle', 'stageLifecycle']),
      displayType: readJsonString(json, ['display_type', 'displayType']),
      buyPressureScore: (json['buy_pressure_score'] as num?)?.toDouble() ??
          (json['buyPressureScore'] as num?)?.toDouble() ??
          0,
      confluenceCount: readJsonInt(json, ['confluence_count', 'confluenceCount']),
      confluenceFactors: (json['confluence_factors'] as List? ?? json['confluenceFactors'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      rvol: (json['rvol'] as num?)?.toDouble() ?? 0,
      volumeAcceleration: (json['volume_acceleration'] as num?)?.toDouble() ??
          (json['volumeAcceleration'] as num?)?.toDouble() ??
          0,
      realJumpMoveStartPrice: (json['real_jump_move_start_price'] as num?)?.toDouble() ??
          (json['realJumpMoveStartPrice'] as num?)?.toDouble() ??
          0,
      realJumpMoveStartTime: readJsonString(json, ['real_jump_move_start_time', 'realJumpMoveStartTime']),
      realJumpCurrentMovePct: (json['real_jump_current_move_pct'] as num?)?.toDouble() ??
          (json['realJumpCurrentMovePct'] as num?)?.toDouble() ??
          0,
      realJumpFirstDetectedPrice: (json['real_jump_first_detected_price'] as num?)?.toDouble() ??
          (json['realJumpFirstDetectedPrice'] as num?)?.toDouble() ??
          0,
      realJumpFirstDetectedPct: (json['real_jump_first_detected_pct'] as num?)?.toDouble() ??
          (json['realJumpFirstDetectedPct'] as num?)?.toDouble() ??
          0,
      realJumpFirstDetectedTime: readJsonString(json, ['real_jump_first_detected_time', 'realJumpFirstDetectedTime']),
      realJumpWavePeakPrice: (json['real_jump_wave_peak_price'] as num?)?.toDouble() ??
          (json['realJumpWavePeakPrice'] as num?)?.toDouble() ??
          0,
      realJumpWavePeakMovePct: (json['real_jump_wave_peak_move_pct'] as num?)?.toDouble() ??
          (json['realJumpWavePeakMovePct'] as num?)?.toDouble() ??
          0,
      realJumpPeakAfterDetectionPct: (json['real_jump_peak_after_detection_pct'] as num?)?.toDouble() ??
          (json['realJumpPeakAfterDetectionPct'] as num?)?.toDouble() ??
          0,
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

  bool get isQualifiedJumpAlert =>
      jumpAlertId.isNotEmpty &&
      jumpQualified &&
      jumpAlertCreated &&
      price > 0 &&
      changePercent > 0;

  bool get isRealNewsJump =>
      isValidExtendedAlert && detectionStage.isNotEmpty && extendedGapPct > 0;

  bool get isExtendedGap => extendedGapPct > 0 || detectionStage.isNotEmpty;

  bool get isRealWatchJump =>
      isValid &&
      changePercent > 0 &&
      !isExtendedGap &&
      (isWatch || isReady || isOpportunityNow);

  bool get isStrongBuyWatch => displayType == 'STRONG_BUY_WATCH';

  bool get isJumpAlertDisplay => displayType == 'JUMP_ALERT';

  bool get isRealJumpAlertDisplay => displayType == 'REAL_JUMP_ALERT';

  bool get isDisplayableBuyPressure =>
      isStrongBuyWatch || isJumpAlertDisplay || isQualifiedJumpAlert;

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
  final List<OpportunityNowSignal> jumpAlerts;
  final List<OpportunityNowSignal> displaySignals;
  final List<OpportunityNowSignal> realJumpAlerts;
  final String jumpEngineStatus;

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
    this.jumpAlerts = const [],
    this.displaySignals = const [],
    this.realJumpAlerts = const [],
    this.jumpEngineStatus = 'ARMED',
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
        .where((s) => s.isValid || s.isQualifiedJumpAlert)
        .toList();

    final rawJumpAlerts = json['jump_alerts'] ?? json['jumpAlerts'];
    final jumpAlerts = rawJumpAlerts is List
        ? rawJumpAlerts
            .map((e) => OpportunityNowSignal.fromJson(e as Map<String, dynamic>))
            .where((s) => s.isQualifiedJumpAlert)
            .toList()
        : <OpportunityNowSignal>[];

    final rawDisplay = json['display_signals'] ?? json['displaySignals'];
    final displaySignals = rawDisplay is List
        ? rawDisplay
            .map((e) => OpportunityNowSignal.fromJson(e as Map<String, dynamic>))
            .where((s) => s.isDisplayableBuyPressure)
            .toList()
        : <OpportunityNowSignal>[];

    final rawRealJump = json['real_jump_alerts'] ?? json['realJumpAlerts'];
    final realJumpAlerts = rawRealJump is List
        ? rawRealJump
            .map((e) => OpportunityNowSignal.fromJson(e as Map<String, dynamic>))
            .where((s) => s.isRealJumpAlertDisplay)
            .toList()
        : <OpportunityNowSignal>[];

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
      jumpAlerts: jumpAlerts,
      displaySignals: displaySignals,
      realJumpAlerts: realJumpAlerts,
      jumpEngineStatus: readJsonString(
        json,
        ['jump_engine_status', 'jumpEngineStatus'],
        defaultValue: 'ARMED',
      ),
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

  /// Strong real buying only — STRONG_BUY_WATCH + JUMP_ALERT from backend filter.
  List<OpportunityNowSignal> confirmedJumps({int limit = 3}) {
    if (displaySignals.isNotEmpty) {
      return displaySignals.take(limit).toList();
    }

    final out = <OpportunityNowSignal>[];
    final seen = <String>{};

    for (final ja in jumpAlerts) {
      if (!ja.isDisplayableBuyPressure) continue;
      final key = ja.symbol.toUpperCase();
      if (seen.contains(key)) continue;
      out.add(ja);
      seen.add(key);
    }

    for (final s in signals) {
      if (!s.isDisplayableBuyPressure) continue;
      final key = s.symbol.toUpperCase();
      if (seen.contains(key)) continue;
      out.add(s);
      seen.add(key);
      if (out.length >= limit) break;
    }

    out.sort((a, b) => b.buyPressureScore.compareTo(a.buyPressureScore));
    return out.take(limit).toList();
  }

  /// REAL_JUMP_ALERT first (no cap), then existing STRONG_BUY_WATCH / JUMP_ALERT cards unchanged.
  List<OpportunityNowSignal> jumpSectionItems({int limit = 3}) {
    final real = realJumpAlerts.toList();
    final seen = real.map((s) => s.symbol.toUpperCase()).toSet();
    final rest = confirmedJumps(limit: limit)
        .where((s) => !seen.contains(s.symbol.toUpperCase()))
        .toList();
    final slots = limit > 0 ? (limit - real.length).clamp(0, limit) : rest.length;
    return [...real, ...rest.take(slots)];
  }

  bool get hasConfirmedJumps => jumpSectionItems().isNotEmpty;
}
