import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Minimum institutional gate from backend `MIN_FACTOR_SCORE`.
const double kFactorPassThreshold = 45.0;

/// Scores at or above this are shown as strong pass (green).
const double kFactorStrongThreshold = 60.0;

enum FactorStatus { passed, warning, failed }

FactorStatus factorStatus(double score) {
  if (score < kFactorPassThreshold) return FactorStatus.failed;
  if (score < kFactorStrongThreshold) return FactorStatus.warning;
  return FactorStatus.passed;
}

Color factorStatusColor(FactorStatus status) {
  switch (status) {
    case FactorStatus.passed:
      return AppTheme.accent;
    case FactorStatus.warning:
      return AppTheme.warning;
    case FactorStatus.failed:
      return AppTheme.danger;
  }
}

/// Display order and labels aligned with backend institutional audit.
const List<MapEntry<String, String>> kInstitutionalFactorOrder = [
  MapEntry('smc', 'SMC'),
  MapEntry('bos', 'BOS'),
  MapEntry('choch', 'CHOCH'),
  MapEntry('order_blocks', 'Order Block'),
  MapEntry('fair_value_gaps', 'Fair Value Gap'),
  MapEntry('liquidity_sweep', 'Liquidity'),
  MapEntry('ema20', 'EMA20'),
  MapEntry('ema50', 'EMA50'),
  MapEntry('ema200', 'EMA200'),
  MapEntry('vwap', 'VWAP'),
  MapEntry('atr', 'ATR'),
  MapEntry('relative_volume', 'Relative Volume'),
  MapEntry('volume_spike', 'Volume Spike'),
  MapEntry('momentum', 'Momentum'),
  MapEntry('trend', 'Trend'),
  MapEntry('news_impact', 'News'),
  MapEntry('institutional_flow', 'Institutional Flow'),
  MapEntry('risk_reward', 'Risk/Reward'),
];

const List<MapEntry<String, String>> kSupplementaryFactorOrder = [
  MapEntry('rsi', 'RSI'),
  MapEntry('macd', 'MACD'),
  MapEntry('delta_volume', 'Delta Volume'),
];

class FactorScorePanel extends StatelessWidget {
  final Map<String, double> factorScores;
  final List<String> buyBlockers;
  final String? finalBlocker;
  final String? aiExplanation;
  final String? signal;

  const FactorScorePanel({
    super.key,
    required this.factorScores,
    this.buyBlockers = const [],
    this.finalBlocker,
    this.aiExplanation,
    this.signal,
  });

  List<String> get _resolvedBlockers {
    if (buyBlockers.isNotEmpty) return buyBlockers;
    final text = aiExplanation;
    if (text == null) return const [];

    for (final header in ['BUY blocked because:', 'AVOID because:']) {
      if (!text.contains(header)) continue;
      final lines = text.split('\n');
      final start = lines.indexWhere((l) => l.contains(header));
      if (start < 0) continue;
      final blockers = <String>[];
      for (var i = start + 1; i < lines.length; i++) {
        final line = lines[i].trim();
        if (line.isEmpty) continue;
        if (line.startsWith('Final blocker:')) break;
        blockers.add(line.replaceFirst(RegExp(r'^[•\-\*]\s*'), ''));
      }
      if (blockers.isNotEmpty) return blockers;
    }
    return const [];
  }

  String get _blockerTitle {
    final sig = (signal ?? '').toUpperCase();
    if (sig == 'AVOID') return 'AVOID because:';
    return 'BUY blocked because:';
  }

  String? get _resolvedFinalBlocker {
    if (finalBlocker != null && finalBlocker!.isNotEmpty) return finalBlocker;
    final text = aiExplanation;
    if (text == null) return null;
    for (final line in text.split('\n')) {
      if (line.startsWith('Final blocker:')) {
        return line.replaceFirst('Final blocker:', '').trim();
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final blockers = _resolvedBlockers;
    final blockerFinal = _resolvedFinalBlocker;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Institutional Factors',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
        ),
        const SizedBox(height: 4),
        _LegendRow(),
        const SizedBox(height: 12),
        ...kInstitutionalFactorOrder.map(
          (entry) => _FactorScoreRow(
            label: entry.value,
            score: factorScores[entry.key] ?? 0,
          ),
        ),
        if (kSupplementaryFactorOrder.any((e) => factorScores.containsKey(e.key))) ...[
          const SizedBox(height: 16),
          const Text(
            'Supplementary',
            style: TextStyle(
              fontWeight: FontWeight.w600,
              fontSize: 13,
              color: AppTheme.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          ...kSupplementaryFactorOrder
              .where((entry) => factorScores.containsKey(entry.key))
              .map(
                (entry) => _FactorScoreRow(
                  label: entry.value,
                  score: factorScores[entry.key] ?? 0,
                ),
              ),
        ],
        if (blockers.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(
            _blockerTitle,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 14,
              color: AppTheme.danger,
            ),
          ),
          const SizedBox(height: 8),
          ...blockers.map(
            (reason) => Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.block, size: 14, color: AppTheme.danger),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      reason,
                      style: const TextStyle(
                        color: AppTheme.textSecondary,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (blockerFinal != null && blockerFinal.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                'Final blocker: $blockerFinal',
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  color: AppTheme.warning,
                ),
              ),
            ),
        ],
      ],
    );
  }
}

class _LegendRow extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 4,
      children: [
        _LegendChip(color: AppTheme.accent, label: 'Passed'),
        _LegendChip(color: AppTheme.warning, label: 'Warning'),
        _LegendChip(color: AppTheme.danger, label: 'Failed'),
      ],
    );
  }
}

class _LegendChip extends StatelessWidget {
  final Color color;
  final String label;

  const _LegendChip({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
      ],
    );
  }
}

class _FactorScoreRow extends StatelessWidget {
  final String label;
  final double score;

  const _FactorScoreRow({required this.label, required this.score});

  @override
  Widget build(BuildContext context) {
    final status = factorStatus(score);
    final color = factorStatusColor(status);
    final scoreText = '${score.round()}/100';

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w500,
                fontSize: 13,
              ),
            ),
          ),
          Expanded(
            flex: 2,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final dotCount = (constraints.maxWidth / 4).floor().clamp(4, 40);
                return Text(
                  '.' * dotCount,
                  maxLines: 1,
                  overflow: TextOverflow.clip,
                  style: TextStyle(
                    color: color.withValues(alpha: 0.35),
                    letterSpacing: 1,
                    fontSize: 12,
                    height: 1.2,
                  ),
                );
              },
            ),
          ),
          Text(
            scoreText,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.bold,
              fontSize: 13,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}
