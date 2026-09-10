import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_stock_assistant/main.dart';

void main() {
  testWidgets('Facility MVP UI uses the live API for setup, branch, and employee', (WidgetTester tester) async {
    await tester.pumpWidget(const FacilityManagementApp());
    await tester.pump();

    await tester.tap(find.text('تهيئة النظام لأول مرة'));
    await tester.pump();

    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'شركة واجهة E2E');
    await tester.enterText(fields.at(1), 'ui-e2e@example.test');
    await tester.enterText(fields.at(2), 'StrongPass123');
    await tester.tap(find.text('إنشاء المنشأة والمدير'));
    await tester.pumpAndSettle(const Duration(seconds: 2));

    expect(find.text('لوحة التحكم'), findsOneWidget);
    expect(find.text('الفروع'), findsOneWidget);
    expect(find.text('الموظفون'), findsOneWidget);

    await tester.tap(find.byTooltip('إضافة فرع'));
    await tester.pump();
    final branchFields = find.byType(TextField);
    await tester.enterText(branchFields.at(0), 'فرع الواجهة');
    await tester.enterText(branchFields.at(1), 'الرياض');
    await tester.tap(find.text('حفظ'));
    await tester.pumpAndSettle(const Duration(seconds: 1));
    expect(find.text('فرع الواجهة'), findsOneWidget);

    await tester.tap(find.byTooltip('إضافة موظف'));
    await tester.pump();
    final employeeFields = find.byType(TextField);
    await tester.enterText(employeeFields.at(0), 'موظف الواجهة');
    await tester.enterText(employeeFields.at(1), 'UI-001');
    await tester.enterText(employeeFields.at(2), '0500000000');
    await tester.enterText(employeeFields.at(3), 'مدير');
    await tester.tap(find.text('حفظ'));
    await tester.pumpAndSettle(const Duration(seconds: 1));

    expect(find.text('موظف الواجهة'), findsOneWidget);
    expect(find.text('UI-001 • مدير'), findsOneWidget);
  });
}
