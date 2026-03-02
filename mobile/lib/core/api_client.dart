import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'constants.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

class ApiClient {
  late final Dio _dio;
  final _storage = const FlutterSecureStorage();

  ApiClient() {
    _dio = Dio(BaseOptions(
      baseUrl: ApiConstants.baseUrl,
      connectTimeout: ApiConstants.connectTimeout,
      receiveTimeout: ApiConstants.receiveTimeout,
      headers: {'Content-Type': 'application/json'},
    ));

    _dio.interceptors.add(_AuthInterceptor(_storage, _dio));
  }

  Dio get dio => _dio;
}

/// Attaches the access token to every request and handles 401 by refreshing.
class _AuthInterceptor extends Interceptor {
  final FlutterSecureStorage _storage;
  final Dio _dio;

  _AuthInterceptor(this._storage, this._dio);

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await _storage.read(key: StorageKeys.accessToken);
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode == 401) {
      final refreshToken = await _storage.read(key: StorageKeys.refreshToken);
      if (refreshToken != null) {
        try {
          final resp = await Dio().post(
            '${ApiConstants.baseUrl}/auth/refresh',
            data: {'refresh_token': refreshToken},
          );
          final newAccess = resp.data['access_token'] as String;
          final newRefresh = resp.data['refresh_token'] as String;
          await _storage.write(key: StorageKeys.accessToken, value: newAccess);
          await _storage.write(key: StorageKeys.refreshToken, value: newRefresh);

          // Retry original request with new token
          err.requestOptions.headers['Authorization'] = 'Bearer $newAccess';
          final retryResp = await _dio.fetch(err.requestOptions);
          return handler.resolve(retryResp);
        } catch (_) {
          // Refresh failed — clear tokens and let the router redirect to login
          await _storage.deleteAll();
        }
      }
    }
    handler.next(err);
  }
}
