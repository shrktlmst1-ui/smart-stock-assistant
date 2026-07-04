class SignalExplanationItem {
  final String label;
  final bool passed;

  SignalExplanationItem({required this.label, required this.passed});

  factory SignalExplanationItem.fromJson(Map<String, dynamic> json) {
    return SignalExplanationItem(
      label: json['label'] as String? ?? '',
      passed: json['passed'] as bool? ?? false,
    );
  }
}

class SignalAnalyticsRecord {
  final int id;
  final String symbol;
  final String signal;
  final String signalDate;
  final String signalTime;
  final String timeframe;
  final double aiScore;
  final double confidenceScore;
  final double entryPrice;
  final double stopLoss;
  final double target1;
  final double target2;
  final double target3;
  final String trendDirection;
  final String marketStatus;
  final String sector;
  final String industry;
  final String trackStatus;
  final int tradeQualityStars;
  final String tradeQualityLabel;
  final List<SignalExplanationItem> explanation;
  final double trendStrength;
  final double relativeVolume;
  final String? failureReason;
  final double profitPct;
  final double? exitPrice;
  final String createdAt;
  final String? closedAt;
  final int holdingSeconds;

  SignalAnalyticsRecord({
    required this.id,
    required this.symbol,
    required this.signal,
    required this.signalDate,
    required this.signalTime,
    required this.timeframe,
    required this.aiScore,
    required this.confidenceScore,
    required this.entryPrice,
    required this.stopLoss,
    required this.target1,
    required this.target2,
    required this.target3,
    required this.trendDirection,
    required this.marketStatus,
    required this.sector,
    required this.industry,
    required this.trackStatus,
    required this.tradeQualityStars,
    required this.tradeQualityLabel,
    required this.explanation,
    required this.trendStrength,
    required this.relativeVolume,
    this.failureReason,
    required this.profitPct,
    this.exitPrice,
    required this.createdAt,
    this.closedAt,
    required this.holdingSeconds,
  });

  factory SignalAnalyticsRecord.fromJson(Map<String, dynamic> json) {
    final explanationRaw = json['explanation'] as List<dynamic>? ?? [];
    return SignalAnalyticsRecord(
      id: json['id'] as int? ?? 0,
      symbol: json['symbol'] as String? ?? '',
      signal: json['signal'] as String? ?? '',
      signalDate: json['signal_date'] as String? ?? '',
      signalTime: json['signal_time'] as String? ?? '',
      timeframe: json['timeframe'] as String? ?? 'live',
      aiScore: (json['ai_score'] as num?)?.toDouble() ?? 0,
      confidenceScore: (json['confidence_score'] as num?)?.toDouble() ?? 0,
      entryPrice: (json['entry_price'] as num?)?.toDouble() ?? 0,
      stopLoss: (json['stop_loss'] as num?)?.toDouble() ?? 0,
      target1: (json['target_1'] as num?)?.toDouble() ?? 0,
      target2: (json['target_2'] as num?)?.toDouble() ?? 0,
      target3: (json['target_3'] as num?)?.toDouble() ?? 0,
      trendDirection: json['trend_direction'] as String? ?? '',
      marketStatus: json['market_status'] as String? ?? '',
      sector: json['sector'] as String? ?? '',
      industry: json['industry'] as String? ?? '',
      trackStatus: json['track_status'] as String? ?? '',
      tradeQualityStars: json['trade_quality_stars'] as int? ?? 1,
      tradeQualityLabel: json['trade_quality_label'] as String? ?? '',
      explanation: explanationRaw
          .map((e) => SignalExplanationItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      trendStrength: (json['trend_strength'] as num?)?.toDouble() ?? 0,
      relativeVolume: (json['relative_volume'] as num?)?.toDouble() ?? 0,
      failureReason: json['failure_reason'] as String?,
      profitPct: (json['profit_pct'] as num?)?.toDouble() ?? 0,
      exitPrice: (json['exit_price'] as num?)?.toDouble(),
      createdAt: json['created_at'] as String? ?? '',
      closedAt: json['closed_at'] as String?,
      holdingSeconds: json['holding_seconds'] as int? ?? 0,
    );
  }

  String get qualityStars => '★' * tradeQualityStars + '☆' * (5 - tradeQualityStars);
}

class AnalyticsDashboard {
  final int totalSignals;
  final int winningSignals;
  final int losingSignals;
  final double winRatePct;
  final double averageProfitPct;
  final double averageLossPct;
  final double averageHoldingTimeHours;
  final String bestPerformingSector;
  final String bestPerformingTimeframe;
  final double highestAiScoreToday;
  final double highestConfidenceToday;
  final int openTracks;
  final int activeTracks;

