import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:table_calendar/table_calendar.dart';

import '../../../models/event.dart';
import '../../../services/websocket_service.dart';
import '../providers/schedule_provider.dart';

class ScheduleScreen extends ConsumerStatefulWidget {
  const ScheduleScreen({super.key});

  @override
  ConsumerState<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends ConsumerState<ScheduleScreen> {
  DateTime _selectedDate = DateTime.now();
  bool _calendarExpanded = false;

  @override
  Widget build(BuildContext context) {
    final eventsAsync = ref.watch(eventsForDateProvider(_selectedDate));
    final genState = ref.watch(scheduleProvider);
    final isThinking = genState.status == GenerateStatus.thinking;

    // Listen for WebSocket agent.thinking messages
    ref.listen(wsMessageStreamProvider, (_, next) {
      next.whenData((msg) {
        if (msg['type'] == 'schedule.updated') {
          // Invalidate the events cache so the list refreshes
          ref.invalidate(eventsForDateProvider(_selectedDate));
        }
      });
    });

    return Scaffold(
      appBar: AppBar(
        title: Text(DateFormat('E d MMM yyyy').format(_selectedDate)),
        leading: IconButton(
          icon: const Icon(Icons.chevron_left),
          onPressed: () => setState(
              () => _selectedDate = _selectedDate.subtract(const Duration(days: 1))),
        ),
        actions: [
          IconButton(
            icon: Icon(_calendarExpanded ? Icons.expand_less : Icons.date_range_outlined),
            tooltip: 'Calendar',
            onPressed: () => setState(() => _calendarExpanded = !_calendarExpanded),
          ),
          IconButton(
            icon: const Icon(Icons.today),
            tooltip: 'Today',
            onPressed: () => setState(() => _selectedDate = DateTime.now()),
          ),
          IconButton(
            icon: const Icon(Icons.chevron_right),
            onPressed: () => setState(
                () => _selectedDate = _selectedDate.add(const Duration(days: 1))),
          ),
        ],
      ),
      body: Column(
        children: [
          // Mini calendar (toggleable)
          if (_calendarExpanded)
            TableCalendar(
              firstDay: DateTime.utc(2020, 1, 1),
              lastDay: DateTime.utc(2030, 12, 31),
              focusedDay: _selectedDate,
              selectedDayPredicate: (day) => isSameDay(day, _selectedDate),
              calendarFormat: CalendarFormat.week,
              headerStyle: const HeaderStyle(formatButtonVisible: false),
              onDaySelected: (selected, focused) {
                setState(() => _selectedDate = selected);
              },
            ),

          // Agent thinking banner
          if (isThinking)
            Container(
              color: Theme.of(context).colorScheme.primaryContainer,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                children: [
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Theme.of(context).colorScheme.onPrimaryContainer,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    'AI is building your schedule…',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onPrimaryContainer,
                    ),
                  ),
                ],
              ),
            ),

          // Events list
          Expanded(
            child: eventsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('Error loading schedule: $e')),
              data: (events) {
                if (events.isEmpty) {
                  return const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.event_available, size: 64, color: Colors.grey),
                        SizedBox(height: 12),
                        Text('Nothing scheduled', style: TextStyle(color: Colors.grey)),
                        SizedBox(height: 4),
                        Text(
                          'Tap ✦ to generate an AI schedule',
                          style: TextStyle(color: Colors.grey, fontSize: 12),
                        ),
                      ],
                    ),
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async =>
                      ref.invalidate(eventsForDateProvider(_selectedDate)),
                  child: ListView.separated(
                    padding: const EdgeInsets.all(12),
                    itemCount: events.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 4),
                    itemBuilder: (ctx, i) => _EventCard(
                      event: events[i],
                      onLockToggle: () {
                        ref.invalidate(eventsForDateProvider(_selectedDate));
                      },
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: isThinking ? null : () => _showGenerateDialog(context),
        icon: isThinking
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
              )
            : const Icon(Icons.auto_awesome),
        label: const Text('Generate'),
      ),
    );
  }

  Future<void> _showGenerateDialog(BuildContext context) async {
    final now = DateTime.now();
    // Default: generate for the next 7 days starting from today
    DateTime periodStart = DateTime(now.year, now.month, now.day);
    DateTime periodEnd = periodStart.add(const Duration(days: 6));

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Generate AI schedule'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('The AI will place your tasks into free time slots.'),
            const SizedBox(height: 8),
            Text(
              'Period: ${DateFormat('d MMM').format(periodStart)} – '
              '${DateFormat('d MMM yyyy').format(periodEnd)}',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 4),
            const Text(
              'Existing locked events and external calendar events are preserved.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Generate'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    final success = await ref.read(scheduleProvider.notifier).generateSchedule(
          periodStart: periodStart,
          periodEnd: periodEnd,
        );

    if (!mounted) return;

    if (success) {
      final state = ref.read(scheduleProvider);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Schedule created: ${state.blocksPlaced} blocks '
            'across ${state.tasksScheduled} task(s)',
          ),
        ),
      );
      ref.invalidate(eventsForDateProvider(_selectedDate));
      ref.read(scheduleProvider.notifier).reset();
    } else {
      final err = ref.read(scheduleProvider).errorMessage ?? 'Unknown error';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to generate schedule: $err')),
      );
      ref.read(scheduleProvider.notifier).reset();
    }
  }
}

// ── Event card with lock/unlock on long press ─────────────────────────────────

class _EventCard extends ConsumerWidget {
  const _EventCard({required this.event, required this.onLockToggle});

  final Event event;
  final VoidCallback onLockToggle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final timeFormat = DateFormat('HH:mm');

    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onLongPress: event.isAgentCreated ? () => _toggleLock(context, ref) : null,
        child: ListTile(
          leading: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                timeFormat.format(event.startTime),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              Text(
                timeFormat.format(event.endTime),
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: cs.onSurfaceVariant),
              ),
            ],
          ),
          title: Text(event.title),
          subtitle: event.location != null ? Text(event.location!) : null,
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (event.isAgentCreated)
                Tooltip(
                  message: 'AI-scheduled  (long-press to lock/unlock)',
                  child: Icon(Icons.smart_toy_outlined, size: 18, color: cs.primary),
                ),
              if (event.isLocked)
                Tooltip(
                  message: 'Locked',
                  child: Icon(Icons.lock, size: 18, color: cs.onSurfaceVariant),
                )
              else if (event.isAgentCreated)
                Tooltip(
                  message: 'Unlocked — AI may reschedule',
                  child: Icon(Icons.lock_open_outlined, size: 18, color: cs.outlineVariant),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _toggleLock(BuildContext context, WidgetRef ref) async {
    final api = ref.read(apiClientProvider);
    final newLocked = !event.isLocked;

    try {
      await toggleEventLock(api, event.id, newLocked);
      onLockToggle();
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(newLocked ? 'Event locked' : 'Event unlocked'),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to update lock')),
        );
      }
    }
  }
}
