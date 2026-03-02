import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';

/// Shows a star-rating dialog and submits the rating to the backend.
Future<void> showScheduleRatingDialog(
  BuildContext context,
  WidgetRef ref,
  String scheduleId,
) async {
  int? selectedRating;

  final confirmed = await showDialog<int>(
    context: context,
    builder: (ctx) => _RatingDialog(scheduleId: scheduleId),
  );

  if (confirmed != null && context.mounted) {
    try {
      final api = ref.read(apiClientProvider);
      await api.dio.post(
        '/schedules/$scheduleId/rate',
        data: {'rating': confirmed},
      );
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Thanks for your feedback!')),
        );
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not submit rating')),
        );
      }
    }
  }
}

class _RatingDialog extends StatefulWidget {
  const _RatingDialog({required this.scheduleId});
  final String scheduleId;

  @override
  State<_RatingDialog> createState() => _RatingDialogState();
}

class _RatingDialogState extends State<_RatingDialog> {
  int _rating = 0;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Rate this schedule'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('How well did this AI schedule work for you?'),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(5, (i) {
              final star = i + 1;
              return IconButton(
                icon: Icon(
                  star <= _rating ? Icons.star : Icons.star_border,
                  color: Colors.amber,
                  size: 36,
                ),
                onPressed: () => setState(() => _rating = star),
              );
            }),
          ),
          if (_rating > 0)
            Text(
              _ratingLabel(_rating),
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Skip'),
        ),
        FilledButton(
          onPressed: _rating > 0 ? () => Navigator.pop(context, _rating) : null,
          child: const Text('Submit'),
        ),
      ],
    );
  }

  String _ratingLabel(int r) => switch (r) {
        1 => 'Not helpful at all',
        2 => 'Needs improvement',
        3 => 'OK',
        4 => 'Good',
        5 => 'Perfect!',
        _ => '',
      };
}
