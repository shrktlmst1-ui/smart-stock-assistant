/// Arabic UI strings and backend-value translators for display only.
class ArUi {
  ArUi._();

  /// Marker embedded in web build for deployment verification.
  static const String buildMarker = 'واجهة عربية';

  static String marketStatus(String status) {
    switch (status.toUpperCase()) {
      case 'CLOSED':
        return 'مغلق';
      case 'OPEN':
      case 'REGULAR':
        return 'مفتوح';
      case 'PRE_MARKET':
        return 'ما قبل الافتتاح';
      case 'AFTER_HOURS':
        return 'ما بعد الإغلاق';
      default:
        return status;
    }
  }

  static String marketLabel(String status) => 'السوق: ${marketStatus(status)}';

  static String signal(String value) {
    switch (value.toUpperCase()) {
      case 'BUY':
      case 'STRONG BUY':
        return 'شراء';
      case 'SELL':
      case 'STRONG SELL':
        return 'بيع';
      case 'WAIT':
      case 'NO TRADE':
        return 'انتظار';
      case 'AVOID':
      case 'AVOID / TRAP RISK':
        return 'تجنب';
      default:
        return value;
    }
  }

  static String trackStatus(String value) {
    switch (value) {
      case 'Waiting':
        return 'في الانتظار';
      case 'Active':
        return 'نشطة';
      case 'Target 1 Hit':
        return 'تحقق الهدف 1';
      case 'Target 2 Hit':
        return 'تحقق الهدف 2';
      case 'Target 3 Hit':
        return 'تحقق الهدف 3';
      case 'Stop Loss Hit':
        return 'وقف الخسارة';
      case 'Expired':
        return 'منتهية';
      default:
        return value;
    }
  }

  static String tradeResult(String value) {
    switch (value.toUpperCase()) {
      case 'WIN':
        return 'ربح';
      case 'LOSS':
        return 'خسارة';
      case 'BREAKEVEN':
        return 'تعادل';
      default:
        return value;
    }
  }

  static String tradeQuality(String value) {
    switch (value) {
      case 'Excellent':
        return 'ممتاز';
      case 'Very Good':
        return 'جيد جداً';
      case 'Good':
        return 'جيد';
      case 'Average':
        return 'متوسط';
      case 'Poor':
      case 'Weak':
        return 'ضعيف';
      default:
        return value;
    }
  }

  static String trend(String value) {
    switch (value) {
      case 'صاعد':
      case 'Bullish':
      case 'bullish':
      case 'up':
        return 'صاعد';
      case 'هابط':
      case 'Bearish':
      case 'bearish':
      case 'down':
        return 'هابط';
      case 'محايد':
      case 'Neutral':
      case 'neutral':
      case 'sideways':
        return 'محايد';
      default:
        return value;
    }
  }

  static String riskLevel(String value) {
    switch (value.toLowerCase()) {
      case 'low':
      case 'منخفض':
        return 'منخفض';
      case 'medium':
      case 'متوسط':
        return 'متوسط';
      case 'high':
      case 'مرتفع':
        return 'مرتفع';
      default:
        return value;
    }
  }

  static String timelineEvent(String label) {
    const map = {
      'Signal Generated': 'تم توليد الإشارة',
      'Entry Triggered': 'تم تفعيل الدخول',
      'Target 1 Hit': 'تحقق الهدف 1',
      'Target 2 Hit': 'تحقق الهدف 2',
      'Target 3 Hit': 'تحقق الهدف 3',
      'Stop Loss Hit': 'وقف الخسارة',
      'Trade Expired': 'انتهت الصفقة',
      'Trade Closed': 'إغلاق الصفقة',
    };
    return map[label] ?? label;
  }

  static String explanationLabel(String label) {
    const map = {
      'Trend Alignment': 'محاذاة الاتجاه',
      'BOS Confirmed': 'BOS مؤكد',
      'CHOCH Confirmed': 'CHOCH مؤكد',
      'Order Block': 'Order Block',
      'FVG': 'FVG',
      'Liquidity Sweep': 'سحب السيولة',
      'Relative Volume': 'الحجم النسبي',
      'VWAP': 'VWAP',
      'EMA Alignment': 'محاذاة EMA',
      'Retest Confirmed': 'إعادة الاختبار مؤكدة',
      'Retest Missing': 'إعادة الاختبار مفقودة',
    };
    return map[label] ?? label;
  }

