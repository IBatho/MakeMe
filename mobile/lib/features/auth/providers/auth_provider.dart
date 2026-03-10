import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:dio/dio.dart';

import '../../../core/api_client.dart';
import '../../../core/constants.dart';
import '../../../models/user.dart';

class AuthState {
  final String? token;
  final User? user;
  final bool isLoading;
  final String? error;

  const AuthState({
    this.token,
    this.user,
    this.isLoading = false,
    this.error,
  });

  bool get isLoggedIn => token != null;

  AuthState copyWith({
    String? token,
    User? user,
    bool? isLoading,
    String? error,
    bool clearToken = false,
    bool clearUser = false,
    bool clearError = false,
  }) =>
      AuthState(
        token: clearToken ? null : (token ?? this.token),
        user: clearUser ? null : (user ?? this.user),
        isLoading: isLoading ?? this.isLoading,
        error: clearError ? null : (error ?? this.error),
      );
}

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiClient _api;
  final FlutterSecureStorage _storage;

  AuthNotifier(this._api, this._storage) : super(const AuthState()) {
    _tryRestoreSession();
  }

  Future<void> _tryRestoreSession() async {
    final token = await _storage.read(key: StorageKeys.accessToken);
    if (token != null) {
      state = state.copyWith(token: token, isLoading: true);
      try {
        final resp = await _api.dio.get('/users/me');
        final user = User.fromJson(resp.data as Map<String, dynamic>);
        state = state.copyWith(user: user, isLoading: false);
      } catch (_) {
        await _storage.deleteAll();
        state = const AuthState();
      }
    }
  }

  Future<bool> login(String email, String password) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final resp = await _api.dio.post(
        '/auth/login',
        data: {'email': email, 'password': password},
      );
      await _saveTokens(resp.data);
      await _fetchMe();
        return true;
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.response?.data?['detail'] as String? ?? 'Login failed',
      );
        return false;
    }
  }

  Future<bool> register(String email, String password, String timezone) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final resp = await _api.dio.post(
        '/auth/register',
        data: {'email': email, 'password': password, 'timezone': timezone},
      );
      await _saveTokens(resp.data);
      await _fetchMe();
        return true;
    } on DioException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.response?.data?['detail'] as String? ?? 'Registration failed',
      );
        return false;
    }
  }

  Future<void> logout() async {
    await _api.dio.post('/auth/logout').catchError((_) => Response(requestOptions: RequestOptions(path: '/auth/logout')));
    await _storage.deleteAll();
    state = const AuthState();
  }

  Future<void> _saveTokens(Map<String, dynamic> data) async {
    await _storage.write(
        key: StorageKeys.accessToken, value: data['access_token'] as String);
    await _storage.write(
        key: StorageKeys.refreshToken, value: data['refresh_token'] as String);
    state = state.copyWith(token: data['access_token'] as String);
  }

  Future<void> _fetchMe() async {
    final resp = await _api.dio.get('/users/me');
    final user = User.fromJson(resp.data as Map<String, dynamic>);
    state = state.copyWith(user: user, isLoading: false);
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final api = ref.watch(apiClientProvider);
  return AuthNotifier(api, const FlutterSecureStorage());
});
