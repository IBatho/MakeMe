import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/insights_provider.dart';

class InsightsScreen extends ConsumerWidget {
  const InsightsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final insightsAsync = ref.watch(insightsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Insights'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(insightsProvider),
          ),
        ],
      ),
      body: insightsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Could not load insights: $e')),
        data: (data) => _InsightsBody(data: data),
      ),
    );
  }
}

class _InsightsBody extends StatelessWidget {
  const _InsightsBody({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final dataPoints = data['data_points'] as int? ?? 0;
    final modelWarm = data['model_warm'] as bool? ?? false;
    final banditUpdates = data['bandit_updates'] as int? ?? 0;
    final summary = data['summary'] as String? ?? '';
    final peakHours = (data['peak_hours'] as List?)?.cast<String>() ?? [];
    final compByDay = (data['completion_by_day'] as Map?)?.cast<String, dynamic>() ?? {};
    final durAccuracy =
        (data['duration_accuracy'] as Map?)?.cast<String, String>() ?? {};

    return RefreshIndicator(
      onRefresh: () async {},
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Model status card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        modelWarm ? Icons.psychology : Icons.psychology_outlined,
                        color: modelWarm
                            ? Theme.of(context).colorScheme.primary
                            : Colors.grey,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        modelWarm ? 'AI model active' : 'AI model warming up',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text('$dataPoints activity log(s) · $banditUpdates bandit update(s)'),
                  if (!modelWarm) ...[
                    const SizedBox(height: 8),
                    LinearProgressIndicator(value: banditUpdates / 5),
                    const SizedBox(height: 4),
                    Text(
                      'Complete ${5 - banditUpdates} more activities to activate personalisation',
                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ],
              ),
            ),
          ),

          const SizedBox(height: 12),

          // Summary
          if (summary.isNotEmpty)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Your productivity profile',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(summary),
                  ],
                ),
              ),
            ),

          const SizedBox(height: 12),

          // Peak hours
          if (peakHours.isNotEmpty)
            _SectionCard(
              title: 'Peak hours',
              icon: Icons.schedule,
              child: Wrap(
                spacing: 8,
                children: peakHours
                    .map((h) => Chip(label: Text(h)))
                    .toList(),
              ),
            ),

          const SizedBox(height: 12),

          // Completion by day of week
          if (compByDay.isNotEmpty)
            _SectionCard(
              title: 'Completion rate by day',
              icon: Icons.bar_chart,
              child: Column(
                children: compByDay.entries.map((e) {
                  final rate = (e.value as num).toDouble();
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 36,
                          child: Text(e.key,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600)),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: LinearProgressIndicator(
                            value: rate,
                            backgroundColor: Colors.grey.shade200,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text('${(rate * 100).round()}%'),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),

          const SizedBox(height: 12),

          // Duration accuracy
          if (durAccuracy.isNotEmpty)
            _SectionCard(
              title: 'Duration accuracy',
              icon: Icons.timer_outlined,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: durAccuracy.entries
                    .map((e) => Padding(
                          padding: const EdgeInsets.symmetric(vertical: 2),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${e.key[0].toUpperCase()}${e.key.substring(1)}: ',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600),
                              ),
                              Expanded(child: Text(e.value)),
                            ],
                          ),
                        ))
                    .toList(),
              ),
            ),
        ],
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.icon,
    required this.child,
  });

  final String title;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(title, style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}
