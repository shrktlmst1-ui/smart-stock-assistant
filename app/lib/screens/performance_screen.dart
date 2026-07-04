import 'package:flutter/material.dart';

import '../models/signal_analytics.dart';
import '../models/trade_replay.dart';
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
  TradeReplayListResponse? _replay;
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
        _api.fetchRankedSignals(limit: 25),
        _api.fetchTradeReplayList(limit: 20),
      ]);
      if (mounted) {
        setState(() {
          _report = results[0] as PerformanceReport;
          _ranked = results[1] as RankedSignalsResponse;
          _replay = results[2] as TradeReplayListResponse;
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

  void _openReplayDetail(TradeReplayDetail replay) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TradeReplayDetailScreen(replay: replay),
      ),
    );
  }

  AnalyticsDashboard? get _dashboard =>
      _report?.dashboard ?? _ranked?.dashboard;

  PerformanceInsights? get _insights => _replay?.insights;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Performance'),
        actions: [
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
                      if (_dashboard != null) ...[
                        _SectionHeader(
                          title: 'Win Rate',
                          icon: Icons.emoji_events_outlined,
                        ),
                        _WinRateCard(dashboard: _dashboard!),
                        const SizedBox(height: 20),
                      ],
                      if (_report != null) ...[
                        _SectionHeader(
                          title: 'Performance Analytics',
                          icon: Icons.insights_outlined,
                        ),
                        _PerformanceAnalyticsCard(report: _report!),
                        const SizedBox(height: 20),
                      ],
                      if (_insights != null) ...[
                        _SectionHeader(
                          title: 'Trade Statistics',
                          icon: Icons.bar_chart_outlined,
                        ),
                        _TradeStatisticsCard(
                          insights: _insights!,
                          dashboard: _dashboard,
                        ),
                        const SizedBox(height: 20),
                      ],
                      if (_dashboard != null && _ranked != null) ...[
                        _SectionHeader(
                          title: 'AI Performance',
                          icon: Icons.psychology_outlined,
                        ),
                        _AiPerformanceCard(
                          dashboard: _dashboard!,
                          signals: _ranked!.signals,
                        ),
                        const SizedBox(height: 20),
                      ],
                      if (_ranked != null) ...[
                        _SectionHeader(
                          title: 'Signal History',
                          icon: Icons.list_alt_outlined,
                          count: _ranked!.signals.length,
                        ),
                        if (_ranked!.signals.isEmpty)
                          const _EmptySection(message: 'No signals recorded yet.')
                        else
                          ..._ranked!.signals.map(_SignalHistoryTile.new),
                        const SizedBox(height: 20),
                      ],
                      if (_replay != null) ...[
                        _SectionHeader(
                          title: 'Trade Replay',
                          icon: Icons.history,
                          count: _replay!.replays.length,
                        ),
                        if (_replay!.replays.isEmpty)
                          const _EmptySection(message: 'No trade replays yet.')
                        else
                          ..._replay!.replays.map(
                            (r) => _ReplayTile(
                              replay: r,
                              onTap: () => _openReplayDetail(r),
                            ),
                          ),
                      ],
                      const SizedBox(height: 24),
                    ],
                  ),
                ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final IconData icon;
  final int? count;

  const _SectionHeader({
    required this.title,
    required this.icon,
    this.count,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Icon(icon, size: 20, color: AppTheme.primary),
          const SizedBox(width: 8),
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          if (count != null) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: AppTheme.primary.withOpacity(0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '$count',
                style: const TextStyle(fontSize: 12, color: AppTheme.primary),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _EmptySection extends StatelessWidget {
  final String message;
  const _EmptySection({required this.message});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Center(
          child: Text(message, style: Theme.of(context).textTheme.bodySmall),
        ),
      ),
    );
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
            ElevatedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

class _WinRateCard extends StatelessWidget {
  final AnalyticsDashboard dashboard;
  const _WinRateCard({required this.dashboard});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${dashboard.winRatePct.toStringAsFixed(1)}%',
                    style: const TextStyle(
                      fontSize: 42,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.success,
                    ),
                  ),
                  const Text('Win Rate'),
                  const SizedBox(height: 12),
                  Text(
                    '${dashboard.winningSignals} wins · ${dashboard.losingSignals} losses',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            Column(
              children: [
                _WinStatChip('Total', '${dashboard.totalSignals}'),
                const SizedBox(height: 8),
                _WinStatChip('Open', '${dashboard.openTracks}'),
                const SizedBox(height: 8),
                _WinStatChip('Active', '${dashboard.activeTracks}'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _WinStatChip extends StatelessWidget {
  final String label;
  final String value;
  const _WinStatChip(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(width: 6),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _PerformanceAnalyticsCard extends StatelessWidget {
  final PerformanceReport report;
  const _PerformanceAnalyticsCard({required this.report});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(child: _Metric('Today', '${report.todaySignals}')),
                Expanded(child: _Metric('This Week', '${report.weekSignals}')),
                Expanded(child: _Metric('This Month', '${report.monthSignals}')),
              ],
            ),
            const Divider(height: 24),
            Row(
              children: [
                Expanded(
                  child: _Metric(
                    'Avg Return',
                    '${report.averageReturnPct >= 0 ? '+' : ''}${report.averageReturnPct.toStringAsFixed(2)}%',
                  ),
                ),
                Expanded(
                  child: _Metric(
                    'Avg Drawdown',
                    '-${report.averageDrawdownPct.toStringAsFixed(2)}%',
                  ),
                ),
                Expanded(child: _Metric('Overall', '${report.overallTotal}')),
              ],
            ),
            const Divider(height: 24),
            Row(
              children: [
                Expanded(
                  child: _Metric(
                    'Best Symbol',
                    report.bestSymbol.isEmpty ? '—' : report.bestSymbol,
                  ),
                ),
                Expanded(
                  child: _Metric(
                    'Worst Symbol',
                    report.worstSymbol.isEmpty ? '—' : report.worstSymbol,
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

class _TradeStatisticsCard extends StatelessWidget {
  final PerformanceInsights insights;
  final AnalyticsDashboard? dashboard;

  const _TradeStatisticsCard({required this.insights, this.dashboard});

  String _dur(int seconds) {
    if (seconds <= 0) return '—';
    if (seconds < 3600) return '${seconds ~/ 60}m';
    return '${seconds ~/ 3600}h ${(seconds % 3600) ~/ 60}m';
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 16,
          runSpacing: 14,
          children: [
            _Metric(
              'Avg Time To Target',
              insights.averageTimeToTargetSeconds > 0
                  ? _dur(insights.averageTimeToTargetSeconds.round())
                  : '—',
            ),
            _Metric(
              'Avg Drawdown',
              '${insights.averageDrawdownPct.toStringAsFixed(2)}%',
            ),
            _Metric(
              'Avg Profit',
              '${insights.averageProfitPct.toStringAsFixed(2)}%',
            ),
            _Metric('Best Holding Time', _dur(insights.bestHoldingTimeSeconds)),
            _Metric(
              'Best Timeframe',
              insights.bestTimeframe.isEmpty ? '—' : insights.bestTimeframe,
            ),
            _Metric(
              'Best Entry Quality',
              insights.bestEntryQualitySymbol.isEmpty
                  ? '—'
                  : insights.bestEntryQualitySymbol,
            ),
            _Metric(
              'Worst Entry Quality',
              insights.worstEntryQualitySymbol.isEmpty
                  ? '—'
                  : insights.worstEntryQualitySymbol,
            ),
            if (dashboard != null)
              _Metric(
                'Avg Holding',
                '${dashboard!.averageHoldingTimeHours.toStringAsFixed(1)}h',
              ),
            _Metric('Closed Trades', '${insights.closedTrades}'),
          ],
        ),
      ),
    );
  }
}

class _AiPerformanceCard extends StatelessWidget {
  final AnalyticsDashboard dashboard;
  final List<SignalAnalyticsRecord> signals;

  const _AiPerformanceCard({required this.dashboard, required this.signals});

  double get _avgAi {
    if (signals.isEmpty) return 0;
    return signals.map((s) => s.aiScore).reduce((a, b) => a + b) / signals.length;
  }

  double get _avgConfidence {
    if (signals.isEmpty) return 0;
    return signals.map((s) => s.confidenceScore).reduce((a, b) => a + b) /
        signals.length;
  }

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
                  child: _AiMetric(
                    label: 'Highest AI Today',
                    value: dashboard.highestAiScoreToday.toStringAsFixed(0),
                    color: AppTheme.primary,
                  ),
                ),
                Expanded(
                  child: _AiMetric(
                    label: 'Highest Confidence Today',
                    value: dashboard.highestConfidenceToday.toStringAsFixed(0),
                    color: AppTheme.accent,
                  ),
                ),
              ],
            ),
            const Divider(height: 24),
            Row(
              children: [
                Expanded(
                  child: _AiMetric(
                    label: 'Avg AI Score',
                    value: _avgAi.toStringAsFixed(1),
                    color: AppTheme.primary,
                  ),
                ),
                Expanded(
                  child: _AiMetric(
                    label: 'Avg Confidence',
                    value: '${_avgConfidence.toStringAsFixed(1)}%',
                    color: AppTheme.accent,
                  ),
                ),
              ],
            ),
            if (dashboard.bestPerformingSector.isNotEmpty ||
                dashboard.bestPerformingTimeframe.isNotEmpty) ...[
              const Divider(height: 24),
              if (dashboard.bestPerformingSector.isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Best Sector: ${dashboard.bestPerformingSector}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              if (dashboard.bestPerformingTimeframe.isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Best Timeframe: ${dashboard.bestPerformingTimeframe}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _AiMetric extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _AiMetric({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),
        const SizedBox(height: 4),
        Text(label, style: Theme.of(context).textTheme.bodySmall, textAlign: TextAlign.center),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;
  const _Metric(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 100,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 2),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _SignalHistoryTile extends StatelessWidget {
  final SignalAnalyticsRecord signal;
  const _SignalHistoryTile(this.signal);

  Color _statusColor() {
    if (signal.trackStatus.contains('Target')) return AppTheme.success;
    if (signal.trackStatus == 'Stop Loss Hit') return AppTheme.danger;
    if (signal.trackStatus == 'Active') return AppTheme.primary;
    return AppTheme.textSecondary;
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        title: Row(
          children: [
            Text(
              signal.symbol,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(width: 8),
            Text(signal.signal, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
        subtitle: Text(
          '${signal.signalDate} ${signal.signalTime} · AI ${signal.aiScore.toStringAsFixed(0)} · ${signal.confidenceScore.toStringAsFixed(0)}%',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: _statusColor().withOpacity(0.15),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            signal.trackStatus,
            style: TextStyle(fontSize: 11, color: _statusColor()),
          ),
        ),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 12,
                  runSpacing: 6,
                  children: [
                    _DetailChip('Entry', signal.entryPrice.toStringAsFixed(2)),
                    _DetailChip('SL', signal.stopLoss.toStringAsFixed(2)),
                    _DetailChip('TP1', signal.target1.toStringAsFixed(2)),
                    _DetailChip('TP2', signal.target2.toStringAsFixed(2)),
                    _DetailChip('TP3', signal.target3.toStringAsFixed(2)),
                    _DetailChip('Quality', signal.tradeQualityLabel),
                  ],
                ),
                if (signal.explanation.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  const Text('Signal Explanation', style: TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  ...signal.explanation.map(
                    (item) => Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        children: [
                          Icon(
                            item.passed ? Icons.check_circle : Icons.cancel,
                            size: 14,
                            color: item.passed ? AppTheme.success : AppTheme.danger,
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(item.label, style: const TextStyle(fontSize: 12)),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
                if (signal.profitPct != 0)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      'Return: ${signal.profitPct >= 0 ? '+' : ''}${signal.profitPct.toStringAsFixed(2)}%',
                      style: TextStyle(color: AppTheme.changeColor(signal.profitPct)),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReplayTile extends StatelessWidget {
  final TradeReplayDetail replay;
  final VoidCallback onTap;

  const _ReplayTile({required this.replay, required this.onTap});

  Color _resultColor(String result) {
    switch (result) {
      case 'WIN':
        return AppTheme.success;
      case 'LOSS':
        return AppTheme.danger;
      default:
        return AppTheme.warning;
    }
  }

  @override
  Widget build(BuildContext context) {
    final post = replay.postTrade;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          backgroundColor: AppTheme.primary.withOpacity(0.15),
          child: Text(
            replay.symbol.length > 2 ? replay.symbol.substring(0, 2) : replay.symbol,
            style: const TextStyle(fontSize: 12, color: AppTheme.primary),
          ),
        ),
        title: Text('${replay.symbol} · ${replay.signal}'),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${replay.signalDate} ${replay.signalTime}'),
            if (replay.timeline.isNotEmpty)
              Text(
                replay.timeline.map((e) => '${e.eventTime} ${e.eventLabel}').take(3).join(' → '),
                style: const TextStyle(fontSize: 11),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
          ],
        ),
        isThreeLine: true,
        trailing: post != null
            ? Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    post.finalResult,
                    style: TextStyle(
                      color: _resultColor(post.finalResult),
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    post.postTradeQuality,
                    style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                  ),
                ],
              )
            : const Icon(Icons.timelapse, color: AppTheme.primary, size: 20),
      ),
    );
  }
}

class _DetailChip extends StatelessWidget {
  final String label;
  final String value;
  const _DetailChip(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text('$label: $value', style: const TextStyle(fontSize: 11)),
    );
  }
}
