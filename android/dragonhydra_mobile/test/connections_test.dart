import 'package:dragonhydra_mobile/connections.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('ai.dragonhydra.mobile/connections');
  final values = <String, String>{};
  setUp(() {
    values.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      final arguments = call.arguments as Map;
      final id = arguments['providerId'] as String?;
      if (call.method == 'save') values[id!] = arguments['value'] as String;
      if (call.method == 'read') return values[id];
      if (call.method == 'remove') values.remove(id);
      return null;
    });
  });
  tearDown(() => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));

  test('credentials can be saved, read and deleted without a network request', () async {
    const vault = CredentialVault();
    await vault.save('api_football', 'sample');
    expect(await vault.read('api_football'), 'sample');
    await vault.remove('api_football');
    expect(await vault.read('api_football'), isNull);
  });

  test('configuration alone is not a connected provider', () async {
    var calls = 0;
    final tester = ProviderConnectionTester(const CredentialVault(), transport: (uri, headers) async {
      calls++;
      return const ProviderReply(200, '{"competitions":[]}', {'x-authenticated-client': 'member'});
    });
    expect((await tester.test('football_data_org')).state, 'NOT_CONFIGURED');
    expect(calls, 0);
    await const CredentialVault().save('football_data_org', 'fixture-key');
    expect((await tester.test('football_data_org')).state, 'CONNECTED');
    expect(calls, 1);
  });

  test('anonymous football-data response never establishes authentication', () async {
    await const CredentialVault().save('football_data_org', 'fixture-key');
    final tester = ProviderConnectionTester(const CredentialVault(), transport: (uri, headers) async =>
        const ProviderReply(200, '{"competitions":[]}', {'x-authenticated-client': 'anonymous'}));
    expect((await tester.test('football_data_org')).state, 'AUTHENTICATION_REQUIRED');
  });

  test('response errors, authorization and quota remain visible', () async {
    await const CredentialVault().save('api_football', 'fixture-key');
    var status = 200;
    var body = '{"errors":{"token":"invalid"},"response":{}}';
    final tester = ProviderConnectionTester(const CredentialVault(), transport: (uri, headers) async {
      expect(uri.host, 'v3.football.api-sports.io');
      expect(headers['x-apisports-key'], 'fixture-key');
      return ProviderReply(status, body, const {'x-ratelimit-requests-remaining': '10'});
    });
    expect((await tester.test('api_football')).state, 'AUTHENTICATION_REQUIRED');
    status = 429;
    expect((await tester.test('api_football')).state, 'RATE_LIMITED');
    status = 200;
    body = '{"errors":[],"response":{"foo":1}}';
    expect((await tester.test('api_football')).state, 'UNAVAILABLE');
    body = '{"errors":[],"response":{"account":{"firstname":"test"},"subscription":{"active":false}}}';
    expect((await tester.test('api_football')).state, 'ACCESS_RESTRICTED');
    body = '{"errors":[],"response":{"account":{"firstname":"test"},"subscription":{"active":true}}}';
    final success = await tester.test('api_football');
    expect(success.state, 'CONNECTED');
    expect(success.quota, '10 remaining');
    expect(success.message.contains('fixture-key'), isFalse);
  });

  test('The Odds API requires a key and a validated catalog response', () async {
    const vault = CredentialVault();
    var status = 200;
    var body = '[{"key":"soccer_epl","active":true}]';
    var calls = 0;
    final tester = ProviderConnectionTester(vault, transport: (uri, headers) async {
      calls++;
      expect(uri.scheme, 'https');
      expect(uri.host, 'api.the-odds-api.com');
      expect(uri.path, '/v4/sports/');
      expect(uri.queryParameters['apiKey'], 'example+with&reserved');
      expect(headers, isEmpty);
      return ProviderReply(status, body, {'x-requests-remaining': '45'});
    });
    expect((await tester.test('the_odds_api')).state, 'NOT_CONFIGURED');
    expect(calls, 0);
    await vault.save('the_odds_api', 'example+with&reserved');
    final connected = await tester.test('the_odds_api');
    expect(connected.state, 'CONNECTED');
    expect(connected.quota, '45 remaining');
    expect(connected.message, isNot(contains('example+with&reserved')));
    body = '[]';
    expect((await tester.test('the_odds_api')).state, 'UNAVAILABLE');
    body = '{"message":"invalid"}';
    expect((await tester.test('the_odds_api')).state, 'UNAVAILABLE');
    status = 401;
    expect((await tester.test('the_odds_api')).state, 'AUTHENTICATION_REQUIRED');
    status = 429;
    expect((await tester.test('the_odds_api')).state, 'RATE_LIMITED');
  });
}
