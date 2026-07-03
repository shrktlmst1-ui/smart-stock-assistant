import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/stock.dart';
import '../services/app_state.dart';
import '../theme/app_theme.dart';
import '../widgets/stock_card.dart';
import 'stock_analysis_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  OpportunitiesDashboard? _dashboard;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = context.read<AppState>().stockData;
      final dashboard = await data.getOpportunitiesDashboard(limit: 20);
      if (mounted) {
        setState(() {
          _dashboard = dashboard;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _dashboard = null;
          _loading = false;
          _error = e.toString();
        });
      }
    }
  }

  void _openAnalysis(String symbol) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => StockAnalysisScreen(symbol: symbol),
      ),
    );
  }

  Future<void> _logout() async {
    await context.read<AppState>().logout();
    if (mounted) {
      Navigator.of(context).pushNamedAndRemoveUntil('/login', (_) => false);
    }
  }

  Widget _buildDebugSummary(OpportunitiesDashboard dashboard) {
    final d = dashboard.debug;
    final reason = dashboard.noSignalReason.isNotEmpty
        ? dashboard.noSignalReason
        : dashboard.explanation;

    return Card(
      color: AppTheme.surface,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.analytics_outlined, color: AppTheme.primary, size: 20),
                const SizedBox(width: 8),
                Text(
                  'Market: ${dashboard.marketStatus}',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    color: AppTheme.textPrimary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _DebugRow('Symbols scanned', '${d.symbolsScanned}'),
            _DebugRow('Universe symbols', '${d.universeSymbols}'),
            _DebugRow('Passed liquidity', '${d.passedLiquidity}'),
            _DebugRow('Deep analysis', '${d.deepAnalysisCompleted}'),
            _DebugRow('Passed all 18 filters', '${d.passedAllFilters}'),
            if (d.signalWait > 0 || d.signalAvoid > 0) ...[
              const SizedBox(height: 8),
              Text(
                'Signals: WAIT ${d.signalWait}, AVOID ${d.signalAvoid}',
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
              ),
            ],
            if (reason.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                reason,
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final dashboard = _dashboard;
    final items = dashboard?.displayItems ?? [];
    final showingWatchlist = dashboard?.showingWatchlist ?? false;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Smart Stock Assistant'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
            tooltip: 'Refresh',
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _logout,
            tooltip: 'خروج',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        color: AppTheme.primary,
        child: _loading
            ? const LoadingView(message: 'Loading live opportunities...')
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          AppTheme.primary.withOpacity( 0.2),
                          AppTheme.surface,
                        ],
                        begin: Alignment.topRight,
                        end: Alignment.bottomLeft,
                      ),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: AppTheme.primary.withOpacity( 0.3),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          showingWatchlist
                              ? 'Top Watchlist Candidates'
                              : 'Top Institutional Opportunities',
                          style: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                            color: AppTheme.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          showingWatchlist
                              ? 'Highest AI scores — not live entry signals until all filters pass'
                              : 'Live US market — all 18 factors must pass',
                          style: const TextStyle(color: AppTheme.textSecondary),
                        ),
                      ],
                    ),
                  ),
                  if (dashboard != null) ...[
                    const SizedBox(height: 12),
                    _buildDebugSummary(dashboard),
                  ],
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _load,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Refresh'),
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_error != null) ...[
                    Card(
                      color: AppTheme.danger.withOpacity( 0.12),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Backend connection error',
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: AppTheme.danger,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              _error!,
                              style: const TextStyle(
                                color: AppTheme.textSecondary,
                                fontSize: 13,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  if (items.isEmpty && _error == null)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 32),
                      child: Column(
                        children: [
                          Icon(
                            Icons.insights_outlined,
                            size: 56,
                            color: AppTheme.textSecondary,
                          ),
                          SizedBox(height: 16),
                          Text(
                            'No High Quality Opportunities Right Now',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                              color: AppTheme.textPrimary,
                            ),
                          ),
                          SizedBox(height: 8),
                          Text(
                            'See scanner summary above for pipeline counts and rejection reasons.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: AppTheme.textSecondary),
                          ),
                        ],
                      ),
                    )
                  else if (items.isNotEmpty) ...[
                    SectionHeader(
                      title: showingWatchlist ? 'Watchlist Candidates' : 'Top Opportunities',
                      subtitle: showingWatchlist
                          ? 'Ranked by AI score (filters may not all pass)'
                          : 'Live data from Polygon',
                    ),
                    ...List.generate(items.length, (i) {
                      final stock = items[i];
                      return StockCard(
                        stock: stock,
                        rank: i + 1,
                        onTap: () => _openAnalysis(stock.symbol),
                      );
                    }),
                  ],
                  const SizedBox(height: 8),
                  const Text(
                    'For monitoring only — not investment advice.',
                    style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
      ),
    );
  }
}

class _DebugRow extends StatelessWidget {
  final String label;
  final String value;

  const _DebugRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
          Text(
            value,
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }
}
