import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';

import '../../../core/api_client.dart';

// ── Model ─────────────────────────────────────────────────────────────────────

class ActivityLog {
  final String id;
  final String? eventId;
  final String? taskId;
  final String loggedAt;
  final String action;
  final double? completionPercentage;
  final String? notes;
  final String? deviceId;

  const ActivityLog({
    required this.id,
    this.eventId,
    this.taskId,
    required this.loggedAt,
    required this.action,
    this.completionPercentage,
    this.notes,
    this.deviceId,
  });

  factory ActivityLog.fromJson(Map<String, dynamic> json) => ActivityLog(
        id: json['id'] as String,
        eventId: json['event_id'] as String?,
        taskId: json['task_id'] as String?,
        loggedAt: json['logged_at'] as String,
        action: json['action'] as String,
        completionPercentage: (json['completion_percentage'] as num?)?.toDouble(),
        notes: json['notes'] as String?,
        deviceId: json['device_id'] as String?,
      );
}

// ── Tracking state ────────────────────────────────────────────────────────────

class TrackingState {
  final bool isTracking;
  final String? activeEventId;
  final String? activeEventTitle;
  final double completionPercentage;

  const TrackingState({
    this.isTracking = false,
    this.activeEventId,
    this.activeEventTitle,
    this.completionPercentage = 0.0,
  });

  TrackingState copyWith({
    bool? isTracking,
    String? activeEventId,
    String? activeEventTitle,
    double? completionPercentage,
  }) =>
      TrackingState(
        isTracking: isTracking ?? this.isTracking,
        activeEventId: activeEventId ?? this.activeEventId,
        activeEventTitle: activeEventTitle ?? this.activeEventTitle,
        completionPercentage: completionPercentage ?? this.completionPercentage,
      );
}

// ── Notifier ──────────────────────────────────────────────────────────────────

class ActivityNotifier extends StateNotifier<TrackingState> {
  final ApiClient _api;

  ActivityNotifier(this._api) : super(const TrackingState());

  Future<bool> startTracking({
    required String eventId,
    required String eventTitle,
    String? deviceId,
  }) async {
    try {
      await _api.dio.post('/activity/start', data: {
        'event_id': eventId,
        if (deviceId != null) 'device_id': deviceId,
      });
      state = state.copyWith(
        isTracking: true,
        activeEventId: eventId,
        activeEventTitle: eventTitle,
        completionPercentage: 0.0,
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> updateProgress(double percentage) async {
    if (!state.isTracking || state.activeEventId == null) return false;
    try {
      await _api.dio.post('/activity/update', data: {
        'event_id': state.activeEventId,
        'completion_percentage': percentage,
      });
      state = state.copyWith(completionPercentage: percentage);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> stopTracking({
    required double completionPercentage,
    String? notes,
  }) async {
    if (!state.isTracking || state.activeEventId == null) return false;
    try {
      await _api.dio.post('/activity/stop', data: {
        'event_id': state.activeEventId,
        'completion_percentage': completionPercentage,
        if (notes != null && notes.isNotEmpty) 'notes': notes,
      });
      state = const TrackingState();
      return true;
    } catch (_) {
      return false;
    }
  }
}

final activityProvider =
    StateNotifierProvider<ActivityNotifier, TrackingState>((ref) {
  return ActivityNotifier(ref.watch(apiClientProvider));
});

// ── Recent logs ───────────────────────────────────────────────────────────────

final activityLogsProvider = FutureProvider.family<List<ActivityLog>, String?>(
  (ref, eventId) async {
    final api = ref.watch(apiClientProvider);
    final params = eventId != null ? {'event_id': eventId} : null;
    final resp = await api.dio.get('/activity', queryParameters: params);
    return (resp.data as List)
        .map((e) => ActivityLog.fromJson(e as Map<String, dynamic>))
        .toList();
  },
);
