import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/ar_localization.dart';
import '../models/market_pulse.dart';
import '../services/app_state.dart';
import '../services/market_pulse_service.dart';
import '../theme/app_theme.dart';
import '../widgets/market_pulse_card.dart';
import 'market_pulse_detail_screen.dart';

class MarketPulseScreen extends StatefulWidget {
  const MarketPulseScreen({super.key});

  @override
  State<MarketPulseScreen> createState() => _MarketPulseScreenState();
}

class _MarketPulseScreenState extends State<MarketPulseScreen> with WidgetsBindingObserver {
  late MarketPulseService _service;
  bool _serviceStarted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_serviceStarted) return;
    _serviceStarted = true;
    final authSession = context.read<AppState>().api.authSession;
    final service = MarketPulseService(authSession: authSession);
    _service = service;
    service.updates.listen((_) {
      if (mounted) setState(() {});
    });
    service.start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _service.stop();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused || state == AppLifecycleState.detached) {
      _service.stop();
    } else if (state == AppLifecycleState.resumed) {
      _service.start();
    }
  }

  Future<void> _refresh() async {
    await _service.refresh();
  }

  Color _statusColor() {
    switch (_service.state) {
      case PulseServiceState.live:
        return AppTheme.success;
      case PulseServiceState.delayed:
        return const Color(0xFFD29922);
      case PulseServiceState.stale:
        return AppTheme.danger;
      case PulseServiceState.error:
        return AppTheme.danger;
      default:
        return AppTheme.textSecondary;
    }
  }

  Widget _buildStatusBar() {
    final updated = _service.lastUpdated;
    return Card(
      color: AppTheme.surface,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.circle, size: 10, color: _statusColor()),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'حالة الخدمة: ${ArUi.pulseServiceState(_service.state)}',
                    style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                  ),
                  if (updated != null)
                    Text(
                      'آخر تحديث: ${updated.hour.toString().padLeft(2, '0')}:${updated.minute.toString().padLeft(2, '0')}:${updated.second.toString().padLeft(2, '0')}',
                      style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                    ),
                ],
              ),
            ),
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: _refresh,
              tooltip: 'تحديث',
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    switch (_service.state) {
      case PulseServiceState.loading:
        return const PulseSkeletonList();
      case PulseServiceState.disabled:
        return _messageCard(
          icon: Icons.power_off_outlined,
          title: 'الاشتراك غير مفعّل',
          body: _service.health?.message ?? 'ميزة نبض السوق معطّلة على الخادم',
        );
      case PulseServiceState.error:
        return _messageCard(
          icon: Icons.cloud_off_outlined,
          title: 'فشل الاتصال',
          body: ArUi.backendText(_service.errorMessage ?? 'تعذر الاتصال'),
          action: OutlinedButton.icon(
            onPressed: () {
              _service.stop();
              _service.start();
            },
            icon: const Icon(Icons.refresh),
            label: const Text('إعادة المحاولة'),
          ),
        );
      case PulseServiceState.empty:
        return _messageCard(
          icon: Icons.notifications_off_outlined,
          title: 'لا توجد إشارات',
          body: 'لا توجد تنبيهات نبض نشطة حالياً',
        );
      case PulseServiceState.stale:
      case PulseServiceState.live:
      case PulseServiceState.delayed:
      case PulseServiceState.stopped:
        final alerts = _service.listing?.alerts ?? [];
        if (alerts.isEmpty) {
          return _messageCard(
            icon: Icons.notifications_off_outlined,
            title: 'لا توجد إشارات',
            body: 'لا توجد تنبيهات نبض نشطة حالياً',
          );
        }
        return Column(
          children: alerts.map((a) {
            return MarketPulseAlertCard(
              alert: a,
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => MarketPulseDetailScreen(alert: a),
                ),
              ),
            );
          }).toList(),
        );
    }
  }

  Widget _messageCard({
    required IconData icon,
    required String title,
    required String body,
    Widget? action,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(icon, size: 48, color: AppTheme.textSecondary),
            const SizedBox(height: 16),
            Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(body, textAlign: TextAlign.center, style: const TextStyle(color: AppTheme.textSecondary)),
            if (action != null) ...[const SizedBox(height: 16), action],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('نبض السوق')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        color: AppTheme.primary,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _buildStatusBar(),
            const SizedBox(height: 12),
            _buildBody(),
            const SizedBox(height: 16),
            const Text(
              'تحليل معلوماتي فقط — ليس ضماناً للربح',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
