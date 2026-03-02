class Event {
  final String id;
  final String userId;
  final String? taskId;
  final String? scheduleId;
  final String title;
  final String? description;
  final String? location;
  final DateTime startTime;
  final DateTime endTime;
  final bool isAllDay;
  final String status;
  final bool isAgentCreated;
  final bool isLocked;
  final double completionPercentage;
  final String? provider;

  const Event({
    required this.id,
    required this.userId,
    this.taskId,
    this.scheduleId,
    required this.title,
    this.description,
    this.location,
    required this.startTime,
    required this.endTime,
    required this.isAllDay,
    required this.status,
    required this.isAgentCreated,
    required this.isLocked,
    required this.completionPercentage,
    this.provider,
  });

  factory Event.fromJson(Map<String, dynamic> json) => Event(
        id: json['id'] as String,
        userId: json['user_id'] as String,
        taskId: json['task_id'] as String?,
        scheduleId: json['schedule_id'] as String?,
        title: json['title'] as String,
        description: json['description'] as String?,
        location: json['location'] as String?,
        startTime: DateTime.parse(json['start_time'] as String),
        endTime: DateTime.parse(json['end_time'] as String),
        isAllDay: json['is_all_day'] as bool,
        status: json['status'] as String,
        isAgentCreated: json['is_agent_created'] as bool,
        isLocked: json['is_locked'] as bool,
        completionPercentage: (json['completion_percentage'] as num).toDouble(),
        provider: json['provider'] as String?,
      );
}
