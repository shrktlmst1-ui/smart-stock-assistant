import 'package:flutter/material.dart';

import '../models/opportunity_now.dart';
import '../theme/app_theme.dart';

/// Watch jump card — CISS / ADIL / BTCT style (live confirmation engine).
class WatchJumpHomeCard extends StatelessWidget {
  final OpportunityNowSignal signal;
  final bool wsConnected;
  final VoidCallback? onTap;

  const WatchJumpHomeCard({
    super.key,
    required this.signal,
    required this.wsConnected,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final changePrefix = signal.changePercent >= 0 ? '+' : '';
    final isJump = signal.isJumpAlertDisplay || signal.isQualifiedJumpAlert;
    final title = isJump ? 'قفزة مؤكدة' : 'ضغط شراء قوي';
    final subtitle = isJump
        ? 'JUMP_ALERT — حركة صاعدة مؤكدة'
        : 'STRONG_BUY_WATCH — شراء قوي قبل الانفجار';

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
                      color: AppTheme.primary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(Icons.visibility_outlined, color: AppTheme.primary, size: 26),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      title,
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
                        signal.symbol,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      Text(
                        '\$${signal.price.toStringAsFixed(2)} ($changePrefix${signal.changePercent.toStringAsFixed(1)}%)',
                        style: const TextStyle(
                          color: AppTheme.primary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                subtitle,
                style: TextStyle(
                  color: isJump ? AppTheme.success : const Color(0xFFD29922),
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              if (signal.confluenceCount > 0) ...[
                const SizedBox(height: 8),
                Text(
                  'Confluence: ${signal.confluenceCount} — ${signal.confluenceFactors.take(4).join(', ')}',
                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                ),
              ],
              if (!isJump) ...[
                const SizedBox(height: 10),
                const Text(
                  'ضغط شراء حقيقي — انتظر تأكيد القفزة',
                  style: TextStyle(
                    color: Color(0xFFD29922),
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ],
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  if (signal.buyPressureScore > 0)
                    _Chip(
                      label: 'Buy ${signal.buyPressureScore.toStringAsFixed(0)}',
                      color: AppTheme.primary,
                    ),
                  if (signal.rvol > 0)
                    _Chip(label: 'RVOL ${signal.rvol.toStringAsFixed(1)}x', color: AppTheme.success),
                  if (signal.volumeAcceleration > 0)
                    _Chip(
                      label: 'VolAcc ${signal.volumeAcceleration.toStringAsFixed(2)}',
                      color: AppTheme.success,
                    ),
                  _Chip(label: 'Score ${signal.score.toStringAsFixed(0)}', color: AppTheme.primary),
                  _Chip(
                    label: '${signal.confirmedFactors}/${signal.totalFactors} Factors',
                    color: AppTheme.success,
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 12,
                runSpacing: 4,
                children: [
                  _Meta('Entry', _entryLabel(signal)),
                  _Meta('Stop', signal.stopLoss.toStringAsFixed(2)),
                  _Meta('TP1', signal.target1.toStringAsFixed(2)),
                  _Meta('TP2', signal.target2.toStringAsFixed(2)),
                ],
              ),
              if (signal.reasonsAr.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  'Reason Now: ${signal.reasonsAr.take(3).join(' • ')}',
                  style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
                ),
              ],
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(
                    Icons.circle,
                    size: 8,
                    color: wsConnected ? AppTheme.success : AppTheme.textSecondary,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    wsConnected ? 'Latency Source: WS' : 'Latency Source: REST',
                    style: TextStyle(
                      color: wsConnected ? AppTheme.success : AppTheme.textSecondary,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ],
          ),
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
