import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/alert.dart';
import '../models/stock.dart';
import '../services/app_state.dart';
import '../theme/app_theme.dart';
import '../widgets/factor_score_panel.dart';
import '../widgets/metric_tile.dart';
import '../widgets/stock_card.dart';

class StockAnalysisScreen extends StatefulWidget {
  final String symbol;

  const StockAnalysisScreen({super.key, required this.symbol});

  @override
  State<StockAnalysisScreen> createState() => _StockAnalysisScreenState();
}

class _StockAnalysisScreenState extends State<StockAnalysisScreen> {
  StockAnalysis? _analysis;
  bool _loading = true;
  bool _inWatchlist = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final appState = context.read<AppState>();
    try {
      final analysis = await appState.stockData.getAnalysis(widget.symbol);
      final inList = await appState.isInWatchlist(widget.symbol);
      if (mounted) {
        setState(() {
          _analysis = analysis;
          _inWatchlist = inList;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _analysis = null;
          _loading = false;
        });
      }
    }
  }

  Future<void> _toggleWatchlist() async {
    final appState = context.read<AppState>();
    if (_analysis == null) return;

    if (_inWatchlist) {
      await appState.removeFromWatchlist(_analysis!.symbol);
    } else {
      await appState.addToWatchlist(_analysis!.symbol, _analysis!.name);
    }

    if (mounted) {
      setState(() => _inWatchlist = !_inWatchlist);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _inWatchlist ? 'تمت الإضافة للمراقبة' : 'تمت الإزالة من المراقبة',
          ),
        ),
      );
    }
  }

  Future<void> _addAlert() async {
    if (_analysis == null) return;

    final priceController = TextEditingController(
      text: _analysis!.price.toStringAsFixed(2),
    );
    String condition = 'above';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          backgroundColor: AppTheme.card,
          title: const Text('إضافة تنبيه'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: priceController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                textDirection: TextDirection.ltr,
                decoration: const InputDecoration(labelText: 'السعر المستهدف \$'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: condition,
                decoration: const InputDecoration(labelText: 'الشرط'),
                items: const [
                  DropdownMenuItem(value: 'above', child: Text('عندما يتجاوز')),
                  DropdownMenuItem(value: 'below', child: Text('عندما ينخفض عن')),
                ],
                onChanged: (v) => setDialogState(() => condition = v ?? 'above'),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('إلغاء'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(ctx, true),
              style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primary),
              child: const Text('حفظ'),
            ),
          ],
        ),
      ),
    );

    if (confirmed == true && mounted) {
      final price = double.tryParse(priceController.text);
      if (price == null) return;

      final alert = StockAlert(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        symbol: _analysis!.symbol,
        name: _analysis!.name,
        targetPrice: price,
        condition: condition,
        createdAt: DateTime.now(),
      );

      await context.read<AppState>().addAlert(alert);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('تم حفظ التنبيه')),
        );
      }
    }
    priceController.dispose();
  }

  String _recommendationSummary(StockAnalysis analysis) {
    final explanation = analysis.tradeDecision?.aiExplanation;
    if (explanation != null && explanation.isNotEmpty) {
      return explanation.split('\n').first;
    }
    return analysis.recommendationReason;
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: Text(widget.symbol)),
        body: const LoadingView(message: 'جاري تحليل السهم...'),
      );
    }

    if (_analysis == null) {
      return Scaffold(
        appBar: AppBar(title: Text(widget.symbol)),
        body: const EmptyState(
          icon: Icons.error_outline,
          title: 'السهم غير موجود',
          subtitle: 'تحقق من رمز السهم وحاول مرة أخرى',
        ),
      );
    }

    final a = _analysis!;
    final changeColor = AppTheme.changeColor(a.changePercent);

    return Scaffold(
      appBar: AppBar(
        title: Text(a.symbol),
        actions: [
          IconButton(
            icon: Icon(_inWatchlist ? Icons.bookmark : Icons.bookmark_outline),
            onPressed: _toggleWatchlist,
            tooltip: 'قائمة المراقبة',
          ),
          IconButton(
            icon: const Icon(Icons.notifications_active_outlined),
            onPressed: _addAlert,
            tooltip: 'تنبيه',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    a.name,
                    style: const TextStyle(color: AppTheme.textSecondary),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        formatPrice(a.price),
                        style: const TextStyle(
                          fontSize: 32,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text(
                        formatPercent(a.changePercent),
                        style: TextStyle(
                          fontSize: 18,
                          color: changeColor,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      TrendChip(trend: a.trend),
                      const SizedBox(width: 8),
                      ScoreBadge(score: a.score),
                      const SizedBox(width: 8),
                      RiskBadge(riskLevel: a.riskLevel),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SectionHeader(title: 'المؤشرات الفنية'),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 1.8,
            children: [
              MetricTile(label: 'RSI', value: a.rsi.toStringAsFixed(1), icon: Icons.speed),
              MetricTile(
                label: 'MACD',
                value: a.macd.toStringAsFixed(2),
                valueColor: a.macd >= a.macdSignal ? AppTheme.accent : AppTheme.danger,
                icon: Icons.show_chart,
              ),
              MetricTile(label: 'EMA 20', value: formatPrice(a.ema20)),
              MetricTile(label: 'EMA 50', value: formatPrice(a.ema50)),
              MetricTile(label: 'EMA 200', value: formatPrice(a.ema200)),
              MetricTile(
                label: 'حجم التداول',
                value: formatVolume(a.volume),
                icon: Icons.bar_chart,
              ),
            ],
          ),
          const SectionHeader(title: 'الدعم والمقاومة'),
          Row(
            children: [
              Expanded(
                child: MetricTile(
                  label: 'الدعم',
                  value: formatPrice(a.support),
                  valueColor: AppTheme.accent,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: MetricTile(
                  label: 'المقاومة',
                  value: formatPrice(a.resistance),
                  valueColor: AppTheme.danger,
                ),
              ),
            ],
          ),
          if (a.tradeDecision != null) ...[
            const SectionHeader(title: 'قرار المحرك — Decision Engine'),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      a.tradeDecision!.professionalSignal ?? a.tradeDecision!.recommendation,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.primary,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'AI Score: ${(a.tradeDecision!.professionalAiScore ?? a.tradeDecision!.aiConfidence).toStringAsFixed(0)} · R:R ${a.tradeDecision!.riskRewardRatio.toStringAsFixed(2)}',
                      style: const TextStyle(color: AppTheme.textSecondary),
                    ),
                    if (a.tradeDecision!.expectedHoldingTime != null &&
                        a.tradeDecision!.expectedHoldingTime!.isNotEmpty)
                      Text(
                        'مدة الاحتفاظ: ${a.tradeDecision!.expectedHoldingTime}',
                        style: const TextStyle(color: AppTheme.textSecondary),
                      ),
                    const SizedBox(height: 12),
                    Text('منطقة الدخول: ${formatPrice(a.tradeDecision!.entryZoneLow)} – ${formatPrice(a.tradeDecision!.entryZoneHigh)}'),
                    Text('وقف الخسارة: ${formatPrice(a.tradeDecision!.stopLoss)}'),
                    Text('TP1: ${formatPrice(a.tradeDecision!.takeProfit1)} · TP2: ${formatPrice(a.tradeDecision!.takeProfit2)}'),
                    Text('سيولة واردة: ${a.tradeDecision!.liquidityInflow.toStringAsFixed(0)}% · صادرة: ${a.tradeDecision!.liquidityOutflow.toStringAsFixed(0)}%'),
                    Text('مخاطر الفخ: ${a.tradeDecision!.trapRisk.toStringAsFixed(0)}% · الأخبار: ${a.tradeDecision!.newsRisk.toStringAsFixed(0)}%'),
                    Text('البنية: ${a.tradeDecision!.marketStructure}'),
                    const SizedBox(height: 16),
                    if (a.tradeDecision!.factorScores.isNotEmpty)
                      FactorScorePanel(
                        factorScores: a.tradeDecision!.factorScores,
                        buyBlockers: a.tradeDecision!.buyBlockers,
                        finalBlocker: a.tradeDecision!.finalBlocker,
                        aiExplanation: a.tradeDecision!.aiExplanation,
                        signal: a.tradeDecision!.professionalSignal ?? a.tradeDecision!.recommendation,
                      )
                    else if ((a.tradeDecision!.aiExplanation ?? a.tradeDecision!.triggerReason).isNotEmpty)
                      Text(
                        a.tradeDecision!.aiExplanation ?? a.tradeDecision!.triggerReason,
                        style: const TextStyle(color: AppTheme.textSecondary, height: 1.5),
                      ),
                    if (a.tradeDecision!.devilsAdvocate.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      Text('Devil\'s Advocate: ${a.tradeDecision!.devilsAdvocate}'),
                    ],
                  ],
                ),
              ),
            ),
          ],
          const SectionHeader(title: 'خطة التداول المقترحة'),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 1.8,
            children: [
              MetricTile(
                label: 'سعر الدخول',
                value: formatPrice(a.entryPrice),
                valueColor: AppTheme.primary,
              ),
              MetricTile(
                label: 'وقف الخسارة',
                value: formatPrice(a.stopLoss),
                valueColor: AppTheme.danger,
              ),
              MetricTile(
                label: 'الهدف الأول',
                value: formatPrice(a.target1),
                valueColor: AppTheme.accent,
              ),
              MetricTile(
                label: 'الهدف الثاني',
                value: formatPrice(a.target2),
                valueColor: AppTheme.accent,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.lightbulb_outline, color: AppTheme.warning, size: 20),
                      SizedBox(width: 8),
                      Text(
                        'سبب التوصية',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    _recommendationSummary(a),
                    style: const TextStyle(
                      color: AppTheme.textSecondary,
                      height: 1.6,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            '⚠️ للمتابعة والتحليل فقط — لا ينفذ أوامر تلقائية.',
            style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
