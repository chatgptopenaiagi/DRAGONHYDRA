// Explicit, bounded provider verification; saves raw response and receipt.
import 'dart:convert';
import 'dart:io';

import 'package:dragonhydra_mobile/public_sources.dart';

Future<void> main(List<String> args) async {
  if (args.length != 2 ||
      !['openfootball', 'statsbomb_open_data'].contains(args[0])) {
    stderr.writeln(
      'Usage: dart run tool/public_source_probe.dart <source-id> <output-directory>',
    );
    exitCode = 2;
    return;
  }
  final result = await fetchPublicSource(args[0]);
  final directory = Directory(args[1]);
  await directory.create(recursive: true);
  final id =
      '${result.sourceId}-${result.retrievedAtUtc.microsecondsSinceEpoch}-${result.contentSha256.substring(0, 12)}';
  final raw = File('${directory.path}/$id.json');
  await raw.writeAsBytes(result.rawBytes, flush: true);
  final receipt = <String, Object?>{
    ...result.provenance,
    'raw_file': raw.path,
    'raw_persisted_acknowledged_at_utc': DateTime.now()
        .toUtc()
        .toIso8601String(),
    'earliest_usable_at': null,
    'persistence_qualification':
        'Local probe file, not an operational database receipt.',
  };
  await File('${directory.path}/$id.receipt.json').writeAsString(
    '${const JsonEncoder.withIndent('  ').convert(receipt)}\n',
    flush: true,
  );
  stdout.writeln(jsonEncode(receipt));
}
