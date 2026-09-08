class SpxLevels {
  final double? previousDayHigh;
  final double? previousDayLow;
  final double? previousWeekHigh;
  final double? previousWeekLow;
  final double? overnightHigh;
  final double? overnightLow;
  final double? openingRangeHigh;
  final double? openingRangeLow;
  final double? swingHigh;
  final double? swingLow;
  final double? vwap;
  final String? supportZone;
  final String? resistanceZone;

  const SpxLevels({
    this.previousDayHigh,
    this.previousDayLow,
    this.previousWeekHigh,
    this.previousWeekLow,
    this.overnightHigh,
    this.overnightLow,
    this.openingRangeHigh,
    this.openingRangeLow,
    this.swingHigh,
    this.swingLow,
    this.vwap,
    this.supportZone,
    this.resistanceZone,
  });

  factory SpxLevels.fromJson(Map<String, dynamic> json) => SpxLevels(
        previousDayHigh: (json['previous_day_high'] as num?)?.toDouble(),
        previousDayLow: (json['previous_day_low'] as num?)?.toDouble(),
        previousWeekHigh: (json['previous_week_high'] as num?)?.toDouble(),
        previousWeekLow: (json['previous_week_low'] as num?)?.toDouble(),
        overnightHigh: (json['overnight_high'] as num?)?.toDouble(),
        overnightLow: (json['overnight_low'] as num?)?.toDouble(),
        openingRangeHigh: (json['opening_range_high'] as num?)?.toDouble(),
        openingRangeLow: (json['opening_range_low'] as num?)?.toDouble(),
        swingHigh: (json['swing_high'] as num?)?.toDouble(),
        swingLow: (json['swing_low'] as num?)?.toDouble(),
        vwap: (json['vwap'] as num?)?.toDouble(),
        supportZone: json['support_zone']?.toString(),
        resistanceZone: json['resistance_zone']?.toString(),
      );
}

class SpxOptionCandidate {
  final String? ticker;
  final String? contractType;
  final String? expirationDate;
  final double? strike;
  final double? bid;
  final double? ask;
  final double? midpoint;
  final double? spreadPct;
  final double? delta;
  final double? iv;
  final int volume;
  final int openInterest;
  final bool liquid;

  const SpxOptionCandidate({
    this.ticker,
    this.contractType,
    this.expirationDate,
    this.strike,
    this.bid,
    this.ask,
    this.midpoint,
    this.spreadPct,
    this.delta,
    this.iv,
    this.volume = 0,
    this.openInterest = 0,
    this.liquid = false,
  });

  factory SpxOptionCandidate.fromJson(Map<String, dynamic> json) => SpxOptionCandidate(
        ticker: json['ticker']?.toString(),
        contractType: json['contract_type']?.toString(),
        expirationDate: json['expiration_date']?.toString(),
        strike: (json['strike'] as num?)?.toDouble(),
        bid: (json['bid'] as num?)?.toDouble(),
        ask: (json['ask'] as num?)?.toDouble(),
        midpoint: (json['midpoint'] as num?)?.toDouble(),
        spreadPct: (json['spread_pct'] as num?)?.toDouble(),
        delta: (json['delta'] as num?)?.toDouble(),
        iv: (json['iv'] as num?)?.toDouble(),
        volume: (json['volume'] as num?)?.toInt() ?? 0,
        openInterest: (json['open_interest'] as num?)?.toInt() ?? 0,
        liquid: json['liquid'] == true,
      );
}

class SpxSignal {
  final String symbol;
  final String decision;
  final int score;
  final String regime;
  final double confidence;
  final String reason;
  final double? entry;
  final double? stopLoss;
  final double? takeProfit1;
  final double? takeProfit2;
  final SpxLevels levels;
  final SpxOptionCandidate? option;
  final List<String> factors;
  final List<String> rejectedFactors;
  final bool dataFresh;
  final bool optionsReady;
  final bool killSwitch;
  final String? cycleId;
  final String? timestamp;

  const SpxSignal({
    required this.symbol,
    required this.decision,
    required this.score,
    required this.regime,
    required this.confidence,
    required this.reason,
    required this.levels,
    this.entry,
    this.stopLoss,
    this.takeProfit1,
    this.takeProfit2,
    this.option,
    this.factors = const [],
    this.rejectedFactors = const [],
    this.dataFresh = false,
    this.optionsReady = false,
    this.killSwitch = true,
    this.cycleId,
    this.timestamp,
  });

  factory SpxSignal.fromJson(Map<String, dynamic> json) => SpxSignal(
        symbol: json['symbol']?.toString() ?? 'I:SPX',
        decision: json['decision']?.toString() ?? 'NO TRADE',
        score: (json['score'] as num?)?.toInt() ?? 0,
        regime: json['regime']?.toString() ?? 'UNKNOWN',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        reason: json['reason']?.toString() ?? '',
        entry: (json['entry'] as num?)?.toDouble(),
        stopLoss: (json['stop_loss'] as num?)?.toDouble(),
        takeProfit1: (json['take_profit_1'] as num?)?.toDouble(),
        takeProfit2: (json['take_profit_2'] as num?)?.toDouble(),
        levels: SpxLevels.fromJson((json['levels'] as Map?)?.cast<String, dynamic>() ?? const {}),
        option: json['option'] is Map
            ? SpxOptionCandidate.fromJson((json['option'] as Map).cast<String, dynamic>())
            : null,
        factors: (json['factors'] as List?)?.map((e) => e.toString()).toList() ?? const [],
        rejectedFactors: (json['rejected_factors'] as List?)?.map((e) => e.toString()).toList() ?? const [],
        dataFresh: json['data_fresh'] == true,
        optionsReady: json['options_ready'] == true,
        killSwitch: json['kill_switch'] == true,
        cycleId: json['cycle_id']?.toString(),
        timestamp: json['timestamp']?.toString(),
      );
}
