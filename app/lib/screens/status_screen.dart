import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/system_status.dart';
import '../services/app_state.dart';
import '../l10n/ar_localization.dart';
import '../theme/app_theme.dart';
import '../widgets/stock_card.dart';

class StatusScreen extends StatefulWidget {
  const StatusScreen({super.key});

  @override
  State<StatusScreen> createState() => _StatusScreenState();
}

class _StatusScreenState extends State<StatusScreen> {
  SystemStatus? _status;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final status = await context.read<AppState>().stockData.getSystemStatus();
      if (mounted) {
        setState(() {
          _status = status;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _status = SystemStatus.offline(e.toString());
          _loading = false;
        });
      }
    }
  }

  String _formatLastUpdate(DateTime? dt) {
    if (dt == null) return '—';
    final local = dt.toLocal();
    return '${local.year}-${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')} '
        '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}:${local.second.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;

    return Scaffold(
      appBar: AppBar(
        title: const Text('حالة النظام'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'تحديث',
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        color: AppTheme.primary,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: LoadingView(message: 'جاري التحقق من الحالة...'),
              )
            else if (status != null) ...[
              _StatusRow(
                label: 'متصل بالخادم',
                ok: status.backendConnected,
              ),
              _StatusRow(
                label: 'متصل بـ Polygon',
                ok: status.polygonConnected,
              ),
              _StatusRow(
                label: 'بث WebSocket مباشر',
                ok: status.websocketLive,
              ),
              _StatusRow(
                label: 'الماسح يعمل',
                ok: status.marketScannerRunning,
              ),
              const SizedBox(height: 16),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.schedule, color: AppTheme.primary),
                  title: const Text('آخر تحديث'),
                  subtitle: Text(
                    _formatLastUpdate(status.lastUpdate),
                    style: const TextStyle(
                      color: AppTheme.textPrimary,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              ),
              if (status.error != null) ...[
                const SizedBox(height: 12),
                Text(
                  ArUi.backendText(status.error!),
                  style: const TextStyle(color: AppTheme.danger, fontSize: 13),
                ),
              ],
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh),
                  label: const Text('تحديث'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final String label;
  final bool ok;

  const _StatusRow({required this.label, required this.ok});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(
          ok ? Icons.check_circle : Icons.cancel,
          color: ok ? AppTheme.success : AppTheme.danger,
        ),
        title: Text(label),
        trailing: Text(
          ok ? 'نشط' : 'متوقف',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            color: ok ? AppTheme.success : AppTheme.danger,
          ),
        ),
      ),
    );
  }
}
