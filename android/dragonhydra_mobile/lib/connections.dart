import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

/// Provider credentials are encrypted at rest by Android Keystore. Never log keys.
class CredentialVault {
  const CredentialVault();
  static const _channel = MethodChannel('ai.dragonhydra.mobile/connections');

  Future<void> save(String providerId, String key) async {
    if (key.trim().isEmpty) throw ArgumentError('A credential is required');
    await _channel.invokeMethod<void>('save', {'providerId': providerId, 'value': key.trim()});
  }

  Future<String?> read(String providerId) =>
      _channel.invokeMethod<String>('read', {'providerId': providerId});

  Future<void> remove(String providerId) =>
      _channel.invokeMethod<void>('remove', {'providerId': providerId});

  Future<void> openUrl(String url) => _channel.invokeMethod<void>('openUrl', {'url': url});
}

class ConnectionResult {
  const ConnectionResult(this.state, this.message, {this.quota, this.checkedAt});
  final String state;
  final String message;
  final String? quota;
  final DateTime? checkedAt;
}

class ProviderReply {
  const ProviderReply(this.status, this.body, this.headers);
  final int status;
  final String body;
  final Map<String, String> headers;
}

typedef ProviderTransport = Future<ProviderReply> Function(Uri uri, Map<String, String> headers);

Future<ProviderReply> _get(Uri uri, Map<String, String> headers) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  try {
    final request = await client.getUrl(uri).timeout(const Duration(seconds: 10));
    request.followRedirects = false; // Never forward a credential to a redirected host.
    headers.forEach(request.headers.set);
    final response = await request.close().timeout(const Duration(seconds: 10));
    final bytes = <int>[];
    await for (final chunk in response.timeout(const Duration(seconds: 10))) {
      if (bytes.length + chunk.length > 1024 * 1024) throw const FormatException('Response too large');
      bytes.addAll(chunk);
    }
    return ProviderReply(response.statusCode, utf8.decode(bytes), {
      'x-ratelimit-requests-remaining': response.headers.value('x-ratelimit-requests-remaining') ?? '',
      'x-ratelimit-requests-limit': response.headers.value('x-ratelimit-requests-limit') ?? '',
      'x-authenticated-client': response.headers.value('x-authenticated-client') ?? '',
      'x-requests-remaining': response.headers.value('x-requests-remaining') ?? '',
    });
  } finally {
    client.close(force: true);
  }
}

/// A connection succeeds only after a valid response from the official endpoint.
class ProviderConnectionTester {
  ProviderConnectionTester(this.vault, {ProviderTransport? transport}) : _transport = transport ?? _get;
  final CredentialVault vault;
  final ProviderTransport _transport;

