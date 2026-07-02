import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/models/system_status.dart';

void main() {
  test('SystemStatus parses live API payloads', () {
    final status = SystemStatus.fromApi(
      health: {
        'ok': true,
        'scanner': {'interval_seconds': 15, 'universe_size': 3000},
      },
      connection: {
        'api_connected': true,
        'authentication_status': 'authenticated',
        'live_market_data_status': 'live',
        'websocket_available': true,
        'stream_mode': 'websocket_scanner',
        'last_check': '2026-07-01T12:00:00+00:00',
      },
      scanner: {
        'last_universe_refresh': '2026-07-01T12:05:00+00:00',
        'last_tick_ms': 1200,
      },
    );

    expect(status.backendConnected, isTrue);
    expect(status.polygonConnected, isTrue);
    expect(status.websocketLive, isTrue);
    expect(status.marketScannerRunning, isTrue);
    expect(status.lastUpdate, isNotNull);
  });

  test('SystemStatus.offline marks all flags false', () {
    final status = SystemStatus.offline('timeout');
    expect(status.backendConnected, isFalse);
    expect(status.error, 'timeout');
  });
}
