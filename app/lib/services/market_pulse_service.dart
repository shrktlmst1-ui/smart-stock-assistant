import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/market_pulse.dart';
import '../services/api_service.dart';
import 'auth_session.dart';

/// Market Pulse client — WebSocket first, REST polling fallback.
class MarketPulseService {
  static const Duration pollInterval = Duration(seconds: 10);
  static const Duration reconnectBase = Duration(seconds: 2);
  static const Duration reconnectMax = Duration(seconds: 30);

  final http.Client _client;
  final String baseUrl;

  WebSocketChannel? _channel;
  StreamSubscription? _wsSub;
  Timer? _pollTimer;
  Timer? _reconnectTimer;
  int _reconnectAttempt = 0;
  bool _active = false;
  bool _usePolling = false;

  MarketPulseHealth? health;
  MarketPulseListResponse? listing;
  PulseServiceState state = PulseServiceState.loading;
  String? errorMessage;
  DateTime? lastUpdated;

  final _controller = StreamController<void>.broadcast();

  Stream<void> get updates => _controller.stream;

  final AuthSession _auth;

  MarketPulseService({
    http.Client? client,
    String? baseUrl,
    AuthSession? authSession,
  })  : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? ApiService.baseUrl,
        _auth = authSession ?? AuthSession();

  String get wsUrl {
    final uri = Uri.parse(baseUrl);
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    return '$scheme://${uri.host}${uri.hasPort ? ':${uri.port}' : ''}/ws/market-pulse';
  }

  void start() {
    _active = true;
    _setState(PulseServiceState.loading);
    _connectWebSocket();
  }

  void stop() {
    _active = false;
    _pollTimer?.cancel();
    _pollTimer = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _wsSub?.cancel();
    _wsSub = null;
    _channel?.sink.close();
    _channel = null;
  }

  Future<void> refresh() async {
    await _fetchRest();
  }

  void _connectWebSocket() {
    if (!_active) return;
    try {
      _channel?.sink.close();
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      final token = _auth.accessToken;
      if (token != null && token.isNotEmpty) {
        _channel!.sink.add(jsonEncode({'type': 'auth', 'token': token}));
      }
      _wsSub?.cancel();
      _wsSub = _channel!.stream.listen(
        _onWsMessage,
        onError: (_) => _onWsDisconnected(),
        onDone: _onWsDisconnected,
        cancelOnError: true,
      );
      _usePolling = false;
      _reconnectAttempt = 0;
    } catch (_) {
      _onWsDisconnected();
    }
  }

  void _onWsMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = msg['type'] as String? ?? '';
      final data = msg['data'];
      if (type == 'pulse_health' && data is Map<String, dynamic>) {
        health = MarketPulseHealth.fromJson(data);
      } else if (type == 'pulse_list' && data is Map<String, dynamic>) {
        listing = MarketPulseListResponse.fromJson(data);
        lastUpdated = DateTime.now();
      }
      _updateDerivedState();
      _controller.add(null);
    } catch (_) {
      // ignore malformed frames
    }
  }

  void _onWsDisconnected() {
    if (!_active) return;
    _usePolling = true;
    _startPolling();
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (!_active) return;
    _reconnectTimer?.cancel();
    final delay = Duration(
      milliseconds: (reconnectBase.inMilliseconds * (1 << _reconnectAttempt.clamp(0, 4)))
          .clamp(reconnectBase.inMilliseconds, reconnectMax.inMilliseconds),
    );
    _reconnectAttempt++;
    _reconnectTimer = Timer(delay, () {
      if (_active) _connectWebSocket();
    });
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _fetchRest();
    _pollTimer = Timer.periodic(pollInterval, (_) => _fetchRest());
  }

  Future<void> _fetchRest() async {
    if (!_active) return;
    try {
      final headers = _auth.authHeaders();
      final healthResp = await _client
          .get(Uri.parse('$baseUrl/market-pulse/health'), headers: headers)
          .timeout(const Duration(seconds: 12));
      final listResp = await _client
          .get(Uri.parse('$baseUrl/market-pulse'), headers: headers)
          .timeout(const Duration(seconds: 12));
      if (healthResp.statusCode == 200) {
        health = MarketPulseHealth.fromJson(
          jsonDecode(healthResp.body) as Map<String, dynamic>,
        );
      }
      if (listResp.statusCode == 200) {
        listing = MarketPulseListResponse.fromJson(
          jsonDecode(listResp.body) as Map<String, dynamic>,
        );
        lastUpdated = DateTime.now();
        errorMessage = null;
      }
      _updateDerivedState();
      _controller.add(null);
    } catch (e) {
      errorMessage = e.toString();
      if (state != PulseServiceState.disabled) {
        _setState(PulseServiceState.error);
      }
      _controller.add(null);
    }
  }

  void _updateDerivedState() {
    final h = health;
    final list = listing;
    if (h != null && !h.enabled) {
      _setState(PulseServiceState.disabled);
      return;
    }
    if (errorMessage != null && list == null) {
      _setState(PulseServiceState.error);
      return;
    }
    if (list == null) {
      _setState(PulseServiceState.loading);
      return;
    }
    if (list.alerts.isEmpty) {
      _setState(PulseServiceState.empty);
      return;
    }
    final anyLive = list.alerts.any((a) => a.isLive);
    if (anyLive && !_usePolling && (h?.streamConnected ?? false)) {
      _setState(PulseServiceState.live);
    } else if (list.alerts.any((a) => a.isStale)) {
      _setState(PulseServiceState.stale);
    } else if (_usePolling) {
      _setState(PulseServiceState.delayed);
    } else if (h != null && !h.streamConnected) {
      _setState(PulseServiceState.stopped);
    } else {
      _setState(PulseServiceState.delayed);
    }
  }

  void _setState(PulseServiceState next) {
    state = next;
  }
}
