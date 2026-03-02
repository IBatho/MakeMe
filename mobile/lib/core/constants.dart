class ApiConstants {
  // Change to your machine's IP when running on a physical device.
  // For Android emulator use 10.0.2.2; for iOS simulator use 127.0.0.1.
  static const String baseUrl = 'http://10.0.2.2:8000/api/v1';
  static const Duration connectTimeout = Duration(seconds: 10);
  static const Duration receiveTimeout = Duration(seconds: 30);
}

class StorageKeys {
  static const String accessToken = 'access_token';
  static const String refreshToken = 'refresh_token';
}
