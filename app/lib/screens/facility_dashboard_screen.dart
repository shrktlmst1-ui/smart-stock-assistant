import 'package:flutter/material.dart';

class FacilityDashboardScreen extends StatelessWidget {
  const FacilityDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final cards = <_DashboardCardData>[
      _DashboardCardData('الموظفون', 'إدارة بيانات الموظفين', Icons.people_outline),
      _DashboardCardData('الحضور والانصراف', 'متابعة الدوام اليومية', Icons.access_time),
      _DashboardCardData('المهام', 'توزيع ومتابعة المهام', Icons.task_alt),
      _DashboardCardData('المصروفات', 'إدارة ومراجعة المصروفات', Icons.receipt_long),
      _DashboardCardData('السلف والخصومات', 'الحسابات والاستقطاعات', Icons.account_balance_wallet_outlined),
      _DashboardCardData('الفروع', 'إدارة فروع المنشأة', Icons.location_city_outlined),
    ];

    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FB),
      appBar: AppBar(
        title: const Text('نظام إدارة وتشغيل المنشآت'),
        centerTitle: false,
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF18212F),
        elevation: 0,
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final columns = constraints.maxWidth >= 1100 ? 3 : constraints.maxWidth >= 650 ? 2 : 1;
          return SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: const Color(0xFF18212F),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('لوحة التحكم', style: TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold)),
                      SizedBox(height: 8),
                      Text('نظرة سريعة على تشغيل المنشأة وعملياتها اليومية', style: TextStyle(color: Colors.white70, fontSize: 15)),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: cards.length,
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: columns,
                    crossAxisSpacing: 16,
                    mainAxisSpacing: 16,
                    childAspectRatio: 2.2,
                  ),
                  itemBuilder: (_, index) => _DashboardCard(data: cards[index]),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _DashboardCardData {
  final String title;
  final String subtitle;
  final IconData icon;
  const _DashboardCardData(this.title, this.subtitle, this.icon);
}

class _DashboardCard extends StatelessWidget {
  final _DashboardCardData data;
  const _DashboardCard({required this.data});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(color: const Color(0xFFE9EEF7), borderRadius: BorderRadius.circular(12)),
              child: Icon(data.icon, color: const Color(0xFF18212F)),
            ),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
              Text(data.title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              Text(data.subtitle, style: const TextStyle(color: Colors.black54, fontSize: 12)),
            ])),
          ],
        ),
      ),
    );
  }
}
