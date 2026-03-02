/// This screen handles the `makeme://oauth/callback` deep link.
///
/// When the backend finishes the OAuth flow it redirects the user's browser to:
///   makeme://oauth/callback?success=true&provider=google_calendar
///
/// go_router picks up the deep link and routes here.  The screen refreshes
/// the integrations list and shows a confirmation, then navigates away.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/integrations_provider.dart';

class OAuthCallbackScreen extends ConsumerStatefulWidget {
  const OAuthCallbackScreen({
    super.key,
    required this.success,
    required this.provider,
  });

  final bool success;
  final String provider;

  @override
  ConsumerState<OAuthCallbackScreen> createState() => _OAuthCallbackScreenState();
}

class _OAuthCallbackScreenState extends ConsumerState<OAuthCallbackScreen> {
  @override
  void initState() {
    super.initState();
    _handleCallback();
  }

  Future<void> _handleCallback() async {
    if (widget.success) {
      // Refresh integrations list so the new connection shows up
      await ref.read(integrationsProvider.notifier).fetch();
    }
    // Navigate to integrations screen after a short delay
    await Future.delayed(const Duration(seconds: 2));
    if (mounted) context.go('/integrations');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              widget.success ? Icons.check_circle_outline : Icons.error_outline,
              size: 72,
              color: widget.success
                  ? Theme.of(context).colorScheme.primary
                  : Theme.of(context).colorScheme.error,
            ),
            const SizedBox(height: 16),
            Text(
              widget.success
                  ? '${_providerName(widget.provider)} connected!'
                  : 'Connection failed',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            if (widget.success)
              Text(
                'Redirecting to integrations…',
                style: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.copyWith(color: Colors.grey),
              ),
          ],
        ),
      ),
    );
  }

  String _providerName(String provider) =>
      provider.replaceAll('_', ' ').split(' ').map((w) {
        if (w.isEmpty) return w;
        return w[0].toUpperCase() + w.substring(1);
      }).join(' ');
}
