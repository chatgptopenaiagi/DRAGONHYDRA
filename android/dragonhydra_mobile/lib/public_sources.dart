/// Bounded, explicit-request acquisition from public football datasets.
/// No credentialed endpoints, trading actions or background polling.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

const _urls = <String, String>{
  'openfootball': 'https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json',
  'statsbomb_open_data': 'https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json',
};
const int _maxBytes = 2 * 1024 * 1024;

class PublicHttpResponse {
  const PublicHttpResponse(this.statusCode, this.body);
  final int statusCode;
  final Uint8List body;
}

class PublicSourceResult {
  const PublicSourceResult({
    required this.sourceId,
    required this.url,
    required this.retrievedAtUtc,
    required this.rawBytes,
    required this.contentSha256,
    required this.recordCount,
  });
  final String sourceId;
  final String url;
  final DateTime retrievedAtUtc;
  final Uint8List rawBytes;
  final String contentSha256;
  final int recordCount;

  /// No persistence occurs here; the data is not eligible as stored evidence.
  Map<String, Object?> get provenance => {
    'source_id': sourceId,
    'requested_endpoint': url,
    'retrieved_at_utc': retrievedAtUtc.toIso8601String(),
    'source_published_at': null,
    'persisted_at': null,
    'earliest_usable_at': null,
    'data_origin': 'imported_historical',
    'content_sha256': contentSha256,
    'hash_representation': 'HTTP response body after content decoding',
    'adapter_version': 'public-source/1',
    'validation_result': 'validated top-level JSON shape',
    'record_count': recordCount,
  };
}

typedef PublicTransport = Future<PublicHttpResponse> Function(Uri uri);

Future<PublicHttpResponse> _fetch(Uri uri) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  try {
    final request = await client
        .getUrl(uri)
        .timeout(const Duration(seconds: 10));
    request.followRedirects = false;
    final response = await request.close().timeout(const Duration(seconds: 15));
    if (response.statusCode != HttpStatus.ok) {
      return PublicHttpResponse(response.statusCode, Uint8List(0));
    }
    Future<Uint8List> readBody() async {
      final bytes = BytesBuilder(copy: false);
      await for (final chunk in response) {
        if (bytes.length + chunk.length > _maxBytes) {
          throw const FormatException('Response exceeds the 2 MiB limit');
        }
        bytes.add(chunk);
      }
      return bytes.takeBytes();
    }

    return PublicHttpResponse(
      response.statusCode,
      await readBody().timeout(const Duration(seconds: 20)),
    );
  } finally {
    client.close(force: true);
  }
}

/// Fetch one fixed public file. An injected transport allows offline tests.
Future<PublicSourceResult> fetchPublicSource(
  String sourceId, {
  PublicTransport? transport,
}) async {
  final url = _urls[sourceId];
  if (url == null) throw ArgumentError.value(sourceId, 'sourceId');
  final response = await (transport ?? _fetch)(Uri.parse(url));
  if (response.statusCode != HttpStatus.ok) {
    throw HttpException('Public source returned HTTP ${response.statusCode}');
  }
  if (response.body.length > _maxBytes) {
    throw const FormatException('Response exceeds the 2 MiB limit');
  }
  final body = Uint8List.fromList(response.body);
  final parsed = jsonDecode(utf8.decode(body));
  final int count;
  if (sourceId == 'openfootball' &&
      parsed is Map &&
      parsed['matches'] is List) {
    count = (parsed['matches'] as List).length;
  } else if (sourceId == 'statsbomb_open_data' && parsed is List) {
    count = parsed.length;
  } else {
    throw const FormatException('Unexpected public dataset JSON shape');
  }
  return PublicSourceResult(
    sourceId: sourceId,
    url: url,
    retrievedAtUtc: DateTime.now().toUtc(),
    rawBytes: body,
    contentSha256: sha256.convert(body).toString(),
    recordCount: count,
  );
}
