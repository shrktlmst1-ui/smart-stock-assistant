import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/ar_localization.dart';
import '../models/market_pulse.dart';
import '../models/opportunity_now.dart';
import '../services/api_service.dart';
import '../services/app_state.dart';
import '../theme/app_theme.dart';
import '../widgets/jump_section.dart';
import '../widgets/market_pulse_card.dart';
import 'market_pulse_screen.dart';
import 'stock_analysis_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  MarketPulseListResponse? _pulseListing;
  OpportunityNowResponse? _opportunityNow;
  PulseServiceState _pulseState = PulseServiceState.loading;
  bool _loading = true;
  bool _opportunityLoading = true;
  String? _opportunityError;
  Timer? _liveTimer;

  static const _pollSeconds = 12;

  ApiService get _api => context.read<AppState>().api;

  @override
  void initState() {
    super.initState();
    _load();
    _liveTimer = Timer.periodic(const Duration(seconds: _pollSeconds), (_) => _refreshLive());
  }

  @override
  void dispose() {
    _liveTimer?.cancel();
    super.dispose();
  }

  List<MarketPulseAlert> get _validPulseAlerts {
    return (_pulseListing?.alerts ?? const <MarketPulseAlert>[])
        .where((a) => a.price > 0 && a.score > 0 && a.decision != 'EXPIRED')
        .toList();
  }

  Future<void> _refreshLive() async {
    if (!mounted || _loading) return;
    try {
      final results = await Future.wait([
        _api.fetchOpportunityNow(),
        _api.fetchMarketPulseAlerts(),
        _api.fetchMarketPulseHealth(),
      ]);
      final opp = results[0] as OpportunityNowResponse;
      final pulseList = results[1] as MarketPulseListResponse;
      final pulseHealth = results[2] as MarketPulseHealth;
      if (mounted) {
        setState(() {
          _opportunityNow = opp;
          _pulseListing = pulseList;
          _pulseState = _derivePulseState(pulseList, pulseHealth);
          _opportunityError = null;
          _opportunityLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _opportunityError = _friendlyError(e);
          _opportunityLoading = false;
        });
      }
    }
  }

  Future<void> _loadOpportunityNow() async {
    if (mounted) setState(() => _opportunityLoading = true);
    try {
      final opp = await _api.fetchOpportunityNow();
      if (mounted) {
        setState(() {
          _opportunityNow = opp;
          _opportunityError = null;
          _opportunityLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _opportunityError = _friendlyError(e);
          _opportunityLoading = false;
        });
      }
    }
  }

  Future<void> _load({bool backgroundRefresh = false}) async {
    setState(() {
      _loading = false;
      _pulseState = PulseServiceState.loading;
    });
    try {
      var pulseList = const MarketPulseListResponse(enabled: false, alerts: [], count: 0);
      var pulseHealth = const MarketPulseHealth(
        enabled: false,
        status: 'disabled',
        hasApiKey: false,
        subscribedSymbols: 0,
        maxSymbols: 50,
        streamConnected: false,
        message: '',
      );
      String? pulseError;
      try {
        pulseList = await _api.fetchMarketPulseAlerts();
        pulseHealth = await _api.fetchMarketPulseHealth();
      } catch (e) {
        pulseError = _friendlyError(e);
      }
      await _loadOpportunityNow();
      if (mounted) {
        setState(() {
          _pulseListing = pulseList;
          _pulseState = pulseError != null
              ? PulseServiceState.error
              : _derivePulseState(pulseList, pulseHealth);
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _pulseState = PulseServiceState.error;
        });
      }
    }
  }

  String _friendlyError(Object error) {
    final text = error.toString();
    if (text.contains('401') || text.contains('انتهت الجلسة')) {
      return 'انتهت الجلسة — سجّل الدخول مجددًا';
    }
    if (text.contains('ClientException') || text.contains('Load failed')) {
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
    await context.read<AppState>().logout();
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
    return Scaffold(
      appBar: AppBar(
        title: const Text('مساعد الأسهم الذكي'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
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
        onRefresh: () => _load(backgroundRefresh: true),
        color: AppTheme.primary,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            JumpSection(
              data: _opportunityNow,
              loading: _opportunityLoading && _opportunityNow == null,
              onOpenSymbol: _openAnalysis,
            ),
            if (_opportunityError != null) ...[
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
              state: _pulseState,
              alertCount: _validPulseAlerts.length,
              onTap: _openPulse,
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _load,
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
