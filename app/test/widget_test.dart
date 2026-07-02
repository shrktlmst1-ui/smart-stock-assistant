import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/main.dart';

void main() {
  testWidgets('App loads login screen', (WidgetTester tester) async {
    await tester.pumpWidget(const SmartStockApp());
    await tester.pumpAndSettle();

    expect(find.text('Smart Stock Assistant'), findsOneWidget);
    expect(find.text('تسجيل الدخول'), findsOneWidget);
  });
}