  AnalyticsDashboard({
    required this.totalSignals,
    required this.winningSignals,
    required this.losingSignals,
    required this.winRatePct,
    required this.averageProfitPct,
    required this.averageLossPct,
    required this.averageHoldingTimeHours,
    required this.bestPerformingSector,
    required this.bestPerformingTimeframe,
    required this.highestAiScoreToday,
    required this.highestConfidenceToday,
    required this.openTracks,
    required this.activeTracks,
  });

  factory AnalyticsDashboard.fromJson(Map<String, dynamic> json) {
    return AnalyticsDashboard(
      totalSignals: json['total_signals'] as int? ?? 0,
      winningSignals: json['winning_signals'] as int? ?? 0,
      losingSignals: json['losing_signals'] as int? ?? 0,
      winRatePct: (json['win_rate_pct'] as num?)?.toDouble() ?? 0,
      averageProfitPct: (json['average_profit_pct'] as num?)?.toDouble() ?? 0,
      averageLossPct: (json['average_loss_pct'] as num?)?.toDouble() ?? 0,
      averageHoldingTimeHours:
          (json['average_holding_time_hours'] as num?)?.toDouble() ?? 0,
      bestPerformingSector: json['best_performing_sector'] as String? ?? '',
      bestPerformingTimeframe: json['best_performing_timeframe'] as String? ?? '',
      highestAiScoreToday: (json['highest_ai_score_today'] as num?)?.toDouble() ?? 0,
      highestConfidenceToday:
          (json['highest_confidence_today'] as num?)?.toDouble() ?? 0,
      openTracks: json['open_tracks'] as int? ?? 0,
      activeTracks: json['active_tracks'] as int? ?? 0,
    );
  }
}

class PerformanceReport {
  final int todaySignals;
  final int weekSignals;
  final int monthSignals;
  final int overallTotal;
  final double winRate;
  final double averageReturnPct;
  final double averageDrawdownPct;
  final String bestSymbol;
  final String worstSymbol;
  final int wins;
  final int losses;
  final AnalyticsDashboard dashboard;

  PerformanceReport({
    required this.todaySignals,
    required this.weekSignals,
    required this.monthSignals,
    required this.overallTotal,
    required this.winRate,
    required this.averageReturnPct,
    required this.averageDrawdownPct,
    required this.bestSymbol,
    required this.worstSymbol,
    required this.wins,
    required this.losses,
    required this.dashboard,
  });

  factory PerformanceReport.fromJson(Map<String, dynamic> json) {
    return PerformanceReport(
      todaySignals: json['today_signals'] as int? ?? 0,
      weekSignals: json['week_signals'] as int? ?? 0,
      monthSignals: json['month_signals'] as int? ?? 0,
      overallTotal: json['overall_total'] as int? ?? 0,
      winRate: (json['win_rate'] as num?)?.toDouble() ?? 0,
      averageReturnPct: (json['average_return_pct'] as num?)?.toDouble() ?? 0,
      averageDrawdownPct: (json['average_drawdown_pct'] as num?)?.toDouble() ?? 0,
      bestSymbol: json['best_symbol'] as String? ?? '',
      worstSymbol: json['worst_symbol'] as String? ?? '',
      wins: json['wins'] as int? ?? 0,
      losses: json['losses'] as int? ?? 0,
      dashboard: AnalyticsDashboard.fromJson(
        json['dashboard'] as Map<String, dynamic>? ?? {},
      ),
    );
  }
}

class RankedSignalsResponse {
  final List<SignalAnalyticsRecord> signals;
  final AnalyticsDashboard dashboard;

  RankedSignalsResponse({required this.signals, required this.dashboard});

  factory RankedSignalsResponse.fromJson(Map<String, dynamic> json) {
    final list = json['signals'] as List<dynamic>? ?? [];
    return RankedSignalsResponse(
      signals: list
          .map((e) => SignalAnalyticsRecord.fromJson(e as Map<String, dynamic>))
          .toList(),
      dashboard: AnalyticsDashboard.fromJson(
        json['dashboard'] as Map<String, dynamic>? ?? {},
      ),
    );
  }
}
