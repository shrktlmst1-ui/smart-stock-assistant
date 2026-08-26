import 'package:flutter/material.dart';

import '../models/opportunity_now.dart';
import '../theme/app_theme.dart';

class ExtendedAlertHomeCard extends StatelessWidget {
  final OpportunityNowSignal? alert;
  final VoidCallback? onTap;

  const ExtendedAlertHomeCard({super.key, required this.alert, this.onTap});

  @override
  Widget build(BuildContext context) {
    final top = alert;
    if (top == null || !top.isRealNewsJump) {
      return const SizedBox.shrink();
    }

    final accent = const Color(0xFFD29922);
    final gapPrefix = top.extendedGapPct >= 0 ? '+' : '';
    final sessionTag = top.session == 'PRE_MARKET' || top.session == 'AFTER_HOURS'
        ? top.session
        : top.sessionLabelAr;

    return Card(
      color: AppTheme.surface,
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
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: accent.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(Icons.newspaper_outlined, color: accent, size: 26),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'قفزة خبرية',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        top.symbol,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      Text(
                        '$gapPrefix${top.extendedGapPct.toStringAsFixed(1)}%',
                        style: TextStyle(color: accent, fontWeight: FontWeight.w700, fontSize: 15),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                'تم رصد القفزة — لا تطارد السهم',
                style: TextStyle(
                  color: AppTheme.danger,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  if (sessionTag.isNotEmpty)
                    _Chip(label: sessionTag, color: AppTheme.primary),
                  if (top.detectionStage.isNotEmpty)
                    _Chip(
                      label: top.detectionStage == 'EXPLOSIVE' ? 'EXPLOSIVE' : top.detectionStage,
                      color: accent,
                    ),
                ],
              ),
              const SizedBox(height: 10),
              _RowMetric('Current Price', '\$${top.price.toStringAsFixed(2)}'),
              if (top.previousClose > 0)
                _RowMetric('Previous Close', '\$${top.previousClose.toStringAsFixed(2)}'),
              if (top.previousClose > 0)
                _RowMetric(
                  'Move From Close To Current',
                  '\$${top.previousClose.toStringAsFixed(2)} → \$${top.extendedPrice.toStringAsFixed(2)}',
                ),
              _RowMetric(
                'Volume',
                top.volumeUnknown || top.extendedVolume <= 0
                    ? 'غير متاح'
                    : _formatVolume(top.extendedVolume),
              ),
              if (top.catalystTitleAr.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  top.catalystTitleAr,
                  style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                ),
              ],
              if (top.riskFlagsAr.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  top.riskFlagsAr.join(' • '),
                  style: const TextStyle(color: AppTheme.danger, fontSize: 12),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _formatVolume(int vol) {
    if (vol >= 1000000) return '${(vol / 1000000).toStringAsFixed(1)}M';
    if (vol >= 1000) return '${(vol / 1000).toStringAsFixed(0)}K';
    return vol.toString();
  }
}

class _RowMetric extends StatelessWidget {
  final String label;
  final String value;

  const _RowMetric(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
          Text(value, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12, fontWeight: FontWeight.w600)),
        ],
      ),
    );
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
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.35)),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 12),
      ),
    );
  }
}
