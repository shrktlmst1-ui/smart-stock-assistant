import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/market_pulse.dart';
import 'package:smart_stock_assistant/models/opportunity_now.dart';
import 'package:smart_stock_assistant/utils/json_parse.dart';
import 'package:smart_stock_assistant/widgets/extended_alert_card.dart';
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

  group('ExtendedAlertHomeCard', () {
    testWidgets('shows cancelled extended alert in red', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ExtendedAlertHomeCard(
              alert: OpportunityNowSignal(
                symbol: 'SUGP',
                name: 'Su Group',
                price: 4.28,
                changePercent: 54.23,
                score: 88,
                status: 'CANCELLED',
                statusAr: 'أُلغيت',
                opportunityType: 'CANCELLED',
                appearedAt: '2026-01-01T00:00:00Z',
                expiresAt: '',
                entryZone: 2.8,
                entryZoneLow: 2.78,
                entryZoneHigh: 2.89,
                stopLoss: 2.7,
                target1: 4.4,
                target2: 4.5,
                riskLevel: 'مرتفع',
                riskRewardRatio: 0,
                confirmedFactors: 0,
                totalFactors: 17,
                consecutiveConfirmations: 0,
                reasonsAr: const [],
                cancellationReasonsAr: const ['لا تطارد السهم'],
                lateEntryWarning: true,
                hasNewsCatalyst: true,
                movementWithoutNews: false,
                dataTimestamp: '',
                dataAgeSeconds: 0,
                session: 'PRE_MARKET',
                previousClose: 2.775,
                extendedPrice: 4.28,
                extendedGapPct: 54.23,
                detectionStage: 'EXPLOSIVE',
                catalystTitleAr: 'امتثال ناسdaq',
                volumeStatus: 'UNKNOWN',
              ),
            ),
          ),
        ),
      );

      expect(find.text('قفزة خبرية'), findsOneWidget);
      expect(find.text('تم رصد القفزة — لا تطارد السهم'), findsOneWidget);
      expect(find.text('الحجم: غير متاح'), findsOneWidget);
    });
  });

  group('OpportunityNowHomeCard', () {
    testWidgets('shows empty state message when no opportunity', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: OpportunityNowHomeCard(
              data: OpportunityNowResponse(
                status: 'NONE',
                statusAr: 'لا توجد فرصة مكتملة الآن',
                marketStatus: 'REGULAR',
                marketOpen: true,
                scanIntervalSeconds: 15,
                message: '',
                liveSource: 'rest',
                wsConnected: false,
                monitorPoolSize: 0,
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
      expect(find.text('تعذر الاتصال — حاول التحديث'), findsOneWidget);
      expect(find.text('تعذر الاتصال بالخادم'), findsOneWidget);
    });
  });
}
