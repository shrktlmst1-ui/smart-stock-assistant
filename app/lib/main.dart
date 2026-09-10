import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/facility_login_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const FacilityManagementApp());
}

class FacilityManagementApp extends StatelessWidget {
  const FacilityManagementApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'نظام إدارة وتشغيل المنشآت',
      debugShowCheckedModeBanner: false,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: ThemeData(useMaterial3: true, brightness: Brightness.light, colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2563EB))),
      builder: (context, child) => Directionality(textDirection: TextDirection.rtl, child: child ?? const SizedBox.shrink()),
      home: const FacilityLoginScreen(),
    );
  }
}
