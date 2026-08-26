import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/opportunity_now.dart';

void main() {
  group('OpportunityNowResponse', () {
    test('filters zero price and score from signals', () {
      final resp = OpportunityNowResponse.fromJson({
        'status': 'NOW',
        'status_ar': 'فرصة الآن',
        'market_status': 'REGULAR',
        'market_open': true,
        'scan_interval_seconds': 15,
        'message': '',
        'live_source': 'rest',
        'ws_connected': false,
        'monitor_pool_size': 100,
        'signals': [
          {
            'symbol': 'BAD',
            'name': 'Bad',
            'price': 0,
            'change_percent': 0,
            'score': 0,
            'status': 'CANCELLED',
            'status_ar': 'أُلغيت',
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
            'status': 'NOW',
            'status_ar': 'فرصة الآن',
            'appeared_at': '2026-01-01T00:00:00Z',
            'expires_at': '2026-01-01T00:15:00Z',
            'entry_zone': 4.51,
            'stop_loss': 4.36,
            'target_1': 4.63,
            'target_2': 4.77,
            'risk_level': 'منخفض',
            'risk_reward_ratio': 2.1,
            'confirmed_factors': 14,
            'consecutive_confirmations': 3,
            'reasons_ar': ['حجم متسارع'],
          },
        ],
        'top_signal': {
          'symbol': 'GOOD',
          'name': 'Good Co',
          'price': 4.5,
          'change_percent': 5,
          'score': 88,
          'status': 'NOW',
          'status_ar': 'فرصة الآن',
          'appeared_at': '2026-01-01T00:00:00Z',
          'expires_at': '2026-01-01T00:15:00Z',
          'entry_zone': 4.51,
          'stop_loss': 4.36,
          'target_1': 4.63,
          'target_2': 4.77,
          'risk_level': 'منخفض',
          'risk_reward_ratio': 2.1,
          'confirmed_factors': 14,
          'consecutive_confirmations': 3,
          'reasons_ar': ['حجم متسارع'],
        },
      });

      expect(resp.signals.length, 1);
      expect(resp.signals.first.symbol, 'GOOD');
      expect(resp.displayTop?.status, 'NOW');
    });

    test('displayTop null when status NONE and no signals', () {
      final resp = OpportunityNowResponse.fromJson({
        'status': 'NONE',
        'status_ar': 'لا توجد فرصة مكتملة الآن',
        'market_status': 'REGULAR',
        'market_open': true,
        'scan_interval_seconds': 15,
        'message': 'لا توجد فرصة مكتملة الآن',
        'signals': [],
        'top_signal': null,
      });

      expect(resp.displayTop, isNull);
      expect(resp.hasNoOpportunity, isTrue);
    });

    test('displayTop shows WATCH candidate', () {
      final resp = OpportunityNowResponse.fromJson({
        'status': 'WATCH',
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
            'status': 'WATCH',
            'status_ar': 'مراقبة',
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

      expect(resp.displayTop?.status, 'WATCH');
    });

    test('parses extended_alert separately from top_signal', () {
      final resp = OpportunityNowResponse.fromJson({
        'status': 'WATCH',
        'market_status': 'PRE_MARKET',
        'market_open': false,
        'scan_interval_seconds': 15,
        'message': '',
        'top_signal': {
          'symbol': 'BTCT',
          'name': 'BTCT',
          'price': 3.5,
          'change_percent': 2,
          'score': 72,
          'status': 'WATCH',
          'status_ar': 'مراقبة',
          'appeared_at': '2026-01-01T00:00:00Z',
          'expires_at': '2026-01-01T00:15:00Z',
          'entry_zone': 3.5,
          'stop_loss': 3.4,
          'target_1': 3.6,
          'target_2': 3.7,
          'risk_level': 'متوسط',
          'reasons_ar': [],
        },
        'extended_alert': {
          'symbol': 'SUGP',
          'name': 'Su Group',
          'price': 4.28,
          'change_percent': 54.23,
          'score': 88,
          'status': 'CANCELLED',
          'status_ar': 'أُلغيت',
          'appeared_at': '2026-01-01T00:00:00Z',
          'expires_at': '',
          'entry_zone': 2.8,
          'stop_loss': 2.7,
          'target_1': 4.4,
          'target_2': 4.5,
          'risk_level': 'مرتفع',
          'reasons_ar': [],
          'extended_gap_pct': 54.23,
          'detection_stage': 'EXPLOSIVE',
          'previous_close': 2.775,
          'extended_price': 4.28,
          'catalyst_type': 'NASDAQ_COMPLIANCE',
          'volume_status': 'UNKNOWN',
        },
        'signals': [],
      });

      expect(resp.topSignal?.symbol, 'BTCT');
      expect(resp.extendedAlert?.symbol, 'SUGP');
      expect(resp.displayTop?.symbol, 'BTCT');
      expect(resp.hasExtendedAlert, isTrue);
    });

    test('confirmedJumps returns news + watch max 3', () {
      final resp = OpportunityNowResponse.fromJson({
        'status': 'WATCH',
        'market_status': 'PRE_MARKET',
        'market_open': false,
        'scan_interval_seconds': 15,
        'message': '',
        'ws_connected': true,
        'top_signal': {
          'symbol': 'BTCT',
          'name': 'BTCT',
          'price': 3.5,
          'change_percent': 2,
          'score': 72,
          'status': 'WATCH',
          'status_ar': 'مراقبة',
          'appeared_at': '2026-01-01T00:00:00Z',
          'expires_at': '2026-01-01T00:15:00Z',
          'entry_zone': 3.5,
          'entry_zone_low': 3.4,
          'entry_zone_high': 3.6,
          'stop_loss': 3.4,
          'target_1': 3.6,
          'target_2': 3.7,
          'risk_level': 'متوسط',
          'confirmed_factors': 8,
          'total_factors': 17,
          'reasons_ar': ['حجم متسارع'],
        },
        'extended_alert': {
          'symbol': 'SUGP',
          'name': 'Su Group',
          'price': 4.28,
          'change_percent': 54.23,
          'score': 88,
          'status': 'CANCELLED',
          'status_ar': 'أُلغيت',
          'appeared_at': '2026-01-01T00:00:00Z',
          'expires_at': '',
          'entry_zone': 2.8,
          'stop_loss': 2.7,
          'target_1': 4.4,
          'target_2': 4.5,
          'risk_level': 'مرتفع',
          'reasons_ar': [],
          'session': 'PRE_MARKET',
          'extended_gap_pct': 54.23,
          'detection_stage': 'EXPLOSIVE',
          'previous_close': 2.775,
          'extended_price': 4.28,
          'extended_volume': 120000,
          'catalyst_title_ar': 'امتثال ناسdaq',
        },
        'signals': [
          {
            'symbol': 'CISS',
            'name': 'CISS',
            'price': 2.1,
            'change_percent': 4,
            'score': 68,
            'status': 'WATCH',
            'status_ar': 'مراقبة',
            'appeared_at': '2026-01-01T00:00:00Z',
            'expires_at': '2026-01-01T00:15:00Z',
            'entry_zone': 2.1,
            'entry_zone_low': 2.0,
            'entry_zone_high': 2.2,
            'stop_loss': 1.9,
            'target_1': 2.3,
            'target_2': 2.4,
            'risk_level': 'متوسط',
            'confirmed_factors': 6,
            'total_factors': 17,
            'reasons_ar': ['ضغط شرائي'],
          },
        ],
      });

      final jumps = resp.confirmedJumps(limit: 3);
      expect(jumps.length, 3);
      expect(jumps[0].symbol, 'SUGP');
      expect(jumps[0].isRealNewsJump, isTrue);
      expect(jumps[1].symbol, 'BTCT');
      expect(jumps[1].isRealWatchJump, isTrue);
      expect(jumps[2].symbol, 'CISS');
    });

    test('confirmedJumps empty when no real jumps', () {
      final resp = OpportunityNowResponse.fromJson({
        'status': 'NONE',
        'market_status': 'CLOSED',
        'market_open': false,
        'scan_interval_seconds': 15,
        'message': 'السوق مغلق',
        'signals': [],
        'top_signal': null,
      });
      expect(resp.confirmedJumps(), isEmpty);
      expect(resp.hasConfirmedJumps, isFalse);
    });

    test('market closed message preserved', () {
      final resp = OpportunityNowResponse.fromJson({
        'status': 'NONE',
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
