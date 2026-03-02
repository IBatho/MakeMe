import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/providers/auth_provider.dart';
import '../features/auth/screens/login_screen.dart';
import '../features/tasks/screens/task_list_screen.dart';
import '../features/schedule/screens/schedule_screen.dart';
import '../features/integrations/screens/integration_settings_screen.dart';
import '../features/integrations/screens/oauth_callback_screen.dart';
import '../features/activity/screens/activity_tracker_screen.dart';
import '../features/insights/screens/insights_screen.dart';
import '../widgets/scaffold_with_nav.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final authNotifier = ref.watch(authProvider.notifier);

  return GoRouter(
    initialLocation: '/schedule',
    redirect: (context, state) {
      final isLoggedIn = ref.read(authProvider).isLoggedIn;
      final isOnLogin = state.matchedLocation == '/login';

      if (!isLoggedIn && !isOnLogin) return '/login';
      if (isLoggedIn && isOnLogin) return '/schedule';
      return null;
    },
    refreshListenable: authNotifier,
    routes: [
      GoRoute(
        path: '/login',
        builder: (ctx, state) => const LoginScreen(),
      ),
      ShellRoute(
        builder: (ctx, state, child) => ScaffoldWithNav(child: child),
        routes: [
          GoRoute(
            path: '/schedule',
            builder: (ctx, state) => const ScheduleScreen(),
          ),
          GoRoute(
            path: '/tasks',
            builder: (ctx, state) => const TaskListScreen(),
          ),
          GoRoute(
            path: '/integrations',
            builder: (ctx, state) => const IntegrationSettingsScreen(),
          ),
          GoRoute(
            path: '/activity',
            builder: (ctx, state) => const ActivityTrackerScreen(),
          ),
          GoRoute(
            path: '/insights',
            builder: (ctx, state) => const InsightsScreen(),
          ),
        ],
      ),
      // Deep-link handler for OAuth callbacks: makeme://oauth/callback?success=true&provider=...
      GoRoute(
        path: '/oauth/callback',
        builder: (ctx, state) => OAuthCallbackScreen(
          success: state.uri.queryParameters['success'] == 'true',
          provider: state.uri.queryParameters['provider'] ?? '',
        ),
      ),
    ],
  );
});
