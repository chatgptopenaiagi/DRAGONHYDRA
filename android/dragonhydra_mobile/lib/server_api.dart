import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// The desktop/Joomla v1 contract; no sports arithmetic or provider credentials.
class ServerFailure implements Exception {
  const ServerFailure(this.message);
  final String message;
  @override
  String toString() => message;
}

typedef ServerTransport = Future<Map<String, dynamic>> Function(
  Uri uri,
  Map<String, String> headers,
);

Uri validateServerAddress(String address) {
  final uri = Uri.tryParse(address.trim());
  if (uri == null ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/')) {
    throw const ServerFailure(
      'Enter the server root address without credentials, query or path.',
    );
  }
  final local = const ['127.0.0.1', 'localhost', '10.0.2.2'].contains(uri.host);
  if (local && uri.port < 18800) {
    throw const ServerFailure('Select this CORE NEXT installation\'s isolated server port.');
  }
  if (uri.scheme != 'https' && !(uri.scheme == 'http' && local)) {
    throw const ServerFailure(
      'Remote servers require HTTPS. HTTP is limited to local development forwarding.',
    );
  }
  return uri.replace(path: '', query: null, fragment: null);
}

Future<Map<String, dynamic>> _request(
  Uri uri,
  Map<String, String> headers,
) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
  try {
    final request = await client
        .getUrl(uri)
        .timeout(const Duration(seconds: 8));
    request.followRedirects = false;
    headers.forEach(request.headers.set);
    final response = await request.close().timeout(const Duration(seconds: 8));
    if (response.statusCode == 401 || response.statusCode == 403) {
      throw const ServerFailure(
        'Authentication rejected. Check your server pairing token and permissions.',
      );
    }
    if (response.statusCode != 200) {
      throw ServerFailure(
        'Server returned HTTP ${response.statusCode}. Retry when the service is ready.',
      );
    }
    if (!const ['application/json']
        .contains(response.headers.contentType?.mimeType)) {
      throw const ServerFailure(
        'The address did not return the DRAGONHYDRA JSON API.',
      );
    }
    final bytes = <int>[];
    await for (final chunk in response.timeout(const Duration(seconds: 8))) {
      if (bytes.length + chunk.length > 2 * 1024 * 1024) {
        throw const ServerFailure('Server response exceeded the mobile limit.');
      }
      bytes.addAll(chunk);
    }
    final doc = jsonDecode(utf8.decode(bytes));
    if (doc is! Map<String, dynamic>) {
      throw const ServerFailure('Server response does not match API v1.');
    }
    return doc;
  } on ServerFailure {
    rethrow;
  } catch (_) {
    // Transport errors may contain the URL or platform details; show no raw text.
    throw const ServerFailure(
      'Server unavailable. Check the address and reachability, then retry.',
    );
  } finally {
    client.close(force: true);
  }
}

class DragonServer {
  DragonServer(String address, {this.token = '', this.expectedInstallationId = '', ServerTransport? transport})
    : root = validateServerAddress(address),
      _transport = transport ?? _request;
  final Uri root;
  final String token;
  final String expectedInstallationId;
  bool _identified = false;
  String? verifiedInstallationId;
  final ServerTransport _transport;
  static const api = '/dragon/api/v1';

  Future<Map<String, dynamic>> _raw(String path) =>
      _transport(root.resolve('$api$path'), {
        HttpHeaders.acceptHeader: 'application/json',
        if (token.trim().isNotEmpty)
          HttpHeaders.authorizationHeader: 'Bearer ${token.trim()}',
      });
  Future<Map<String, dynamic>> get(String path) async {
    if (!_identified) {
      final system = await _raw('/system');
      final identity = system['installation'];
      if (identity is! Map || identity['product'] != 'DRAGONHYDRA CORE NEXT' ||
          identity['edition'] != 'CORE NEXT' || identity['installation_id'] is! String ||
          !RegExp(r'^core-next-[a-f0-9]{32}$').hasMatch(identity['installation_id'] as String) ||
          (expectedInstallationId.isNotEmpty && identity['installation_id'] != expectedInstallationId)) {
        throw const ServerFailure('This address does not identify the selected CORE NEXT installation.');
      }
      _identified = true;
      verifiedInstallationId = identity['installation_id'] as String;
    }
    return _raw(path);
  }

  Future<Map<String, dynamic>> matches() async {
    final data = await get('/matches?limit=25');
    if (data['items'] is! List || data['total'] is! int) {
      throw const ServerFailure(
        'Server response does not match the match-list contract.',
      );
    }
    for (final item in data['items']) {
      if (item is! Map ||
          item['id'] is! String ||
          !RegExp(r'^[a-f0-9]{64}$').hasMatch(item['id']) ||
          item['home'] is! Map ||
          item['away'] is! Map) {
        throw const ServerFailure(
          'Server returned an invalid canonical match.',
        );
      }
    }
    return data;
  }
}
