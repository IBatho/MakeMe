import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';
import '../../../models/event.dart';

// ── Schedule generation state ─────────────────────────────────────────────────

enum GenerateStatus { idle, thinking, success, error }

class GenerateState {
  final GenerateStatus status;
  final String? errorMessage;
  final int? blocksPlaced;
  final int? tasksScheduled;

  const GenerateState({
    this.status = GenerateStatus.idle,
    this.errorMessage,
    this.blocksPlaced,
    this.tasksScheduled,
  });

  GenerateState copyWith({
    GenerateStatus? status,
    String? errorMessage,
    int? blocksPlaced,
    int? tasksScheduled,
  }) =>
      GenerateState(
        status: status ?? this.status,
        errorMessage: errorMessage ?? this.errorMessage,
        blocksPlaced: blocksPlaced ?? this.blocksPlaced,
        tasksScheduled: tasksScheduled ?? this.tasksScheduled,
      );
}

class ScheduleNotifier extends StateNotifier<GenerateState> {
  ScheduleNotifier(this._api) : super(const GenerateState());

  final ApiClient _api;

  Future<bool> generateSchedule({
    required DateTime periodStart,
    required DateTime periodEnd,
  }) async {
    state = state.copyWith(status: GenerateStatus.thinking);

    try {
      final resp = await _api.dio.post(
        '/schedules/generate',
        data: {
          'period_start': _formatDate(periodStart),
          'period_end': _formatDate(periodEnd),
        },
      );
      final data = resp.data as Map<String, dynamic>;
      state = state.copyWith(
        status: GenerateStatus.success,
        blocksPlaced: data['blocks_placed'] as int? ?? 0,
        tasksScheduled: data['tasks_scheduled'] as int? ?? 0,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        status: GenerateStatus.error,
        errorMessage: e.toString(),
      );
      return false;
    }
  }

  void reset() => state = const GenerateState();

  static String _formatDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}

final scheduleProvider = StateNotifierProvider<ScheduleNotifier, GenerateState>(
  (ref) => ScheduleNotifier(ref.watch(apiClientProvider)),
);

// ── Events for a specific date ────────────────────────────────────────────────

final eventsForDateProvider =
    FutureProvider.family<List<Event>, DateTime>((ref, date) async {
  final api = ref.watch(apiClientProvider);
  final start = DateTime(date.year, date.month, date.day);
  final end = start.add(const Duration(days: 1));

  final resp = await api.dio.get('/events', queryParameters: {
    'start': start.toIso8601String(),
    'end': end.toIso8601String(),
  });
  return (resp.data as List)
      .map((e) => Event.fromJson(e as Map<String, dynamic>))
      .toList();
});

// ── Lock / unlock an event ────────────────────────────────────────────────────

Future<void> toggleEventLock(ApiClient api, String eventId, bool locked) async {
  final endpoint = locked ? '/events/$eventId/lock' : '/events/$eventId/unlock';
  await api.dio.post(endpoint);
}
