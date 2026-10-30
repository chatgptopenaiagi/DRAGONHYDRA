import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'simulation.dart';
import 'public_sources.dart';
import 'connections.dart';
import 'server_connection.dart';

void main() => runApp(const DragonHydraApp());

const crimson = Color(0xffea4c61);
const electric = Color(0xff64c7ed);
const panel = Color(0xff1c2430);
const releaseSource = String.fromEnvironment('DRAGONHYDRA_SOURCE_SHA', defaultValue: 'unversioned development source');
const releaseVersion = String.fromEnvironment('DRAGONHYDRA_VERSION', defaultValue: 'development');

class DragonHydraApp extends StatelessWidget {
  const DragonHydraApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'DRAGONHYDRA',
    theme: ThemeData.dark(useMaterial3: true).copyWith(
      scaffoldBackgroundColor: const Color(0xff0d121a),
      colorScheme: const ColorScheme.dark(primary: crimson, secondary: electric, surface: panel),
      cardTheme: CardThemeData(color: panel, elevation: 0, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
      navigationBarTheme: const NavigationBarThemeData(backgroundColor: Color(0xff121923), indicatorColor: Color(0xff502d3b)),
    ),
    home: const Shell(),
  );
}

String display(dynamic value, [String fallback = 'Unavailable']) => value == null ? fallback : value.toString();
String percent(dynamic value) => value is num ? '${(value * 100).toStringAsFixed(1)}%' : 'Unavailable';
Map<String, dynamic> mapOf(dynamic value) => value is Map ? Map<String, dynamic>.from(value) : {};
List<dynamic> listOf(dynamic value) => value is List ? value : [];

class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  final names = ['Home', 'Football', 'Odds', 'Simulation lab', 'Cognitive memory', 'API Galaxy', 'Settings'];
  final icons = [Icons.dashboard_outlined, Icons.sports_soccer, Icons.stacked_line_chart, Icons.science_outlined,
    Icons.psychology_outlined, Icons.hub_outlined, Icons.settings_outlined];
  int selected = 0;
  late final Future<List<dynamic>> data = Future.wait([
    rootBundle.loadString('assets/football-snapshot.json').then(jsonDecode),
    rootBundle.loadString('assets/provider-manifest.json').then(jsonDecode),
  ]);
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(backgroundColor: const Color(0xff0d121a), titleSpacing: 0,
      title: Row(children: [const Icon(Icons.shield_moon_outlined, color: crimson), const SizedBox(width: 8),
        Expanded(child: Text(names[selected], style: const TextStyle(fontWeight: FontWeight.w700, letterSpacing: .2))) ])),
    drawer: Drawer(child: SafeArea(child: Column(children: [
      const Padding(padding: EdgeInsets.all(24), child: Row(children: [Icon(Icons.shield_moon, color: crimson, size: 36), SizedBox(width: 12),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('DRAGONHYDRA', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 20)), Text('GENESIS-3 Android alpha', style: TextStyle(color: electric))])])),
      Expanded(child: ListView.builder(itemCount: names.length, itemBuilder: (context, i) => ListTile(
        leading: Icon(icons[i], color: selected == i ? crimson : null), title: Text(names[i]), selected: selected == i,
        onTap: () { setState(() => selected = i); Navigator.pop(context); }))),
    ]))),
    body: FutureBuilder<List<dynamic>>(future: data, builder: (context, snap) {
      if (snap.hasError) return Center(child: Text('Offline data unavailable: ${snap.error}'));
      if (!snap.hasData) return const Center(child: CircularProgressIndicator());
      final snapshot = mapOf(snap.data![0]);
      final registry = mapOf(snap.data![1]);
      final pages = <Widget>[
        HomePage(snapshot: snapshot, onNavigate: (i) => setState(() => selected = i)),
        FootballPage(snapshot: snapshot), OddsPage(snapshot: snapshot), const LabPage(),
        MemoryPage(snapshot: snapshot), GalaxyPage(registry: registry), const SettingsPage(),
      ];
      return pages[selected];
    }),
    bottomNavigationBar: NavigationBar(selectedIndex: [0,1,2,3,5].contains(selected) ? [0,1,2,3,5].indexOf(selected) : 0,
      onDestinationSelected: (i) => setState(() => selected = [0,1,2,3,5][i]),
      destinations: const [NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
        NavigationDestination(icon: Icon(Icons.sports_soccer), label: 'Football'),
        NavigationDestination(icon: Icon(Icons.stacked_line_chart), label: 'Odds'),
        NavigationDestination(icon: Icon(Icons.science_outlined), label: 'Lab'),
        NavigationDestination(icon: Icon(Icons.hub_outlined), label: 'Galaxy')]),
  );
}

