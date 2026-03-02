/// Background location service.
///
/// Sends GPS pings to POST /location/ping every [_pingIntervalSeconds] seconds
/// while tracking is active.  Designed to work with flutter_background_service
/// for continued operation when the app is backgrounded.

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

import '../core/api_client.dart';

const int _pingIntervalSeconds = 30;

final locationServiceProvider = Provider<LocationService>((ref) {
  final service = LocationService(ref.watch(apiClientProvider));
  ref.onDispose(service.stop);
  return service;
});

class LocationService {
  LocationService(this._api);

  final ApiClient _api;
  Timer? _timer;
  bool _active = false;
  String? _currentEventId;

  bool get isTracking => _active;

  /// Request permissions and start pinging.
  Future<bool> start({String? eventId}) async {
    final permission = await _requestPermission();
    if (!permission) return false;

    _currentEventId = eventId;
    _active = true;
    _timer = Timer.periodic(
      const Duration(seconds: _pingIntervalSeconds),
      (_) => _sendPing(),
    );
    await _sendPing(); // immediate first ping
    return true;
  }

  void stop() {
    _active = false;
    _timer?.cancel();
    _timer = null;
    _currentEventId = null;
  }

  Future<bool> _requestPermission() async {
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    return permission == LocationPermission.always ||
        permission == LocationPermission.whileInUse;
  }

  Future<void> _sendPing() async {
    if (!_active) return;
    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
      );
      await _api.dio.post('/location/ping', data: {
        'latitude': pos.latitude,
        'longitude': pos.longitude,
        'accuracy_meters': pos.accuracy,
        if (_currentEventId != null) 'event_id': _currentEventId,
        'context': _currentEventId != null ? 'pre_event' : 'free',
      });
    } catch (_) {
      // Silently ignore — offline or permission denied
    }
  }
}
