import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:smart_stock_assistant/services/home_screen_cache.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await HomeScreenCache.clear();
  });

  group('HomeScreenCache', () {
    test('seedMemory rejects older snapshot', () {
      final newer = HomeCachedSnapshot(
        fetchedAt: DateTime(2026, 8, 27, 12, 0),
        opportunityRaw: const {'status': 'WATCH', 'display_signals': []},
      );
      final older = HomeCachedSnapshot(
        fetchedAt: DateTime(2026, 8, 27, 11, 0),
        opportunityRaw: const {'status': 'NONE', 'display_signals': []},
      );
      HomeScreenCache.seedMemory(newer);
      HomeScreenCache.seedMemory(older);
      expect(HomeScreenCache.memorySnapshot?.fetchedAt, newer.fetchedAt);
    });

    test('save keeps newer in memory', () async {
      final first = HomeCachedSnapshot(
        fetchedAt: DateTime(2026, 8, 27, 10, 0),
        opportunityRaw: const {
          'status': 'WATCH',
          'status_ar': 'ضغط شراء قوي',
          'market_status': 'REGULAR',
          'market_open': true,
          'scan_interval_seconds': 15,
          'message': '',
          'display_signals': [
            {
              'symbol': 'CRE',
              'name': 'CRE',
              'price': 1.15,
              'change_percent': 10,
              'score': 68,
              'status': 'WATCH',
              'status_ar': 'ضغط شراء قوي',
              'display_type': 'STRONG_BUY_WATCH',
              'buy_pressure_score': 12,
              'confluence_count': 5,
              'appeared_at': '2026-08-27T10:00:00Z',
              'expires_at': '',
              'entry_zone': 1.15,
              'entry_zone_low': 1.1,
              'entry_zone_high': 1.2,
              'stop_loss': 1.05,
              'target_1': 1.25,
              'target_2': 1.35,
              'risk_level': 'متوسط',
              'confirmed_factors': 5,
              'total_factors': 17,
              'reasons_ar': [],
            },
          ],
          'signals': [],
        },
      );
      await HomeScreenCache.save(first);
      final loaded = await HomeScreenCache.load();
      expect(loaded?.opportunity?.confirmedJumps().first.symbol, 'CRE');

      final older = HomeCachedSnapshot(
        fetchedAt: DateTime(2026, 8, 27, 9, 0),
        opportunityRaw: const {'status': 'NONE', 'display_signals': [], 'signals': []},
      );
      await HomeScreenCache.save(older);
      expect(HomeScreenCache.memorySnapshot?.fetchedAt, first.fetchedAt);
    });

    test('roundtrip json preserves fetched_at', () {
      final snap = HomeCachedSnapshot(
        fetchedAt: DateTime.utc(2026, 8, 27, 7, 30),
        pulseListRaw: const {'enabled': true, 'alerts': [], 'count': 0},
      );
      final decoded = HomeCachedSnapshot.fromJson(snap.toJson());
      expect(decoded.fetchedAt.millisecondsSinceEpoch, snap.fetchedAt.millisecondsSinceEpoch);
    });
  });
}
