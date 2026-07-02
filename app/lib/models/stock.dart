class TradeDecision {
  final String recommendation;
  final String? professionalSignal;
  final double? professionalAiScore;
  final bool? allFiltersPassed;
  final String? expectedHoldingTime;
  final String? aiExplanation;
  final String direction;
  final String symbol;
  final double currentPrice;
  final double entryZoneLow;
  final double entryZoneHigh;
  final double stopLoss;
  final double takeProfit1;
  final double takeProfit2;
  final double riskRewardRatio;
  final double aiConfidence;
  final double liquidityInflow;
  final double liquidityOutflow;
  final double trapRisk;
  final double newsRisk;
  final String marketStructure;
  final String triggerReason;
  final String devilsAdvocate;
  final Map<String, double> factorScores;
  final List<String> filtersPassed;
  final List<String> filtersFailed;
  final List<String> buyBlockers;
  final String? finalBlocker;

  TradeDecision({
    required this.recommendation,
    this.professionalSignal,
    this.professionalAiScore,
    this.allFiltersPassed,
    this.expectedHoldingTime,
    this.aiExplanation,
    required this.direction,
    required this.symbol,
    required this.currentPrice,
    required this.entryZoneLow,
    required this.entryZoneHigh,
    required this.stopLoss,
    required this.takeProfit1,
    required this.takeProfit2,
    required this.riskRewardRatio,
    required this.aiConfidence,
    required this.liquidityInflow,
    required this.liquidityOutflow,
    required this.trapRisk,
    required this.newsRisk,
    required this.marketStructure,
    required this.triggerReason,
    required this.devilsAdvocate,
    this.factorScores = const {},
    this.filtersPassed = const [],
    this.filtersFailed = const [],
    this.buyBlockers = const [],
    this.finalBlocker,
  });

  static Map<String, double> _parseFactorScores(dynamic raw) {
    if (raw is! Map) return const {};
    return raw.map(
      (key, value) => MapEntry(
        key.toString(),
        (value as num?)?.toDouble() ?? 0,
      ),
    );
  }

  static List<String> _parseStringList(dynamic raw) {
    if (raw is! List) return const [];
    return raw.map((e) => e.toString()).toList();
  }

  factory TradeDecision.fromJson(Map<String, dynamic> json) {
    return TradeDecision(
      recommendation: json['recommendation'] as String? ?? 'WAIT',
      professionalSignal: json['professional_signal'] as String?,
      professionalAiScore: (json['professional_ai_score'] as num?)?.toDouble(),
      allFiltersPassed: json['all_filters_passed'] as bool?,
      expectedHoldingTime: json['expected_holding_time'] as String?,
      aiExplanation: json['ai_explanation'] as String?,
      direction: json['direction'] as String? ?? 'neutral',
      symbol: json['symbol'] as String? ?? '',
      currentPrice: (json['current_price'] as num?)?.toDouble() ?? 0,
      entryZoneLow: (json['entry_zone_low'] as num?)?.toDouble() ?? 0,
      entryZoneHigh: (json['entry_zone_high'] as num?)?.toDouble() ?? 0,
      stopLoss: (json['stop_loss'] as num?)?.toDouble() ?? 0,
      takeProfit1: (json['take_profit_1'] as num?)?.toDouble() ?? 0,
      takeProfit2: (json['take_profit_2'] as num?)?.toDouble() ?? 0,
      riskRewardRatio: (json['risk_reward_ratio'] as num?)?.toDouble() ?? 0,
      aiConfidence: (json['ai_confidence'] as num?)?.toDouble() ?? 0,
      liquidityInflow: (json['liquidity_inflow'] as num?)?.toDouble() ?? 50,
      liquidityOutflow: (json['liquidity_outflow'] as num?)?.toDouble() ?? 50,
      trapRisk: (json['trap_risk'] as num?)?.toDouble() ?? 0,
      newsRisk: (json['news_risk'] as num?)?.toDouble() ?? 0,
      marketStructure: json['market_structure'] as String? ?? '',
      triggerReason: json['trigger_reason'] as String? ?? '',
      devilsAdvocate: json['devils_advocate'] as String? ?? '',
      factorScores: _parseFactorScores(json['factor_scores']),
      filtersPassed: _parseStringList(json['filters_passed']),
      filtersFailed: _parseStringList(json['filters_failed']),
      buyBlockers: _parseStringList(json['buy_blockers']),
      finalBlocker: json['final_blocker'] as String?,
    );
  }
}

class StockOpportunity {
  final String symbol;
  final String name;
  final double price;
  final double changePercent;
  final int score;
  final String trend;
  final String riskLevel;

  StockOpportunity({
    required this.symbol,
    required this.name,
    required this.price,
    required this.changePercent,
    required this.score,
    required this.trend,
    required this.riskLevel,
  });

  factory StockOpportunity.fromJson(Map<String, dynamic> json) {
    return StockOpportunity(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      price: (json['price'] as num).toDouble(),
      changePercent: (json['change_percent'] as num).toDouble(),
      score: (json['score'] as num?)?.toInt() ?? 0,
      trend: json['trend'] as String? ?? 'محايد',
      riskLevel: json['risk_level'] as String? ?? 'متوسط',
    );
  }
}

class ScannerStageCounts {
  final String marketStatus;
  final int symbolsScanned;
  final int universeSymbols;
  final int passedLiquidity;
  final int deepAnalysisCompleted;
  final int passedAllFilters;
  final int signalAvoid;
  final int signalWait;
  final Map<String, int> filterFailures;

  const ScannerStageCounts({
    required this.marketStatus,
    required this.symbolsScanned,
    required this.universeSymbols,
    required this.passedLiquidity,
    required this.deepAnalysisCompleted,
    required this.passedAllFilters,
    required this.signalAvoid,
    required this.signalWait,
    required this.filterFailures,
  });

