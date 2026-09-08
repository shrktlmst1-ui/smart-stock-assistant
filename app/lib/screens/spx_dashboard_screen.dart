import 'dart:async';

import 'package:flutter/material.dart';

import '../models/spx_signal.dart';
import '../services/spx_api_service.dart';

class SpxDashboardScreen extends StatefulWidget {
  const SpxDashboardScreen({super.key});

  @override
  State<SpxDashboardScreen> createState() => _SpxDashboardScreenState();
}

class _SpxDashboardScreenState extends State<SpxDashboardScreen> {
  final _api = SpxApiService();
  SpxSignal? _signal;
  String? _error;
  bool _loading = true;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(minutes: 1), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool refresh = false}) async {
    if (mounted) setState(() => _loading = true);
    try {
      final signal = await _api.fetchSignal(refresh: refresh);
      if (!mounted) return;
      setState(() {
        _signal = signal;
        _error = null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Color _decisionColor(String decision) {
    if (decision == 'CALL') return Colors.greenAccent;
    if (decision == 'PUT') return Colors.redAccent;
    return Colors.amberAccent;
  }

  String _decisionText(String decision) {
    if (decision == 'CALL') return 'CALL — أفضلية شراء';
    if (decision == 'PUT') return 'PUT — أفضلية بيع';
    return 'NO TRADE — لا توجد صفقة تستحق المخاطرة';
  }

  String _regime(String regime) {
    switch (regime) {
      case 'TREND_UP':
        return 'اتجاه صاعد';
      case 'TREND_DOWN':
        return 'اتجاه هابط';
      case 'RANGE':
        return 'تذبذب / Range';
      default:
        return 'غير واضح';
    }
  }

  Widget _metric(String label, double? value) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        margin: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Text(label, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 5),
            Text(
              value == null ? '—' : value.toStringAsFixed(2),
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final signal = _signal;
    final color = signal == null ? Theme.of(context).colorScheme.primary : _decisionColor(signal.decision);

    return Scaffold(
      appBar: AppBar(
        title: const Text('وجه المؤشر — SPX'),
        actions: [
          IconButton(
            tooltip: 'تحديث الآن',
            onPressed: _loading ? null : () => _load(refresh: true),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _load(refresh: true),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                ),
              ),
            if (signal == null && _loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 80),
                child: Center(child: CircularProgressIndicator()),
              ),
            if (signal != null) ...[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    children: [
                      const Text('قرار النظام الآن', style: TextStyle(fontSize: 15)),
                      const SizedBox(height: 10),
                      Text(
                        _decisionText(signal.decision),
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: color),
                      ),
                      const SizedBox(height: 12),
                      Text('${signal.score}/100', style: const TextStyle(fontSize: 42, fontWeight: FontWeight.bold)),
                      Text('Confidence ${(signal.confidence * 100).toStringAsFixed(0)}%'),
                      const SizedBox(height: 12),
                      LinearProgressIndicator(value: signal.score / 100, minHeight: 8),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: _infoCard('النظام', _regime(signal.regime))),
                  Expanded(child: _infoCard('البيانات', signal.dataFresh ? 'Fresh' : 'Stale')),
                  Expanded(child: _infoCard('0DTE', signal.optionsReady ? 'جاهز' : 'مرفوض')),
                ],
              ),
              const SizedBox(height: 12),
              _section('المستويات', [
                Row(children: [
                  _metric('VWAP', signal.levels.vwap),
                  _metric('PDH', signal.levels.previousDayHigh),
                  _metric('PDL', signal.levels.previousDayLow),
                ]),
                Row(children: [
                  _metric('OR High', signal.levels.openingRangeHigh),
                  _metric('OR Low', signal.levels.openingRangeLow),
                  _metric('Swing H', signal.levels.swingHigh),
                ]),
                Row(children: [
                  _metric('Swing L', signal.levels.swingLow),
                  _metric('PWH', signal.levels.previousWeekHigh),
                  _metric('PWL', signal.levels.previousWeekLow),
                ]),
              ]),
              const SizedBox(height: 12),
              _section('خطة الصفقة', [
                Row(children: [
                  _metric('Entry', signal.entry),
                  _metric('Stop', signal.stopLoss),
                ]),
                Row(children: [
                  _metric('TP1', signal.takeProfit1),
                  _metric('TP2', signal.takeProfit2),
                ]),
              ]),
              if (signal.option != null) ...[
                const SizedBox(height: 12),
                _section('عقد 0DTE المؤهل', [
                  Text(signal.option!.ticker ?? 'SPX option', style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _chip('Strike', signal.option!.strike),
                      _chip('Delta', signal.option!.delta),
                      _chip('IV', signal.option!.iv),
                      _chip('Spread', signal.option!.spreadPct == null ? null : signal.option!.spreadPct! * 100, suffix: '%'),
                      _chip('Volume', signal.option!.volume.toDouble()),
                      _chip('OI', signal.option!.openInterest.toDouble()),
                    ],
                  ),
                ]),
              ],
              const SizedBox(height: 12),
              _section('لماذا؟', [
                Text(signal.reason.isEmpty ? 'لا يوجد سبب إضافي.' : signal.reason),
                if (signal.factors.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  ...signal.factors.map((x) => ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.check_circle_outline, size: 19),
                        title: Text(x),
                      )),
                ],
                if (signal.rejectedFactors.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  ...signal.rejectedFactors.map((x) => ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.block, size: 19),
                        title: Text(x),
                      )),
                ],
              ]),
            ],
          ],
        ),
      ),
    );
  }

  Widget _infoCard(String label, String value) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        child: Column(children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 4),
          Text(value, textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.bold)),
        ]),
      ),
    );
  }

  Widget _section(String title, List<Widget> children) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          ...children,
        ]),
      ),
    );
  }

  Widget _chip(String label, double? value, {String suffix = ''}) {
    return Chip(label: Text('$label: ${value == null ? '—' : value.toStringAsFixed(2)}$suffix'));
  }
}
