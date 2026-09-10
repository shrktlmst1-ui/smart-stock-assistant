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

  Future<void> addBranch() async {
    final name = TextEditingController();
    final address = TextEditingController();
    final ok = await showDialog<bool>(context: context, builder: (_) => AlertDialog(
      title: const Text('إضافة فرع'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: name, decoration: const InputDecoration(labelText: 'اسم الفرع')),
        TextField(controller: address, decoration: const InputDecoration(labelText: 'العنوان')),
      ]),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('إلغاء')), FilledButton(onPressed: () async { if (name.text.trim().isEmpty) return; try { await widget.api.createBranch(name.text.trim(), address.text.trim()); if (context.mounted) Navigator.pop(context, true); } catch (e) { if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString()))); } }, child: const Text('حفظ'))],
    ));
    // The dialog's reverse animation can still reference its TextFields briefly after pop.
    // Dispose controllers after the route has fully detached them from the widget tree.
    Future.delayed(const Duration(milliseconds: 500), () { name.dispose(); address.dispose(); });
    if (ok == true) await load();
  }

  Future<void> addEmployee() async {
    final name = TextEditingController();
    final number = TextEditingController();
    final phone = TextEditingController();
    final title = TextEditingController();
    int? branchId;
    final ok = await showDialog<bool>(context: context, builder: (_) => StatefulBuilder(builder: (context, setDialogState) => AlertDialog(
      title: const Text('إضافة موظف'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: name, decoration: const InputDecoration(labelText: 'اسم الموظف')),
        TextField(controller: number, decoration: const InputDecoration(labelText: 'رقم الموظف')),
        TextField(controller: phone, decoration: const InputDecoration(labelText: 'الجوال')),
        TextField(controller: title, decoration: const InputDecoration(labelText: 'المسمى الوظيفي')),
        DropdownButtonFormField<int?>(value: branchId, decoration: const InputDecoration(labelText: 'الفرع'), items: [const DropdownMenuItem<int?>(value: null, child: Text('بدون فرع')), ...branches.map((b) => DropdownMenuItem<int?>(value: b['id'] as int, child: Text(b['name'].toString())))], onChanged: (v) => setDialogState(() => branchId = v)),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('إلغاء')), FilledButton(onPressed: () async { if (name.text.trim().isEmpty || number.text.trim().isEmpty) return; try { await widget.api.createEmployee({'name': name.text.trim(), 'employee_no': number.text.trim(), 'phone': phone.text.trim(), 'job_title': title.text.trim(), 'branch_id': branchId}); if (context.mounted) Navigator.pop(context, true); } catch (e) { if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString()))); } }, child: const Text('حفظ'))],
    )));
    Future.delayed(const Duration(milliseconds: 500), () { name.dispose(); number.dispose(); phone.dispose(); title.dispose(); });
    if (ok == true) await load();
  }

  @override void initState() { super.initState(); load(); }

  @override Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('نظام إدارة وتشغيل المنشآت'), actions: [IconButton(onPressed: addBranch, tooltip: 'إضافة فرع', icon: const Icon(Icons.add_business_outlined)), IconButton(onPressed: addEmployee, tooltip: 'إضافة موظف', icon: const Icon(Icons.person_add_alt_1_outlined)), IconButton(onPressed: load, icon: const Icon(Icons.refresh))]),
    body: RefreshIndicator(onRefresh: load, child: ListView(padding: const EdgeInsets.all(24), children: [
      Text('لوحة التحكم', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold)),
      const SizedBox(height: 8), const Text('بيانات حقيقية من قاعدة البيانات — المنشأة والفروع والموظفون'), const SizedBox(height: 24),
      if (loading) const Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator())),
      if (error != null) Card(child: Padding(padding: const EdgeInsets.all(16), child: Text('تعذر تحميل البيانات: $error'))),
      if (!loading && error == null) ...[
        Row(children: [_Stat(title: 'الفروع', value: branches.length.toString(), icon: Icons.location_city_outlined), const SizedBox(width: 12), _Stat(title: 'الموظفون', value: employees.length.toString(), icon: Icons.people_outline)]),
        const SizedBox(height: 24), const Text('الفروع', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)), const SizedBox(height: 10),
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
