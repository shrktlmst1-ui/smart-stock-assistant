import 'package:flutter/material.dart';
import '../services/facility_api_service.dart';

class FacilityDashboardScreen extends StatefulWidget {
  final FacilityApiService api;
  const FacilityDashboardScreen({super.key, required this.api});
  @override State<FacilityDashboardScreen> createState() => _FacilityDashboardScreenState();
}

class _FacilityDashboardScreenState extends State<FacilityDashboardScreen> {
  List<dynamic> branches = [], employees = [];
  bool loading = true;
  String? error;

  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final results = await Future.wait([widget.api.branches(), widget.api.employees()]);
      if (mounted) setState(() { branches = results[0]; employees = results[1]; loading = false; });
    } catch (e) { if (mounted) setState(() { error = e.toString(); loading = false; }); }
  }

  @override void initState() { super.initState(); load(); }

  @override Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('نظام إدارة وتشغيل المنشآت'), actions: [IconButton(onPressed: load, icon: const Icon(Icons.refresh))]),
    body: RefreshIndicator(onRefresh: load, child: ListView(padding: const EdgeInsets.all(24), children: [
      Text('لوحة التحكم', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold)),
      const SizedBox(height: 8), const Text('بيانات حقيقية من قاعدة البيانات — المنشآت والفروع والموظفون'), const SizedBox(height: 24),
      if (loading) const Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator())),
      if (error != null) Card(child: Padding(padding: const EdgeInsets.all(16), child: Text('تعذر تحميل البيانات: $error'))),
      if (!loading && error == null) ...[
        Row(children: [_Stat(title: 'الفروع', value: branches.length.toString(), icon: Icons.location_city_outlined), const SizedBox(width: 12), _Stat(title: 'الموظفون', value: employees.length.toString(), icon: Icons.people_outline)]),
        const SizedBox(height: 24),
        const Text('الفروع', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)), const SizedBox(height: 10),
        if (branches.isEmpty) const Card(child: ListTile(title: Text('لا توجد فروع بعد'))),
        ...branches.map((b) => Card(child: ListTile(leading: const Icon(Icons.location_on_outlined), title: Text(b['name'].toString()), subtitle: Text((b['address'] ?? '').toString())))),
        const SizedBox(height: 20), const Text('الموظفون', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)), const SizedBox(height: 10),
        if (employees.isEmpty) const Card(child: ListTile(title: Text('لا يوجد موظفون بعد'))),
        ...employees.map((e) => Card(child: ListTile(leading: const Icon(Icons.person_outline), title: Text(e['name'].toString()), subtitle: Text('${e['employee_no']} • ${(e['job_title'] ?? '').toString()}')))),
      ],
    ])),
  );
}

class _Stat extends StatelessWidget {
  final String title, value; final IconData icon;
  const _Stat({required this.title, required this.value, required this.icon});
  @override Widget build(BuildContext context) => Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(18), child: Row(children: [Icon(icon, size: 30), const SizedBox(width: 12), Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(value, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold)), Text(title)])]))));
}
