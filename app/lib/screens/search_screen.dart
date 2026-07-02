import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/stock.dart';
import '../services/app_state.dart';
import '../widgets/stock_card.dart';
import 'stock_analysis_screen.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  List<SearchResult> _results = [];
  bool _searching = false;
  String? _lastQuery;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _search(String query) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty) {
      setState(() {
        _results = [];
        _lastQuery = null;
      });
      return;
    }

    setState(() {
      _searching = true;
      _lastQuery = trimmed;
    });

    final data = context.read<AppState>().stockData;
    final results = await data.search(trimmed);

    if (mounted) {
      setState(() {
        _results = results;
        _searching = false;
      });
    }
  }

  void _openAnalysis(String symbol) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => StockAnalysisScreen(symbol: symbol),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('بحث عن سهم')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: _controller,
              textDirection: TextDirection.ltr,
              textCapitalization: TextCapitalization.characters,
              decoration: InputDecoration(
                hintText: 'TSLA / NVDA / AMD ...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _controller.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _controller.clear();
                          _search('');
                        },
                      )
                    : null,
              ),
              onChanged: (v) {
                setState(() {});
                if (v.length >= 1) _search(v);
              },
              onSubmitted: _search,
            ),
          ),
          Expanded(
            child: _searching
                ? const LoadingView(message: 'جاري البحث...')
                : _lastQuery == null
                    ? const EmptyState(
                        icon: Icons.search,
                        title: 'ابحث عن سهم',
                        subtitle: 'أدخل رمز السهم مثل TSLA أو NVDA',
                      )
                    : _results.isEmpty
                        ? EmptyState(
                            icon: Icons.search_off,
                            title: 'لا توجد نتائج',
                            subtitle: 'لم يتم العثور على "$_lastQuery"',
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.symmetric(horizontal: 16),
                            itemCount: _results.length,
                            itemBuilder: (_, i) {
                              final r = _results[i];
                              return SearchResultTile(
                                result: r,
                                onTap: () => _openAnalysis(r.symbol),
                              );
                            },
                          ),
          ),
        ],
      ),
    );
  }
}
