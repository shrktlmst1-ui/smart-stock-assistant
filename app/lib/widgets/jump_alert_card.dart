import 'package:flutter/material.dart';

import '../l10n/ar_localization.dart';
import '../models/stock.dart';
import '../theme/app_theme.dart';
import 'stock_card.dart';

class JumpAlertCard extends StatelessWidget {
  final JumpAlert alert;
  final int rank;
  final VoidCallback? onTap;

  const JumpAlertCard({
    super.key,
    required this.alert,
    required this.rank,
    this.onTap,
  });

  String get _timingLabel {
    if (alert.isTooLate) return 'متأخر — لا دخول جديد';
    if (alert.timing == 'EARLY') return 'دخول مبكر';
    if (alert.timing == 'LATE') return 'دخول متأخر';
    return 'دخول طبيعي';
  }

  @override
  Widget build(BuildContext context) {
    final changeColor = AppTheme.changeColor(alert.changePercent);

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
                  Container(
                    width: 32,
                    height: 32,
                    margin: const EdgeInsets.only(left: 12),
                    decoration: BoxDecoration(
                      color: AppTheme.primary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      '$rank',
                      style: const TextStyle(
                        color: AppTheme.primary,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              alert.symbol,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                color: AppTheme.textPrimary,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: AppTheme.success.withOpacity(0.15),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                alert.jumpType.isNotEmpty ? alert.jumpType : 'JUMP',
                                style: const TextStyle(
                                  color: AppTheme.success,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                        Text(
                          alert.name.isNotEmpty ? alert.name : alert.symbol,
                          style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        formatPrice(alert.price),
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      Text(
                        formatPercent(alert.changePercent),
                        style: TextStyle(color: changeColor, fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _metricChip('Entry', formatPrice(alert.entryLow)),
                  _metricChip('Stop', formatPrice(alert.stopLoss)),
                  _metricChip('TP1', formatPrice(alert.tp1)),
                  _metricChip('TP2', formatPrice(alert.tp2)),
                  _metricChip('RVOL', '${alert.rvol.toStringAsFixed(1)}x'),
                  _metricChip('VolAcc', alert.volumeAcceleration.toStringAsFixed(2)),
                  _metricChip('Trigger', formatPrice(alert.triggerPrice)),
                  _metricChip('R:R', alert.riskReward.toStringAsFixed(1)),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                _timingLabel,
                style: TextStyle(
                  color: alert.isTooLate ? AppTheme.warning : AppTheme.success,
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
              if (alert.statusReasonAr.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  alert.statusReasonAr,
                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _metricChip(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppTheme.border),
      ),
      child: Text(
        '$label: $value',
        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
      ),
    );
  }
}
