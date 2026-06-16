import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('Welcome screen smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const SynapseApp(initialRoute: '/welcome'));
    await tester.pumpAndSettle();

    expect(find.text('SYNAPSE'), findsOneWidget);
    expect(find.text('Get started'), findsOneWidget);
  });
}
