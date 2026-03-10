import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:makeme/main.dart';

void main() {
  testWidgets('App smoke test — renders without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: MakeMeApp()));
    await tester.pump();
    // App should render the router-controlled top level
    expect(tester.takeException(), isNull);
  });
}
