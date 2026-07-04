class TradeTimelineEvent {
  final String eventTime;
  final String eventLabel;
  final double? price;

  TradeTimelineEvent({
    required this.eventTime,
    required this.eventLabel,
    this.price,
  });

  factory TradeTimelineEvent.fromJson(Map<String, dynamic> json) {
    return TradeTimelineEvent(
      eventTime: json['event_time'] as String? ?? '',
      eventLabel: json['event_label'] as String? ?? '',
      price: (json['price'] as num?)?.toDouble(),
    );
  }
}

class PostTradeAnalysis {
  final String finalResult;
  final double maxProfitPct;
  final double maxDrawdownPct;
  final double? highestPriceAfterEntry;
  final double? lowestPriceAfterEntry;
  final int? timeToTarget1Seconds;
  final int? timeToTarget2Seconds;
  final int? timeToTarget3Seconds;
  final int? timeToStopLossSeconds;
  final int tradeDurationSeconds;
  final String postTradeQuality;
  final double entryQualityScore;
  final double riskRewardRatio;

  PostTradeAnalysis({
    required this.finalResult,
    required this.maxProfitPct,
    required this.maxDrawdownPct,
    this.highestPriceAfterEntry,
    this.lowestPriceAfterEntry,
    this.timeToTarget1Seconds,
    this.timeToTarget2Seconds,
    this.timeToTarget3Seconds,
    this.timeToStopLossSeconds,
    required this.tradeDurationSeconds,
    required this.postTradeQuality,
    required this.entryQualityScore,
    required this.riskRewardRatio,
  });

  factory PostTradeAnalysis.fromJson(Map<String, dynamic> json) {
    return PostTradeAnalysis(
      finalResult: json['final_result'] as String? ?? '',
      maxProfitPct: (json['max_profit_pct'] as num?)?.toDouble() ?? 0,
      maxDrawdownPct: (json['max_drawdown_pct'] as num?)?.toDouble() ?? 0,
      highestPriceAfterEntry: (json['highest_price_after_entry'] as num?)?.toDouble(),
      lowestPriceAfterEntry: (json['lowest_price_after_entry'] as num?)?.toDouble(),
      timeToTarget1Seconds: json['time_to_target_1_seconds'] as int?,
      timeToTarget2Seconds: json['time_to_target_2_seconds'] as int?,
      timeToTarget3Seconds: json['time_to_target_3_seconds'] as int?,
      timeToStopLossSeconds: json['time_to_stop_loss_seconds'] as int?,
      tradeDurationSeconds: json['trade_duration_seconds'] as int? ?? 0,
      postTradeQuality: json['post_trade_quality'] as String? ?? '',
      entryQualityScore: (json['entry_quality_score'] as num?)?.toDouble() ?? 0,
      riskRewardRatio: (json['risk_reward_ratio'] as num?)?.toDouble() ?? 0,
    );
  }

  String formatDuration(int seconds) {
    if (seconds < 60) return '${seconds}s';
    if (seconds < 3600) return '${seconds ~/ 60}m';
    return '${seconds ~/ 3600}h ${(seconds % 3600) ~/ 60}m';
  }
}

class TradeReplayDetail {
  final int signalId;
  final String symbol;
  final String signal;
  final String signalDate;
  final String signalTime;
  final double entryPrice;
  final double stopLoss;
  final double target1;
  final double target2;
  final double target3;
  final double aiScore;
  final double confidenceScore;
  final String timeframe;
  final String trackStatus;
  final List<TradeTimelineEvent> timeline;
  final PostTradeAnalysis? postTrade;
  final double liveMaxProfitPct;
  final double liveMaxDrawdownPct;
  final double entryQualityScore;
  final bool isClosed;

  TradeReplayDetail({
    required this.signalId,
    required this.symbol,
    required this.signal,
    required this.signalDate,
    required this.signalTime,
    required this.entryPrice,
    required this.stopLoss,
    required this.target1,
    required this.target2,
    required this.target3,
    required this.aiScore,
    required this.confidenceScore,
    required this.timeframe,
    required this.trackStatus,
    required this.timeline,
    this.postTrade,
    required this.liveMaxProfitPct,
    required this.liveMaxDrawdownPct,
    required this.entryQualityScore,
    required this.isClosed,
  });

