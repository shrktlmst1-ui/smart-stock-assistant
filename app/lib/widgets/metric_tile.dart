import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../l10n/ar_localization.dart';
import '../theme/app_theme.dart';

class MetricTile extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;
  final IconData? icon;

  const MetricTile({
    super.key,
    required this.label,
    required this.value,
    this.valueColor,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[
                Icon(icon, size: 14, color: AppTheme.textSecondary),
                const SizedBox(width: 6),
              ],
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    color: AppTheme.textSecondary,
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              color: valueColor ?? AppTheme.textPrimary,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class ScoreBadge extends StatelessWidget {
  final int score;

  const ScoreBadge({super.key, required this.score});

  @override
  Widget build(BuildContext context) {
    final color = AppTheme.scoreColor(score);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity( 0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity( 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.star_rounded, color: color, size: 16),
          const SizedBox(width: 4),
          Text(
            '$score/100',
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }
}

class TrendChip extends StatelessWidget {
  final String trend;

  const TrendChip({super.key, required this.trend});

  @override
  Widget build(BuildContext context) {
    IconData icon;
    Color color;
    switch (trend) {
      case 'صاعد':
        icon = Icons.trending_up;
        color = AppTheme.accent;
        break;
      case 'هابط':
        icon = Icons.trending_down;
        color = AppTheme.danger;
        break;
      default:
        icon = Icons.trending_flat;
        color = AppTheme.warning;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity( 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 4),
          Text(ArUi.trend(trend), style: TextStyle(color: color, fontSize: 13)),
        ],
      ),
    );
  }
}

class RiskBadge extends StatelessWidget {
  final String riskLevel;

  const RiskBadge({super.key, required this.riskLevel});

  @override
  Widget build(BuildContext context) {
    final color = AppTheme.riskColor(riskLevel);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity( 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity( 0.4)),
      ),
      child: Text(
        'مخاطرة: ${ArUi.riskLevel(riskLevel)}',
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w500),
      ),
    );
  }
}

String formatPrice(double price) => '\$${price.toStringAsFixed(2)}';

String formatPercent(double percent) {
  final sign = percent >= 0 ? '+' : '';
  return '$sign${percent.toStringAsFixed(2)}%';
}

String formatVolume(int volume) {
  if (volume >= 1000000000) {
    return '${(volume / 1000000000).toStringAsFixed(1)}B';
  }
  if (volume >= 1000000) {
    return '${(volume / 1000000).toStringAsFixed(1)}M';
  }
  if (volume >= 1000) {
    return '${(volume / 1000).toStringAsFixed(1)}K';
  }
  return volume.toString();
}

String formatDate(DateTime date) => DateFormat('yyyy/MM/dd HH:mm').format(date);
