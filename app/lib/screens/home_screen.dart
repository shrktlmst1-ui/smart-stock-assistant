import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/ar_localization.dart';
import '../models/market_pulse.dart';
import '../models/opportunity_now.dart';
import '../services/api_service.dart';
import '../services/app_state.dart';
import '../services/home_screen_cache.dart';
import '../theme/app_theme.dart';
import '../widgets/distinguished_jump_section.dart';
import '../widgets/jump_section.dart';
import '../widgets/market_pulse_card.dart';
import 'market_pulse_screen.dart';
import 'stock_analysis_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  MarketPulseListResponse? _pulseListing;
  OpportunityNowResponse? _opportunityNow;
  PulseServiceState _pulseState = PulseServiceState.loading;
  bool _opportunityLoading = true;
  String? _opportunityError;
  Timer? _liveTimer;
  Timer? _resumeDebounce;
  DateTime? _lastSuccessfulFetch;
  bool _refreshInFlight = false;
  bool _bootstrapComplete = false;

  static const _pollSeconds = 12;
  static const _resumeDebounceMs = 600;
  static const _minResumeRefreshGap = Duration(seconds: 4);

  ApiService get _api => context.read<AppState>().api;

  bool get _hasCachedOpportunity =>
      _opportunityNow != null || (HomeScreenCache.memorySnapshot?.opportunity != null);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _restoreCachedSnapshotSync();
    _bootstrap();
    _liveTimer = Timer.periodic(const Duration(seconds: _pollSeconds), (_) => _refreshAll(background: true));
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _liveTimer?.cancel();
    _resumeDebounce?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _scheduleResumeRefresh();
    }
  }

  void _restoreCachedSnapshotSync() {
    final cached = HomeScreenCache.memorySnapshot;
    if (cached != null) {
      _applyCachedSnapshot(cached);
    }
  }

  Future<void> _bootstrap() async {
    final cached = await HomeScreenCache.load();
    if (cached != null && mounted) {
      _applyCachedSnapshot(cached);
    }
    await _refreshAll(background: _hasCachedOpportunity);
    if (mounted) {
      setState(() => _bootstrapComplete = true);
    }
  }

  void _applyCachedSnapshot(HomeCachedSnapshot cached) {
    HomeScreenCache.seedMemory(cached);
    if (_lastSuccessfulFetch != null && cached.fetchedAt.isBefore(_lastSuccessfulFetch!)) {
      return;
    }
    _lastSuccessfulFetch = cached.fetchedAt;

    final opp = cached.opportunity;
    if (opp != null) {
      _opportunityNow = opp;
      _opportunityLoading = false;
      _opportunityError = null;
    }

    final pulseList = cached.pulseList;
    if (pulseList != null) {
      _pulseListing = pulseList;
      final health = cached.pulseHealth;
      if (health != null) {
        _pulseState = _derivePulseState(pulseList, health);
      } else if (_pulseState == PulseServiceState.loading) {
        _pulseState = pulseList.alerts.isEmpty ? PulseServiceState.empty : PulseServiceState.delayed;
      }
    }

    if (mounted) setState(() {});
  }

  void _scheduleResumeRefresh() {
    _resumeDebounce?.cancel();
    _resumeDebounce = Timer(const Duration(milliseconds: _resumeDebounceMs), () {
      if (!mounted || _refreshInFlight) return;
      final last = _lastSuccessfulFetch;
      if (last != null && DateTime.now().difference(last) < _minResumeRefreshGap) {
        return;
      }
      _refreshAll(background: true);
    });
  }

  List<MarketPulseAlert> get _validPulseAlerts {
    return (_pulseListing?.alerts ?? const <MarketPulseAlert>[])
        .where((a) => a.price > 0 && a.score > 0 && a.decision != 'EXPIRED')
        .toList();
  }

  Future<void> _refreshAll({bool background = false}) async {
    if (_refreshInFlight) return;
    _refreshInFlight = true;
    final fetchedAt = DateTime.now();

    if (!background && !_hasCachedOpportunity && mounted) {
      setState(() => _opportunityLoading = true);
    }

    Map<String, dynamic>? oppRaw;
    Map<String, dynamic>? pulseListRaw;
    Map<String, dynamic>? pulseHealthRaw;
    OpportunityNowResponse? opp;
    MarketPulseListResponse? pulseList;
    MarketPulseHealth? pulseHealth;
    String? pulseError;
    String? oppError;

    try {
      final oppPayload = await _api.fetchOpportunityNowPayload();
      opp = oppPayload.data;
      oppRaw = oppPayload.raw;
    } catch (e) {
      oppError = _friendlyError(e);
    }

    try {
      final listPayload = await _api.fetchMarketPulseAlertsPayload();
      pulseList = listPayload.data;
      pulseListRaw = listPayload.raw;
      try {
        final healthPayload = await _api.fetchMarketPulseHealthPayload();
        pulseHealth = healthPayload.data;
        pulseHealthRaw = healthPayload.raw;
      } catch (e) {
        pulseError = _friendlyError(e);
      }
    } catch (e) {
      pulseError = _friendlyError(e);
    }

    try {
      final hasFreshOpportunity = opp != null || pulseList != null;
      if (hasFreshOpportunity &&
          (_lastSuccessfulFetch == null || !fetchedAt.isBefore(_lastSuccessfulFetch!))) {
        final snapshot = HomeCachedSnapshot(
          fetchedAt: fetchedAt,
          opportunityRaw: oppRaw ?? HomeScreenCache.memorySnapshot?.opportunityRaw,
          pulseListRaw: pulseListRaw ?? HomeScreenCache.memorySnapshot?.pulseListRaw,
          pulseHealthRaw: pulseHealthRaw ?? HomeScreenCache.memorySnapshot?.pulseHealthRaw,
        );
        await HomeScreenCache.save(snapshot);
        _lastSuccessfulFetch = fetchedAt;

        if (mounted) {
          setState(() {
            if (opp != null) {
              _opportunityNow = opp;
              _opportunityError = null;
            }
            if (pulseList != null) {
              _pulseListing = pulseList;
              _pulseState = pulseError != null
                  ? (_pulseListing != null ? _pulseState : PulseServiceState.error)
                  : _derivePulseState(pulseList, pulseHealth ?? _defaultPulseHealth());
            }
            _opportunityLoading = false;
          });
        }
      } else if (mounted) {
        setState(() {
          if (oppError != null && _opportunityNow == null) {
            _opportunityError = oppError;
          }
          _opportunityLoading = false;
        });
      }
    } finally {
      _refreshInFlight = false;
    }
  }

  MarketPulseHealth _defaultPulseHealth() {
    return const MarketPulseHealth(
      enabled: false,
      status: 'disabled',
      hasApiKey: false,
      subscribedSymbols: 0,
      maxSymbols: 50,
      streamConnected: false,
      message: '',
    );
  }

  String _friendlyError(Object error) {
    final text = error.toString();
    if (text.contains('401') || text.contains('انتهت الجلسة')) {
      return 'انتهت الجلسة — سجّل الدخول مجددًا';
    }
    if (text.contains('ClientException') || text.contains('Load failed') || text.contains('TimeoutException')) {
      return 'تعذر الاتصال بالخادم — تحقق من الشبكة';
    }
    return ArUi.backendText(text);
  }

  PulseServiceState _derivePulseState(
    MarketPulseListResponse list,
    MarketPulseHealth health,
  ) {
    final enabled = health.isActive || list.enabled;
    if (!enabled) return PulseServiceState.disabled;
    final valid = list.alerts.where((a) => a.price > 0 && a.score > 0).toList();
    if (valid.isEmpty) return PulseServiceState.empty;
    if (valid.any((a) => a.isLive) && health.streamConnected) {
      return PulseServiceState.live;
    }
    return PulseServiceState.delayed;
  }

  void _openPulse() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const MarketPulseScreen()),
    );
  }

  void _openAnalysis(String symbol) {
    if (symbol.trim().isEmpty) return;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => StockAnalysisScreen(symbol: symbol.trim().toUpperCase()),
      ),
    );
  }

  Future<void> _logout() async {
    await HomeScreenCache.clear();
    final appState = context.read<AppState>();
    await appState.logout();
    if (mounted) {
      Navigator.of(context).pushNamedAndRemoveUntil('/login', (_) => false);
    }
  }

  Widget _buildHeroBanner() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            AppTheme.primary.withOpacity(0.2),
            AppTheme.surface,
          ],
          begin: Alignment.topRight,
          end: Alignment.bottomLeft,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.primary.withOpacity(0.3),
        ),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'مساعد الأسهم الذكي',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
          ),
          SizedBox(height: 4),
          Text(
            'قفزات خبرية ومراقبة — فقط عند تأكيد حقيقي',
            style: TextStyle(color: AppTheme.textSecondary),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final showOpportunitySpinner = _opportunityLoading && _opportunityNow == null;

    return Scaffold(
      appBar: AppBar(
        title: const Text('مساعد الأسهم الذكي'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _refreshInFlight ? null : () => _refreshAll(background: _hasCachedOpportunity),
            tooltip: 'تحديث',
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _logout,
            tooltip: 'خروج',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _refreshAll(background: _hasCachedOpportunity),
        color: AppTheme.primary,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            DistinguishedJumpSection(
              data: _opportunityNow,
              loading: showOpportunitySpinner,
              onOpenSymbol: _openAnalysis,
            ),
            JumpSection(
              data: _opportunityNow,
              loading: showOpportunitySpinner,
              onOpenSymbol: _openAnalysis,
            ),
            if (_opportunityError != null && _opportunityNow != null) ...[
              const SizedBox(height: 8),
              Text(
                _opportunityError!,
                style: const TextStyle(color: AppTheme.danger, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ] else if (_opportunityError != null && _opportunityNow == null && _bootstrapComplete) ...[
              const SizedBox(height: 8),
              Text(
                _opportunityError!,
                style: const TextStyle(color: AppTheme.danger, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: 16),
            _buildHeroBanner(),
            const SizedBox(height: 12),
            MarketPulseHomeEntryCard(
              state: _pulseState == PulseServiceState.loading && _pulseListing != null
                  ? PulseServiceState.delayed
                  : _pulseState,
              alertCount: _validPulseAlerts.length,
              onTap: _openPulse,
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _refreshInFlight ? null : () => _refreshAll(background: _hasCachedOpportunity),
                icon: const Icon(Icons.refresh),
                label: const Text('تحديث'),
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'للمتابعة فقط وليس توصية استثمارية',
              style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
