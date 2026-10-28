import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:dragonhydra_mobile/public_sources.dart';

void main() {
  test(
    'captures JSON response with SHA and actual receipt, not backdated',
    () async {
      final before = DateTime.now().toUtc();
      final result = await fetchPublicSource(
        'openfootball',
        transport: (uri) async {
          expect(uri.host, 'raw.githubusercontent.com');
          return PublicHttpResponse(
            200,
            Uint8List.fromList(utf8.encode('{"matches":[]}')),
          );
        },
      );
      final after = DateTime.now().toUtc();
      expect(result.recordCount, 0);
      expect(
        result.contentSha256,
        '1329bed5a664bbf035723754d90023adf1034d44b942c070a37741a1b762d35c',
      );
      expect(result.retrievedAtUtc.isUtc, isTrue);
      expect(result.retrievedAtUtc.isBefore(before), isFalse);
      expect(result.retrievedAtUtc.isAfter(after), isFalse);
      expect(result.provenance['persisted_at'], isNull);
      expect(result.provenance['earliest_usable_at'], isNull);
      expect(result.provenance['data_origin'], 'imported_historical');
    },
  );

  test('rejects unexpected shape, oversized response and HTTP error', () async {
    Future<PublicHttpResponse> malformed(Uri _) async =>
        PublicHttpResponse(200, Uint8List.fromList(utf8.encode('{}')));
    Future<PublicHttpResponse> large(Uri _) async =>
        PublicHttpResponse(200, Uint8List(2 * 1024 * 1024 + 1));
    Future<PublicHttpResponse> forbidden(Uri _) async =>
        PublicHttpResponse(403, Uint8List(0));
    expect(
      () => fetchPublicSource('openfootball', transport: malformed),
      throwsFormatException,
    );
    expect(
      () => fetchPublicSource('openfootball', transport: large),
      throwsFormatException,
    );
    expect(
      () => fetchPublicSource('openfootball', transport: forbidden),
      throwsA(isA<Exception>()),
    );
  });
}
