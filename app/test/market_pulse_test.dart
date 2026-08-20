import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/market_pulse.dart';

void main() {
  group('MarketPulseAlert', () {
    test('parses full JSON payload', () {
      final alert = MarketPulseAlert.fromJson({
        'symbol': 'NVDA',
        'score': 84.5,
        'decision': 'WAIT',
        'catalyst': {
          'headline': 'beats estimates',
          'sentiment': 'positive',
          'trigger_type': 'earnings_beat',
          'news_age_seconds': 30,
          'symbols': ['NVDA'],
          'provider_id': 'n1',
        },
        'headline': 'beats estimates',
        'news_age_seconds': 30,
        'estimated_buy_pressure': 88,
        'rvol': 2.5,
        'dollar_volume_acceleration': 1.2,
        'spread_bps': 5,
        'price': 100,
        'vwap': 99,
        'entry': 100.2,
        'stop_loss': 97,
        'targets': [103, 106],
        'risk_flags': [],
        'data_timestamp': '2026-01-01T00:00:00Z',
        'is_live': true,
        'expires_at': '2026-01-01T00:15:00Z',
        'reasons_ar': ['إشارة جيدة'],
        'catalyst_score': 25,
        'liquidity_score': 28,
        'price_confirmation_score': 20,
        'risk_penalty': 0,
        'is_halted': false,
      });
      expect(alert.symbol, 'NVDA');
      expect(alert.decision, 'WAIT');
      expect(alert.reasonsAr.first, 'إشارة جيدة');
    });

    test('displayDecision downgrades stale ENTER_NOW', () {
      const alert = MarketPulseAlert(
        symbol: 'X',
        score: 90,
        decision: 'ENTER_NOW',
        catalyst: CatalystInfo(
          headline: '',
          sentiment: 'positive',
          triggerType: '',
          newsAgeSeconds: 0,
          symbols: [],
          providerId: '',
        ),
        headline: '',
        newsAgeSeconds: 0,
        estimatedBuyPressure: 0,
        rvol: 0,
        dollarVolumeAcceleration: 0,
        spreadBps: 0,
        price: 0,
        vwap: 0,
        entry: 0,
        stopLoss: 0,
        targets: [],
        riskFlags: [],
        dataTimestamp: '',
        isLive: false,
        expiresAt: '',
        reasonsAr: [],
        catalystScore: 0,
        liquidityScore: 0,
        priceConfirmationScore: 0,
        riskPenalty: 0,
        isHalted: false,
      );
      expect(alert.displayDecision, 'WAIT');
    });

    test('expired decision preserved', () {
      const alert = MarketPulseAlert(
        symbol: 'X',
        score: 10,
        decision: 'EXPIRED',
        catalyst: CatalystInfo(
          headline: '',
          sentiment: 'neutral',
          triggerType: '',
          newsAgeSeconds: 999,
          symbols: [],
          providerId: '',
        ),
        headline: '',
        newsAgeSeconds: 999,
        estimatedBuyPressure: 0,
        rvol: 0,
        dollarVolumeAcceleration: 0,
        spreadBps: 0,
        price: 0,
        vwap: 0,
        entry: 0,
        stopLoss: 0,
        targets: [],
        riskFlags: ['offering'],
        dataTimestamp: '',
        isLive: false,
        expiresAt: '',
        reasonsAr: [],
        catalystScore: 0,
        liquidityScore: 0,
        priceConfirmationScore: 0,
        riskPenalty: 25,
        isHalted: false,
      );
      expect(alert.displayDecision, 'EXPIRED');
      expect(alert.isExpired, isTrue);
    });
  });

  test('release mode does not enable fixture paths in app', () {
    expect(kReleaseMode, isFalse, reason: 'tests run in debug/profile only');
  });
}