class Content extends StatelessWidget {
  const Content({super.key, required this.children});
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.fromLTRB(18, 8, 18, 30), children: children);
}
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Card(margin: const EdgeInsets.only(bottom: 14), child: Padding(padding: const EdgeInsets.all(18), child: child));
}
class SectionTitle extends StatelessWidget {
  const SectionTitle(this.title, {super.key, this.caption});
  final String title;
  final String? caption;
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.only(top: 12, bottom: 10), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(title, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
    if (caption != null) Padding(padding: const EdgeInsets.only(top: 3), child: Text(caption!, style: const TextStyle(color: Colors.white60, fontSize: 12)))
  ]));
}
Widget label(String s, {Color color = electric}) => Text(s.toUpperCase(), style: TextStyle(color: color, fontSize: 11, letterSpacing: 1.2, fontWeight: FontWeight.w700));
Widget line(String a, String b) => Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [Expanded(child: Text(a, style: const TextStyle(color: Colors.white70))), const SizedBox(width: 12), Flexible(child: Text(b, textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w600)))]));

class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.snapshot, required this.onNavigate});
  final Map<String, dynamic> snapshot;
  final ValueChanged<int> onNavigate;
  @override
  Widget build(BuildContext context) {
    final forecast = mapOf(snapshot['forecast']);
    final metadata = mapOf(snapshot['metadata']);
    return Content(children: [
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        label('Offline research companion'), const SizedBox(height: 10),
        const Text('Intelligence,\nin your pocket.', style: TextStyle(fontSize: 29, height: 1.12, fontWeight: FontWeight.w800)),
        const SizedBox(height: 12), const Text('Explore an archived football forecast, market prices and conditional simulations.', style: TextStyle(color: Colors.white70, height: 1.4)),
        const SizedBox(height: 16), FilledButton.icon(onPressed: () => onNavigate(1), icon: const Icon(Icons.arrow_forward), label: const Text('Explore forecast')),
        TextButton.icon(onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ServerConnectionPage())), icon: const Icon(Icons.dns_outlined), label: const Text('Connect to DRAGONHYDRA server'))
      ])),
      const SectionTitle('At a glance', caption: 'Bundled snapshot • no account required'),
      Panel(child: Column(children: [line('Data mode', 'Offline / archived'), line('Sports', 'Football'),
        line('Forecast', '${display(forecast['home'])} vs ${display(forecast['away'])}'),
        line('Model', 'Four statistical models'), line('Snapshot generated', display(metadata['generated_at_utc']))])),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [label('Research alerts', color: crimson), const SizedBox(height: 8),
        const Text('Historical odds have no verified quote times. Operational outcomes and synchronized current quotes are unavailable.', style: TextStyle(height: 1.4)),
        TextButton(onPressed: () => onNavigate(4), child: const Text('Review memory & gaps'))])),
    ]);
  }
}

