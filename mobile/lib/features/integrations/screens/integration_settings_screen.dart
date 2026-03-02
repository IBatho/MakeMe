import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/integrations_provider.dart';

class IntegrationSettingsScreen extends ConsumerWidget {
  const IntegrationSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final integrationsAsync = ref.watch(integrationsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Integrations'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.read(integrationsProvider.notifier).fetch(),
          ),
        ],
      ),
      body: integrationsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (integrations) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _SectionHeader(title: 'Connected'),
            if (integrations.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text(
                  'No integrations connected yet.',
                  style: TextStyle(color: Colors.grey),
                ),
              )
            else
              ...integrations.map(
                (i) => _IntegrationTile(integration: i),
              ),
            const SizedBox(height: 24),
            _SectionHeader(title: 'Available'),
            _AvailableProviderTile(
              icon: Icons.task_alt,
              name: 'Notion',
              subtitle: 'Import tasks from a Notion database',
              onConnect: () => _showNotionConnectDialog(context, ref),
            ),
            _AvailableProviderTile(
              icon: Icons.calendar_month,
              name: 'Google Calendar',
              subtitle: 'Sync events with your Google Calendar',
              onConnect: () => _launchOAuth(context, ref, 'google_calendar'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _launchOAuth(
      BuildContext context, WidgetRef ref, String provider) async {
    final url = await ref.read(integrationsProvider.notifier).getOAuthUrl(provider);
    if (url == null) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Could not get OAuth URL')));
      }
      return;
    }
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _showNotionConnectDialog(BuildContext context, WidgetRef ref) async {
    final tokenCtrl = TextEditingController();
    final dbIdCtrl = TextEditingController();
    final nameCtrl = TextEditingController();

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Connect Notion'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Create an internal integration at notion.so/my-integrations, '
                'then paste the secret below.',
                style: TextStyle(fontSize: 13),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: nameCtrl,
                decoration: const InputDecoration(labelText: 'Display name (optional)'),
              ),
              TextField(
                controller: tokenCtrl,
                decoration: const InputDecoration(labelText: 'Integration secret'),
                obscureText: true,
              ),
              TextField(
                controller: dbIdCtrl,
                decoration: const InputDecoration(labelText: 'Database ID'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () async {
              Navigator.pop(ctx);
              final result = await ref.read(integrationsProvider.notifier).connectNotion(
                    apiToken: tokenCtrl.text.trim(),
                    databaseId: dbIdCtrl.text.trim(),
                    displayName: nameCtrl.text.trim().isEmpty ? null : nameCtrl.text.trim(),
                  );
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      result != null ? 'Notion connected!' : 'Connection failed',
                    ),
                  ),
                );
              }
            },
            child: const Text('Connect'),
          ),
        ],
      ),
    );
  }
}

// ── widgets ───────────────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title});
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: Theme.of(context).colorScheme.primary,
              letterSpacing: 1.2,
            ),
      ),
    );
  }
}

class _IntegrationTile extends ConsumerWidget {
  const _IntegrationTile({required this.integration});
  final Integration integration;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusColor = switch (integration.lastSyncStatus) {
      'success' => Colors.green,
      'error' => Colors.red,
      'partial' => Colors.orange,
      _ => Colors.grey,
    };

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(_providerIcon(integration.provider)),
        title: Text(integration.displayLabel),
        subtitle: integration.lastSyncedAt != null
            ? Row(
                children: [
                  Icon(Icons.circle, size: 8, color: statusColor),
                  const SizedBox(width: 4),
                  Text(
                    'Last synced ${_formatRelative(integration.lastSyncedAt!)}',
                    style: const TextStyle(fontSize: 12),
                  ),
                ],
              )
            : const Text('Never synced', style: TextStyle(fontSize: 12)),
        trailing: PopupMenuButton<_Action>(
          onSelected: (action) async {
            switch (action) {
              case _Action.sync:
                final result =
                    await ref.read(integrationsProvider.notifier).sync(integration.id);
                if (context.mounted) {
                  final msg = result != null
                      ? 'Synced: ${result['tasks_upserted']} tasks, ${result['events_upserted']} events'
                      : 'Sync failed';
                  ScaffoldMessenger.of(context)
                      .showSnackBar(SnackBar(content: Text(msg)));
                }
              case _Action.toggle:
                await ref.read(integrationsProvider.notifier).toggle(
                      integration.id,
                      enabled: !integration.isEnabled,
                    );
              case _Action.disconnect:
                final confirmed = await showDialog<bool>(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    title: const Text('Disconnect?'),
                    content: Text(
                        'Remove ${integration.displayLabel}? Synced tasks will not be deleted.'),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(ctx, false),
                          child: const Text('Cancel')),
                      FilledButton(
                          onPressed: () => Navigator.pop(ctx, true),
                          child: const Text('Disconnect')),
                    ],
                  ),
                );
                if (confirmed == true) {
                  await ref.read(integrationsProvider.notifier).disconnect(integration.id);
                }
            }
          },
          itemBuilder: (_) => [
            PopupMenuItem(
              value: _Action.sync,
              child: const ListTile(
                leading: Icon(Icons.sync),
                title: Text('Sync now'),
                contentPadding: EdgeInsets.zero,
              ),
            ),
            PopupMenuItem(
              value: _Action.toggle,
              child: ListTile(
                leading: Icon(
                    integration.isEnabled ? Icons.pause : Icons.play_arrow),
                title: Text(integration.isEnabled ? 'Disable' : 'Enable'),
                contentPadding: EdgeInsets.zero,
              ),
            ),
            const PopupMenuItem(
              value: _Action.disconnect,
              child: ListTile(
                leading: Icon(Icons.link_off, color: Colors.red),
                title: Text('Disconnect', style: TextStyle(color: Colors.red)),
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ],
        ),
      ),
    );
  }

  IconData _providerIcon(String provider) {
    return switch (provider) {
      'notion' => Icons.article_outlined,
      'google_calendar' => Icons.calendar_month,
      'apple_caldav' => Icons.calendar_today,
      'microsoft_365' => Icons.work_outline,
      _ => Icons.extension_outlined,
    };
  }

  String _formatRelative(String isoString) {
    final dt = DateTime.tryParse(isoString);
    if (dt == null) return isoString;
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}

class _AvailableProviderTile extends StatelessWidget {
  const _AvailableProviderTile({
    required this.icon,
    required this.name,
    required this.subtitle,
    required this.onConnect,
  });

  final IconData icon;
  final String name;
  final String subtitle;
  final VoidCallback onConnect;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(icon),
        title: Text(name),
        subtitle: Text(subtitle, style: const TextStyle(fontSize: 12)),
        trailing: FilledButton.tonal(
          onPressed: onConnect,
          child: const Text('Connect'),
        ),
      ),
    );
  }
}

enum _Action { sync, toggle, disconnect }
