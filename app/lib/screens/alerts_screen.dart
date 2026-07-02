import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/app_state.dart';
import '../theme/app_theme.dart';
import '../widgets/metric_tile.dart';
import '../widgets/stock_card.dart';
import 'stock_analysis_screen.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppState>().refreshAlerts();
    });
  }

  String _conditionLabel(String condition) {
    return condition == 'above' ? 'يتجاوز' : 'ينخفض عن';
  }

  @override
  Widget build(BuildContext context) {
    final alerts = context.watch<AppState>().alerts;

    return Scaffold(
      appBar: AppBar(
        title: const Text('التنبيهات'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<AppState>().refreshAlerts(),
          ),
        ],
      ),
      body: alerts.isEmpty
          ? const EmptyState(
              icon: Icons.notifications_none,
              title: 'لا توجد تنبيهات',
              subtitle: 'أضف تنبيهات من شاشة تحليل السهم',
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: alerts.length,
              itemBuilder: (_, i) {
                final alert = alerts[i];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) =>
                              StockAnalysisScreen(symbol: alert.symbol),
                        ),
                      );
                    },
                    leading: CircleAvatar(
                      backgroundColor: alert.isActive
                          ? AppTheme.warning.withValues(alpha: 0.15)
                          : AppTheme.textSecondary.withValues(alpha: 0.15),
                      child: Icon(
                        alert.isActive
                            ? Icons.notifications_active
                            : Icons.notifications_off,
                        color: alert.isActive
                            ? AppTheme.warning
                            : AppTheme.textSecondary,
                      ),
                    ),
                    title: Text(
                      alert.symbol,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    subtitle: Text(
                      '${_conditionLabel(alert.condition)} ${formatPrice(alert.targetPrice)}',
                      textDirection: TextDirection.rtl,
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Switch(
                          value: alert.isActive,
                          activeThumbColor: AppTheme.primary,
                          onChanged: (v) => context
                              .read<AppState>()
                              .toggleAlert(alert.id, v),
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_outline,
                              color: AppTheme.danger),
                          onPressed: () =>
                              context.read<AppState>().removeAlert(alert.id),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
