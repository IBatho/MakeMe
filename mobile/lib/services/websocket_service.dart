/// WebSocket client service.
///
/// Connects to ws(s)://<host>/ws?token=<jwt> and exposes a stream of
/// incoming messages.  Automatically reconnects with exponential back-off
/// when the connection drops.

import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/constants.dart';

/// All messages received from the server are broadcast on this stream.
final wsMessageStreamProvider = StreamProvider<Map<String, dynamic>>((ref) {
  final service = ref.watch(webSocketServiceProvider);
  return service.messageStream;
});

final webSocketServiceProvider = Provider<WebSocketService>((ref) {
  final service = WebSocketService();
  ref.onDispose(service.dispose);
  return service;
});

class WebSocketService {
  final _storage = const FlutterSecureStorage();
  final _controller = StreamController<Map<String, dynamic>>.broadcast();

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  bool _disposed = false;
  int _retryDelay = 2; // seconds

  Stream<Map<String, dynamic>> get messageStream => _controller.stream;

  /// Call once after the user is authenticated.
  Future<void> connect() async {
    if (_disposed) return;
    final token = await _storage.read(key: StorageKeys.accessToken);
    if (token == null) return;

    final wsBase = ApiConstants.baseUrl
        .replaceFirst('http://', 'ws://')
        .replaceFirst('https://', 'wss://');

    // Strip the /api/v1 prefix — WebSocket is mounted at /ws
    final host = wsBase.replaceAll('/api/v1', '');
    final uri = Uri.parse('$host/ws?token=$token');

    try {
      _channel = WebSocketChannel.connect(uri);
      _sub = _channel!.stream.listen(
        (raw) {
          final data = jsonDecode(raw as String) as Map<String, dynamic>;
          _controller.add(data);
          _retryDelay = 2; // reset on successful message
        },
        onError: (_) => _scheduleReconnect(),
        onDone: _scheduleReconnect,
        cancelOnError: false,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void disconnect() {
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
    _sub = null;
  }

  void send(Map<String, dynamic> message) {
    _channel?.sink.add(jsonEncode(message));
  }

  void ping() => send({'type': 'ping'});

  void _scheduleReconnect() {
    if (_disposed) return;
    disconnect();
    Future.delayed(Duration(seconds: _retryDelay), () {
      if (!_disposed) {
        _retryDelay = (_retryDelay * 2).clamp(2, 60);
        connect();
      }
    });
  }

  void dispose() {
    _disposed = true;
    disconnect();
    _controller.close();
  }
}
