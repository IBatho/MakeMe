class Task {
  final String id;
  final String userId;
  final String title;
  final String? description;
  final String priority; // need | want | like
  final int totalDurationMinutes;
  final int minBlockMinutes;
  final int maxBlockMinutes;
  final String? deadline;
  final double completionPercentage;
  final bool isComplete;
  final String source;
  final DateTime createdAt;
  final DateTime updatedAt;

  const Task({
    required this.id,
    required this.userId,
    required this.title,
    this.description,
    required this.priority,
    required this.totalDurationMinutes,
    required this.minBlockMinutes,
    required this.maxBlockMinutes,
    this.deadline,
    required this.completionPercentage,
    required this.isComplete,
    required this.source,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Task.fromJson(Map<String, dynamic> json) => Task(
        id: json['id'] as String,
        userId: json['user_id'] as String,
        title: json['title'] as String,
        description: json['description'] as String?,
        priority: json['priority'] as String,
        totalDurationMinutes: json['total_duration_minutes'] as int,
        minBlockMinutes: json['min_block_minutes'] as int,
        maxBlockMinutes: json['max_block_minutes'] as int,
        deadline: json['deadline'] as String?,
        completionPercentage: (json['completion_percentage'] as num).toDouble(),
        isComplete: json['is_complete'] as bool,
        source: json['source'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'user_id': userId,
        'title': title,
        'description': description,
        'priority': priority,
        'total_duration_minutes': totalDurationMinutes,
        'min_block_minutes': minBlockMinutes,
        'max_block_minutes': maxBlockMinutes,
        'deadline': deadline,
        'completion_percentage': completionPercentage,
        'is_complete': isComplete,
        'source': source,
      };
}
