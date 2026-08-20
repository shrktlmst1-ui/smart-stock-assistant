import 'package:flutter/material.dart';

import '../l10n/ar_localization.dart';
import '../models/market_pulse.dart';
import '../theme/app_theme.dart';

Color pulseDecisionColor(String decision) {
  switch (decision.toUpperCase()) {
    case 'ENTER_NOW':
      return AppTheme.success;
    case 'WAIT':
      return const Color(0xFFD29922);
    case 'AVOID':
      return AppTheme.danger;
    case 'EXPIRED':
    default:
      return AppTheme.textSecondary;
  }
}

class MarketPulseAlertCard extends StatelessWidget {
  final MarketPulseAlert alert;
  final VoidCallback? onTap;

  const MarketPulseAlertCard({super.key, required this.alert, this.onTap});

  @override
  Widget build(BuildContext context) {
    final decision = alert.displayDecision;
    final color = pulseDecisionColor(decision);
    final changeHint = alert.price > alert.vwap ? '+' : '';

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    alert.symbol,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.textPrimary,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    '\$${alert.price.toStringAsFixed(2)}',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.textPrimary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  _Chip(
                    label: ArUi.pulseDecision(decision),
                    color: color,
                  ),
                  const SizedBox(width: 8),
                  _Chip(
                    label: 'Score ${alert.score.toStringAsFixed(0)}/100',
                    color: AppTheme.primary,
                  ),
                  const Spacer(),
                  Text(
                    changeHint,
                    style: TextStyle(color: color, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                alert.headline,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  _Meta(label: 'محفز', value: ArUi.pulseTriggerType(alert.catalyst.triggerType)),
                  _Meta(label: 'عمر الخبر', value: ArUi.durationShort(alert.newsAgeSeconds.toInt())),
                  _Meta(label: 'ضغط شراء', value: '${alert.estimatedBuyPressure.toStringAsFixed(0)}%'),
                  _Meta(label: 'RVOL', value: alert.rvol.toStringAsFixed(1)),
                  _Meta(label: 'تسارع دولار', value: '${(alert.dollarVolumeAcceleration * 100).toStringAsFixed(0)}%'),
                  _Meta(label: 'Spread', value: '${alert.spreadBps.toStringAsFixed(0)} bps'),
                  _Meta(label: 'VWAP', value: alert.vwap.toStringAsFixed(2)),
                  _Meta(label: 'مخاطرة', value: ArUi.pulseRiskLevel(alert)),
                  _Meta(label: 'ينتهي', value: _shortTime(alert.expiresAt)),
                ],
              ),
              if (alert.isLive) ...[
                const SizedBox(height: 8),
                const Row(
                  children: [
                    Icon(Icons.circle, size: 8, color: AppTheme.success),
                    SizedBox(width: 6),
                    Text('بيانات لحظية', style: TextStyle(color: AppTheme.success, fontSize: 12)),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _shortTime(String iso) {
    if (iso.length >= 16) return iso.substring(11, 16);
    return iso;
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final Color color;

  const _Chip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 12),
      ),
    );
  }
}

class _Meta extends StatelessWidget {
  final String label;
  final String value;

  const _Meta({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Text(
      '$label: $value',
      style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
    );
  }
}

class MarketPulseHomeEntryCard extends StatelessWidget {
  final PulseServiceState state;
  final int alertCount;
  final VoidCallback onTap;

  const MarketPulseHomeEntryCard({
    super.key,
    required this.state,
    required this.alertCount,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppTheme.surface,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.primary.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.monitor_heart_outlined, color: AppTheme.primary, size: 28),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'نبض السوق',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      alertCount > 0
                          ? '$alertCount إشارة نشطة — ${ArUi.pulseServiceState(state)}'
                          : ArUi.pulseServiceState(state),
                      style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_left, color: AppTheme.textSecondary),
            ],
          ),
        ),
      ),
    );
  }
}

class PulseSkeletonList extends StatelessWidget {
  final int count;

  const PulseSkeletonList({super.key, this.count = 3});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: List.generate(count, (i) {
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: Container(
            height: 140,
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(width: 80, height: 16, color: AppTheme.border),
                const SizedBox(height: 12),
                Container(width: double.infinity, height: 12, color: AppTheme.border),
                const SizedBox(height: 8),
                Container(width: 200, height: 12, color: AppTheme.border),
              ],
            ),
          ),
        );
      }),
    );
  }
}
