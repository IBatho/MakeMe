import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/activity_provider.dart';
import '../../../services/location_service.dart';

class ActivityTrackerScreen extends ConsumerStatefulWidget {
  const ActivityTrackerScreen({super.key});

  @override
  ConsumerState<ActivityTrackerScreen> createState() => _ActivityTrackerScreenState();
}

class _ActivityTrackerScreenState extends ConsumerState<ActivityTrackerScreen> {
  final _notesCtrl = TextEditingController();
  double _sliderValue = 0.0;
  Timer? _elapsedTimer;
  Duration _elapsed = Duration.zero;
  DateTime? _startedAt;

  @override
  void dispose() {
    _notesCtrl.dispose();
    _elapsedTimer?.cancel();
    super.dispose();
  }

  void _startTimer() {
    _startedAt = DateTime.now();
    _elapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() {
          _elapsed = DateTime.now().difference(_startedAt!);
        });
      }
    });
  }

  void _stopTimer() {
    _elapsedTimer?.cancel();
    _elapsedTimer = null;
    _elapsed = Duration.zero;
    _startedAt = null;
  }

  String _formatElapsed(Duration d) {
    final h = d.inHours.toString().padLeft(2, '0');
    final m = (d.inMinutes % 60).toString().padLeft(2, '0');
    final s = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final tracking = ref.watch(activityProvider);
    final notifier = ref.read(activityProvider.notifier);

    // Start/stop the elapsed timer whenever tracking state changes.
    ref.listen<TrackingState>(activityProvider, (prev, next) {
      if (next.isTracking && !(prev?.isTracking ?? false)) {
        _startTimer();
      } else if (!next.isTracking && (prev?.isTracking ?? false)) {
        _stopTimer();
      }
    });

    return Scaffold(
      appBar: AppBar(title: const Text('Activity Tracker')),
      body: tracking.isTracking
          ? _buildActiveTracking(context, tracking, notifier)
          : _buildIdle(context, notifier),
    );
  }

  Widget _buildIdle(BuildContext context, ActivityNotifier notifier) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.play_circle_outline,
              size: 80,
              color: Theme.of(context).colorScheme.primary.withOpacity(0.5),
            ),
            const SizedBox(height: 24),
            const Text(
              'No active session',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w500),
            ),
            const SizedBox(height: 8),
            const Text(
              'Start tracking from the schedule or task view.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey),
            ),
            const SizedBox(height: 32),
            // Quick-start demo (for testing without schedule)
            OutlinedButton.icon(
              icon: const Icon(Icons.add),
              label: const Text('Quick start (demo)'),
              onPressed: () => _showQuickStartDialog(context, notifier),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActiveTracking(
    BuildContext context,
    TrackingState tracking,
    ActivityNotifier notifier,
  ) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Event title
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Icon(Icons.timer, size: 40, color: Theme.of(context).colorScheme.primary),
                  const SizedBox(height: 8),
                  Text(
                    tracking.activeEventTitle ?? 'Active session',
                    style: Theme.of(context).textTheme.titleLarge,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _formatElapsed(_elapsed),
                    style: Theme.of(context).textTheme.displaySmall?.copyWith(
                          fontFeatures: [const FontFeature.tabularFigures()],
                          color: Theme.of(context).colorScheme.primary,
                        ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Completion slider
          Text(
            'Progress: ${(_sliderValue * 100).round()}%',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          Slider(
            value: _sliderValue,
            onChanged: (v) => setState(() => _sliderValue = v),
            onChangeEnd: (v) => notifier.updateProgress(v),
            divisions: 20,
            label: '${(_sliderValue * 100).round()}%',
          ),

          const SizedBox(height: 16),

          // Notes
          TextField(
            controller: _notesCtrl,
            decoration: const InputDecoration(
              labelText: 'Notes (optional)',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.notes),
            ),
            maxLines: 2,
          ),

          const Spacer(),

          // Stop button
          FilledButton.icon(
            onPressed: () => _confirmStop(context, notifier),
            icon: const Icon(Icons.stop_circle),
            label: const Text('Stop session'),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
              padding: const EdgeInsets.symmetric(vertical: 16),
            ),
          ),

          const SizedBox(height: 12),

          // Complete button
          FilledButton.icon(
            onPressed: () => _stopSession(context, notifier, 1.0),
            icon: const Icon(Icons.check_circle),
            label: const Text('Mark complete'),
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmStop(BuildContext context, ActivityNotifier notifier) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Stop session?'),
        content: const Text('Current progress will be saved.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Stop')),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await _stopSession(context, notifier, _sliderValue);
    }
  }

  Future<void> _stopSession(
    BuildContext context,
    ActivityNotifier notifier,
    double pct,
  ) async {
    final success = await notifier.stopTracking(
      completionPercentage: pct,
      notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
    );
    _stopTimer();
    ref.read(locationServiceProvider).stop();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(success ? 'Session saved!' : 'Failed to save session')),
      );
    }
  }

  Future<void> _showQuickStartDialog(BuildContext context, ActivityNotifier notifier) async {
    // For demo/testing: requires the user to have at least one event
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Start tracking from an event in the Schedule tab')),
    );
  }
}

// Allows starting a session from the schedule screen by passing event details
class StartActivityScreen extends ConsumerStatefulWidget {
  const StartActivityScreen({
    super.key,
    required this.eventId,
    required this.eventTitle,
  });

  final String eventId;
  final String eventTitle;

  @override
  ConsumerState<StartActivityScreen> createState() => _StartActivityScreenState();
}

class _StartActivityScreenState extends ConsumerState<StartActivityScreen> {
  bool _starting = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.eventTitle)),
      body: Center(
        child: _starting
            ? const CircularProgressIndicator()
            : Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.play_circle_outline,
                      size: 72,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Ready to start?',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      widget.eventTitle,
                      style: Theme.of(context).textTheme.bodyLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 32),
                    FilledButton.icon(
                      onPressed: () => _start(context),
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('Start tracking'),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                      ),
                    ),
                  ],
                ),
              ),
      ),
    );
  }

  Future<void> _start(BuildContext context) async {
    setState(() => _starting = true);
    final success = await ref.read(activityProvider.notifier).startTracking(
          eventId: widget.eventId,
          eventTitle: widget.eventTitle,
        );
    // Also start location pings
    if (success) {
      await ref.read(locationServiceProvider).start(eventId: widget.eventId);
    }
    if (mounted) {
      if (success) {
        // Navigate to the tracker screen
        Navigator.of(context).pushReplacementNamed('/activity');
      } else {
        setState(() => _starting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to start session')),
        );
      }
    }
  }
}

// Small helper widget — a button shown on event cards
class TrackActivityButton extends ConsumerWidget {
  const TrackActivityButton({
    super.key,
    required this.eventId,
    required this.eventTitle,
  });

  final String eventId;
  final String eventTitle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tracking = ref.watch(activityProvider);
    final isThisEvent = tracking.isTracking && tracking.activeEventId == eventId;

    return isThisEvent
        ? FilledButton.icon(
            onPressed: () => Navigator.pushNamed(context, '/activity'),
            icon: const Icon(Icons.timer, size: 18),
            label: const Text('In progress'),
          )
        : OutlinedButton.icon(
            onPressed: tracking.isTracking
                ? null // another event is active
                : () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => StartActivityScreen(
                          eventId: eventId,
                          eventTitle: eventTitle,
                        ),
                      ),
                    ),
            icon: const Icon(Icons.play_arrow, size: 18),
            label: const Text('Start'),
          );
  }
}

