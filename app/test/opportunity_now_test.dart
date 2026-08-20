import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/opportunity_now.dart';

void main() {
  group('OpportunityNowResponse', () {
    test('filters zero price and score from signals', () {
      final resp = OpportunityNowResponse.fromJson({
        'market_status': 'REGULAR',
        'market_open': true,
        'scan_interval_seconds': 15,
        'message': '',
        'signals': [
          {
            'symbol': 'BAD',
            'name': 'Bad',
            'price': 0,
            'change_percent': 0,
            'score': 0,
            'status': 'تجنب',
            'appeared_at': '2026-01-01T00:00:00Z',
            'expires_at': '2026-01-01T00:15:00Z',
            'entry_zone': 0,
            'stop_loss': 0,
            'target_1': 0,
            'target_2': 0,
            'risk_level': 'مرتفع',
            'reasons_ar': [],
          },
          {
            'symbol': 'GOOD',
            'name': 'Good Co',
            'price': 4.5,
            'change_percent': 5,
            'score': 88,
            'status': 'فرصة الآن',
            'appeared_at': '2026-01-01T00:00:00Z',
            'expires_at': '2026-01-01T00:15:00Z',
            'entry_zone': 4.51,
            'stop_loss': 4.36,
            'target_1': 4.63,
            'target_2': 4.77,
            'risk_level': 'منخفض',
            'reasons_ar': ['حجم متسارع'],
          },
        ],
        'top_signal': {
          'symbol': 'GOOD',
          'name': 'Good Co',
          'price': 4.5,
          'change_percent': 5,
          'score': 88,
          'status': 'فرصة الآن',
          'appeared_at': '2026-01-01T00:00:00Z',
          'expires_at': '2026-01-01T00:15:00Z',
          'entry_zone': 4.51,
          'stop_loss': 4.36,
          'target_1': 4.63,
          'target_2': 4.77,
          'risk_level': 'منخفض',
          'reasons_ar': ['حجم متسارع'],
        },
      });

      expect(resp.signals.length, 1);
      expect(resp.signals.first.symbol, 'GOOD');
      expect(resp.displayTop?.status, 'فرصة الآن');
    });

    test('displayTop null when no valid opportunity', () {
      final resp = OpportunityNowResponse.fromJson({
        'market_status': 'REGULAR',
        'market_open': true,
        'scan_interval_seconds': 15,
        'message': '',
        'signals': [
          {
            'symbol': 'WATCH',
            'name': 'Watch',
            'price': 3.2,
            'change_percent': 2,
            'score': 70,
            'status': 'مراقبة',
            'appeared_at': '2026-01-01T00:00:00Z',
            'expires_at': '2026-01-01T00:15:00Z',
            'entry_zone': 3.2,
            'stop_loss': 3.1,
            'target_1': 3.3,
            'target_2': 3.4,
            'risk_level': 'متوسط',
            'reasons_ar': [],
          },
        ],
        'top_signal': null,
      });

      expect(resp.displayTop, isNull);
    });

    test('market closed message preserved', () {
      final resp = OpportunityNowResponse.fromJson({
        'market_status': 'CLOSED',
        'market_open': false,
        'scan_interval_seconds': 15,
        'message': 'السوق مغلق — مراقبة فقط',
        'signals': [],
        'top_signal': null,
      });

      expect(resp.marketOpen, isFalse);
      expect(resp.message, contains('السوق مغلق'));
    });
  });
}