class FootballPage extends StatelessWidget {
  const FootballPage({super.key, required this.snapshot});
  final Map<String, dynamic> snapshot;
  @override
  Widget build(BuildContext context) {
    final f = mapOf(snapshot['forecast']), p = mapOf(f['probabilities']), goals = mapOf(f['expected_goals']);
    final fixtures = listOf(snapshot['fixtures']);
    return Content(children: [
      const SectionTitle('Football intelligence', caption: 'Archived model output • not a live prediction'),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        label(display(f['competition'], 'Football')), const SizedBox(height: 10),
        Text('${display(f['home'])}  vs  ${display(f['away'])}', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
        const SizedBox(height: 5), Text(display(f['event_date']), style: const TextStyle(color: Colors.white60)),
        const Divider(height: 28),
        Row(children: ['home','draw','away'].map((key) => Expanded(child: Column(children: [
          Text(percent(p[key]), style: const TextStyle(fontSize: 22, color: electric, fontWeight: FontWeight.w700)),
          Text(key.toUpperCase(), style: const TextStyle(color: Colors.white60, fontSize: 10, letterSpacing: 1))]))).toList()),
        const SizedBox(height: 18), line('Expected goals', '${display(goals['home'])} / ${display(goals['away'])}'),
        line('Method', display(f['model_version'], 'Statistical ensemble')),
        line('Data cutoff', display(f['data_cutoff'])),
        line('Decision cutoff', display(f['decision_cutoff'], 'Not retained')),
        const SizedBox(height: 8), const Text('Uncalibrated estimates. Fixture date and historical data do not establish live availability.', style: TextStyle(color: Colors.white60, fontSize: 12))
      ])),
      const SectionTitle('Most likely scorelines'),
      Panel(child: Column(children: listOf(f['scorelines']).take(5).map((v) { final s = mapOf(v); return line('${display(s['home'])} – ${display(s['away'])}', percent(s['probability'])); }).toList())),
      SectionTitle('Historical fixtures', caption: '${fixtures.length} selected fixtures'),
      ...fixtures.take(15).map((v) { final row = mapOf(v); return Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${display(row['home'])}  ${display(row['home_goals'], '–')} : ${display(row['away_goals'], '–')}  ${display(row['away'])}', style: const TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 5), Text('${display(row['event_date'])}  •  ${display(row['competition'])}', style: const TextStyle(color: Colors.white60, fontSize: 12))])); }),
    ]);
  }
}

class OddsPage extends StatelessWidget {
  const OddsPage({super.key, required this.snapshot});
  final Map<String, dynamic> snapshot;
  @override
  Widget build(BuildContext context) {
    final odds = listOf(snapshot['archived_odds']);
    final groups = <String, Map<String, double>>{};
    for (final item in odds) {
      final row = mapOf(item);
      final price = double.tryParse(display(row['odds_decimal'], ''));
      if (price == null || !price.isFinite || price <= 1) continue;
      final key = '${display(row['provider_label'])} • ${display(row['phase'])}';
      groups.putIfAbsent(key, () => {})[display(row['outcome'])] = price;
    }
    return Content(children: [const SectionTitle('Odds intelligence', caption: 'Archived source labels • not current quotes'),
      const Panel(child: Text('Liverpool vs Bournemouth, 15 August 2025 — a different fixture from the model forecast. Source-recorded and closing-labelled prices are retrospective. Quote times, provider independence and fixture-to-model mapping are not verified.')),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [label('Inverse-price sum minus one'), const SizedBox(height: 7),
        ...groups.entries.map((g) { final x = g.value; final complete = ['home','draw','away'].every(x.containsKey);
          return line(g.key, complete ? percent((1/x['home']!) + (1/x['draw']!) + (1/x['away']!) - 1) : 'Incomplete'); }),
        const SizedBox(height: 6), const Text('Sum of inverse decimal odds minus one. Formal overround is unavailable: scope and timing are unverified.', style: TextStyle(color: Colors.white60, fontSize: 12)),
      ])),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [label('Source-labelled price changes'), const SizedBox(height: 7),
        ...['B365', 'PS'].expand((provider) => ['home', 'draw', 'away'].map((outcome) {
          final before = groups['$provider • source_recorded']?[outcome];
          final after = groups['$provider • source_close']?[outcome];
          return line('$provider $outcome', before == null || after == null ? 'Unavailable' : '${before.toStringAsFixed(2)} → ${after.toStringAsFixed(2)}  (${(after-before).toStringAsFixed(2)})');
        })),
        const SizedBox(height: 6), const Text('Closing-labelled minus recorded price; elapsed time and true provider identity are unavailable.', style: TextStyle(color: Colors.white60, fontSize: 12)),
      ])),
      ...odds.map((v) { final row = mapOf(v); final price = double.tryParse(display(row['odds_decimal'], ''));
        return Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          label(display(row['provider_label'])), const SizedBox(height: 6),
          line('${display(row['outcome'])} • ${display(row['phase'])}', price == null ? 'Unavailable' : price.toStringAsFixed(2)),
          line('Raw implied probability', price == null || price <= 1 ? 'Unavailable' : percent(1 / price)),
          line('Evidence', display(row['evidence_id']))])); }),
      if (odds.isEmpty) const Panel(child: Text('No retained archived odds in this snapshot.')),
      const Panel(child: Text('Model-versus-market comparison and time-aligned provider divergence are unavailable without verified event, timing and settlement mappings.')),
    ]);
  }
}

