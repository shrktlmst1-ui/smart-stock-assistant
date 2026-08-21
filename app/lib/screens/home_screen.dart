import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/ar_localization.dart';
import '../models/stock.dart';
import '../models/market_pulse.dart';
import '../models/opportunity_now.dart';
import '../services/api_service.dart';
import '../services/app_state.dart';
import '../theme/app_theme.dart';
import '../widgets/stock_card.dart';
import '../widgets/market_pulse_card.dart';
import '../widgets/extended_alert_card.dart';
import '../widgets/opportunity_now_card.dart';
import 'market_pulse_screen.dart';
import 'stock_analysis_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  OpportunitiesDashboard? _dashboard;
  MarketPulseListResponse? _pulseListing;
  OpportunityNowResponse? _opportunityNow;
  PulseServiceState _pulseState = PulseServiceState.loading;
  bool _loading = true;
  bool _opportunityLoading = true;
  String? _error;
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

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _pulseState = PulseServiceState.loading;
    });
    try {
      final data = context.read<AppState>().stockData;
      final dashboard = await data.getOpportunitiesDashboard(limit: 20);
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
          _dashboard = dashboard;
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
          _dashboard = null;
          _loading = false;
          _error = _friendlyError(e);
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
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => StockAnalysisScreen(symbol: symbol),
      ),
    );
  }

  Future<void> _logout() async {
    await context.read<AppState>().logout();
    if (mounted) {
      Navigator.of(context).pushNamedAndRemoveUntil('/login', (_) => false);
    }
  }

  Widget _buildHeroBanner(bool showingWatchlist) {
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            showingWatchlist
                ? 'أفضل الأسهم المرشحة للمراقبة'
                : 'أفضل الفرص المؤسسية',
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            showingWatchlist
                ? 'أعلى درجات التحليل — مراقبة حتى اجتياز شروط الأمان'
                : 'السوق الأمريكي — أسهم حتى 10 دولارات مع شروط أمان إلزامية',
            style: const TextStyle(color: AppTheme.textSecondary),
          ),
        ],
      ),
    );
  }

  Widget _buildDebugSummary(OpportunitiesDashboard dashboard) {
    final d = dashboard.debug;
    final reason = dashboard.noSignalReason.isNotEmpty
        ? dashboard.noSignalReason
        : dashboard.explanation;

    return Card(
      color: AppTheme.surface,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.analytics_outlined, color: AppTheme.primary, size: 20),
                const SizedBox(width: 8),
                Text(
                  ArUi.marketLabel(dashboard.marketStatus),
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    color: AppTheme.textPrimary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _DebugRow('المرحلة 1 — فحص سريع', '${d.phase1QuickScanned > 0 ? d.phase1QuickScanned : d.symbolsScanned}'),
            _DebugRow('المرحلة 2 — مرشحون', '${d.phase2RankedCandidates}'),
            _DebugRow('المرحلة 3 — تحليل عميق', '${d.phase3DeepCompleted > 0 ? d.phase3DeepCompleted : d.deepAnalysisCompleted}'),
            _DebugRow('تغطية السوق', '${d.marketCoveragePct.toStringAsFixed(1)}%'),
            if (d.lastFullScanAt.isNotEmpty)
              _DebugRow('آخر مسح كامل', _shortScanTime(d.lastFullScanAt)),
            _DebugRow('اجتازت السيولة', '${d.passedLiquidity}'),
            _DebugRow('اجتازت شروط الأمان', '${d.passedSafety > 0 ? d.passedSafety : d.passedAllFilters}'),
            if (d.signalWait > 0 || d.signalAvoid > 0) ...[
              const SizedBox(height: 8),
              Text(
                'الإشارات: انتظار ${d.signalWait}، تجنب ${d.signalAvoid}',
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
              ),
            ],
            if (reason.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                ArUi.backendText(reason),
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _shortScanTime(String iso) {
    if (iso.length >= 16) return iso.substring(11, 16);
    return iso;
  }

  Widget _buildOpportunitiesSection() {
    final dashboard = _dashboard;
    final items = dashboard?.displayItems ?? [];
    final showingWatchlist = dashboard?.showingWatchlist ?? false;

    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 32),
        child: Center(
          child: Column(
            children: [
              CircularProgressIndicator(color: AppTheme.primary),
              SizedBox(height: 16),
              Text(
                'جاري تحميل الفرص المباشرة...',
                style: TextStyle(color: AppTheme.textSecondary),
              ),
            ],
          ),
        ),
      );
    }

    if (_error != null) {
      return Card(
        color: AppTheme.danger.withOpacity(0.12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'خطأ في الاتصال بالخادم',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: AppTheme.danger,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _error!,
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 13,
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (items.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 32),
        child: Column(
          children: [
            Icon(
              Icons.insights_outlined,
              size: 56,
              color: AppTheme.textSecondary,
            ),
            SizedBox(height: 16),
            Text(
              'لا توجد فرص عالية الجودة حالياً',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: AppTheme.textPrimary,
              ),
            ),
            SizedBox(height: 8),
            Text(
              'راجع ملخص الماسح أعلاه لأعداد المراحل وأسباب الرفض.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppTheme.textSecondary),
            ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: showingWatchlist ? 'قائمة المراقبة' : 'أفضل الفرص',
          subtitle: showingWatchlist
              ? 'مرتبة حسب درجة التحليل (قد لا تجتاز جميع الفلاتر)'
              : 'بيانات مباشرة من Polygon',
        ),
        ...List.generate(items.length, (i) {
          final stock = items[i];
          MarketPulseAlert? pulse;
          for (final a in _validPulseAlerts) {
            if (a.symbol == stock.symbol) {
              pulse = a;
              break;
            }
          }
          return StockCard(
            stock: stock,
            rank: i + 1,
            pulseScore: pulse?.score,
            pulseDecision: pulse?.displayDecision,
            pulseHeadline: pulse?.headline,
            onTap: () => _openAnalysis(stock.symbol),
          );
        }),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final showingWatchlist = _dashboard?.showingWatchlist ?? false;

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
        onRefresh: _load,
        color: AppTheme.primary,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildHeroBanner(showingWatchlist),
            const SizedBox(height: 12),
            ExtendedAlertHomeCard(alert: _opportunityNow?.extendedAlert),
            if (_opportunityNow?.hasExtendedAlert == true) const SizedBox(height: 12),
            OpportunityNowHomeCard(
              data: _opportunityNow,
              loading: _opportunityLoading && _opportunityNow == null,
              error: _opportunityError,
              onRefresh: _refreshLive,
            ),
            const SizedBox(height: 12),
            MarketPulseHomeEntryCard(
              state: _pulseState,
              alertCount: _validPulseAlerts.length,
              onTap: _openPulse,
            ),
            if (_dashboard != null) ...[
              const SizedBox(height: 12),
              _buildDebugSummary(_dashboard!),
            ],
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
            _buildOpportunitiesSection(),
            const SizedBox(height: 8),
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

class _DebugRow extends StatelessWidget {
  final String label;
  final String value;

  const _DebugRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
          Text(
            value,
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }
}