  Future<ConnectionResult> test(String providerId) async {
    if (providerId != 'football_data_org' && providerId != 'api_football' && providerId != 'the_odds_api') {
      return const ConnectionResult('UNAVAILABLE', 'Connection test is not implemented for this provider.');
    }
    String? key;
    try {
      key = await vault.read(providerId);
    } catch (_) {
      return const ConnectionResult('ERROR', 'Secure credential storage is unavailable.');
    }
    if (key == null || key.isEmpty) {
      return const ConnectionResult('NOT_CONFIGURED', 'Add a provider API key to test this connection.');
    }
    final uri = providerId == 'the_odds_api'
        ? Uri.https('api.the-odds-api.com', '/v4/sports/', {'apiKey': key})
        : Uri.parse(providerId == 'football_data_org'
            ? 'https://api.football-data.org/v4/competitions'
            : 'https://v3.football.api-sports.io/status');
    final headers = providerId == 'the_odds_api'
        ? <String, String>{}
        : <String, String>{providerId == 'football_data_org' ? 'X-Auth-Token' : 'x-apisports-key': key};
    try {
      final reply = await _transport(uri, headers);
      final now = DateTime.now().toUtc();
      if (reply.status == 401) return ConnectionResult('AUTHENTICATION_REQUIRED', 'Provider rejected authentication.', checkedAt: now);
      if (reply.status == 403) return ConnectionResult('ACCESS_RESTRICTED', 'Provider denied access.', checkedAt: now);
      if (reply.status == 429) return ConnectionResult('RATE_LIMITED', 'Provider rate limit reached.', checkedAt: now);
      if (reply.status >= 500) return ConnectionResult('UNAVAILABLE', 'Provider service unavailable.', checkedAt: now);
      if (reply.status != 200) return ConnectionResult('ERROR', 'Provider returned HTTP ${reply.status}.', checkedAt: now);
      final parsed = jsonDecode(reply.body);
      if (providerId == 'the_odds_api') {
        if (parsed is! List || parsed.isEmpty ||
            parsed.any((item) => item is! Map || item['key'] is! String || (item['key'] as String).isEmpty)) {
          return ConnectionResult('UNAVAILABLE', 'Provider did not return a verifiable sports catalog.', checkedAt: now);
        }
        final remaining = reply.headers['x-requests-remaining'];
        final quota = remaining != null && RegExp(r'^\d{1,12}$').hasMatch(remaining)
            ? '$remaining remaining' : null;
        return ConnectionResult('CONNECTED', 'Authenticated sports catalog received.', quota: quota, checkedAt: now);
      }
      if (parsed is! Map<String, dynamic>) return ConnectionResult('ERROR', 'Unexpected provider response.', checkedAt: now);
      if (providerId == 'api_football') {
        final errors = parsed['errors'];
        if ((errors is Map && errors.isNotEmpty) || (errors is List && errors.isNotEmpty)) {
          final description = jsonEncode(errors).toLowerCase();
          if (description.contains('rate') || description.contains('limit') || description.contains('requests')) {
            return ConnectionResult('RATE_LIMITED', 'Provider reported a request limit.', checkedAt: now);
          }
          if (description.contains('key') || description.contains('token') || description.contains('auth')) {
            return ConnectionResult('AUTHENTICATION_REQUIRED', 'Provider reported an authentication error.', checkedAt: now);
          }
          return ConnectionResult('ACCESS_RESTRICTED', 'Provider reported an account or access error.', checkedAt: now);
        }
        if (parsed['response'] is! Map || (parsed['response'] as Map).isEmpty) {
          return ConnectionResult('ERROR', 'Unexpected account status response.', checkedAt: now);
        }
        final status = parsed['response'] as Map;
        final account = status['account'];
        final subscription = status['subscription'];
        if (account is! Map || account.isEmpty || subscription is! Map || subscription['active'] is! bool) {
          return ConnectionResult('UNAVAILABLE', 'Provider did not return a verifiable account status.', checkedAt: now);
        }
        if (subscription['active'] == false) {
          return ConnectionResult('ACCESS_RESTRICTED', 'Provider subscription is inactive.', checkedAt: now);
        }
      } else if (parsed['competitions'] is! List) {
        return ConnectionResult('ERROR', 'Unexpected competition response.', checkedAt: now);
      } else {
        final identity = reply.headers['x-authenticated-client']?.trim();
        if (identity == null || identity.isEmpty) {
          return ConnectionResult('UNAVAILABLE', 'The provider did not confirm an authenticated client.', checkedAt: now);
        }
        if (identity.toLowerCase() == 'anonymous') {
          return ConnectionResult('AUTHENTICATION_REQUIRED', 'Provider returned an anonymous response.', checkedAt: now);
        }
      }
      final remaining = reply.headers['x-ratelimit-requests-remaining'];
      final limit = reply.headers['x-ratelimit-requests-limit'];
      final quota = remaining != null && remaining.isNotEmpty ? '$remaining remaining${limit != null && limit.isNotEmpty ? ' of $limit' : ''}' : null;
      return ConnectionResult('CONNECTED', 'Authenticated provider response received.', quota: quota, checkedAt: now);
    } on TimeoutException {
      return const ConnectionResult('UNAVAILABLE', 'Connection timed out.');
    } on SocketException {
      return const ConnectionResult('UNAVAILABLE', 'Network unavailable.');
    } catch (_) {
      return const ConnectionResult('ERROR', 'Connection or response validation failed.');
    }
  }
}
