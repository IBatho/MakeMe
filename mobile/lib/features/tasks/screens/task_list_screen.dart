import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/tasks_provider.dart';
import '../../../models/task.dart';

class TaskListScreen extends ConsumerWidget {
  const TaskListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tasksAsync = ref.watch(tasksProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Tasks'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.read(tasksProvider.notifier).fetchTasks(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _showAddTaskSheet(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Add task'),
      ),
      body: tasksAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (tasks) {
          if (tasks.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.task_alt, size: 64, color: Colors.grey),
                  SizedBox(height: 12),
                  Text('No tasks yet', style: TextStyle(color: Colors.grey)),
                ],
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(12),
            itemCount: tasks.length,
            separatorBuilder: (_, __) => const SizedBox(height: 4),
            itemBuilder: (ctx, i) => _TaskCard(task: tasks[i]),
          );
        },
      ),
    );
  }

  void _showAddTaskSheet(BuildContext context, WidgetRef ref) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _AddTaskSheet(ref: ref),
    );
  }
}

class _TaskCard extends ConsumerWidget {
  const _TaskCard({required this.task});
  final Task task;

  Color _priorityColor(String priority, ColorScheme cs) => switch (priority) {
        'need' => cs.error,
        'want' => cs.primary,
        _ => cs.tertiary,
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final durationHours = task.totalDurationMinutes ~/ 60;
    final durationMins = task.totalDurationMinutes % 60;

    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: _priorityColor(task.priority, cs).withOpacity(0.15),
          child: Text(
            task.priority[0].toUpperCase(),
            style: TextStyle(
              color: _priorityColor(task.priority, cs),
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        title: Text(
          task.title,
          style: TextStyle(
            decoration: task.isComplete ? TextDecoration.lineThrough : null,
          ),
        ),
        subtitle: Text(
          durationHours > 0
              ? '${durationHours}h ${durationMins}min'
              : '${durationMins}min',
        ),
        trailing: PopupMenuButton<String>(
          onSelected: (action) async {
            if (action == 'complete') {
              await ref.read(tasksProvider.notifier).completeTask(task.id);
            } else if (action == 'delete') {
              await ref.read(tasksProvider.notifier).deleteTask(task.id);
            }
          },
          itemBuilder: (_) => [
            if (!task.isComplete)
              const PopupMenuItem(
                  value: 'complete', child: Text('Mark complete')),
            const PopupMenuItem(
                value: 'delete', child: Text('Delete')),
          ],
        ),
      ),
    );
  }
}

class _AddTaskSheet extends StatefulWidget {
  const _AddTaskSheet({required this.ref});
  final WidgetRef ref;

  @override
  State<_AddTaskSheet> createState() => _AddTaskSheetState();
}

class _AddTaskSheetState extends State<_AddTaskSheet> {
  final _formKey = GlobalKey<FormState>();
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _durationCtrl = TextEditingController(text: '60');
  String _priority = 'want';
  bool _isSubmitting = false;

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    _durationCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isSubmitting = true);
    await widget.ref.read(tasksProvider.notifier).createTask(
          title: _titleCtrl.text.trim(),
          priority: _priority,
          totalDurationMinutes: int.parse(_durationCtrl.text),
          description: _descCtrl.text.isEmpty ? null : _descCtrl.text.trim(),
        );
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 16,
        right: 16,
        top: 24,
      ),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('New Task',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            TextFormField(
              controller: _titleCtrl,
              decoration: const InputDecoration(
                  labelText: 'Title', border: OutlineInputBorder()),
              validator: (v) =>
                  v != null && v.isNotEmpty ? null : 'Title required',
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _descCtrl,
              decoration: const InputDecoration(
                  labelText: 'Description (optional)',
                  border: OutlineInputBorder()),
              maxLines: 2,
            ),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                child: TextFormField(
                  controller: _durationCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Duration (min)',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) {
                    final n = int.tryParse(v ?? '');
                    return (n != null && n > 0) ? null : 'Enter minutes > 0';
                  },
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: _priority,
                  decoration: const InputDecoration(
                      labelText: 'Priority',
                      border: OutlineInputBorder()),
                  items: const [
                    DropdownMenuItem(value: 'need', child: Text('Need')),
                    DropdownMenuItem(value: 'want', child: Text('Want')),
                    DropdownMenuItem(value: 'like', child: Text('Like')),
                  ],
                  onChanged: (v) => setState(() => _priority = v!),
                ),
              ),
            ]),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const SizedBox(
                      height: 20, width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Add Task'),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}
