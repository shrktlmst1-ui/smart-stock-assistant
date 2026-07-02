import '../models/stock.dart';

/// Embedded mock data — used when backend is unavailable.
class MockStockData {
  static final Map<String, Map<String, dynamic>> stocks = {
    'TSLA': {
      'symbol': 'TSLA',
      'name': 'Tesla Inc.',
      'price': 248.50,
      'change_percent': 2.35,
      'trend': 'صاعد',
      'rsi': 58.4,
      'macd': 3.21,
      'macd_signal': 2.85,
      'ema_20': 241.20,
      'ema_50': 232.80,
      'ema_200': 215.40,
      'volume': 98500000,
      'support': 235.00,
      'resistance': 265.00,
      'score': 78,
      'entry_price': 245.00,
      'stop_loss': 232.00,
      'target_1': 265.00,
      'target_2': 285.00,
      'risk_level': 'متوسط',
      'recommendation_reason':
          'اختراق EMA 50 مع RSI في منطقة صحية وMACD إيجابي. حجم تداول مرتفع يدعم الاتجاه الصاعد.',
    },
    'NVDA': {
      'symbol': 'NVDA',
      'name': 'NVIDIA Corporation',
      'price': 875.30,
      'change_percent': 1.82,
      'trend': 'صاعد',
      'rsi': 62.1,
      'macd': 8.45,
      'macd_signal': 7.20,
      'ema_20': 860.50,
      'ema_50': 820.30,
      'ema_200': 680.00,
      'volume': 45200000,
      'support': 840.00,
      'resistance': 920.00,
      'score': 85,
      'entry_price': 868.00,
      'stop_loss': 835.00,
      'target_1': 920.00,
      'target_2': 980.00,
      'risk_level': 'متوسط',
      'recommendation_reason':
          'السهم فوق جميع EMAs مع زخم قوي في قطاع الذكاء الاصطناعي. MACD فوق خط الإشارة.',
    },
    'AMD': {
      'symbol': 'AMD',
      'name': 'Advanced Micro Devices',
      'price': 162.75,
      'change_percent': -0.45,
      'trend': 'محايد',
      'rsi': 48.2,
      'macd': -0.35,
      'macd_signal': -0.20,
      'ema_20': 164.00,
      'ema_50': 158.50,
      'ema_200': 145.20,
      'volume': 32100000,
      'support': 155.00,
      'resistance': 172.00,
      'score': 62,
      'entry_price': 158.00,
      'stop_loss': 150.00,
      'target_1': 172.00,
      'target_2': 185.00,
      'risk_level': 'متوسط',
      'recommendation_reason':
          'تذبذب حول EMA 20. انتظر تأكيد اختراق المقاومة 172\$ أو ارتداد من الدعم 155\$.',
    },
    'AAPL': {
      'symbol': 'AAPL',
      'name': 'Apple Inc.',
      'price': 189.95,
      'change_percent': 0.72,
      'trend': 'صاعد',
      'rsi': 55.8,
      'macd': 1.12,
      'macd_signal': 0.95,
      'ema_20': 187.30,
      'ema_50': 182.50,
      'ema_200': 175.00,
      'volume': 52800000,
      'support': 182.00,
      'resistance': 198.00,
      'score': 74,
      'entry_price': 187.50,
      'stop_loss': 178.00,
      'target_1': 198.00,
      'target_2': 210.00,
      'risk_level': 'منخفض',
      'recommendation_reason':
          'اتجاه صاعد مستقر فوق EMA 200. RSI متوازن وMACD إيجابي.',
    },
    'MSFT': {
      'symbol': 'MSFT',
      'name': 'Microsoft Corporation',
      'price': 415.20,
      'change_percent': 1.15,
      'trend': 'صاعد',
      'rsi': 59.3,
      'macd': 2.80,
      'macd_signal': 2.40,
      'ema_20': 408.00,
      'ema_50': 395.50,
      'ema_200': 370.00,
      'volume': 22400000,
      'support': 400.00,
      'resistance': 430.00,
      'score': 80,
      'entry_price': 410.00,
      'stop_loss': 395.00,
      'target_1': 430.00,
      'target_2': 450.00,
      'risk_level': 'منخفض',
      'recommendation_reason':
          'سهم دفاعي قوي مع اتجاه صاعد واضح. مناسب للاحتفاظ متوسط المدى.',
    },
    'GOOGL': {
      'symbol': 'GOOGL',
      'name': 'Alphabet Inc.',
      'price': 172.40,
      'change_percent': 0.95,
      'trend': 'صاعد',
      'rsi': 57.0,
      'macd': 1.55,
      'macd_signal': 1.30,
      'ema_20': 169.80,
      'ema_50': 165.20,
      'ema_200': 155.00,
      'volume': 18900000,
      'support': 165.00,
      'resistance': 180.00,
      'score': 76,
      'entry_price': 170.00,
      'stop_loss': 162.00,
      'target_1': 180.00,
      'target_2': 192.00,
      'risk_level': 'منخفض',
      'recommendation_reason':
          'اختراق EMA 50 مع تحسن في حجم التداول. إعلانات قوية تدعم السعر.',
    },
    'META': {
      'symbol': 'META',
      'name': 'Meta Platforms Inc.',
      'price': 505.80,
      'change_percent': 2.10,
      'trend': 'صاعد',
      'rsi': 64.5,
      'macd': 4.20,
      'macd_signal': 3.50,
      'ema_20': 495.00,
      'ema_50': 475.00,
      'ema_200': 420.00,
      'volume': 15600000,
      'support': 485.00,
      'resistance': 530.00,
      'score': 82,
      'entry_price': 500.00,
      'stop_loss': 475.00,
      'target_1': 530.00,
      'target_2': 560.00,
      'risk_level': 'متوسط',
      'recommendation_reason':
          'زخم قوي في قطاع التكنولوجيا. RSI قريب من منطقة تشبع شرائي — انتبه للتصحيح.',
    },
    'AMZN': {
      'symbol': 'AMZN',
      'name': 'Amazon.com Inc.',
      'price': 185.60,
      'change_percent': 0.55,
      'trend': 'محايد',
      'rsi': 52.0,
      'macd': 0.80,
      'macd_signal': 0.75,
      'ema_20': 184.00,
      'ema_50': 180.50,
      'ema_200': 168.00,
      'volume': 31200000,
      'support': 178.00,
      'resistance': 192.00,
      'score': 68,
      'entry_price': 180.00,
      'stop_loss': 172.00,
      'target_1': 192.00,
      'target_2': 205.00,
      'risk_level': 'منخفض',
      'recommendation_reason': 'تجميع فوق EMA 50. انتظر كسر 192\$ للتأكيد.',
    },
  };

  static List<StockOpportunity> getTopOpportunities({int limit = 5}) {
    final sorted = stocks.values.toList()
      ..sort((a, b) => (b['score'] as int).compareTo(a['score'] as int));
    return sorted
        .take(limit)
        .map((s) => StockOpportunity.fromJson(s))
        .toList();
  }

  static List<SearchResult> search(String query) {
    final q = query.toUpperCase().trim();
    if (q.isEmpty) return [];

    return stocks.entries
        .where((e) =>
            e.key.contains(q) ||
            (e.value['name'] as String).toUpperCase().contains(q))
        .map((e) => SearchResult.fromJson(e.value))
        .toList();
  }

  static StockAnalysis? getAnalysis(String symbol) {
    final data = stocks[symbol.toUpperCase()];
    if (data == null) return null;
    return StockAnalysis.fromJson(data);
  }
}