class LabPage extends StatefulWidget {
  const LabPage({super.key});
  @override State<LabPage> createState() => _LabPageState();
}
class _LabPageState extends State<LabPage> {
  final fields = <String, String>{'Win probability': '.55', 'Decimal odds': '2.0', 'Starting bankroll': '1000', 'Stake fraction': '.02', 'Kelly multiplier': '.25', 'Maximum stake cap': '.05', 'Simulations': '500', 'Horizon': '100'};
  Scenario? scenario; Map<String,double>? output; String? error;
  void calculate() {
    try {
      final v = fields.values.map((x) => double.parse(x)).toList();
      if (v[6] != v[6].roundToDouble() || v[7] != v[7].roundToDouble()) throw const FormatException('Simulations and horizon must be integers.');
      final s = Scenario(probability: v[0], odds: v[1], bankroll: v[2], stakeFraction: v[3], kellyMultiplier: v[4], cap: v[5], trials: v[6].toInt(), horizon: v[7].toInt());
      final result = s.run(); setState(() { scenario = s; output = result; error = null; });
    } catch (_) { setState(() { error = 'Check inputs: probability and fractions 0–1, odds > 1, bankroll > 0, at most 2 million steps.'; output = null; }); }
  }
  @override Widget build(BuildContext context) => Content(children: [
    const SectionTitle('Simulation lab', caption: 'Hypothetical binary outcomes • independent trials'),
    Panel(child: Column(children: [
      ...fields.keys.map((key) => Padding(padding: const EdgeInsets.only(bottom: 10), child: TextFormField(initialValue: fields[key],
        keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: key, border: const OutlineInputBorder()),
        onChanged: (v) => fields[key] = v))),
      SizedBox(width: double.infinity, child: FilledButton(onPressed: calculate, child: const Text('Run scenario'))),
      if (error != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text(error!, style: const TextStyle(color: crimson))),
    ])),
    if (output != null) Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      label('Research scenario'), const SizedBox(height: 8),
      line('Raw implied probability', percent(scenario!.implied)), line('Expected return per unit', percent(scenario!.expectedReturn)),
      line('Full Kelly fraction', percent(scenario!.fullKelly)), line('Fractional Kelly, capped', percent(scenario!.fractionalKelly)),
      line('Simulated mean final bankroll', output!['mean_final']!.toStringAsFixed(2)),
      line('Mean maximum drawdown', percent(output!['mean_max_drawdown'])), line('Ending below 1% of initial', percent(output!['below_one_percent'])),
      const SizedBox(height: 8), const Text('Simulation policy: constant stake fraction of current bankroll, independent of the Kelly calculation. Assumed probability; no prediction or guaranteed return.', style: TextStyle(color: Colors.white60, fontSize: 12)),
    ])),
  ]);
}

