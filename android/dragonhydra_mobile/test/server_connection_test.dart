import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:dragonhydra_mobile/server_api.dart';
import 'package:dragonhydra_mobile/server_connection.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('ai.dragonhydra.mobile/connections');
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async => null);
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });
  test('server address rejects credentials, remote cleartext and paths', () {
    expect(
      validateServerAddress('https://sports.example.test').host,
      'sports.example.test',
    );
    expect(validateServerAddress('http://127.0.0.1:18743').port, 18743);
    for (final value in [
      'http://192.168.1.2',
      'https://user:secret@example.test',
      'https://example.test/private',
      'https://example.test/?token=secret',
      'file:///private',
    ]) {
      expect(
        () => validateServerAddress(value),
        throwsA(isA<ServerFailure>()),
        reason: value,
      );
    }
  });
  test('server uses versioned API with explicit bearer identity', () async {
    final server = DragonServer(
      'https://sports.example.test',
      token: 'test-only',
      transport: (uri, headers) async {
        expect(uri.path, '/dragon/api/v1/matches');
        expect(uri.queryParameters['limit'], '25');
        expect(headers['authorization'], 'Bearer test-only');
        return {'items': [], 'total': 0};
      },
    );
    expect((await server.matches())['total'], 0);
    final bad = DragonServer(
      'https://sports.example.test',
      transport: (_, _) async => {
        'items': [{}],
        'total': 1,
      },
    );
    await expectLater(bad.matches(), throwsA(isA<ServerFailure>()));
  });
  testWidgets('server outage has a visible working retry', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: ServerConnectionPage(
          transport: (_, _) async {
            calls++;
            if (calls == 1) {
              throw const ServerFailure(
                'Server unavailable. Check address and retry.',
              );
            }
            return {'items': [], 'total': 0};
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('server-address')),
      'https://sports.example.test',
    );
    await tester.tap(find.text('Connect and browse'));
    await tester.pumpAndSettle();
    expect(find.text('Retry server'), findsOneWidget);
    expect(find.textContaining('Server unavailable'), findsOneWidget);
    await tester.tap(find.text('Retry server'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Connected: 0 of 0'), findsOneWidget);
    expect(calls, 2);
  });
  testWidgets('same canonical server match opens team and standings', (
    tester,
  ) async {
    final id = 'a' * 64,
        competition = 'b' * 64,
        home = 'c' * 64,
        away = 'd' * 64;
    final paths = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: ServerConnectionPage(
          transport: (uri, _) async {
            paths.add(uri.path);
            if (uri.path.endsWith('/matches')) {
              return {
                'items': [
                  {
                    'id': id,
                    'competition_id': competition,
                    'competition': 'Synthetic test league',
                    'home': {'id': home, 'name': 'Test Home'},
                    'away': {'id': away, 'name': 'Test Away'},
                    'event_date': '2026-01-01',
                    'status': 'finished',
                    'data_state': 'Synthetic test',
                    'score': {'home': 1, 'away': 0},
                    'source_id': 'test-only',
                    'usable_at': '2026-01-02T00:00:00Z',
                  },
                ],
                'total': 1,
              };
            }
            if (uri.path.endsWith('/teams/$home')) {
              return {
                'name': 'Test Home',
                'form': [],
                'unknowns': ['Injuries not supplied'],
              };
            }
            if (uri.path.endsWith('/standings')) {
              return {
                'competition': 'Synthetic test league',
                'official': false,
                'items': [
                  {'team': 'Test Home', 'played': 1, 'points': 3},
                ],
                'limitations': ['Test reconstruction'],
              };
            }
            throw const ServerFailure('Unexpected test route');
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('server-address')),
      'https://sports.example.test',
    );
    await tester.tap(find.text('Connect and browse'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Test Home vs Test Away'));
    await tester.tap(find.text('Test Home vs Test Away'));
    await tester.pumpAndSettle();
    expect(find.text('Canonical match: $id'), findsOneWidget);
    await tester.tap(find.text('Test Home'));
    await tester.pumpAndSettle();
    expect(find.text('Injuries not supplied'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open standings'));
    await tester.pumpAndSettle();
    expect(find.text('Unofficial reconstructed standings'), findsOneWidget);
    expect(
      paths,
      contains('/dragon/api/v1/competitions/$competition/standings'),
    );
  });
}
