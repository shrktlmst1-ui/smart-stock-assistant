import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:smart_stock_assistant/main.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Facility MVP UI uses the live API', (WidgetTester tester) async {
    await tester.pumpWidget(const FacilityManagementApp());
    await tester.pump();

    await tester.tap(find.text('تهيئة النظام لأول مرة'));
    await tester.pump();

    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'منشأة اختبار');
    await tester.enterText(fields.at(1), 'test@example.test');
    await tester.enterText(fields.at(2), 'TestPassword123');
    await tester.tap(find.text('إنشاء المنشأة والمدير'));
    await tester.pumpAndSettle(const Duration(seconds: 2));

    expect(find.text('لوحة التحكم'), findsOneWidget);
    expect(find.text('الفروع'), findsOneWidget);
    expect(find.text('الموظفون'), findsOneWidget);

    await tester.tap(find.byTooltip('إضافة فرع'));
    await tester.pump();
    final branchFields = find.byType(TextField);
    await tester.enterText(branchFields.at(0), 'الفرع الرئيسي');
    await tester.enterText(branchFields.at(1), 'المدينة');
    await tester.tap(find.text('حفظ'));
    await tester.pumpAndSettle(const Duration(seconds: 1));
    expect(find.text('الفرع الرئيسي'), findsOneWidget);

    await tester.tap(find.byTooltip('إضافة موظف'));
    await tester.pump();
    final employeeFields = find.byType(TextField);
    await tester.enterText(employeeFields.at(0), 'موظف اختبار');
    await tester.enterText(employeeFields.at(1), 'EMP-001');
    await tester.enterText(employeeFields.at(2), '0500000000');
    await tester.enterText(employeeFields.at(3), 'مدير');
    await tester.tap(find.text('حفظ'));
    await tester.pumpAndSettle(const Duration(seconds: 1));

    expect(find.text('موظف اختبار'), findsOneWidget);
    expect(find.text('EMP-001 • مدير'), findsOneWidget);
  });
}