  factory TradeReplayDetail.fromJson(Map<String, dynamic> json) {
    final timelineRaw = json['timeline'] as List<dynamic>? ?? [];
    return TradeReplayDetail(
      signalId: json['signal_id'] as int? ?? 0,
      symbol: json['symbol'] as String? ?? '',
      signal: json['signal'] as String? ?? '',
      signalDate: json['signal_date'] as String? ?? '',
      signalTime: json['signal_time'] as String? ?? '',
      entryPrice: (json['entry_price'] as num?)?.toDouble() ?? 0,
      stopLoss: (json['stop_loss'] as num?)?.toDouble() ?? 0,
      target1: (json['target_1'] as num?)?.toDouble() ?? 0,
      target2: (json['target_2'] as num?)?.toDouble() ?? 0,
      target3: (json['target_3'] as num?)?.toDouble() ?? 0,
      aiScore: (json['ai_score'] as num?)?.toDouble() ?? 0,
      confidenceScore: (json['confidence_score'] as num?)?.toDouble() ?? 0,
      timeframe: json['timeframe'] as String? ?? 'live',
      trackStatus: json['track_status'] as String? ?? '',
      timeline: timelineRaw
          .map((e) => TradeTimelineEvent.fromJson(e as Map<String, dynamic>))
          .toList(),
      postTrade: json['post_trade'] != null
          ? PostTradeAnalysis.fromJson(json['post_trade'] as Map<String, dynamic>)
          : null,
      liveMaxProfitPct: (json['live_max_profit_pct'] as num?)?.toDouble() ?? 0,
      liveMaxDrawdownPct: (json['live_max_drawdown_pct'] as num?)?.toDouble() ?? 0,
      entryQualityScore: (json['entry_quality_score'] as num?)?.toDouble() ?? 0,
      isClosed: json['is_closed'] as bool? ?? false,
    );
  }
}

class PerformanceInsights {
  final double averageTimeToTargetSeconds;
  final double averageDrawdownPct;
  final double averageProfitPct;
  final int bestHoldingTimeSeconds;
  final String bestTimeframe;
  final String bestEntryQualitySymbol;
  final String worstEntryQualitySymbol;
  final int closedTrades;

  PerformanceInsights({
    required this.averageTimeToTargetSeconds,
    required this.averageDrawdownPct,
    required this.averageProfitPct,
    required this.bestHoldingTimeSeconds,
    required this.bestTimeframe,
    required this.bestEntryQualitySymbol,
    required this.worstEntryQualitySymbol,
    required this.closedTrades,
  });

  factory PerformanceInsights.fromJson(Map<String, dynamic> json) {
    return PerformanceInsights(
      averageTimeToTargetSeconds:
          (json['average_time_to_target_seconds'] as num?)?.toDouble() ?? 0,
      averageDrawdownPct: (json['average_drawdown_pct'] as num?)?.toDouble() ?? 0,
      averageProfitPct: (json['average_profit_pct'] as num?)?.toDouble() ?? 0,
      bestHoldingTimeSeconds: json['best_holding_time_seconds'] as int? ?? 0,
      bestTimeframe: json['best_timeframe'] as String? ?? '',
      bestEntryQualitySymbol: json['best_entry_quality_symbol'] as String? ?? '',
      worstEntryQualitySymbol: json['worst_entry_quality_symbol'] as String? ?? '',
      closedTrades: json['closed_trades'] as int? ?? 0,
    );
  }
}

class TradeReplayListResponse {
  final List<TradeReplayDetail> replays;
  final PerformanceInsights insights;

  TradeReplayListResponse({required this.replays, required this.insights});

  factory TradeReplayListResponse.fromJson(Map<String, dynamic> json) {
    final list = json['replays'] as List<dynamic>? ?? [];
    return TradeReplayListResponse(
      replays: list
          .map((e) => TradeReplayDetail.fromJson(e as Map<String, dynamic>))
          .toList(),
      insights: PerformanceInsights.fromJson(
        json['insights'] as Map<String, dynamic>? ?? {},
      ),
    );
  }
}