  factory ScannerStageCounts.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const ScannerStageCounts(
        marketStatus: 'CLOSED',
        symbolsScanned: 0,
        universeSymbols: 0,
        passedLiquidity: 0,
        deepAnalysisCompleted: 0,
        passedAllFilters: 0,
        signalAvoid: 0,
        signalWait: 0,
        filterFailures: {},
      );
    }
    final failures = json['filter_failures'] as Map<String, dynamic>? ?? {};
    return ScannerStageCounts(
      marketStatus: json['market_status'] as String? ?? 'CLOSED',
      symbolsScanned: (json['symbols_scanned'] as num?)?.toInt() ?? 0,
      universeSymbols: (json['universe_symbols'] as num?)?.toInt() ?? 0,
      passedLiquidity: (json['passed_liquidity'] as num?)?.toInt() ?? 0,
      deepAnalysisCompleted: (json['deep_analysis_completed'] as num?)?.toInt() ?? 0,
      passedAllFilters: (json['passed_all_filters'] as num?)?.toInt() ?? 0,
      signalAvoid: (json['signal_avoid'] as num?)?.toInt() ?? 0,
      signalWait: (json['signal_wait'] as num?)?.toInt() ?? 0,
      filterFailures: failures.map((k, v) => MapEntry(k, (v as num).toInt())),
    );
  }
}

class OpportunitiesDashboard {
  final String marketStatus;
  final List<StockOpportunity> opportunities;
  final List<StockOpportunity> watchlistCandidates;
  final String explanation;
  final String noSignalReason;
  final ScannerStageCounts debug;

  const OpportunitiesDashboard({
    required this.marketStatus,
    required this.opportunities,
    required this.watchlistCandidates,
    required this.explanation,
    required this.noSignalReason,
    required this.debug,
  });

  factory OpportunitiesDashboard.fromJson(Map<String, dynamic> json) {
    final live = json['opportunities'] as List<dynamic>? ?? [];
    final watch = json['watchlist_candidates'] as List<dynamic>? ?? [];
    return OpportunitiesDashboard(
      marketStatus: json['market_status'] as String? ?? 'CLOSED',
      opportunities: live
          .map((e) => StockOpportunity.fromJson(e as Map<String, dynamic>))
          .toList(),
      watchlistCandidates: watch
          .map((e) => StockOpportunity.fromJson(e as Map<String, dynamic>))
          .toList(),
      explanation: json['explanation'] as String? ?? '',
      noSignalReason: json['no_signal_reason'] as String? ?? '',
      debug: ScannerStageCounts.fromJson(json['debug'] as Map<String, dynamic>?),
    );
  }

  List<StockOpportunity> get displayItems =>
      opportunities.isNotEmpty ? opportunities : watchlistCandidates;

  bool get showingWatchlist =>
      opportunities.isEmpty && watchlistCandidates.isNotEmpty;
}

class SearchResult {
  final String symbol;
  final String name;
  final double price;
  final double changePercent;

  SearchResult({
    required this.symbol,
    required this.name,
    required this.price,
    required this.changePercent,
  });

  factory SearchResult.fromJson(Map<String, dynamic> json) {
    return SearchResult(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      price: (json['price'] as num).toDouble(),
      changePercent: (json['change_percent'] as num).toDouble(),
    );
  }
}

class StockAnalysis {
  final String symbol;
  final String name;
  final double price;
  final double changePercent;
  final String trend;
  final double rsi;
  final double macd;
  final double macdSignal;
  final double ema20;
  final double ema50;
  final double ema200;
  final int volume;
  final double support;
  final double resistance;
  final int score;
  final double entryPrice;
  final double stopLoss;
  final double target1;
  final double target2;
  final String riskLevel;
  final String recommendationReason;
  final TradeDecision? tradeDecision;

  StockAnalysis({
    required this.symbol,
    required this.name,
    required this.price,
    required this.changePercent,
    required this.trend,
    required this.rsi,
    required this.macd,
    required this.macdSignal,
    required this.ema20,
    required this.ema50,
    required this.ema200,
    required this.volume,
    required this.support,
    required this.resistance,
    required this.score,
    required this.entryPrice,
    required this.stopLoss,
    required this.target1,
    required this.target2,
    required this.riskLevel,
    required this.recommendationReason,
    this.tradeDecision,
  });

  factory StockAnalysis.fromJson(Map<String, dynamic> json) {
    return StockAnalysis(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      price: (json['price'] as num).toDouble(),
      changePercent: (json['change_percent'] as num).toDouble(),
      trend: json['trend'] as String,
      rsi: (json['rsi'] as num).toDouble(),
      macd: (json['macd'] as num).toDouble(),
      macdSignal: (json['macd_signal'] as num).toDouble(),
      ema20: (json['ema_20'] as num).toDouble(),
      ema50: (json['ema_50'] as num).toDouble(),
      ema200: (json['ema_200'] as num).toDouble(),
      volume: json['volume'] as int,
      support: (json['support'] as num).toDouble(),
      resistance: (json['resistance'] as num).toDouble(),
      score: json['score'] as int,
      entryPrice: (json['entry_price'] as num).toDouble(),
      stopLoss: (json['stop_loss'] as num).toDouble(),
      target1: (json['target_1'] as num).toDouble(),
      target2: (json['target_2'] as num).toDouble(),
      riskLevel: json['risk_level'] as String,
      recommendationReason: json['recommendation_reason'] as String,
      tradeDecision: json['trade_decision'] != null
          ? TradeDecision.fromJson(json['trade_decision'] as Map<String, dynamic>)
          : null,
    );
  }
}
