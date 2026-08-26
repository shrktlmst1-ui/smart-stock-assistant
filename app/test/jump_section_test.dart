import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/opportunity_now.dart';
import 'package:smart_stock_assistant/widgets/jump_section.dart';

void main() {
  testWidgets('JumpSection shows news and watch cards only', (tester) async {
    final data = OpportunityNowResponse.fromJson({
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
        'symbol': 'CRE',
        'name': 'CRE',
        'price': 5.2,
        'change_percent': 35,
        'score': 88,
        'status': 'CANCELLED',
        'status_ar': 'أُلغيت',
        'appeared_at': '2026-01-01T00:00:00Z',
        'expires_at': '',
        'entry_zone': 3.8,
        'stop_loss': 3.6,
        'target_1': 5.4,
        'target_2': 5.6,
        'risk_level': 'مرتفع',
        'reasons_ar': [],
        'session': 'PRE_MARKET',
        'extended_gap_pct': 35,
        'detection_stage': 'EXPLOSIVE',
        'previous_close': 3.85,
        'extended_price': 5.2,
        'extended_volume': 500000,
      },
      'signals': [],
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JumpSection(data: data, onOpenSymbol: (_) {}),
        ),
      ),
    );

    expect(find.text('قفزة خبرية'), findsOneWidget);
    expect(find.text('CRE'), findsOneWidget);
    expect(find.text('EXPLOSIVE'), findsOneWidget);
    expect(find.text('تم رصد القفزة — لا تطارد السهم'), findsOneWidget);
    expect(find.text('قفزة مراقبة'), findsOneWidget);
    expect(find.text('BTCT'), findsOneWidget);
    expect(find.text('Latency Source: WS'), findsOneWidget);
    expect(find.text('JUMP_QUALIFIED'), findsNothing);
  });

  testWidgets('JumpSection empty state', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: JumpSection(
            data: OpportunityNowResponse(
              status: 'NONE',
              statusAr: 'لا توجد',
              marketStatus: 'CLOSED',
              marketOpen: false,
              scanIntervalSeconds: 15,
              message: '',
              liveSource: 'rest',
              wsConnected: false,
              monitorPoolSize: 0,
              signals: [],
              topSignal: null,
            ),
          ),
        ),
      ),
    );

    expect(find.text('لا توجد قفزات مؤكدة الآن'), findsOneWidget);
  });
}
