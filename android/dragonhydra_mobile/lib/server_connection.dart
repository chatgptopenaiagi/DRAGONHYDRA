import 'package:flutter/material.dart';

import 'connections.dart';
import 'server_api.dart';

Map<String, dynamic> _map(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};
String _text(dynamic value) =>
    value == null ? 'Not supplied' : value.toString();

class ServerConnectionPage extends StatefulWidget {
  const ServerConnectionPage({super.key, this.transport});
  final ServerTransport? transport;
  @override
  State<ServerConnectionPage> createState() => _ServerConnectionPageState();
}

class _ServerConnectionPageState extends State<ServerConnectionPage> {
  final address = TextEditingController();
  final token = TextEditingController();
  final vault = const CredentialVault();
  bool loading = false;
  String? error, status;
  DragonServer? server;
  List<dynamic> matches = [];

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    try {
      final savedAddress = await vault.read('dragonhydra_server_url');
      final savedToken = await vault.read('dragonhydra_server_token');
      if (!mounted) return;
      address.text = savedAddress ?? '';
      token.text = savedToken ?? '';
    } catch (_) {
      // The offline app remains usable when no platform vault is available.
    }
  }

  @override
  void dispose() {
    address.dispose();
    token.dispose();
    super.dispose();
  }

  Future<void> connect() async {
    setState(() {
      loading = true;
      error = null;
      status = null;
    });
    try {
      final selected = DragonServer(
        address.text,
        token: token.text,
        transport: widget.transport,
      );
      final data = await selected.matches();
      try {
        await vault.save('dragonhydra_server_url', selected.root.toString());
        if (token.text.trim().isEmpty) {
          await vault.remove('dragonhydra_server_token');
        } else {
          await vault.save('dragonhydra_server_token', token.text.trim());
        }
      } catch (_) {
        // Widget tests have no Android vault. Real-device errors stay explicit.
        if (mounted) status = 'Connected; secure settings could not be retained on this device.';
      }
      if (!mounted) return;
      setState(() {
        server = selected;
        matches = data['items'] as List;
        status ??=
            'Connected: ${matches.length} of ${data['total']} retained matches.';
      });
    } on ServerFailure catch (failure) {
      if (mounted) {
        setState(() {
          error = failure.message;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          error = 'Server unavailable. Check the address and retry.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('DRAGONHYDRA server')),
    body: ListView(
      padding: const EdgeInsets.all(18),
      children: [
        const Text(
          'Connect to the same API used by desktop and Joomla.',
          style: TextStyle(fontSize: 18),
        ),
        const SizedBox(height: 10),
        const Text(
          'Use your configured server HTTPS address. On a phone, localhost means the phone. Local HTTP is only for an explicit emulator/ADB forward. A public read-only gateway needs no pairing token.',
        ),
        const SizedBox(height: 16),
        TextField(
          key: const Key('server-address'),
          controller: address,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'Server address',
            hintText: 'https://your-server-address',
          ),
        ),
        const SizedBox(height: 10),
        TextField(
          key: const Key('server-token'),
          controller: token,
          obscureText: true,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'Pairing token (optional for public gateway)',
          ),
        ),
        const SizedBox(height: 14),
        FilledButton(
          onPressed: loading ? null : connect,
          child: Text(loading ? 'Connecting…' : 'Connect and browse'),
        ),
        if (loading)
          const Padding(
            padding: EdgeInsets.all(12),
            child: LinearProgressIndicator(),
          ),
        if (error != null) ...[
          Semantics(
            liveRegion: true,
            child: Text(
              error!,
              style: const TextStyle(color: Colors.orangeAccent),
            ),
          ),
          TextButton(
            onPressed: loading ? null : connect,
            child: const Text('Retry server'),
          ),
        ],
        if (status != null) Semantics(liveRegion: true, child: Text(status!)),
        if (server != null && matches.isEmpty)
          const Text(
            'No retained matches. Import data in the server application, then reconnect.',
          ),
        for (final raw in matches)
          Builder(
            builder: (context) {
              final match = _map(raw),
                  home = _map(match['home']),
                  away = _map(match['away']);
              return Card(
                child: ListTile(
                  title: Text(
                    '${_text(home['name'])} vs ${_text(away['name'])}',
                  ),
                  subtitle: Text(
                    '${_text(match['event_date'])} · ${_text(match['status'])} · ${_text(match['data_state'])}',
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) =>
                          ServerMatchPage(server: server!, match: match),
                    ),
                  ),
                ),
              );
            },
          ),
      ],
    ),
  );
}

