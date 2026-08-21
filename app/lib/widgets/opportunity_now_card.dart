import 'package:flutter/material.dart';

import '../models/opportunity_now.dart';
import '../theme/app_theme.dart';

Color opportunityStatusColor(String status) {
  switch (status) {
    case 'NOW':
    case 'فرصة الآن':
      return AppTheme.success;
    case 'READY':
    case 'استعد':
      return const Color(0xFFD29922);
    case 'WATCH':
    case 'مراقبة':
      return AppTheme.textSecondary;
    case 'CANCELLED':
    case 'أُلغيت':
      return AppTheme.danger;
    default:
      return AppTheme.textSecondary;
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
    final isConnectionError = error != null;
    final isNone = resp?.hasNoOpportunity ?? true;

    if (top == null || isNone) {
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
                isConnectionError
                    ? 'تعذر الاتصال — حاول التحديث'
                    : (!marketOpen && message.isNotEmpty
                        ? message
                        : 'لا توجد فرصة مكتملة الآن'),
                style: TextStyle(
                  color: isConnectionError ? AppTheme.danger : AppTheme.textSecondary,
                  fontSize: 14,
                ),
              ),
              if (isConnectionError && error != null) ...[
                const SizedBox(height: 8),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.error_outline, size: 16, color: AppTheme.danger),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        error!,
                        style: const TextStyle(color: AppTheme.danger, fontSize: 12),
                      ),
                    ),
                  ],
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
    final countdown = _countdownSeconds(top.expiresAt);

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
                      Text(
                        top.statusAr.isNotEmpty ? top.statusAr : 'فرصة الآن',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: color,
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
                _StatusChip(label: top.statusAr, color: color),
                _StatusChip(label: '${top.score.toStringAsFixed(0)}/100', color: AppTheme.primary),
                _StatusChip(
                  label: '${top.confirmedFactors}/${top.totalFactors} عامل',
                  color: AppTheme.primary,
                ),
                if (top.riskRewardRatio > 0)
                  _StatusChip(
                    label: 'R:R ${top.riskRewardRatio.toStringAsFixed(1)}',
                    color: AppTheme.success,
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: [
                _Meta('دخول', _entryLabel(top)),
                _Meta('وقف', top.stopLoss.toStringAsFixed(2)),
                _Meta('هدف 1', top.target1.toStringAsFixed(2)),
                _Meta('هدف 2', top.target2.toStringAsFixed(2)),
              ],
            ),
            if (countdown != null && top.isOpportunityNow) ...[
              const SizedBox(height: 8),
              Text(
                'ينتهي خلال ${countdown}s',
                style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 13),
              ),
            ],
            const SizedBox(height: 8),
            Text(
              'تأكيدات: ${top.consecutiveConfirmations} — ${_shortTime(top.appearedAt)}',
              style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
            ),
            if (top.reasonsAr.isNotEmpty) ...[
              const SizedBox(height: 8),
              const Text(
                'لماذا الآن؟',
                style: TextStyle(
                  color: AppTheme.textPrimary,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                top.reasonsAr.take(3).join(' • '),
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
              ),
            ],
            if (top.cancellationReasonsAr.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                top.cancellationReasonsAr.join(' • '),
                style: const TextStyle(color: AppTheme.danger, fontSize: 12),
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
            Row(
              children: [
                Icon(
                  Icons.circle,
                  size: 8,
                  color: resp?.wsConnected == true ? AppTheme.success : AppTheme.textSecondary,
                ),
                const SizedBox(width: 6),
                Text(
                  resp?.wsConnected == true ? 'مراقبة لحظية (WS)' : 'مراقبة عبر REST',
                  style: TextStyle(
                    color: resp?.wsConnected == true ? AppTheme.success : AppTheme.textSecondary,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _entryLabel(OpportunityNowSignal top) {
    if (top.entryZoneLow > 0 && top.entryZoneHigh > 0) {
      return '${top.entryZoneLow.toStringAsFixed(2)}–${top.entryZoneHigh.toStringAsFixed(2)}';
    }
    return top.entryZone.toStringAsFixed(2);
  }

  int? _countdownSeconds(String expiresAt) {
    if (expiresAt.isEmpty) return null;
    try {
      final exp = DateTime.parse(expiresAt);
      final diff = exp.difference(DateTime.now().toUtc()).inSeconds;
      return diff > 0 ? diff : 0;
    } catch (_) {
      return null;
    }
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
