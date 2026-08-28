import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/opportunity_now.dart';
import 'package:smart_stock_assistant/widgets/distinguished_jump_section.dart';
import 'package:smart_stock_assistant/widgets/jump_section.dart';

Map<String, dynamic> _distinguishedItem({
  required String symbol,
  required double moveStart,
  required double price,
  required double movePct,
  String moveStartTime = '2026-08-28T14:00:00Z',
  String firstDetected = '2026-08-28T14:02:00Z',
}) {
  return {
    'symbol': symbol,
    'name': symbol,
    'price': price,
    'change_percent': 90,
    'score': 80,
    'status': 'NOW',
    'status_ar': 'قفزة سعرية مميزة',
    'display_type': 'DISTINGUISHED_PRICE_JUMP',
    'real_jump_move_start_price': moveStart,
    'real_jump_current_move_pct': movePct,
    'real_jump_wave_peak_price': price * 1.02,
    'real_jump_move_start_time': moveStartTime,
    'real_jump_first_detected_time': firstDetected,
    'real_jump_wave_state': 'ACTIVE_UPWARD_WAVE',
    'real_jump_retracement_from_peak_pct': 1.5,
    'appeared_at': moveStartTime,
    'expires_at': '',
    'entry_zone': moveStart,
    'stop_loss': moveStart * 0.95,
    'target_1': price,
    'target_2': price * 1.05,
    'risk_level': 'مرتفع',
  };
}

void main() {
  testWidgets('DistinguishedJumpSection shows all items without limit', (tester) async {
    final distinguished = List.generate(
      12,
      (i) => _distinguishedItem(
        symbol: 'S${i + 1}',
        moveStart: 2.0,
        price: 3.2 + i * 0.01,
        movePct: 50.0 + i,
      ),
    );

    final data = OpportunityNowResponse.fromJson({
      'status': 'NOW',
      'market_status': 'REGULAR',
      'market_open': true,
      'scan_interval_seconds': 15,
      'message': '',
      'ws_connected': true,
      'distinguished_jump_alerts': distinguished,
      'display_signals': [],
      'signals': [],
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: DistinguishedJumpSection(data: data, onOpenSymbol: (_) {}),
          ),
        ),
      ),
    );

    expect(find.text('قفزة سعرية مميزة'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    for (var i = 1; i <= 12; i++) {
      expect(find.text('S$i'), findsOneWidget);
    }
  });

  testWidgets('DistinguishedJumpSection appears above JumpSection', (tester) async {
    final data = OpportunityNowResponse.fromJson({
      'status': 'NOW',
      'market_status': 'REGULAR',
      'market_open': true,
      'scan_interval_seconds': 15,
      'message': '',
      'ws_connected': true,
      'distinguished_jump_alerts': [
        _distinguishedItem(symbol: 'W1', moveStart: 2.0, price: 3.2, movePct: 60.0),
      ],
      'display_signals': [],
      'signals': [],
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DistinguishedJumpSection(data: data, onOpenSymbol: (_) {}),
              JumpSection(data: data, onOpenSymbol: (_) {}),
            ],
          ),
        ),
      ),
    );

    expect(find.text('قفزة سعرية مميزة'), findsOneWidget);
    expect(find.text('W1'), findsOneWidget);
    expect(find.text('القفزات'), findsOneWidget);

    final distinguishedY = tester.getTopLeft(find.text('قفزة سعرية مميزة')).dy;
    final jumpsY = tester.getTopLeft(find.text('القفزات')).dy;
    expect(distinguishedY, lessThan(jumpsY));
  });

  testWidgets('DistinguishedJumpSection hidden when empty', (tester) async {
    const data = OpportunityNowResponse(
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
    );

    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: DistinguishedJumpSection(data: data),
        ),
      ),
    );

    expect(find.text('قفزة سعرية مميزة'), findsNothing);
  });

  test('parses distinguished_jump_alerts without daily-change filter', () {
    final resp = OpportunityNowResponse.fromJson({
      'status': 'NOW',
      'market_status': 'REGULAR',
      'market_open': true,
      'scan_interval_seconds': 15,
      'message': '',
      'distinguished_jump_alerts': [
        _distinguishedItem(symbol: 'W1', moveStart: 2.0, price: 2.9, movePct: 45.0),
        _distinguishedItem(symbol: 'W2', moveStart: 2.0, price: 3.2, movePct: 60.0),
      ],
      'signals': [],
    });

    expect(resp.distinguishedJumpAlerts.length, 2);
    expect(resp.distinguishedJumpAlerts.every((s) => s.isDistinguishedJumpDisplay), isTrue);
  });
}
