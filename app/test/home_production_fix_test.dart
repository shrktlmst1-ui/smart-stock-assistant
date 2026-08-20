import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/market_pulse.dart';
import 'package:smart_stock_assistant/models/opportunity_now.dart';
import 'package:smart_stock_assistant/utils/json_parse.dart';
import 'package:smart_stock_assistant/widgets/opportunity_now_card.dart';

void main() {
  group('parseJsonBool', () {
    test('accepts bool true/false', () {
      expect(parseJsonBool(true), isTrue);
      expect(parseJsonBool(false), isFalse);
    });

    test('accepts string true and 1', () {
      expect(parseJsonBool('true'), isTrue);
      expect(parseJsonBool('TRUE'), isTrue);
      expect(parseJsonBool('1'), isTrue);
    });

    test('accepts numeric 1 and 0', () {
      expect(parseJsonBool(1), isTrue);
      expect(parseJsonBool(0), isFalse);
    });
  });

  group('MarketPulseHealth', () {
    test('enabled=true when MARKET_PULSE_ENABLED sent as string', () {
      final health = MarketPulseHealth.fromJson({
        'enabled': 'true',
        'status': 'ok',
        'has_api_key': '1',
        'subscribed_symbols': '12',
        'max_symbols': 50,
        'stream_connected': 1,
        'message': 'جاهز',
      });

      expect(health.enabled, isTrue);
      expect(health.isActive, isTrue);
      expect(health.hasApiKey, isTrue);
      expect(health.streamConnected, isTrue);
      expect(health.subscribedSymbols, 12);
    });

    test('reads alternate enabled field names', () {
      final health = MarketPulseHealth.fromJson({
        'market_pulse_enabled': true,
        'status': 'idle',
        'has_api_key': true,
        'subscribed_symbols': 0,
        'max_symbols': 50,
        'stream_connected': false,
        'message': '',
      });

      expect(health.enabled, isTrue);
      expect(health.isActive, isTrue);
    });
  });

  group('MarketPulseListResponse', () {
    test('enabled when feature flag is true', () {
      final list = MarketPulseListResponse.fromJson({
        'enabled': true,
        'alerts': [],
        'count': 0,
      });

      expect(list.enabled, isTrue);
    });
  });

  group('OpportunityNowHomeCard', () {
    testWidgets('shows empty state message when no opportunity', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: OpportunityNowHomeCard(
              data: OpportunityNowResponse(
                marketStatus: 'REGULAR',
                marketOpen: true,
                scanIntervalSeconds: 15,
                message: '',
                signals: [],
                topSignal: null,
              ),
              loading: false,
            ),
          ),
        ),
      );

      expect(find.text('فرصة الآن'), findsOneWidget);
      expect(find.text('لا توجد فرصة مكتملة الآن'), findsOneWidget);
    });

    testWidgets('shows error without hiding card', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: OpportunityNowHomeCard(
              data: null,
              loading: false,
              error: 'تعذر الاتصال بالخادم',
            ),
          ),
        ),
      );

      expect(find.text('فرصة الآن'), findsOneWidget);
      expect(find.text('لا توجد فرصة مكتملة الآن'), findsOneWidget);
      expect(find.text('تعذر الاتصال بالخادم'), findsOneWidget);
    });
  });
}
