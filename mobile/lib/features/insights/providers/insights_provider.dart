import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';

final insightsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  final api = ref.watch(apiClientProvider);
  final resp = await api.dio.get('/insights');
  return Map<String, dynamic>.from(resp.data as Map);
});
