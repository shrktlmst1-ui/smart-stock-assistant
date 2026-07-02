import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/app_state.dart';
import '../theme/app_theme.dart';
import '../widgets/stock_card.dart';
import 'stock_analysis_screen.dart';

class WatchlistScreen extends StatefulWidget {
  const WatchlistScreen({super.key});

  @override
  State<WatchlistScreen> createState() => _WatchlistScreenState();
}

class _WatchlistScreenState extends State<WatchlistScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppState>().refreshWatchlist();
    });
  }

  @override
  Widget build(BuildContext context) {
    final watchlist = context.watch<AppState>().watchlist;

    return Scaffold(
      appBar: AppBar(
        title: const Text('قائمة المراقبة'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<AppState>().refreshWatchlist(),
          ),
        ],
      ),
      body: watchlist.isEmpty
          ? const EmptyState(
              icon: Icons.bookmark_border,
              title: 'قائمة المراقبة فارغة',
              subtitle: 'أضف أسهماً من شاشة التحليل',
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: watchlist.length,
              itemBuilder: (_, i) {
                final item = watchlist[i];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) =>
                              StockAnalysisScreen(symbol: item.symbol),
                        ),
                      );
                    },
                    leading: CircleAvatar(
                      backgroundColor:
                          AppTheme.primary.withValues(alpha: 0.15),
                      child: Text(
                        item.symbol.substring(0, 1),
                        style: const TextStyle(
                          color: AppTheme.primary,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    title: Text(
                      item.symbol,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    subtitle: Text(item.name),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline, color: AppTheme.danger),
                      onPressed: () async {
                        await context
                            .read<AppState>()
                            .removeFromWatchlist(item.symbol);
                      },
                    ),
                  ),
                );
              },
            ),
    );
  }
}
