/// Live system status from backend — no mock values.
class SystemStatus {
  final bool backendConnected;
  final bool polygonConnected;
  final bool websocketLive;
  final bool marketScannerRunning;
  final DateTime? lastUpdate;
  final String? error;

  const SystemStatus({
    required this.backendConnected,
    required this.polygonConnected,
    required this.websocketLive,
    required this.marketScannerRunning,
    this.lastUpdate,
    this.error,
  });

  factory SystemStatus.offline([String? error]) => SystemStatus(
        backendConnected: false,
        polygonConnected: false,
        websocketLive: false,
        marketScannerRunning: false,
        error: error ?? 'الخادم غير متاح',
      );

  static DateTime? _parseTime(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    return DateTime.tryParse(raw);
  }

  factory SystemStatus.fromApi({
    required Map<String, dynamic> health,
    required Map<String, dynamic> connection,
    Map<String, dynamic>? scanner,
  }) {
    final apiOk = health['ok'] == true;
    final apiConnected = connection['api_connected'] == true;
    final auth = connection['authentication_status'] as String? ?? '';
    final live = connection['live_market_data_status'] as String? ?? '';
    final wsAvailable = connection['websocket_available'] == true;
    final streamMode = connection['stream_mode'] as String? ?? '';

    final scannerMap = health['scanner'] as Map<String, dynamic>?;
    final scannerActive = streamMode.contains('scanner') ||
        (scannerMap != null && (scannerMap['interval_seconds'] as num? ?? 0) > 0);

    DateTime? last = _parseTime(connection['last_check'] as String?);
    final scanRefresh = scanner?['last_universe_refresh'] as String?;
    final tickMs = scanner?['last_tick_ms'];
    if (scanRefresh != null && scanRefresh.isNotEmpty) {
      last = _parseTime(scanRefresh) ?? last;
    } else if (tickMs != null && (tickMs as num) > 0) {
      last = DateTime.now().toUtc();
    }

    return SystemStatus(
      backendConnected: apiOk,
      polygonConnected: apiConnected && auth == 'authenticated',
      websocketLive: wsAvailable || live == 'live',
      marketScannerRunning: apiOk && scannerActive,
      lastUpdate: last,
    );
  }
}
