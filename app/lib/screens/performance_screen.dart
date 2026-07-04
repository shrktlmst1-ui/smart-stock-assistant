import 'package:flutter/material.dart';

import '../models/signal_analytics.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'trade_replay_screen.dart';

class PerformanceScreen extends StatefulWidget {
  const PerformanceScreen({super.key});

  @override
  State<PerformanceScreen> createState() => _PerformanceScreenState();
}

class _PerformanceScreenState extends State<PerformanceScreen> {
  final _api = ApiService();
  PerformanceReport? _report;
  RankedSignalsResponse? _ranked;
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
      final results = await Future.wait([
        _api.fetchPerformanceReport(),
        _api.fetchRankedSignals(limit: 30),
      ]);
      if (mounted) {
        setState(() {
          _report = results[0] as PerformanceReport;
          _ranked = results[1] as RankedSignalsResponse;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('تحليلات الإشارات'),
        actions: [
          IconButton(
            icon: const Icon(Icons.history),
            tooltip: 'إعادة الصفقات',
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const TradeReplayScreen()),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppTheme.primary))
          : _error != null
              ? _ErrorView(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  color: AppTheme.primary,
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      if (_report != null) ...[
                        _SectionTitle('تقرير الأداء'),
                        _PerformanceSummary(report: _report!),
                        const SizedBox(height: 16),
                        _SectionTitle('إحصائيات عامة'),
                        _DashboardGrid(dashboard: _report!.dashboard),
                        const SizedBox(height: 16),
                      ],
                      if (_ranked != null) ...[
                        _SectionTitle('الإشارات مرتبة حسب الجودة'),
                        const SizedBox(height: 8),
                        ..._ranked!.signals.map(_SignalCard.new),
                      ],
                    ],
                  ),
                ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String title;
  const _SectionTitle(this.title);

  @override
  Widget build(BuildContext context) {
    return Text(title, style: Theme.of(context).textTheme.titleMedium);
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorView({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppTheme.danger, size: 48),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
          ],
        ),
      ),
    );
  }
}

class _PerformanceSummary extends StatelessWidget {
  final PerformanceReport report;
  const _PerformanceSummary({required this.report});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: _StatTile(
                    label: 'اليوم',
                    value: '${report.todaySignals}',
                    accent: AppTheme.primary,
                  ),
                ),
                Expanded(
                  child: _StatTile(
                    label: 'هذا الأسبوع',
                    value: '${report.weekSignals}',
                    accent: AppTheme.primary,
                  ),
                ),
                Expanded(
                  child: _StatTile(
                    label: 'هذا الشهر',
                    value: '${report.monthSignals}',
                    accent: AppTheme.primary,
                  ),
                ),
              ],
            ),
            const Divider(height: 24),
            Row(
              children: [
                Expanded(
                  child: _StatTile(
                    label: 'نسبة الفوز',
                    value: '${report.winRate.toStringAsFixed(1)}%',
                    accent: AppTheme.success,
                  ),
                ),
                Expanded(
                  child: _StatTile(
                    label: 'متوسط العائد',
                    value: '${report.averageReturnPct >= 0 ? '+' : ''}${report.averageReturnPct.toStringAsFixed(2)}%',
                    accent: AppTheme.changeColor(report.averageReturnPct),
                  ),
                ),
                Expanded(
                  child: _StatTile(
                    label: 'متوسط الخسارة',
                    value: '-${report.averageDrawdownPct.toStringAsFixed(2)}%',
                    accent: AppTheme.danger,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _StatTile(
                    label: 'أفضل سهم',
                    value: report.bestSymbol.isEmpty ? '—' : report.bestSymbol,
                    accent: AppTheme.success,
                  ),
                ),
                Expanded(
                  child: _StatTile(
                    label: 'أسوأ سهم',
                    value: report.worstSymbol.isEmpty ? '—' : report.worstSymbol,
                    accent: AppTheme.danger,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _DashboardGrid extends StatelessWidget {
  final AnalyticsDashboard dashboard;
  const _DashboardGrid({required this.dashboard});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _MiniStat('إجمالي الإشارات', '${dashboard.totalSignals}'),
            _MiniStat('رابحة', '${dashboard.winningSignals}'),
            _MiniStat('خاسرة', '${dashboard.losingSignals}'),
            _MiniStat('نسبة الفوز', '${dashboard.winRatePct.toStringAsFixed(1)}%'),
            _MiniStat('متوسط الربح', '+${dashboard.averageProfitPct.toStringAsFixed(2)}%'),
            _MiniStat('متوسط الخسارة', '-${dashboard.averageLossPct.toStringAsFixed(2)}%'),
            _MiniStat(
              'متوسط مدة الصفقة',
              '${dashboard.averageHoldingTimeHours.toStringAsFixed(1)} س',
            ),
            _MiniStat(
              'أفضل قطاع',
              dashboard.bestPerformingSector.isEmpty ? '—' : dashboard.bestPerformingSector,
            ),
            _MiniStat(
              'أفضل إطار',
              dashboard.bestPerformingTimeframe.isEmpty
                  ? '—'
                  : dashboard.bestPerformingTimeframe,
            ),
            _MiniStat(
              'أعلى AI اليوم',
              dashboard.highestAiScoreToday.toStringAsFixed(0),
            ),
            _MiniStat(
              'أعلى ثقة اليوم',
              dashboard.highestConfidenceToday.toStringAsFixed(0),
            ),
            _MiniStat('مفتوحة', '${dashboard.openTracks}'),
            _MiniStat('نشطة', '${dashboard.activeTracks}'),
          ],
        ),
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label;
  final String value;
  final Color accent;
  const _StatTile({required this.label, required this.value, required this.accent});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(label, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            color: accent,
            fontWeight: FontWeight.bold,
            fontSize: 16,
          ),
        ),
      ],
    );
  }
}