class ServerMatchPage extends StatelessWidget {
  const ServerMatchPage({super.key, required this.server, required this.match});
  final DragonServer server;
  final Map<String, dynamic> match;
  @override
  Widget build(BuildContext context) {
    final home = _map(match['home']),
        away = _map(match['away']),
        score = _map(match['score']);
    void details(String title, String path, String kind) =>
        Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => ServerDetailsPage(
              server: server,
              title: title,
              path: path,
              kind: kind,
            ),
          ),
        );
    return Scaffold(
      appBar: AppBar(title: const Text('Server match')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Text(
            '${_text(home['name'])} vs ${_text(away['name'])}',
            style: const TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
          ),
          Text(
            '${_text(match['competition'])} · ${_text(match['event_date'])}',
          ),
          Text(
            score.isEmpty
                ? 'Result not supplied'
                : '${score['home']} – ${score['away']}',
            style: const TextStyle(fontSize: 22),
          ),
          const Text(
            'UTC kickoff is shown only when supplied by the server. Missing lineups, injuries or odds do not mean zero.',
          ),
          ListTile(
            title: Text(_text(home['name'])),
            subtitle: const Text('Open team'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () =>
                details(_text(home['name']), '/teams/${home['id']}', 'team'),
          ),
          ListTile(
            title: Text(_text(away['name'])),
            subtitle: const Text('Open team'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () =>
                details(_text(away['name']), '/teams/${away['id']}', 'team'),
          ),
          FilledButton(
            onPressed: () => details(
              'Standings',
              '/competitions/${match['competition_id']}/standings',
              'standings',
            ),
            child: const Text('Open standings'),
          ),
          TextButton(
            onPressed: () => details(
              'Model probabilities',
              '/matches/${match['id']}/predictions',
              'predictions',
            ),
            child: const Text('Model probabilities'),
          ),
          Text('Source: ${_text(match['source_id'])}'),
          Text('Locally usable: ${_text(match['usable_at'])}'),
          SelectableText(
            'Canonical match: ${_text(match['id'])}',
            style: const TextStyle(fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class ServerDetailsPage extends StatefulWidget {
  const ServerDetailsPage({
    super.key,
    required this.server,
    required this.title,
    required this.path,
    required this.kind,
  });
  final DragonServer server;
  final String title, path, kind;
  @override
  State<ServerDetailsPage> createState() => _ServerDetailsPageState();
}

class _ServerDetailsPageState extends State<ServerDetailsPage> {
  late Future<Map<String, dynamic>> data = widget.server.get(widget.path);
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.title)),
    body: FutureBuilder<Map<String, dynamic>>(
      future: data,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  snapshot.error is ServerFailure
                      ? (snapshot.error as ServerFailure).message
                      : 'Server unavailable.',
                ),
                TextButton(
                  onPressed: () => setState(() {
                    data = widget.server.get(widget.path);
                  }),
                  child: const Text('Retry server'),
                ),
              ],
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final doc = snapshot.data!;
        final children = <Widget>[];
        if (widget.kind == 'team') {
          children.add(
            Text(_text(doc['name']), style: const TextStyle(fontSize: 22)),
          );
          children.add(const Text('Recent form'));
          for (final raw in (doc['form'] as List? ?? [])) {
            final row = _map(raw);
            children.add(
              ListTile(
                title: Text(
                  '${_text(row['result'])} · ${_text(row['opponent'])}',
                ),
                subtitle: Text(_text(row['date'])),
              ),
            );
          }
          for (final value in (doc['unknowns'] as List? ?? [])) {
            children.add(Text(_text(value)));
          }
        } else if (widget.kind == 'standings') {
          children.add(
            Text(
              _text(doc['competition']),
              style: const TextStyle(fontSize: 22),
            ),
          );
          children.add(
            Text(
              doc['official'] == true
                  ? 'Provider standings'
                  : 'Unofficial reconstructed standings',
            ),
          );
          for (final raw in (doc['items'] as List? ?? [])) {
            final row = _map(raw);
            children.add(
              ListTile(
                title: Text(_text(row['team'])),
                subtitle: Text(
                  'Played ${_text(row['played'])} · Points ${_text(row['points'])}',
                ),
              ),
            );
          }
          for (final value in (doc['limitations'] as List? ?? [])) {
            children.add(Text(_text(value)));
          }
        } else {
          if (doc['available'] == true) {
            final probabilities = _map(doc['ensemble']);
            for (final side in ['home', 'draw', 'away']) {
              final value = probabilities[side];
              children.add(
                Text(
                  '$side: ${value is num ? '${(value * 100).toStringAsFixed(1)}%' : 'Unavailable'}',
                  style: const TextStyle(fontSize: 21),
                ),
              );
            }
            children.add(Text(_text(doc['interpretation'])));
          } else {
            children.add(Text(_text(doc['reason'])));
          }
        }
        return ListView(padding: const EdgeInsets.all(18), children: children);
      },
    ),
  );
}
