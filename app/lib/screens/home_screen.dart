import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/ar_localization.dart';
import '../models/stock.dart';
import '../models/market_pulse.dart';
import '../services/api_service.dart';
import '../services/app_state.dart';
import '../theme/app_theme.dart';
import '../widgets/stock_card.dart';
import '../widgets/market_pulse_card.dart';
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
  PulseServiceState _pulseState = PulseServiceState.loading;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = context.read<AppState>().stockData;
      final api = ApiService();
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
      try {
        pulseList = await api.fetchMarketPulseAlerts();
        pulseHealth = await api.fetchMarketPulseHealth();
      } catch (_) {
        // pulse optional — keep opportunities working
      }
      if (mounted) {
        setState(() {
          _dashboard = dashboard;
          _pulseListing = pulseList;
          _pulseState = _derivePulseState(pulseList, pulseHealth);
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _dashboard = null;
          _loading = false;
          _error = e.toString();
        });
      }
    }
  }

  PulseServiceState _derivePulseState(
    MarketPulseListResponse list,
    MarketPulseHealth health,
  ) {
    if (!health.enabled) return PulseServiceState.disabled;
    if (list.alerts.isEmpty) return PulseServiceState.empty;
    if (list.alerts.any((a) => a.isLive) && health.streamConnected) {
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
            _DebugRow('الأسهم المفحوصة', '${d.symbolsScanned}'),
            _DebugRow('إجمالي الأسهم', '${d.universeSymbols}'),
            _DebugRow('اجتازت السيولة', '${d.passedLiquidity}'),
            _DebugRow('تحليل عميق', '${d.deepAnalysisCompleted}'),
            _DebugRow('اجتازت جميع الفلاتر 18', '${d.passedAllFilters}'),
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

  @override
  Widget build(BuildContext context) {
    final dashboard = _dashboard;
    final items = dashboard?.displayItems ?? [];
    final showingWatchlist = dashboard?.showingWatchlist ?? false;

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
        child: _loading
            ? const LoadingView(message: 'جاري تحميل الفرص المباشرة...')
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Container(
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
                              ? 'أعلى درجات التحليل — ليست إشارات دخول حتى اجتياز جميع الفلاتر'
                              : 'السوق الأمريكي المباشر — يجب اجتياز 18 عاملاً',
                          style: const TextStyle(color: AppTheme.textSecondary),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  MarketPulseHomeEntryCard(
                    state: _pulseState,
                    alertCount: _pulseListing?.count ?? 0,
                    onTap: _openPulse,
                  ),
                  if (dashboard != null) ...[
                    const SizedBox(height: 12),
                    _buildDebugSummary(dashboard),
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
                  if (_error != null) ...[
                    Card(
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
                              ArUi.backendText(_error!),
                              style: const TextStyle(
                                color: AppTheme.textSecondary,
                                fontSize: 13,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  if (items.isEmpty && _error == null)
                    const Padding(
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
                    )
                  else if (items.isNotEmpty) ...[
                    SectionHeader(
                      title: showingWatchlist ? 'قائمة المراقبة' : 'أفضل الفرص',
                      subtitle: showingWatchlist
                          ? 'مرتبة حسب درجة التحليل (قد لا تجتاز جميع الفلاتر)'
                          : 'بيانات مباشرة من Polygon',
                    ),
                    ...List.generate(items.length, (i) {
                      final stock = items[i];
                      MarketPulseAlert? pulse;
                      for (final a in _pulseListing?.alerts ?? const <MarketPulseAlert>[]) {
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
