/// Lightweight connectivity tracker.
///
/// Marks the app offline when network requests fail and back online when they
/// succeed. Providers use this service to decide whether to serve cached data.
library;

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class ConnectivityService extends StateNotifier<bool> {
  /// Initialises in the online state; the first failing request will correct this.
  ConnectivityService() : super(true);

  bool get isOnline => state;

  void markOnline() {
    if (!state) state = true;
  }

  void markOffline() {
    if (state) state = false;
  }

  /// Run [fn] and track connectivity based on the outcome.
  ///
  /// On success: marks online and returns the result.
  /// On network error: marks offline and rethrows.
  /// On non-network error (e.g. 4xx/5xx): marks online (server was reachable) and rethrows.
  Future<T> execute<T>(Future<T> Function() fn) async {
    try {
      final result = await fn();
      markOnline();
      return result;
    } on DioException catch (e) {
      if (_isNetworkError(e)) {
        markOffline();
      } else {
        markOnline();
      }
      rethrow;
    }
  }

  static bool _isNetworkError(DioException e) {
    return e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout ||
        e.type == DioExceptionType.sendTimeout ||
        e.type == DioExceptionType.connectionError;
  }
}

// ── Riverpod providers ────────────────────────────────────────────────────────

final connectivityServiceProvider =
    StateNotifierProvider<ConnectivityService, bool>(
  (ref) => ConnectivityService(),
);

/// `true` when the app has network connectivity.
final isOnlineProvider = Provider<bool>((ref) {
  return ref.watch(connectivityServiceProvider);
});
