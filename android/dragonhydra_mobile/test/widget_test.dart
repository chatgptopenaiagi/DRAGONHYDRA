import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:dragonhydra_mobile/main.dart';
import 'package:dragonhydra_mobile/simulation.dart';

void main() {
  test('scenario computes conditional return and capped Kelly', () {
    final s = Scenario(probability: .55, odds: 2, bankroll: 1000,
      stakeFraction: .02, kellyMultiplier: .25, cap: .05, trials: 50, horizon: 20);
    expect(s.implied, .5);
    expect(s.expectedReturn, closeTo(.1, 1e-12));
    expect(s.fullKelly, closeTo(.1, 1e-12));
    expect(s.fractionalKelly, closeTo(.025, 1e-12));
    expect(s.run(), s.run());
  });
  test('scenario rejects invalid inputs', () {
    expect(() => Scenario(probability: double.nan, odds: 2, bankroll: 100,
      stakeFraction: .1, kellyMultiplier: .25, cap: .1, trials: 1, horizon: 1), throwsFormatException);
    expect(() => Scenario(probability: .5, odds: 1, bankroll: 100,
      stakeFraction: .1, kellyMultiplier: .25, cap: .1, trials: 1, horizon: 1), throwsFormatException);
    expect(() => Scenario(probability: 1, odds: 1e300, bankroll: 100,
      stakeFraction: 1, kellyMultiplier: .25, cap: .1, trials: 1, horizon: 3).run(), throwsFormatException);
  });
  testWidgets('offline navigation shows snapshot and calculator', (tester) async {
    await tester.runAsync(() async {
      await rootBundle.loadString('assets/football-snapshot.json');
      await rootBundle.loadString('assets/provider-manifest.json');
    });
    await tester.pumpWidget(const DragonHydraApp());
    await tester.runAsync(() => Future<void>.delayed(const Duration(seconds: 1)));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('Intelligence,\nin your pocket.'), findsOneWidget);
    await tester.tap(find.text('Football').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('AFC Bournemouth'), findsWidgets);
    await tester.tap(find.text('Lab').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Run scenario'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Run scenario'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Expected return per unit'));
    expect(find.text('Expected return per unit'), findsOneWidget);
  });
}
