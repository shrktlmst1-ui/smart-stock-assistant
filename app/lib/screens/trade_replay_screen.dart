import 'package:flutter/material.dart';

import '../l10n/ar_localization.dart';
import '../models/trade_replay.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class TradeReplayScreen extends StatefulWidget {
  final TradeReplayDetail? initialReplay;

  const TradeReplayScreen({super.key, this.initialReplay});

  @override
  State<TradeReplayScreen> createState() => _TradeReplayScreenState();
}

class _TradeReplayScreenState extends State<TradeReplayScreen> {
  final _api = ApiService();
  TradeReplayListResponse? _data;
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
      final data = await _api.fetchTradeReplayList(limit: 40);
      if (mounted) {
        setState(() {
          _data = data;
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

  void _openDetail(TradeReplayDetail replay) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TradeReplayDetailScreen(replay: replay),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('إعادة الصفقات'),
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
              ? Center(child: Text(_error!))
              : RefreshIndicator(
                  onRefresh: _load,
                  color: AppTheme.primary,
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      if (_data != null) ...[
                        _InsightsCard(insights: _data!.insights),
                        const SizedBox(height: 16),
                        Text(
                          'سجل الصفقات',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 8),
                        ..._data!.replays.map(
                          (r) => _ReplayListTile(
                            replay: r,
                            onTap: () => _openDetail(r),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
    );
  }
}

class TradeReplayDetailScreen extends StatelessWidget {
  final TradeReplayDetail replay;

  const TradeReplayDetailScreen({super.key, required this.replay});

  String _formatSeconds(int? seconds) {
    if (seconds == null) return '—';
    if (seconds < 60) return '${seconds}s';
    if (seconds < 3600) return '${seconds ~/ 60} د';
    return '${seconds ~/ 3600} س ${(seconds % 3600) ~/ 60} د';
  }

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

    return Scaffold(
      appBar: AppBar(title: Text('${replay.symbol} — إعادة الصفقة')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${replay.symbol} · ${ArUi.signal(replay.signal)}',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  Text('${replay.signalDate} ${replay.signalTime}'),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    children: [
                      _chip('تحليل ${replay.aiScore.toStringAsFixed(0)}'),
                      _chip('ثقة ${replay.confidenceScore.toStringAsFixed(0)}%'),
                      _chip('دخول ${replay.entryPrice.toStringAsFixed(2)}'),
                      _chip(ArUi.trackStatus(replay.trackStatus)),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('الخط الزمني', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: replay.timeline.map((event) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: 48,
                          child: Text(
                            event.eventTime,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                        Container(
                          width: 8,
                          height: 8,
                          margin: const EdgeInsets.only(top: 5, left: 4, right: 12),
                          decoration: const BoxDecoration(
                            color: AppTheme.primary,
                            shape: BoxShape.circle,
                          ),
                        ),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(ArUi.timelineEvent(event.eventLabel)),
                              if (event.price != null)
                                Text(
                                  '\$${event.price!.toStringAsFixed(2)}',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
          if (post != null) ...[
            const SizedBox(height: 16),
            Text('تحليل ما بعد الصفقة', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          ArUi.tradeResult(post.finalResult),
                          style: TextStyle(
                            color: _resultColor(post.finalResult),
                            fontWeight: FontWeight.bold,
                            fontSize: 20,
                          ),
                        ),
                        const Spacer(),
                        Text(
                          ArUi.tradeQuality(post.postTradeQuality),
                          style: const TextStyle(color: AppTheme.warning),
                        ),
                      ],
                    ),
                    const Divider(height: 24),
                    _metricRow('أقصى ربح', '+${post.maxProfitPct.toStringAsFixed(2)}%'),
                    _metricRow('أقصى تراجع', '-${post.maxDrawdownPct.toStringAsFixed(2)}%'),
                    if (post.highestPriceAfterEntry != null)
                      _metricRow(
                        'أعلى سعر',
                        '\$${post.highestPriceAfterEntry!.toStringAsFixed(2)}',
                      ),
                    if (post.lowestPriceAfterEntry != null)
                      _metricRow(
                        'أدنى سعر',
                        '\$${post.lowestPriceAfterEntry!.toStringAsFixed(2)}',
                      ),
                    _metricRow('مدة الصفقة', _formatSeconds(post.tradeDurationSeconds)),
                    _metricRow('وقت TP1', _formatSeconds(post.timeToTarget1Seconds)),
                    _metricRow('وقت TP2', _formatSeconds(post.timeToTarget2Seconds)),
                    _metricRow('وقت TP3', _formatSeconds(post.timeToTarget3Seconds)),
                    _metricRow('وقت وقف الخسارة', _formatSeconds(post.timeToStopLossSeconds)),
                    _metricRow(
                      'جودة الدخول',
                      post.entryQualityScore.toStringAsFixed(1),
                    ),
                    _metricRow('R:R', post.riskRewardRatio.toStringAsFixed(2)),
                  ],
                ),
              ),
            ),
          ] else ...[
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('تتبع مباشر', style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 8),
                    _metricRow(
                      'أقصى ربح حالي',
                      '+${replay.liveMaxProfitPct.toStringAsFixed(2)}%',
                    ),
                    _metricRow(
                      'أقصى تراجع حالي',
                      '-${replay.liveMaxDrawdownPct.toStringAsFixed(2)}%',
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _metricRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(child: Text(label, style: const TextStyle(color: AppTheme.textSecondary))),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _chip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(label, style: const TextStyle(fontSize: 11)),
    );
  }
}

class _InsightsCard extends StatelessWidget {
  final PerformanceInsights insights;
  const _InsightsCard({required this.insights});

  String _dur(int seconds) {
    if (seconds <= 0) return '—';
    if (seconds < 3600) return '${seconds ~/ 60} د';
    return '${seconds ~/ 3600} س';
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('رؤى الأداء', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            Wrap(
              spacing: 16,
              runSpacing: 12,
              children: [
                _item('متوسط وقت الهدف', '${insights.averageTimeToTargetSeconds.toStringAsFixed(0)}s'),
                _item('متوسط التراجع', '${insights.averageDrawdownPct.toStringAsFixed(2)}%'),
                _item('متوسط الربح', '${insights.averageProfitPct.toStringAsFixed(2)}%'),
                _item('أفضل مدة', _dur(insights.bestHoldingTimeSeconds)),
                _item('أفضل إطار', insights.bestTimeframe.isEmpty ? '—' : insights.bestTimeframe),
                _item('أفضل دخول', insights.bestEntryQualitySymbol.isEmpty ? '—' : insights.bestEntryQualitySymbol),
                _item('أسوأ دخول', insights.worstEntryQualitySymbol.isEmpty ? '—' : insights.worstEntryQualitySymbol),
                _item('صفقات مغلقة', '${insights.closedTrades}'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _item(String label, String value) {
    return SizedBox(
      width: 150,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _ReplayListTile extends StatelessWidget {
  final TradeReplayDetail replay;
  final VoidCallback onTap;

  const _ReplayListTile({required this.replay, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final post = replay.postTrade;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        onTap: onTap,
        title: Text('${replay.symbol} · ${ArUi.signal(replay.signal)}'),
        subtitle: Text(
          '${replay.signalDate} ${replay.signalTime} · ${ArUi.trackStatus(replay.trackStatus)}',
        ),
        trailing: post != null
            ? Text(
                ArUi.tradeResult(post.finalResult),
                style: TextStyle(
                  color: post.finalResult == 'WIN'
                      ? AppTheme.success
                      : post.finalResult == 'LOSS'
                          ? AppTheme.danger
                          : AppTheme.warning,
                  fontWeight: FontWeight.bold,
                ),
              )
            : const Icon(Icons.timelapse, color: AppTheme.primary),
      ),
    );
  }
}
