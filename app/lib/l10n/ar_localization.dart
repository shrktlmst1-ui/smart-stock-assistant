/// Arabic UI strings and backend-value translators for display only.
class ArUi {
  ArUi._();

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

  static String professionalSignal(String value) => signal(value);

  static String durationShort(int seconds) {
    if (seconds <= 0) return '—';
    if (seconds < 60) return '${seconds} ث';
    if (seconds < 3600) return '${seconds ~/ 60} د';
    return '${seconds ~/ 3600} س ${(seconds % 3600) ~/ 60} د';
  }
}
