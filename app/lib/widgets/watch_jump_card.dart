import 'package:flutter/material.dart';

import '../models/opportunity_now.dart';
import '../theme/app_theme.dart';

/// Watch jump card — STRONG_BUY_WATCH / JUMP_ALERT / REAL_JUMP_ALERT.
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

  static const _realJumpRed = Color(0xFFE53935);

  @override
  Widget build(BuildContext context) {
    final changePrefix = signal.changePercent >= 0 ? '+' : '';
    final isRealJump = signal.isRealJumpAlertDisplay;
    final isJump = isRealJump || signal.isJumpAlertDisplay || signal.isQualifiedJumpAlert;
    final title = isRealJump
        ? 'قفزة سعرية لحظية'
        : isJump
            ? 'قفزة مؤكدة'
            : 'ضغط شراء قوي';
    final subtitle = isRealJump
        ? 'REAL_JUMP_ALERT'
        : isJump
            ? 'JUMP_ALERT — حركة صاعدة مؤكدة'
            : 'STRONG_BUY_WATCH — شراء قوي قبل الانفجار';

    final cardColor = isRealJump ? _realJumpRed.withOpacity(0.12) : AppTheme.surface;
    final borderColor = isRealJump ? _realJumpRed : Colors.transparent;
    final accentColor = isRealJump ? _realJumpRed : AppTheme.primary;
    final subtitleColor = isRealJump ? _realJumpRed : (isJump ? AppTheme.success : const Color(0xFFD29922));

    return Card(
      color: cardColor,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: borderColor, width: isRealJump ? 1.5 : 0),
      ),
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
                      color: accentColor.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      isRealJump ? Icons.bolt : Icons.visibility_outlined,
                      color: accentColor,
                      size: 26,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      title,
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: isRealJump ? _realJumpRed : AppTheme.textPrimary,
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
                        style: TextStyle(
                          color: accentColor,
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
                  color: subtitleColor,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              if (isRealJump) ...[
                const SizedBox(height: 12),
                if (signal.detectionStage == 'EXPLOSIVE')
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: _realJumpRed.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: _realJumpRed),
                    ),
                    child: const Text(
                      '+150% EXPLOSIVE',
                      style: TextStyle(color: _realJumpRed, fontWeight: FontWeight.bold, fontSize: 12),
                    ),
                  ),
                _RealJumpKpiGrid(signal: signal),
              ],
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
                      color: accentColor,
                    ),
                  if (signal.rvol > 0)
                    _Chip(label: 'RVOL ${signal.rvol.toStringAsFixed(1)}x', color: AppTheme.success),
                  if (signal.volumeAcceleration > 0)
                    _Chip(
                      label: 'VolAcc ${signal.volumeAcceleration.toStringAsFixed(2)}',
                      color: AppTheme.success,
                    ),
                  if (!isRealJump) ...[
                    _Chip(label: 'Score ${signal.score.toStringAsFixed(0)}', color: AppTheme.primary),
                    _Chip(
                      label: '${signal.confirmedFactors}/${signal.totalFactors} Factors',
                      color: AppTheme.success,
                    ),
                  ],
                ],
              ),
              if (!isRealJump) ...[
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
              ],
              if (signal.reasonsAr.isNotEmpty && !isRealJump) ...[
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

class _RealJumpKpiGrid extends StatelessWidget {
  final OpportunityNowSignal signal;

  const _RealJumpKpiGrid({required this.signal});

  @override
  Widget build(BuildContext context) {
    final moveStart = signal.realJumpMoveStartPrice;
    final firstPrice = signal.realJumpFirstDetectedPrice;
    final peak = signal.realJumpWavePeakPrice;
    final currentMove = signal.realJumpCurrentMovePct;
    final firstPct = signal.realJumpFirstDetectedPct;
    final wavePeakMove = signal.realJumpWavePeakMovePct;
    final peakAfter = signal.realJumpPeakAfterDetectionPct;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 16,
          runSpacing: 6,
          children: [
            _Kpi('السعر الحالي', '\$${signal.price.toStringAsFixed(2)}'),
            if (moveStart > 0) _Kpi('بداية الموجة', '\$${moveStart.toStringAsFixed(2)}'),
            if (currentMove != 0) _Kpi('حركة الموجة', '+${currentMove.toStringAsFixed(2)}%'),
            if (firstPrice > 0) _Kpi('سعر الاكتشاف', '\$${firstPrice.toStringAsFixed(2)}'),
            if (firstPct != 0) _Kpi('عند الاكتشاف', '+${firstPct.toStringAsFixed(2)}%'),
            if (peak > 0) _Kpi('أعلى بعد الاكتشاف', '\$${peak.toStringAsFixed(2)}'),
            if (wavePeakMove > 0) _Kpi('ذروة الموجة', '+${wavePeakMove.toStringAsFixed(2)}%'),
            if (peakAfter > 0) _Kpi('صعود بعد الاكتشاف', '+${peakAfter.toStringAsFixed(2)}%'),
          ],
        ),
        if (signal.realJumpMoveStartTime.isNotEmpty || signal.realJumpFirstDetectedTime.isNotEmpty) ...[
          const SizedBox(height: 6),
          Wrap(
            spacing: 16,
            runSpacing: 4,
            children: [
              if (signal.realJumpMoveStartTime.isNotEmpty)
                _Kpi('وقت بداية الموجة', _formatTime(signal.realJumpMoveStartTime)),
              if (signal.realJumpFirstDetectedTime.isNotEmpty)
                _Kpi('وقت الاكتشاف', _formatTime(signal.realJumpFirstDetectedTime)),
            ],
          ),
        ],
      ],
    );
  }

  String _formatTime(String iso) {
    if (iso.length >= 16) {
      return iso.substring(11, 16);
    }
    return iso;
  }
}

class _Kpi extends StatelessWidget {
  final String label;
  final String value;

  const _Kpi(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Text(
      '$label: $value',
      style: const TextStyle(
        color: AppTheme.textPrimary,
        fontSize: 12,
        fontWeight: FontWeight.w600,
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
