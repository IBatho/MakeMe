class User {
  final String id;
  final String email;
  final String timezone;
  final bool isActive;
  final Map<String, dynamic> preferences;

  const User({
    required this.id,
    required this.email,
    required this.timezone,
    required this.isActive,
    required this.preferences,
  });

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as String,
        email: json['email'] as String,
        timezone: json['timezone'] as String,
        isActive: json['is_active'] as bool,
        preferences: Map<String, dynamic>.from(json['preferences'] as Map),
      );
}
