import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';

import '../../../core/api_client.dart';

// ── Model ─────────────────────────────────────────────────────────────────────

class Integration {
  final String id;
  final String provider;
  final String providerType;
  final bool isEnabled;
  final String? displayName;
  final String? lastSyncedAt;
  final String? lastSyncStatus;
  final String? lastSyncError;
  final Map<String, dynamic>? config;

  const Integration({
    required this.id,
    required this.provider,
    required this.providerType,
    required this.isEnabled,
    this.displayName,
    this.lastSyncedAt,
    this.lastSyncStatus,
    this.lastSyncError,
    this.config,
  });

  factory Integration.fromJson(Map<String, dynamic> json) => Integration(
        id: json['id'] as String,
        provider: json['provider'] as String,
        providerType: json['provider_type'] as String,
        isEnabled: json['is_enabled'] as bool,
        displayName: json['display_name'] as String?,
        lastSyncedAt: json['last_synced_at'] as String?,
        lastSyncStatus: json['last_sync_status'] as String?,
        lastSyncError: json['last_sync_error'] as String?,
        config: json['config'] as Map<String, dynamic>?,
      );

  String get displayLabel =>
      displayName ?? provider.replaceAll('_', ' ').split(' ').map((w) {
        if (w.isEmpty) return w;
        return w[0].toUpperCase() + w.substring(1);
      }).join(' ');
}

// ── Notifier ──────────────────────────────────────────────────────────────────

class IntegrationsNotifier extends StateNotifier<AsyncValue<List<Integration>>> {
  final ApiClient _api;

  IntegrationsNotifier(this._api) : super(const AsyncValue.loading()) {
    fetch();
  }

  Future<void> fetch() async {
    state = const AsyncValue.loading();
    try {
      final resp = await _api.dio.get('/integrations');
      final list = (resp.data as List)
          .map((e) => Integration.fromJson(e as Map<String, dynamic>))
          .toList();
      state = AsyncValue.data(list);
    } on DioException catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  /// Connect Notion using an internal integration token.
  Future<Integration?> connectNotion({
    required String apiToken,
    required String databaseId,
    String? displayName,
  }) async {
    try {
      final resp = await _api.dio.post('/integrations', data: {
        'provider': 'notion',
        'api_token': apiToken,
        'display_name': displayName,
        'config': {'database_id': databaseId},
      });
      final integration = Integration.fromJson(resp.data as Map<String, dynamic>);
      state.whenData((list) {
        state = AsyncValue.data([...list, integration]);
      });
      return integration;
    } catch (_) {
      return null;
    }
  }

  /// Returns the OAuth URL to open in the browser for the given provider.
  Future<String?> getOAuthUrl(String provider) async {
    try {
      final resp = await _api.dio.get('/integrations/oauth/$provider/url');
      return resp.data['url'] as String?;
    } catch (_) {
      return null;
    }
  }

  /// Trigger a manual sync for an integration.
  Future<Map<String, dynamic>?> sync(String integrationId) async {
    try {
      final resp = await _api.dio.post('/integrations/$integrationId/sync');
      return resp.data as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  Future<void> toggle(String integrationId, {required bool enabled}) async {
    try {
      await _api.dio.patch('/integrations/$integrationId', data: {'is_enabled': enabled});
      state.whenData((list) {
        state = AsyncValue.data(
          list.map((i) {
            if (i.id == integrationId) {
              return Integration(
                id: i.id,
                provider: i.provider,
                providerType: i.providerType,
                isEnabled: enabled,
                displayName: i.displayName,
                lastSyncedAt: i.lastSyncedAt,
                lastSyncStatus: i.lastSyncStatus,
                config: i.config,
              );
            }
            return i;
          }).toList(),
        );
      });
    } catch (_) {}
  }

  Future<void> disconnect(String integrationId) async {
    try {
      await _api.dio.delete('/integrations/$integrationId');
      state.whenData((list) {
        state = AsyncValue.data(list.where((i) => i.id != integrationId).toList());
      });
    } catch (_) {}
  }
}

final integrationsProvider =
    StateNotifierProvider<IntegrationsNotifier, AsyncValue<List<Integration>>>((ref) {
  final api = ref.watch(apiClientProvider);
  return IntegrationsNotifier(api);
});