class MemoryPage extends StatelessWidget {
  const MemoryPage({super.key, required this.snapshot});
  final Map<String,dynamic> snapshot;
  @override Widget build(BuildContext context) {
    final f = mapOf(snapshot['forecast']), e = mapOf(snapshot['evaluation']);
    final models = listOf(snapshot['model_records']);
    final predictions = listOf(snapshot['prediction_records']);
    final alerts = listOf(snapshot['research_alerts']);
    return Content(children: [const SectionTitle('Cognitive memory', caption: 'Read-only checkpoint snapshot'),
      Panel(child: Column(children: [line('Model version', display(f['model_version'])), line('Forecast record', display(f['prediction_record_id'], 'See bundled evidence')),
        line('Bundled model records', '${models.length}'), line('Bundled prediction records', '${predictions.length}'),
        line('Evaluation mode', display(e['mode'], 'Present-knowledge holdout')), line('Scored matches', display(e['sample_size'])),
        line('Brier score', display(e['brier'])), line('Log loss', display(e['log_loss'])), line('Accuracy', percent(e['accuracy']))])),
      const SectionTitle('Open research gaps'),
      const Panel(child: Text('Collect time-stamped comparable quotes; resolve fixture and settlement mappings; attach eligible later outcomes; verify the SQLite receipt visibility boundary.')),
      Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: alerts.map((a) => Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text('• ${display(a)}'))).toList())),
      Panel(child: ExpansionTile(title: const Text('Prediction evidence IDs'), children: predictions.map((p) => ListTile(title: SelectableText(display(mapOf(p)['record_id']), style: const TextStyle(fontSize: 11)))).toList())),
      const Panel(child: Text('This mobile snapshot is read-only. It does not train a model, mutate desktop memory, or prove a historical operational replay.')),
    ]);
  }
}

