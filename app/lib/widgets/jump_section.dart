import 'package:flutter/material.dart';

import '../models/opportunity_now.dart';
import '../theme/app_theme.dart';
import 'extended_alert_card.dart';
import 'watch_jump_card.dart';

/// Unified Jump section — news + watch only from opportunity-now (old behavior).
class JumpSection extends StatelessWidget {
  final OpportunityNowResponse? data;
  final bool loading;
  final void Function(String symbol)? onOpenSymbol;
  final int maxItems;

  const JumpSection({
    super.key,
    required this.data,
    this.loading = false,
    this.onOpenSymbol,
    this.maxItems = 3,
  });

  @override
  Widget build(BuildContext context) {
    if (loading && data == null) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.primary),
          ),
        ),
      );
    }

    final jumps = data?.jumpSectionItems(limit: maxItems) ?? const <OpportunityNowSignal>[];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Padding(
          padding: EdgeInsets.only(bottom: 12, top: 4),
          child: Text(
            'القفزات',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
          ),
        ),
        if (jumps.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Text(
              'لا يوجد شراء قوي فعلي الآن',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppTheme.textSecondary),
            ),
          )
        else
          ...jumps.map((signal) {
            final onTap = onOpenSymbol == null ? null : () => onOpenSymbol!(signal.symbol);
            if (signal.isRealNewsJump || (signal.isJumpAlertDisplay && signal.extendedGapPct > 0)) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: ExtendedAlertHomeCard(alert: signal, onTap: onTap),
              );
            }
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: WatchJumpHomeCard(
                signal: signal,
                wsConnected: data?.wsConnected ?? false,
                onTap: onTap,
              ),
            );
          }),
      ],
    );
  }
}
