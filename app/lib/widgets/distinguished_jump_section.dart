import 'package:flutter/material.dart';

import '../models/opportunity_now.dart';
import '../theme/app_theme.dart';

/// قفزة سعرية مميزة — live wave >= 50% from move_start (top of home).
class DistinguishedJumpSection extends StatelessWidget {
  final OpportunityNowResponse? data;
  final bool loading;
  final void Function(String symbol)? onOpenSymbol;

  const DistinguishedJumpSection({
    super.key,
    required this.data,
    this.loading = false,
    this.onOpenSymbol,
  });

  static const _accent = Color(0xFFE6A817);
  static const _accentDeep = Color(0xFFB8860B);

  @override
  Widget build(BuildContext context) {
    if (loading && data == null) {
      return const SizedBox.shrink();
    }

    final items = data?.distinguishedJumpAlerts ?? const <OpportunityNowSignal>[];
    if (items.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                _accent.withOpacity(0.22),
                _accentDeep.withOpacity(0.08),
              ],
              begin: Alignment.centerRight,
              end: Alignment.centerLeft,
            ),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: _accent.withOpacity(0.55), width: 1.5),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.auto_graph, color: _accent, size: 22),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'قفزة سعرية مميزة',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: _accent.withOpacity(0.18),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: _accent.withOpacity(0.4)),
                    ),
                    child: Text(
                      '${items.length}',
                      style: const TextStyle(
                        color: _accentDeep,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              const Text(
                'موجة لحظية حية ≥ 50% من بداية الموجة — 1د / 3د / 5د',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        ...items.map(
          (signal) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: DistinguishedJumpCard(
              signal: signal,
              onTap: onOpenSymbol == null ? null : () => onOpenSymbol!(signal.symbol),
            ),
          ),
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}

class DistinguishedJumpCard extends StatelessWidget {
  final OpportunityNowSignal signal;
  final VoidCallback? onTap;

  const DistinguishedJumpCard({
    super.key,
    required this.signal,
    this.onTap,
  });

  static const _accent = Color(0xFFE6A817);

  @override
  Widget build(BuildContext context) {
    final movePct = signal.realJumpCurrentMovePct;
    final retrace = signal.realJumpRetracementFromPeakPct;
    final waveState = signal.realJumpWaveState.isNotEmpty
        ? signal.realJumpWaveState
        : 'ACTIVE_UPWARD_WAVE';

    return Card(
      color: _accent.withOpacity(0.07),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: _accent.withOpacity(0.45), width: 1.2),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    signal.symbol,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.textPrimary,
                    ),
                  ),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: _accent.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '+${movePct.toStringAsFixed(2)}%',
                      style: const TextStyle(
                        color: _accent,
                        fontWeight: FontWeight.bold,
                        fontSize: 15,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 14,
                runSpacing: 6,
                children: [
                  _Kpi('بداية الموجة', _price(signal.realJumpMoveStartPrice)),
                  _Kpi('السعر الحالي', _price(signal.price)),
                  _Kpi('ذروة الموجة', _price(signal.realJumpWavePeakPrice)),
                  _Kpi('تراجع من الذروة', retrace > 0 ? '${retrace.toStringAsFixed(2)}%' : '0%'),
                  _Kpi('حالة الموجة', waveState),
                ],
              ),
              if (signal.realJumpMoveStartTime.isNotEmpty ||
                  signal.realJumpFirstDetectedTime.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 14,
                  runSpacing: 4,
                  children: [
                    if (signal.realJumpMoveStartTime.isNotEmpty)
                      _Kpi('وقت بداية الموجة', _formatTime(signal.realJumpMoveStartTime)),
                    if (signal.realJumpFirstDetectedTime.isNotEmpty)
                      _Kpi('أول اكتشاف', _formatTime(signal.realJumpFirstDetectedTime)),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _price(double v) => v > 0 ? '\$${v.toStringAsFixed(2)}' : '—';

  String _formatTime(String iso) {
    if (iso.length >= 16) return iso.substring(11, 16);
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