class GalaxyPage extends StatefulWidget {
  const GalaxyPage({super.key, required this.registry}); final Map<String,dynamic> registry;
  @override State<GalaxyPage> createState() => _GalaxyPageState();
}
class _GalaxyPageState extends State<GalaxyPage> {
  final Map<String,String> results = {};
  final Map<String,ConnectionResult> connectionResults = {};
  final vault = const CredentialVault();
  Future<void> configure(String id) async {
    final controller = TextEditingController();
    final key = await showDialog<String>(context: context, builder: (dialogContext) => AlertDialog(
      title: const Text('Save provider API key'),
      content: TextField(controller: controller, obscureText: true, autocorrect: false,
        enableSuggestions: false, decoration: const InputDecoration(labelText: 'API key')),
      actions: [TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(dialogContext, controller.text), child: const Text('Save'))],
    ));
    if (key != null && key.trim().isNotEmpty) {
      try { await vault.save(id, key); if (mounted) setState(() { connectionResults.remove(id); results[id] = 'Credential stored securely. Test to verify authentication.'; }); }
      catch (_) { if (mounted) setState(() => results[id] = 'Secure storage unavailable.'); }
    }
    controller.dispose();
  }
  Future<void> removeKey(String id) async {
    try { await vault.remove(id); if (mounted) setState(() { results[id] = 'Credential removed.'; connectionResults.remove(id); }); }
    catch (_) { if (mounted) setState(() => results[id] = 'Could not remove credential.'); }
  }
  Future<void> testKey(String id) async {
    setState(() => results[id] = 'Testing authenticated connection…');
    final r = await ProviderConnectionTester(vault).test(id);
    if (mounted) setState(() { connectionResults[id] = r; results[id] = '${r.message}${r.quota == null ? '' : ' • ${r.quota}'}${r.checkedAt == null ? '' : ' • ${r.checkedAt!.toIso8601String()}'}'; });
  }
  Future<void> fetch(String id) async {
    setState(() => results[id] = 'Contacting public source…');
    try {
      final result = await fetchPublicSource(id);
      if (!mounted) return;
      setState(() => results[id] = 'Public response received • ${result.recordCount} records • ${result.retrievedAtUtc.toIso8601String()} • SHA-256 ${result.contentSha256}');
    } catch (_) {
      if (!mounted) return;
      setState(() => results[id] = 'Unavailable: public request or validation failed.');
    }
  }
  @override Widget build(BuildContext context) {
    final providers = listOf(widget.registry['providers']);
    return Content(children: [const SectionTitle('DRAGONHYDRA API Galaxy', caption: 'Provider catalog • connectivity is verified only by an actual response'),
      ...providers.map((entry) { final p = mapOf(entry); final name = display(p['provider']);
        final id = display(p['id'], '');
        final key = id == 'statsbomb_open_data' || id == 'openfootball' ? id : null;
        final credentialSupported = id == 'football_data_org' || id == 'api_football' || id == 'the_odds_api';
        return Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)), const SizedBox(height: 6),
          label(connectionResults[id]?.state ?? display(p['connection_state'], 'NOT CONFIGURED'), color: Colors.amberAccent),
          const SizedBox(height: 8), Text('Authentication: ${display(p['authentication'])}', style: const TextStyle(color: Colors.white70)),
          if (id == 'the_odds_api') const Text('This provider requires the key in the request URL; provider or intermediary logs may retain it.', style: TextStyle(color: Colors.white70)),
          Text('Sports: ${listOf(p['supported_sports']).join(', ')}', style: const TextStyle(color: Colors.white70)),
          Text('Data: ${listOf(p['supported_data']).join(', ')}', style: const TextStyle(color: Colors.white70)),
          Wrap(children: [
            if (p['official_website'] is String) TextButton(onPressed: () => vault.openUrl(p['official_website']), child: const Text('Website')),
            if (p['documentation'] is String) TextButton(onPressed: () => vault.openUrl(p['documentation']), child: const Text('Documentation')),
            if (p['registration'] is String) TextButton(onPressed: () => vault.openUrl(p['registration']), child: const Text('Register')),
          ]),
          line('Last synchronization', 'Not available'),
          if (credentialSupported) Wrap(children: [
            TextButton(onPressed: () => configure(id), child: const Text('Save key')),
            TextButton(onPressed: () => testKey(id), child: const Text('Test connection')),
            TextButton(onPressed: () => removeKey(id), child: const Text('Remove key')),
          ]),
          if (credentialSupported && results[id] != null) SelectableText(results[id]!, style: const TextStyle(fontSize: 12, color: Colors.white70)),
          if (key != null) ...[TextButton.icon(onPressed: () => fetch(key), icon: const Icon(Icons.cloud_download_outlined), label: const Text('Test public source')),
            if (results[key] != null) SelectableText('${results[key]}\nFetched in memory; not synchronized to local storage.', style: const TextStyle(fontSize: 12, color: Colors.white70))],
        ])); }),
      if (providers.isEmpty) const Panel(child: Text('Provider catalog unavailable.')),
    ]);
  }
}

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});
  @override Widget build(BuildContext context) => Content(children: [
    const SectionTitle('Settings & connections'),
    Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('DRAGONHYDRA SERVER', style: TextStyle(fontWeight: FontWeight.w700)),
      const Text('Browse the same canonical matches, teams and standings as desktop and Joomla.'),
      FilledButton(onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ServerConnectionPage())), child: const Text('Configure server address')),
    ])),
    Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Text('OPENAI INTELLIGENCE', style: TextStyle(fontWeight: FontWeight.w700)), const SizedBox(height: 8),
      const Text('Not connected. OpenAI Platform keys and Codex authentication are separate. A secure backend is required; no paid API request is made by this app.'),
      TextButton(onPressed: () => const CredentialVault().openUrl('https://platform.openai.com/api-keys'), child: const Text('OPEN OPENAI API DASHBOARD'))])),
    const Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('GOOGLE SIGN-IN', style: TextStyle(fontWeight: FontWeight.w700)), SizedBox(height: 8),
      Text('Not configured or verified. OAuth client registration and device testing are required.')])),
    const Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('LOCAL STORAGE', style: TextStyle(fontWeight: FontWeight.w700)), SizedBox(height: 8),
      Text('The bundled sample is read-only. This alpha does not synchronize with the desktop database or run Python models on the phone.')])),
    const Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('ABOUT', style: TextStyle(fontWeight: FontWeight.w700)), SizedBox(height: 8),
      Text('DRAGONHYDRA GENESIS-3 Android alpha\nOffline snapshot and research simulator'),
      Text('Build version: $releaseVersion'), SelectableText('Source: $releaseSource')]))
  ]);
}