class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  const _MiniStat(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 150,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _SignalCard extends StatelessWidget {
  final SignalAnalyticsRecord signal;
  const _SignalCard(this.signal);

  Color _statusColor() {
    if (signal.trackStatus.contains('Target')) return AppTheme.success;
    if (signal.trackStatus == 'Stop Loss Hit') return AppTheme.danger;
    if (signal.trackStatus == 'Active') return AppTheme.primary;
    if (signal.trackStatus == 'Expired') return AppTheme.textSecondary;
    return AppTheme.warning;
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  signal.symbol,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppTheme.card,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: AppTheme.border),
                  ),
                  child: Text(signal.signal, style: const TextStyle(fontSize: 12)),
                ),
                const Spacer(),
                Text(
                  signal.qualityStars,
                  style: const TextStyle(color: AppTheme.warning, fontSize: 14),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              signal.tradeQualityLabel,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                _Chip('AI ${signal.aiScore.toStringAsFixed(0)}'),
                _Chip('ثقة ${signal.confidenceScore.toStringAsFixed(0)}%'),
                _Chip(signal.trackStatus, color: _statusColor()),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '${signal.signalDate} ${signal.signalTime} · ${signal.timeframe}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (signal.sector.isNotEmpty || signal.industry.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                [signal.sector, signal.industry].where((s) => s.isNotEmpty).join(' · '),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: 12),
            const Text('لماذا هذا الإشارة؟', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            ...signal.explanation.map(
              (item) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(
                  children: [
                    Icon(
                      item.passed ? Icons.check_circle : Icons.cancel,
                      size: 16,
                      color: item.passed ? AppTheme.success : AppTheme.danger,
                    ),
                    const SizedBox(width: 8),
                    Expanded(child: Text(item.label, style: const TextStyle(fontSize: 13))),
                  ],
                ),
              ),
            ),
            if (signal.failureReason != null && signal.failureReason!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                'سبب الخسارة: ${signal.failureReason}',
                style: const TextStyle(color: AppTheme.danger, fontSize: 13),
              ),
            ],
            if (signal.profitPct != 0) ...[
              const SizedBox(height: 8),
              Text(
                'العائد: ${signal.profitPct >= 0 ? '+' : ''}${signal.profitPct.toStringAsFixed(2)}%',
                style: TextStyle(color: AppTheme.changeColor(signal.profitPct)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final Color? color;
  const _Chip(this.label, {this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: (color ?? AppTheme.textSecondary).withOpacity(0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.border),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 11, color: color ?? AppTheme.textPrimary),
      ),
    );
  }
}
