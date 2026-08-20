import 'package:flutter/material.dart';

import '../l10n/ar_localization.dart';
import '../models/market_pulse.dart';
import '../theme/app_theme.dart';
import '../widgets/market_pulse_card.dart';

class MarketPulseDetailScreen extends StatelessWidget {
  final MarketPulseAlert alert;

  const MarketPulseDetailScreen({super.key, required this.alert});

  @override
  Widget build(BuildContext context) {
    final decision = alert.displayDecision;
    final color = pulseDecisionColor(decision);
    final rrr = alert.riskRewardRatio;

    return Scaffold(
      appBar: AppBar(title: Text('نبض ${alert.symbol}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        alert.symbol,
                        style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                      ),
                      const Spacer(),
                      Text(
                        '\$${alert.price.toStringAsFixed(2)}',
                        style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    ArUi.pulseDecision(decision),
                    style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  Text(
                    'Score ${alert.score.toStringAsFixed(1)} / 100',
                    style: const TextStyle(color: AppTheme.textSecondary),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          _section('أسباب القرار', alert.reasonsAr.map((r) => '• $r').join('\n')),
          _scoreRow('catalyst', alert.catalystScore, 30),
          _scoreRow('liquidity', alert.liquidityScore, 30),
          _scoreRow('price confirmation', alert.priceConfirmationScore, 25),
          _scoreRow('risk penalty', alert.riskPenalty, 25, inverted: true),
          const SizedBox(height: 12),
          _section('مستويات التداول', '''
الدخول: \$${alert.entry.toStringAsFixed(2)}
وقف الخسارة: \$${alert.stopLoss.toStringAsFixed(2)}
الأهداف: ${alert.targets.map((t) => '\$${t.toStringAsFixed(2)}').join(' → ')}
R/R: ${rrr != null ? rrr.toStringAsFixed(2) : '—'}'''),
          if (alert.riskFlags.isNotEmpty)
            _section('علامات المخاطرة', alert.riskFlags.map(ArUi.pulseTriggerType).join('، ')),
          _section('مصدر الخبر', '''
${alert.headline}
نوع المحفز: ${ArUi.pulseTriggerType(alert.catalyst.triggerType)}
عمر الخبر: ${ArUi.durationShort(alert.newsAgeSeconds.toInt())}
وقت البيانات: ${alert.dataTimestamp}
ينتهي التنبيه: ${alert.expiresAt}'''),
          Card(
            color: AppTheme.danger.withOpacity(0.1),
            child: const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'تنبيه: هذه الإشارة تحليلية مبنية على أخبار وسيولة لحظية تقديرية، وليست ضماناً للربح أو توصية استثمارية.',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _section(String title, String body) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 8),
            Text(body, style: const TextStyle(color: AppTheme.textSecondary, height: 1.5)),
          ],
        ),
      ),
    );
  }

  Widget _scoreRow(String label, double value, double max, {bool inverted = false}) {
    final pct = (value / max).clamp(0.0, 1.0);
    final barColor = inverted ? AppTheme.danger : AppTheme.primary;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(width: 120, child: Text(label)),
          Expanded(
            child: LinearProgressIndicator(
              value: pct,
              backgroundColor: AppTheme.border,
              color: barColor,
            ),
          ),
          const SizedBox(width: 8),
          Text('${value.toStringAsFixed(1)}/$max'),
        ],
      ),
    );
  }
}
