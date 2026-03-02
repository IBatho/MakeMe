/// Dialog that presents two overlapping schedule events and asks the user
/// to choose which one to keep.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../models/event.dart';

/// Shows the [ConflictResolutionDialog] as a modal and returns the kept event,
/// or null if the user dismissed without choosing.
Future<Event?> showConflictResolutionDialog(
  BuildContext context, {
  required Event conflictA,
  required Event conflictB,
}) {
  return showDialog<Event>(
    context: context,
    barrierDismissible: false,
    builder: (_) => ConflictResolutionDialog(
      conflictA: conflictA,
      conflictB: conflictB,
    ),
  );
}

class ConflictResolutionDialog extends StatelessWidget {
  final Event conflictA;
  final Event conflictB;

  const ConflictResolutionDialog({
    super.key,
    required this.conflictA,
    required this.conflictB,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Schedule Conflict'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'These two events overlap. Choose which one to keep:',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            _EventCard(
              event: conflictA,
              onKeep: () => Navigator.of(context).pop(conflictA),
            ),
            const SizedBox(height: 8),
            _EventCard(
              event: conflictB,
              onKeep: () => Navigator.of(context).pop(conflictB),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}

class _EventCard extends StatelessWidget {
  final Event event;
  final VoidCallback onKeep;

  const _EventCard({required this.event, required this.onKeep});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final timeFmt = DateFormat('HH:mm');
    final dateFmt = DateFormat('EEE d MMM');

    final sameDay = event.startTime.day == event.endTime.day &&
        event.startTime.month == event.endTime.month;

    final timeRange = sameDay
        ? '${dateFmt.format(event.startTime)}  '
            '${timeFmt.format(event.startTime)} – ${timeFmt.format(event.endTime)}'
        : '${dateFmt.format(event.startTime)} ${timeFmt.format(event.startTime)} – '
            '${dateFmt.format(event.endTime)} ${timeFmt.format(event.endTime)}';

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    event.title,
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w600),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(
                        Icons.access_time,
                        size: 14,
                        color: theme.colorScheme.secondary,
                      ),
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          timeRange,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.secondary,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  if (event.location != null && event.location!.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        Icon(
                          Icons.location_on_outlined,
                          size: 14,
                          color: theme.colorScheme.secondary,
                        ),
                        const SizedBox(width: 4),
                        Flexible(
                          child: Text(
                            event.location!,
                            style: theme.textTheme.bodySmall,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 12),
            FilledButton(
              onPressed: onKeep,
              child: const Text('Keep'),
            ),
          ],
        ),
      ),
    );
  }
}
