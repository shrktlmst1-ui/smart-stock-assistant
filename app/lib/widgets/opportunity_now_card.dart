import 'package:flutter/material.dart';

import '../models/opportunity_now.dart';
import '../theme/app_theme.dart';

Color opportunityStatusColor(String status) {
  switch (status) {
    case 'فرصة الآن':
      return AppTheme.success;
    case 'استعد':
      return const Color(0xFFD29922);
    case 'مراقبة':
      return AppTheme.primary;
    case 'تجنب':
    default:
      return AppTheme.danger;
  }
}

class OpportunityNowHomeCard extends StatelessWidget {
  final OpportunityNowResponse? data;
  final bool loading;
  final String? error;
  final VoidCallback? onRefresh;

  const OpportunityNowHomeCard({
    super.key,
    required this.data,
    required this.loading,
    this.error,
    this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    if (loading && data == null) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Center(
            child: SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.primary),
            ),
          ),
        ),
      );
    }

    final resp = data;
    final top = resp?.displayTop;
    final marketOpen = resp?.marketOpen ?? false;
    final message = resp?.message ?? '';

    if (top == null || !top.isOpportunityNow) {
      return Card(
        color: AppTheme.surface,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.bolt_outlined, color: AppTheme.primary, size: 28),
                  SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'فرصة الآن',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                !marketOpen && message.isNotEmpty
                    ? message
                    : 'لا توجد فرصة مكتملة الآن',
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 14),
              ),
              if (error != null) ...[
                const SizedBox(height: 8),
                Text(
                  error!,
                  style: const TextStyle(color: AppTheme.danger, fontSize: 12),
                ),
              ],
              if (onRefresh != null) ...[
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: onRefresh,
                    icon: const Icon(Icons.refresh, size: 18),
                    label: const Text('تحديث'),
                  ),
                ),
              ],
            ],
          ),
        ),
      );
    }

    final color = opportunityStatusColor(top.status);
    final changePrefix = top.changePercent >= 0 ? '+' : '';

    return Card(
      color: AppTheme.surface,
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
                    color: color.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(Icons.bolt, color: color, size: 26),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'فرصة الآن',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      Text(
                        top.name.isNotEmpty ? top.name : top.symbol,
                        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                      ),
                    ],
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
                      '\$${top.price.toStringAsFixed(2)} ($changePrefix${top.changePercent.toStringAsFixed(1)}%)',
                      style: TextStyle(color: color, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                _StatusChip(label: top.status, color: color),
                _StatusChip(label: '${top.score.toStringAsFixed(0)}/100', color: AppTheme.primary),
                _StatusChip(label: 'مخاطرة: ${top.riskLevel}', color: AppTheme.textSecondary),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: [
                _Meta('دخول', top.entryZone.toStringAsFixed(2)),
                _Meta('وقف', top.stopLoss.toStringAsFixed(2)),
                _Meta('هدف 1', top.target1.toStringAsFixed(2)),
                _Meta('هدف 2', top.target2.toStringAsFixed(2)),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'ظهرت: ${_shortTime(top.appearedAt)} — تنتهي: ${_shortTime(top.expiresAt)}',
              style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
            ),
            if (top.reasonsAr.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                top.reasonsAr.take(4).join(' • '),
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
              ),
            ],
            if (top.lateEntryWarning) ...[
              const SizedBox(height: 8),
              const Row(
                children: [
                  Icon(Icons.warning_amber_rounded, size: 16, color: Color(0xFFD29922)),
                  SizedBox(width: 6),
                  Text(
                    'دخول متأخر — السعر ممتد',
                    style: TextStyle(color: Color(0xFFD29922), fontSize: 12),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 4),
            const Row(
              children: [
                Icon(Icons.circle, size: 8, color: AppTheme.success),
                SizedBox(width: 6),
                Text('أسعار لحظية', style: TextStyle(color: AppTheme.success, fontSize: 11)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _shortTime(String iso) {
    if (iso.length >= 16) return iso.substring(11, 16);
    return iso;
  }
}

class _StatusChip extends StatelessWidget {
  final String label;
  final Color color;

  const _StatusChip({required this.label, required this.color});

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

class _Meta extends StatelessWidget {
  final String label;
  final String value;

  const _Meta(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Text(
      '$label: \$$value',
      style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
    );
  }
}
