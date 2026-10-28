import 'dart:math';

/// Conditional binary outcomes with a constant fraction of the current bankroll.
class Scenario {
  Scenario({required this.probability, required this.odds, required this.bankroll,
    required this.stakeFraction, required this.kellyMultiplier, required this.cap,
    required this.trials, required this.horizon, this.seed = 7}) {
    if (![probability, odds, bankroll, stakeFraction, kellyMultiplier, cap].every((x) => x.isFinite) ||
        probability < 0 || probability > 1 || odds <= 1 || bankroll <= 0 ||
        stakeFraction < 0 || stakeFraction > 1 || kellyMultiplier < 0 ||
        kellyMultiplier > 1 || cap < 0 || cap > 1 || trials < 1 ||
        horizon < 1 || trials * horizon > 2000000) {
      throw const FormatException('Enter finite values: probability and fractions 0–1; odds > 1; bankroll > 0; at most 2 million simulated steps.');
    }
  }
  final double probability, odds, bankroll, stakeFraction, kellyMultiplier, cap;
  final int trials, horizon, seed;
  double get implied => 1 / odds;
  double get expectedReturn => probability * odds - 1;
  double get fullKelly => max(0, min(1, (probability * odds - 1) / (odds - 1)));
  double get fractionalKelly => min(cap, fullKelly * kellyMultiplier);

  Map<String, double> run() {
    final random = Random(seed);
    var sum = 0.0, maxDrawdownSum = 0.0, depleted = 0;
    for (var i = 0; i < trials; i++) {
      var cash = bankroll, peak = cash, maxDrawdown = 0.0;
      for (var j = 0; j < horizon; j++) {
        final stake = cash * stakeFraction;
        cash += random.nextDouble() < probability ? stake * (odds - 1) : -stake;
        if (!cash.isFinite) throw const FormatException('Simulation overflow; reduce odds or horizon.');
        peak = max(peak, cash);
        maxDrawdown = max(maxDrawdown, peak > 0 ? (peak - cash) / peak : 0);
      }
      if (cash < bankroll * .01) depleted++;
      sum += cash;
      if (!sum.isFinite) throw const FormatException('Simulation overflow; reduce odds or horizon.');
      maxDrawdownSum += maxDrawdown;
    }
    return {'mean_final': sum / trials, 'mean_max_drawdown': maxDrawdownSum / trials,
      'below_one_percent': depleted / trials};
  }
}
