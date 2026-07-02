import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/stock.dart';

void main() {
  test('TradeDecision parses API snapshot fields', () {
    final decision = TradeDecision.fromJson({
      'recommendation': 'POSSIBLE ENTRY',
      'direction': 'long',
      'symbol': 'AAPL',
      'current_price': 195.5,
      'entry_zone_low': 194.0,
      'entry_zone_high': 196.0,
      'stop_loss': 192.0,
      'take_profit_1': 199.0,
      'take_profit_2': 202.0,
      'risk_reward_ratio': 2.5,
      'ai_confidence': 82.3,
      'liquidity_inflow': 65.0,
      'liquidity_outflow': 40.0,
      'trap_risk': 15.0,
      'news_risk': 10.0,
      'market_structure': 'BOS bullish',
      'trigger_reason': 'Setup forming',
      'devils_advocate': 'Watch volume',
    });

    expect(decision.recommendation, 'POSSIBLE ENTRY');
    expect(decision.aiConfidence, closeTo(82.3, 0.01));
    expect(decision.riskRewardRatio, closeTo(2.5, 0.01));
    expect(decision.liquidityInflow, closeTo(65.0, 0.01));
  });

  test('TradeDecision parses factor scores and blockers', () {
    final decision = TradeDecision.fromJson({
      'recommendation': 'WAIT',
      'direction': 'long',
      'symbol': 'AHMA',
      'current_price': 2.26,
      'entry_zone_low': 2.1,
      'entry_zone_high': 2.3,
      'stop_loss': 2.08,
      'take_profit_1': 2.62,
      'take_profit_2': 2.8,
      'risk_reward_ratio': 3.9,
      'ai_confidence': 77.2,
      'liquidity_inflow': 65.0,
      'liquidity_outflow': 40.0,
      'trap_risk': 15.0,
      'news_risk': 10.0,
      'market_structure': 'CHOCH bullish',
      'trigger_reason': 'WAIT',
      'devils_advocate': 'none',
      'factor_scores': {
        'bos': 34,
        'choch': 87,
        'trend': 38,
        'institutional_flow': 94,
      },
      'buy_blockers': ['BOS (34) below minimum 45'],
      'final_blocker': 'BOS (34) below minimum 45',
    });

    expect(decision.factorScores['bos'], 34);
    expect(decision.factorScores['choch'], 87);
    expect(decision.buyBlockers, hasLength(1));
    expect(decision.finalBlocker, contains('BOS'));
  });
}
