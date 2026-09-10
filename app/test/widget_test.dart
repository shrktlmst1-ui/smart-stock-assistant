import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/main.dart';

void main() {
  testWidgets('App loads facility login screen', (WidgetTester tester) async {
    await tester.pumpWidget(const FacilityManagementApp());
    await tester.pump();

    expect(find.text('نظام إدارة وتشغيل المنشآت'), findsOneWidget);
    expect(find.text('تسجيل الدخول'), findsOneWidget);
    expect(find.text('البريد الإلكتروني'), findsOneWidget);
    expect(find.text('كلمة المرور'), findsOneWidget);
  });
}