  static String factorLabel(String label) {
    const map = {
      'SMC': 'SMC',
      'BOS': 'BOS',
      'CHOCH': 'CHOCH',
      'Order Block': 'Order Block',
      'FVG': 'FVG',
      'Liquidity': 'السيولة',
      'EMA20': 'EMA20',
      'EMA50': 'EMA50',
      'EMA200': 'EMA200',
      'VWAP': 'VWAP',
      'ATR': 'ATR',
      'Relative Volume': 'الحجم النسبي',
      'Volume Spike': 'ارتفاع الحجم',
      'Momentum': 'الزخم',
      'Trend': 'الاتجاه',
      'News': 'الأخبار',
      'Institutional Flow': 'التدفق المؤسسي',
      'R:R': 'R:R',
      'RSI': 'RSI',
      'MACD': 'MACD',
      'Delta Volume': 'Delta Volume',
    };
    return map[label] ?? label;
  }

  static String professionalSignal(String value) => signal(value);

  static String durationShort(int seconds) {
    if (seconds <= 0) return '—';
    if (seconds < 60) return '${seconds} ث';
    if (seconds < 3600) return '${seconds ~/ 60} د';
    return '${seconds ~/ 3600} س ${(seconds % 3600) ~/ 60} د';
  }

  /// Translates common backend English messages for display only.
  static String backendText(String text) {
    if (text.isEmpty) return text;

    var out = text;

    const exact = {
      'Market is currently in Pre-Market. Live liquidity filters are disabled. Showing the highest-quality watchlist candidates based on completed market data.':
          'السوق حالياً في مرحلة ما قبل الافتتاح. فلاتر السيولة المباشرة معطّلة. يتم عرض أفضل مرشحي المراقبة بناءً على بيانات السوق المكتملة.',
      'Market is currently in After-Hours. Live liquidity filters are disabled. Showing the highest-quality watchlist candidates based on completed market data.':
          'السوق حالياً في مرحلة ما بعد الإغلاق. فلاتر السيولة المباشرة معطّلة. يتم عرض أفضل مرشحي المراقبة بناءً على بيانات السوق المكتملة.',
      'Market is currently Closed. Live liquidity filters are disabled. Showing the highest-quality watchlist candidates based on completed market data.':
          'السوق مغلق حالياً. فلاتر السيولة المباشرة معطّلة. يتم عرض أفضل مرشحي المراقبة بناءً على بيانات السوق المكتملة.',
      'BUY blocked because:': 'تم منع الشراء بسبب:',
      'AVOID because:': 'سبب التجنب:',
      'Final blocker:': 'الحاجز النهائي:',
      'multiple factors': 'عوامل متعددة',
    };

    for (final entry in exact.entries) {
      out = out.replaceAll(entry.key, entry.value);
    }

    const partial = {
      'Market is currently in Pre-Market.': 'السوق حالياً في مرحلة ما قبل الافتتاح.',
      'Market is currently in After-Hours.': 'السوق حالياً في مرحلة ما بعد الإغلاق.',
      'Market is currently Closed.': 'السوق مغلق حالياً.',
      'Live liquidity filters are disabled.': 'فلاتر السيولة المباشرة معطّلة.',
      'Showing the highest-quality watchlist candidates based on completed market data.':
          'يتم عرض أفضل مرشحي المراقبة بناءً على بيانات السوق المكتملة.',
      'none passed live liquidity filters (min day volume, RVOL, spread, market cap).':
          'لم يجتز أي سهم فلاتر السيولة المباشرة (الحد الأدنى للحجم اليومي، RVOL، الفارق، القيمة السوقية).',
      'passed liquidity but deep analysis returned no snapshots.':
          'اجتازت السيولة لكن التحليل العميق لم يُرجع لقطات.',
      'completed full SMC/trend/momentum analysis;':
          'أكملت تحليل SMC/الاتجاه/الزخم؛',
      'institutional factor gates (min': 'بوابات العوامل المؤسسية (الحد الأدنى',
      'each). Most common failures:': 'لكل عامل). أكثر الإخفاقات شيوعاً:',
      'Scanned': 'تم فحص',
      'snapshot tickers;': 'رمزاً؛',
      'symbol(s) passed liquidity but deep analysis returned no snapshots.':
          'سهم/أسهم اجتازت السيولة لكن التحليل العميق لم يُرجع لقطات.',
      'symbol(s) completed full SMC/trend/momentum analysis; none passed all':
          'سهم/أسهم أكملت تحليل SMC/الاتجاه/الزخم؛ لم يجتز أي منها جميع',
      'long': 'صاعد',
      'short': 'هابط',
      'neutral': 'محايد',
      'bullish': 'صاعد',
      'bearish': 'هابط',
      'uptrend': 'اتجاه صاعد',
      'downtrend': 'اتجاه هابط',
      'range': 'نطاق',
      'accumulation': 'تجميع',
      'distribution': 'توزيع',
      'breakout': 'اختراق',
      'pullback': 'تراجع',
      'retest': 'إعادة اختبار',
      'liquidity grab': 'سحب سيولة',
      'trap': 'فخ',
      'low risk': 'مخاطرة منخفضة',
      'medium risk': 'مخاطرة متوسطة',
      'high risk': 'مخاطرة مرتفعة',
      'Signal BUY': 'إشارة شراء',
      'Signal SELL': 'إشارة بيع',
      'Signal WAIT': 'إشارة انتظار',
      'Signal AVOID': 'إشارة تجنب',
      'AI Score': 'درجة التحليل',
      'Expected holding': 'مدة الاحتفاظ المتوقعة',
      'Entry zone': 'منطقة الدخول',
      'Stop loss': 'وقف الخسارة',
      'Take profit': 'جني الأرباح',
      'Market structure': 'البنية السوقية',
      'Trap risk': 'مخاطر الفخ',
      'News risk': 'مخاطر الأخبار',
      'Liquidity inflow': 'سيولة واردة',
      'Liquidity outflow': 'سيولة صادرة',
      'Devil\'s advocate': 'رأي معارض',
      'Failed filter': 'فشل الفلتر',
      'Passed filter': 'نجح الفلتر',
      'Insufficient volume': 'حجم غير كافٍ',
      'Trend misalignment': 'عدم محاذاة الاتجاه',
      'No BOS confirmation': 'لا يوجد تأكيد BOS',
      'No CHOCH confirmation': 'لا يوجد تأكيد CHOCH',
      'Order block missing': 'Order Block مفقود',
      'FVG not filled': 'FVG غير ممتلئ',
      'Below minimum score': 'أقل من الحد الأدنى للدرجة',
      'Market closed': 'السوق مغلق',
      'Pre-market': 'ما قبل الافتتاح',
      'After-hours': 'ما بعد الإغلاق',
      'Regular session': 'جلسة عادية',
      'live': 'مباشر',
      'offline': 'غير متصل',
      'authenticated': 'مصادق',
      'disconnected': 'غير متصل',
      'connected': 'متصل',
      'active': 'نشط',
      'inactive': 'غير نشط',
      'running': 'يعمل',
      'stopped': 'متوقف',
    };

    for (final entry in partial.entries) {
      out = out.replaceAll(entry.key, entry.value);
    }

    out = out.replaceAllMapped(
      RegExp(r'Market is (PRE_MARKET|AFTER_HOURS|CLOSED|REGULAR)\.', caseSensitive: false),
      (m) => 'السوق: ${marketStatus(m.group(1)!)}.',
    );

    out = out.replaceAllMapped(
      RegExp(r'(\d[\d,]*) symbol\(s\)'),
      (m) => '${m.group(1)} سهم/أسهم',
    );

    return out;
  }
}
