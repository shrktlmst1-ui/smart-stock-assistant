import 'package:flutter/material.dart';
import '../services/facility_api_service.dart';
import 'facility_dashboard_screen.dart';

class FacilityLoginScreen extends StatefulWidget {
  const FacilityLoginScreen({super.key});
  @override State<FacilityLoginScreen> createState() => _FacilityLoginScreenState();
}

class _FacilityLoginScreenState extends State<FacilityLoginScreen> {
  final api = FacilityApiService();
  final email = TextEditingController();
  final password = TextEditingController();
  final facility = TextEditingController();
  bool setupMode = false, loading = false;

  Future<void> submit() async {
    if (email.text.trim().isEmpty || password.text.isEmpty || (setupMode && facility.text.trim().isEmpty)) return;
    setState(() => loading = true);
    try {
      if (setupMode) await api.setup(facility.text.trim(), email.text.trim(), password.text);
      else await api.login(email.text.trim(), password.text);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => FacilityDashboardScreen(api: api)));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))));
    } finally { if (mounted) setState(() => loading = false); }
  }

  @override Widget build(BuildContext context) => Scaffold(
    body: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 460), child: Card(margin: const EdgeInsets.all(24), child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Icon(Icons.business_center_outlined, size: 54), const SizedBox(height: 16),
      Text(setupMode ? 'تهيئة المنشأة' : 'تسجيل الدخول', style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
      const SizedBox(height: 24),
      if (setupMode) ...[TextField(controller: facility, decoration: const InputDecoration(labelText: 'اسم المنشأة', border: OutlineInputBorder())), const SizedBox(height: 12)],
      TextField(controller: email, keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'البريد الإلكتروني', border: OutlineInputBorder())),
      const SizedBox(height: 12), TextField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'كلمة المرور', border: OutlineInputBorder())),
      const SizedBox(height: 20), SizedBox(width: double.infinity, height: 48, child: FilledButton(onPressed: loading ? null : submit, child: loading ? const CircularProgressIndicator() : Text(setupMode ? 'إنشاء المنشأة والمدير' : 'دخول'))),
      const SizedBox(height: 8), TextButton(onPressed: loading ? null : () => setState(() => setupMode = !setupMode), child: Text(setupMode ? 'لدي حساب بالفعل' : 'تهيئة النظام لأول مرة')),
    ])))))
  );

  @override void dispose() { email.dispose(); password.dispose(); facility.dispose(); super.dispose(); }
}
