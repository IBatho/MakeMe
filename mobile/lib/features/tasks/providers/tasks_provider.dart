import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';

import '../../../core/api_client.dart';
import '../../../models/task.dart';

class TasksNotifier extends StateNotifier<AsyncValue<List<Task>>> {
  final ApiClient _api;

  TasksNotifier(this._api) : super(const AsyncValue.loading()) {
    fetchTasks();
  }

  Future<void> fetchTasks({String? priority, bool? isComplete}) async {
    state = const AsyncValue.loading();
    try {
      final queryParams = <String, dynamic>{};
      if (priority != null) queryParams['priority'] = priority;
      if (isComplete != null) queryParams['is_complete'] = isComplete;

      final resp = await _api.dio.get('/tasks', queryParameters: queryParams);
      final tasks = (resp.data as List)
          .map((e) => Task.fromJson(e as Map<String, dynamic>))
          .toList();
      state = AsyncValue.data(tasks);
    } on DioException catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  Future<Task?> createTask({
    required String title,
    required String priority,
    required int totalDurationMinutes,
    int minBlockMinutes = 30,
    int maxBlockMinutes = 120,
    String? description,
    String? deadline,
  }) async {
    try {
      final resp = await _api.dio.post('/tasks', data: {
        'title': title,
        'priority': priority,
        'total_duration_minutes': totalDurationMinutes,
        'min_block_minutes': minBlockMinutes,
        'max_block_minutes': maxBlockMinutes,
        if (description != null) 'description': description,
        if (deadline != null) 'deadline': deadline,
      });
      final task = Task.fromJson(resp.data as Map<String, dynamic>);
      state.whenData((tasks) {
        state = AsyncValue.data([task, ...tasks]);
      });
      return task;
    } catch (_) {
      return null;
    }
  }

  Future<void> completeTask(String taskId) async {
    await _api.dio.post('/tasks/$taskId/complete');
    fetchTasks();
  }

  Future<void> deleteTask(String taskId) async {
    await _api.dio.delete('/tasks/$taskId');
    state.whenData((tasks) {
      state = AsyncValue.data(tasks.where((t) => t.id != taskId).toList());
    });
  }
}

final tasksProvider =
    StateNotifierProvider<TasksNotifier, AsyncValue<List<Task>>>((ref) {
  final api = ref.watch(apiClientProvider);
  return TasksNotifier(api);
});
