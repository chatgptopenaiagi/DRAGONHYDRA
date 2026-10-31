<?php
/** Explicit isolated migration test. No default execution, cleanup, or authority change. */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { exit(1); }
ini_set('memory_limit', '512M');
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);

const CORE_TABLES = ['connector_acquisitions','connector_attempts','connector_identity_review',
    'connector_observations','connector_quarantine','connector_settings','product_bridge_nonces',
    'product_jobs','product_schema','product_sessions','product_updates','public_fixture_quarantine',
    'public_fixture_records','public_result_captures','public_result_receipts','raw_sources'];
const SQL_MODE = 'STRICT_ALL_TABLES,NO_AUTO_VALUE_ON_ZERO,NO_BACKSLASH_ESCAPES,ERROR_FOR_DIVISION_BY_ZERO';

function demand(bool $value, string $code): void { if (!$value) { throw new RuntimeException($code); } }
function orderedStructure(mixed $value): mixed {
    if (!is_array($value)) { return $value; }
    if (!array_is_list($value)) { ksort($value, SORT_STRING); }
    foreach ($value as $key=>$item) { $value[$key] = orderedStructure($item); }
    return $value;
}
function schemaProfile(array $manifest): string {
    $profile = $manifest['schema_profile'] ?? 'core-1';
    demand(($manifest['format_version'] === 'dragonhydra-mariadb-staging/1' && $profile === 'core-1')
        || ($manifest['format_version'] === 'dragonhydra-mariadb-staging/2' && $profile === 'core-context-1'), 'SCHEMA_PROFILE_UNSUPPORTED');
    return $profile;
}
function profileTables(string $profile): array {
    demand(in_array($profile, ['core-1','core-context-1'], true), 'SCHEMA_PROFILE_UNSUPPORTED');
    $tables = CORE_TABLES;
    if ($profile === 'core-context-1') { array_push($tables, 'cognitive_records', 'cognitive_receipts'); }
    sort($tables); return $tables;
}
function profileTriggers(string $profile): array {
    $triggers = [];
    foreach (['raw_sources'=>'public_raw', 'public_result_captures'=>'public_capture',
        'public_result_receipts'=>'public_receipt', 'public_fixture_records'=>'public_fixture',
        'public_fixture_quarantine'=>'public_quarantine'] as $table=>$prefix) {
        foreach (['update','delete'] as $operation) {
            $triggers[] = ['name'=>$prefix . '_immutable_' . $operation, 'table'=>$table, 'operation'=>strtoupper($operation)];
        }
    }
    if ($profile === 'core-context-1') {
        foreach (['cognitive_records'=>'record', 'cognitive_receipts'=>'receipt'] as $table=>$kind) {
            foreach (['update','delete'] as $operation) {
                $triggers[] = ['name'=>$table . '_no_' . $operation, 'table'=>$table, 'operation'=>strtoupper($operation),
                    'message'=>'immutable cognitive ' . $kind];
            }
        }
    }
    usort($triggers, fn($left,$right) => strcmp($left['name'], $right['name'])); return $triggers;
}
function validateContextMapping(array $tables, array $mapping): void {
    $expected = [
        'cognitive_records'=>['kind'=>[64,0,true], 'record_id'=>[128,1,true], 'natural_key'=>[64,0,true],
            'fingerprint'=>[null,0,true], 'payload'=>[null,0,true]],
        'cognitive_receipts'=>['record_id'=>[128,1,false], 'received_at'=>[null,0,true],
            'persisted_at'=>[null,0,true], 'usable_at'=>[null,0,true]],
    ];
    foreach ($expected as $name=>$columns) {
        $table = $tables[$name];
        demand(array_column($table['columns'], 'name') === array_keys($columns)
            && $table['primary_key'] === ['record_id'] && $table['auto_increment'] === null, 'CONTEXT_TABLE_MAPPING_MISMATCH');
        foreach ($table['columns'] as $column) {
            [$capacity,$primary,$required] = $columns[$column['name']];
            demand($column['source_declared_type'] === 'TEXT' && $column['source_not_null'] === $required
                && $column['primary_key_position'] === $primary && $column['nullable'] === false
                && $column['binary_text'] === ($capacity !== null) && $column['capacity_bytes'] === $capacity
                && $column['target_type'] === ($capacity === null ? 'LONGTEXT' : 'VARBINARY(' . $capacity . ')')
                && $column['source_default_sql'] === null && $column['target_default_sql'] === null, 'CONTEXT_COLUMN_MAPPING_MISMATCH');
        }
    }
    demand($tables['cognitive_records']['foreign_keys'] === []
        && orderedStructure($tables['cognitive_records']['indexes']) === orderedStructure([['name'=>'sqlite_autoindex_cognitive_records_2', 'unique'=>true,
            'columns'=>[['column'=>'kind','descending'=>false],['column'=>'natural_key','descending'=>false]]]])
        && $tables['cognitive_receipts']['indexes'] === [], 'CONTEXT_INDEX_MAPPING_MISMATCH');
    demand(orderedStructure($tables['cognitive_receipts']['foreign_keys']) === orderedStructure([['name'=>'fk_cognitive_receipts_0', 'parent_table'=>'cognitive_records',
        'on_update'=>'NO ACTION','on_delete'=>'NO ACTION','match'=>'NONE','columns'=>['record_id'],'parent_columns'=>['record_id'],
        'target_on_update'=>'RESTRICT','target_on_delete'=>'RESTRICT']]), 'CONTEXT_RECEIPT_FOREIGN_KEY_MISMATCH');
    demand(orderedStructure($mapping['key_capacity_policy']['cognitive_records'] ?? null) === orderedStructure(['kind'=>64,'record_id'=>128,'natural_key'=>64])
        && ($mapping['key_capacity_policy']['cognitive_receipts'] ?? null) === ['record_id'=>128], 'CONTEXT_KEY_CAPACITY_MISMATCH');
}
function ident(string $name): string {
    demand((bool) preg_match('/\A[a-z_][a-z0-9_]{0,63}\z/D', $name), 'IDENTIFIER_UNSUPPORTED');
    return '`' . $name . '`';
}
function localPath(string $path, string $root): string {
    $resolved = realpath($path);
    demand($resolved !== false && str_starts_with(strtolower(str_replace('\\','/',$resolved)),
        strtolower(str_replace('\\','/',$root)) . '/'), 'PATH_OUTSIDE_PROJECT');
    return $resolved;
}
function decode(string $path): array {
    $result = json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
    demand(is_array($result), 'JSON_OBJECT_REQUIRED');
    return $result;
}
function artifact(string $bundle, array $entry, string $expected): string {
    demand(($entry['path'] ?? null) === $expected, 'ARTIFACT_PATH_MISMATCH');
    $path = $bundle . DIRECTORY_SEPARATOR . $expected;
    demand(is_file($path) && !is_link($path) && filesize($path) === $entry['bytes']
        && hash_file('sha256', $path) === $entry['sha256'], 'ARTIFACT_HASH_MISMATCH');
    return $path;
}
function literalPattern(array $column, bool $nullable = true): string {
    $kind = $column['source_declared_type'];
    $pattern = match ($kind) {
        'INTEGER' => '-?(?:0|[1-9][0-9]*)',
        'REAL' => '-?[0-9]+(?:\.[0-9]+)?e[+-]?[0-9]+',
        'BLOB' => "X'[0-9a-f]*'",
        'TEXT' => $column['binary_text'] ? "X'[0-9a-f]*'" : "CONVERT\(X'[0-9a-f]*' USING utf8mb4\)",
        default => throw new RuntimeException('COLUMN_TYPE_UNSUPPORTED'),
    };
    return $nullable && $column['nullable'] ? '(?:NULL|' . $pattern . ')' : $pattern;
}
function tableDdl(array $table, array $scope): string {
    $lines = [];
    foreach ($table['columns'] as $column) {
        $target = $column['target_type'];
        demand((bool) preg_match('/\A(?:BIGINT|DOUBLE|LONGBLOB|LONGTEXT|VARBINARY\([1-9][0-9]{0,3}\))\z/', $target), 'TARGET_TYPE_UNSUPPORTED');
        $line = ident($column['name']) . ' ' . $target;
        if ($target === 'LONGTEXT') { $line .= ' CHARACTER SET utf8mb4 COLLATE utf8mb4_bin'; }
        $line .= $column['nullable'] ? ' NULL' : ' NOT NULL';
        if ($table['auto_increment'] && $table['auto_increment']['column'] === $column['name']) { $line .= ' AUTO_INCREMENT'; }
        if ($column['target_default_sql'] !== null) {
            $default = $column['target_default_sql'];
            $pattern = literalPattern($column, false);
            if ($column['source_declared_type'] === 'TEXT' && !$column['binary_text']) { $pattern = preg_quote('(', '/') . $pattern . preg_quote(')', '/'); }
            demand((bool) preg_match('/\A' . $pattern . '\z/D', $default), 'DEFAULT_EXPRESSION_UNSUPPORTED');
            $line .= ' DEFAULT ' . $default;
        }
        $lines[] = $line;
    }
    $lines[] = 'PRIMARY KEY (' . implode(',', array_map('ident', $table['primary_key'])) . ')';
    foreach ($table['indexes'] as $index) {
        $parts = array_map(fn($part) => ident($part['column']) . ($part['descending'] ? ' DESC' : ' ASC'), $index['columns']);
        $lines[] = ($index['unique'] ? 'UNIQUE KEY ' : 'KEY ') . ident($index['name']) . ' USING BTREE (' . implode(',', $parts) . ')';
    }
    foreach ($table['foreign_keys'] as $foreign) {
        demand(in_array($foreign['parent_table'], $scope, true), 'FOREIGN_SCHEMA_UNSUPPORTED');
        $lines[] = 'CONSTRAINT ' . ident($foreign['name']) . ' FOREIGN KEY (' . implode(',', array_map('ident', $foreign['columns'])) . ') REFERENCES '
            . ident($foreign['parent_table']) . ' (' . implode(',', array_map('ident', $foreign['parent_columns'])) . ') ON UPDATE RESTRICT ON DELETE RESTRICT';
    }
    return 'CREATE TABLE ' . ident($table['name']) . " (\n  " . implode(",\n  ", $lines) . "\n) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;";
}
function validateStatements(array $statements, array $mapping, string $schema, string $profile): void {
    $scope = profileTables($profile);
    $tables = array_column($mapping['tables'], null, 'name');
    $names = array_keys($tables); sort($names);
    demand($names === $scope && count($mapping['tables']) === count($scope) && count($mapping['creation_order']) === count($scope)
        && count(array_unique($mapping['creation_order'])) === count($scope), 'TABLE_SCOPE_MISMATCH');
    if ($profile === 'core-context-1') { validateContextMapping($tables, $mapping); }
    demand(orderedStructure($mapping['triggers']) === orderedStructure(profileTriggers($profile)), 'TRIGGER_PROFILE_MISMATCH');
    foreach ($statements as $sql) {
        demand(is_string($sql) && substr_count($sql, ';') === 1 && !str_contains($sql, "\0"), 'SINGLE_STATEMENT_REQUIRED');
    }
    $position = 0;
    $take = function(string $expected) use ($statements, &$position): void {
        $sql = $statements[$position++] ?? '';
        // The first generated group includes fixed documentation comments.
        $sql = preg_replace('/\A(?:--[^\r\n]*\r?\n)*/', '', $sql);
        demand(trim($sql) === $expected, 'STATEMENT_PLAN_MISMATCH');
    };
    $take("SET SESSION sql_mode='" . SQL_MODE . "';");
    $take('SET SESSION innodb_strict_mode=ON;');
    $take('SET SESSION foreign_key_checks=1;');
    $take('SET SESSION unique_checks=1;');
    $take('SET NAMES utf8mb4 COLLATE utf8mb4_bin;');
    $take('CREATE DATABASE ' . ident($schema) . ' CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;');
    $take('USE ' . ident($schema) . ';');
    foreach ($mapping['creation_order'] as $name) { demand(isset($tables[$name]), 'TABLE_SCOPE_MISMATCH'); $take(tableDdl($tables[$name], $scope)); }
    $take('START TRANSACTION;');
    foreach ($mapping['creation_order'] as $name) {
        $table = $tables[$name];
        $prefix = 'INSERT INTO ' . ident($name) . ' (' . implode(',', array_map(fn($column) => ident($column['name']), $table['columns'])) . ') VALUES (';
        $pattern = '/\A' . preg_quote($prefix, '/') . implode(',', array_map('literalPattern', $table['columns'])) . '\);\z/D';
        for ($row = 0; $row < $table['row_count']; $row++) {
            demand((bool) preg_match($pattern, trim($statements[$position++] ?? '')), 'INSERT_LITERAL_PLAN_MISMATCH');
        }
    }
    $take('COMMIT;');
    foreach ($mapping['tables'] as $table) {
        if ($table['auto_increment']) { $take('ALTER TABLE ' . ident($table['name']) . ' AUTO_INCREMENT = ' . $table['auto_increment']['next_value'] . ';'); }
    }
    foreach ($mapping['triggers'] as $trigger) {
        demand(in_array($trigger['table'], $scope, true) && in_array($trigger['operation'], ['UPDATE','DELETE'], true), 'TRIGGER_SCOPE_MISMATCH');
        $take('CREATE TRIGGER ' . ident($trigger['name']) . ' BEFORE ' . $trigger['operation'] . ' ON ' . ident($trigger['table'])
            . " FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='" . ($trigger['message'] ?? 'immutable') . "';");
    }
    $take("SELECT 'mariadb_staging_script_only' AS migration_status;");
    demand($position === count($statements), 'UNEXPECTED_TRAILING_STATEMENTS');
}
function selectRows(mysqli $db, string $sql, string $schema): array {
    $stmt = $db->prepare($sql); $stmt->bind_param('s', $schema); $stmt->execute();
    return $stmt->get_result()->fetch_all(MYSQLI_ASSOC);
}
function metadata(mysqli $db, string $schema): array {
    return [
        'tables' => selectRows($db, 'SELECT TABLE_NAME,ENGINE,ROW_FORMAT,AUTO_INCREMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=? ORDER BY TABLE_NAME', $schema),
        'columns' => selectRows($db, 'SELECT TABLE_NAME,COLUMN_NAME,ORDINAL_POSITION,COLUMN_TYPE,IS_NULLABLE,COLLATION_NAME,CHARACTER_SET_NAME,EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=? ORDER BY TABLE_NAME,ORDINAL_POSITION', $schema),
        'indexes' => selectRows($db, 'SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,COLLATION,SUB_PART,INDEX_TYPE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=? ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX', $schema),
        'foreign_keys' => selectRows($db, 'SELECT K.TABLE_NAME,K.CONSTRAINT_NAME,K.ORDINAL_POSITION,K.COLUMN_NAME,K.REFERENCED_TABLE_SCHEMA,K.REFERENCED_TABLE_NAME,K.REFERENCED_COLUMN_NAME,R.UPDATE_RULE,R.DELETE_RULE FROM information_schema.KEY_COLUMN_USAGE K JOIN information_schema.REFERENTIAL_CONSTRAINTS R ON R.CONSTRAINT_SCHEMA=K.CONSTRAINT_SCHEMA AND R.CONSTRAINT_NAME=K.CONSTRAINT_NAME WHERE K.TABLE_SCHEMA=? AND K.REFERENCED_TABLE_NAME IS NOT NULL ORDER BY K.TABLE_NAME,K.CONSTRAINT_NAME,K.ORDINAL_POSITION', $schema),
        'triggers' => selectRows($db, 'SELECT TRIGGER_NAME,EVENT_MANIPULATION,EVENT_OBJECT_TABLE,ACTION_TIMING,ACTION_STATEMENT FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=? ORDER BY TRIGGER_NAME', $schema),
    ];
}
function rowsFile(mysqli $db, array $table, string $file): int {
    demand(is_file($file) && filesize($file) === 0 && !is_link($file), 'PRIVATE_EMPTY_EXPORT_REQUIRED');
    $sql = 'SELECT ' . implode(',', array_map(fn($column) => ident($column['name']), $table['columns'])) . ' FROM ' . ident($table['name'])
        . ' ORDER BY ' . implode(',', array_map('ident', $table['primary_key']));
    $stmt = $db->prepare($sql); $stmt->execute(); $result = $stmt->get_result();
    $fileHandle = fopen($file, 'wb'); demand($fileHandle !== false, 'EXPORT_OPEN_FAILED');
    $count = 0;
    try {
        while ($row = $result->fetch_row()) {
            $cells = [];
            foreach ($row as $index => $value) {
                $column = $table['columns'][$index]; $kind = $column['source_declared_type'];
                if ($value === null) { $cells[] = ['null']; continue; }
                if ($kind === 'INTEGER') { demand(is_int($value), 'MYSQLND_NATIVE_INTEGER_REQUIRED'); $cells[] = ['int', (string) $value]; }
                elseif ($kind === 'REAL') { demand(is_float($value) && is_finite($value), 'MYSQLND_NATIVE_DOUBLE_REQUIRED'); $cells[] = ['float_bits', bin2hex(pack('E', $value))]; }
                else { demand(is_string($value), 'MYSQLND_STRING_REQUIRED'); $cells[] = [$kind === 'BLOB' ? 'blob_hex' : 'text_hex', bin2hex($value)]; }
            }
            $line = json_encode(['values' => $cells], JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n";
            demand(fwrite($fileHandle, $line) === strlen($line), 'EXPORT_WRITE_FAILED'); $count++;
        }
    } finally { fclose($fileHandle); $stmt->close(); }
    return $count;
}
function rejectedProbe(mysqli $db, string $name, callable $operation, int $errno, string $sqlstate): array {
    $db->begin_transaction();
    try {
        try { $operation(); }
        catch (mysqli_sql_exception $failure) {
            demand($failure->getCode() === $errno && $failure->getSqlState() === $sqlstate, 'CONSTRAINT_PROBE_WRONG_FAILURE');
            return ['name' => $name, 'passed' => true, 'errno' => $errno, 'sqlstate' => $sqlstate, 'rolled_back' => true];
        }
        throw new RuntimeException('CONSTRAINT_PROBE_UNEXPECTEDLY_ACCEPTED');
    } finally { $db->rollback(); }
}
function insertRawProbe(mysqli $db): string {
    $bytes = random_bytes(16); $hash = hash('sha256', $bytes);
    $statement = $db->prepare('INSERT INTO raw_sources(source_hash,bytes) VALUES(?,?)');
    $statement->bind_param('ss', $hash, $bytes); $statement->execute(); return $hash;
}
function insertCognitiveProbe(mysqli $db, bool $receipt = false): string {
    $id = 'source_context:' . bin2hex(random_bytes(32)); $key = bin2hex(random_bytes(32));
    $fingerprint = bin2hex(random_bytes(32));
    $statement = $db->prepare("INSERT INTO cognitive_records(kind,record_id,natural_key,fingerprint,payload) VALUES('source_context',?,?,?, '{\"synthetic\":true,\"purpose\":\"rollback-probe\"}')");
    $statement->bind_param('sss', $id, $key, $fingerprint); $statement->execute();
    if ($receipt) {
        $statement = $db->prepare("INSERT INTO cognitive_receipts(record_id,received_at,persisted_at,usable_at) VALUES(?,'2000-01-01','2000-01-01','2000-01-01')");
        $statement->bind_param('s', $id); $statement->execute();
    }
    return $id;
}
function probes(mysqli $db, string $profile): array {
    $results = [];
    $results[] = rejectedProbe($db, 'duplicate-primary-key', function() use ($db) {
        $hash = insertRawProbe($db);
        $statement = $db->prepare('INSERT INTO raw_sources SELECT * FROM raw_sources WHERE source_hash=?');
        $statement->bind_param('s', $hash); $statement->execute();
    }, 1062, '23000');
    $results[] = rejectedProbe($db, 'missing-composite-foreign-key', function() use ($db) {
        $key = 'probe_' . bin2hex(random_bytes(12));
        $stmt = $db->prepare('INSERT INTO public_result_receipts(source_id,acquisition_id,persisted_at,usable_at) VALUES(?,?,?,?)');
        $stamp = '2000-01-01T00:00:00Z'; $stmt->bind_param('ssss', $key, $key, $stamp, $stamp); $stmt->execute();
    }, 1452, '23000');
    foreach (['UPDATE','DELETE'] as $operation) {
        $results[] = rejectedProbe($db, 'immutable-raw-source-' . strtolower($operation), function() use ($db, $operation) {
            $hash = insertRawProbe($db);
            $sql = $operation === 'UPDATE' ? 'UPDATE raw_sources SET source_hash=source_hash WHERE source_hash=?' : 'DELETE FROM raw_sources WHERE source_hash=?';
            $statement = $db->prepare($sql); $statement->bind_param('s', $hash); $statement->execute();
        }, 1644, '45000');
    }
    $results[] = rejectedProbe($db, 'owner-idempotency-unique', function() use ($db) {
        $owner = 'probe_' . bin2hex(random_bytes(10)); $key = 'same_key';
        $stmt = $db->prepare("INSERT INTO product_jobs(id,owner,kind,payload,idempotency_key,status,created_at,updated_at) VALUES(?,?,'probe','{}',?,'queued','2000-01-01','2000-01-01')");
        $id = bin2hex(random_bytes(16)); $stmt->bind_param('sss', $id, $owner, $key); $stmt->execute();
        $id = bin2hex(random_bytes(16)); $stmt->execute();
    }, 1062, '23000');
    $db->begin_transaction();
    try {
        $owner = 'probe_' . bin2hex(random_bytes(10));
        $stmt = $db->prepare("INSERT INTO product_jobs(id,owner,kind,payload,idempotency_key,status,created_at,updated_at) VALUES(?,?,'probe','{}',NULL,'queued','2000-01-01','2000-01-01')");
        $id = bin2hex(random_bytes(16)); $stmt->bind_param('ss', $id, $owner); $stmt->execute();
        $id = bin2hex(random_bytes(16)); $stmt->execute();
        $results[] = ['name' => 'nullable-idempotency-multiple-null', 'passed' => true, 'rolled_back' => true];
    } finally { $db->rollback(); }
    $db->begin_transaction();
    try {
        $base = 'probe_' . bin2hex(random_bytes(10));
        $stmt = $db->prepare('INSERT INTO product_bridge_nonces(nonce,expires) VALUES(?,0e0)');
        foreach ([$base . 'A', $base . 'a', $base . 'a '] as $key) { $stmt->bind_param('s', $key); $stmt->execute(); }
        $results[] = ['name' => 'binary-identity-case-and-trailing-space', 'passed' => true, 'rolled_back' => true];
    } finally { $db->rollback(); }
    if ($profile === 'core-context-1') {
        $results[] = rejectedProbe($db, 'context-duplicate-primary-key', function() use ($db) {
            $id = insertCognitiveProbe($db);
            $statement = $db->prepare("INSERT INTO cognitive_records(kind,record_id,natural_key,fingerprint,payload) VALUES('different_kind',?,'different_key','fingerprint','{}')");
            $statement->bind_param('s', $id); $statement->execute();
        }, 1062, '23000');
        $results[] = rejectedProbe($db, 'context-kind-natural-key-unique', function() use ($db) {
            $id = insertCognitiveProbe($db);
            $statement = $db->prepare('INSERT INTO cognitive_records(kind,record_id,natural_key,fingerprint,payload) SELECT kind,CONCAT(record_id,?),natural_key,fingerprint,payload FROM cognitive_records WHERE record_id=?');
            $suffix = '_probe'; $statement->bind_param('ss', $suffix, $id); $statement->execute();
        }, 1062, '23000');
        $results[] = rejectedProbe($db, 'context-receipt-foreign-key', function() use ($db) {
            $id = 'missing_context:' . bin2hex(random_bytes(32));
            $statement = $db->prepare("INSERT INTO cognitive_receipts(record_id,received_at,persisted_at,usable_at) VALUES(?,'2000-01-01','2000-01-01','2000-01-01')");
            $statement->bind_param('s', $id); $statement->execute();
        }, 1452, '23000');
        foreach (['cognitive_records','cognitive_receipts'] as $table) {
            foreach (['UPDATE','DELETE'] as $operation) {
                $results[] = rejectedProbe($db, 'immutable-' . $table . '-' . strtolower($operation), function() use ($db, $table, $operation) {
                    $id = insertCognitiveProbe($db, true);
                    $sql = $operation === 'UPDATE' ? 'UPDATE ' . ident($table) . ' SET record_id=record_id WHERE record_id=?'
                        : 'DELETE FROM ' . ident($table) . ' WHERE record_id=?';
                    $statement = $db->prepare($sql); $statement->bind_param('s', $id); $statement->execute();
                }, 1644, '45000');
            }
        }
    }
    return $results;
}

$options = getopt('', ['apply','validate-only','config:','bundle:','schema:','output:','reviewed-manifest-sha256:']);
$record = ['passed' => false, 'schema_created' => false, 'application_authority' => 'sqlite',
    'cutover' => false, 'existing_schemas_modified' => false, 'schema_preserved_after_test' => true];
$output = null; $db = null;
try {
    demand(isset($options['bundle'], $options['schema'], $options['reviewed-manifest-sha256'])
        && (isset($options['apply']) !== isset($options['validate-only'])), 'EXPLICIT_ACTION_AND_REVIEWED_ARGUMENTS_REQUIRED');
    if (isset($options['apply'])) { demand(isset($options['config'], $options['output']), 'APPLY_CONFIG_AND_OUTPUT_REQUIRED'); }
    $root = realpath(__DIR__ . '/../..');
    $bundle = localPath($options['bundle'], $root); $schema = $options['schema'];
    if (isset($options['apply'])) { $output = localPath($options['output'], $root); $config = localPath($options['config'], $root); }
    demand((bool) preg_match('/\Adragonhydra_migration_[a-z0-9][a-z0-9_]{0,42}\z/D', $schema), 'NEW_TEST_SCHEMA_REQUIRED');
    demand((bool) preg_match('/\A[a-f0-9]{64}\z/D', $options['reviewed-manifest-sha256']), 'REVIEWED_MANIFEST_HASH_REQUIRED');
    demand(hash_file('sha256', $bundle . '/manifest.json') === $options['reviewed-manifest-sha256'], 'REVIEWED_MANIFEST_HASH_MISMATCH');
    $manifest = decode($bundle . '/manifest.json');
    $profile = schemaProfile($manifest);
    demand($manifest['status'] === 'mariadb_staging_script_only'
        && $manifest['schema'] === $schema && $manifest['executed'] === false && $manifest['cutover'] === false && $manifest['backend_changed'] === false, 'UNEXECUTED_STAGING_MANIFEST_REQUIRED');
    artifact($bundle, $manifest['sql'], 'migration.sql');
    $statementPath = artifact($bundle, $manifest['statements'], 'statements.json');
    demand(filesize($statementPath) <= 128 * 1024 * 1024, 'STATEMENT_BUNDLE_TOO_LARGE');
    $statements = decode($statementPath);
    demand(array_is_list($statements) && count($statements) === $manifest['statements']['count'], 'STATEMENT_COUNT_MISMATCH');
    validateStatements($statements, $manifest['mapping'], $schema, $profile);
    $record['schema_profile'] = $profile;
    $record['schema'] = $schema; $record['reviewed_manifest_sha256'] = $options['reviewed-manifest-sha256'];
    if (isset($options['validate-only'])) {
        $record['passed'] = true; $record['database_connected'] = false;
        $record['validated_statements'] = count($statements);
        return;
    }
    $cfg = decode($config);
    $state = localPath($cfg['state_root'], $root); $install = localPath($cfg['install_root'], $root);
    demand(realpath(dirname($config)) === $state && $cfg['kernel_backend'] === 'sqlite'
        && !in_array($schema, [$cfg['db_name'], $cfg['core_db_name']], true), 'PRIVATE_INSTANCE_CONFIG_MISMATCH');
    $db = new mysqli('127.0.0.1', 'root', $cfg['root_password'], '', (int) $cfg['database_port']); $db->set_charset('utf8mb4');
    $server = $db->query('SELECT @@version AS version,@@port AS port,@@datadir AS datadir,@@basedir AS basedir,@@bind_address AS bind_address,CURRENT_USER() AS authenticated_identity,@@innodb_page_size AS page_size,@@max_allowed_packet AS max_allowed_packet,@@auto_increment_increment AS auto_increment_increment,@@auto_increment_offset AS auto_increment_offset')->fetch_assoc();
    $normalize = fn($value) => strtolower(rtrim(str_replace('\\','/', $value), '/'));
    demand((int) $server['port'] === (int) $cfg['database_port'] && $server['bind_address'] === '127.0.0.1'
        && $normalize($server['datadir']) === $normalize($state . '/mysql-data')
        && $normalize($server['basedir']) === $normalize($install . '/web/mariadb'), 'PRIVATE_INSTANCE_OWNERSHIP_MISMATCH');
    demand(version_compare($server['version'], '10.11', '>=') && (int) $server['page_size'] >= 16384
        && (int) $server['max_allowed_packet'] >= $manifest['target_requirements']['minimum_max_allowed_packet_bytes']
        && (int) $server['auto_increment_increment'] === 1 && (int) $server['auto_increment_offset'] === 1, 'TARGET_RUNTIME_REQUIREMENTS_FAILED');
    $record['server'] = $server;
    $exists = selectRows($db, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=?', $schema);
    demand(count($exists) === 0, 'TEST_SCHEMA_ALREADY_EXISTS');
    $record['stage'] = 'apply';
    foreach ($statements as $index => $sql) {
        $record['statement_index'] = $index;
        $result = $db->query($sql); if ($result instanceof mysqli_result) { $result->free(); }
        if ($index === 5) { $record['schema_created'] = true; }
    }
    unset($statements);
    demand($db->query('SELECT DATABASE()')->fetch_row()[0] === $schema, 'SELECTED_SCHEMA_MISMATCH');
    $record['executed_statements'] = $manifest['statements']['count'];
    $record['metadata_before_probes'] = metadata($db, $schema);
    $record['stage'] = 'export'; $record['tables'] = [];
    foreach ($manifest['mapping']['tables'] as $table) {
        $path = $output . '/rows/' . $table['name'] . '.jsonl';
        $count = rowsFile($db, $table, $path);
        demand($count === $table['row_count'], 'IMPORTED_ROW_COUNT_MISMATCH');
        $record['tables'][] = ['name' => $table['name'], 'row_count' => $count, 'path' => 'rows/' . $table['name'] . '.jsonl', 'sha256' => hash_file('sha256', $path)];
    }
    $record['stage'] = 'rollback-probes'; $record['probes'] = probes($db, $profile);
    $record['metadata_after_probes'] = metadata($db, $schema);
    foreach ($manifest['mapping']['tables'] as $table) {
        demand((int) $db->query('SELECT COUNT(*) FROM ' . ident($table['name']))->fetch_row()[0] === $table['row_count'], 'PROBE_ROLLBACK_ROW_COUNT_MISMATCH');
    }
    $record['stage'] = 'complete'; $record['passed'] = true;
} catch (Throwable $failure) {
    if ($db) { try { $db->rollback(); } catch (Throwable) {} }
    $record['error'] = $failure instanceof mysqli_sql_exception ? 'MARIADB_OPERATION_FAILED' : $failure->getMessage();
    $record['exception_class'] = get_class($failure); $record['error_number'] = $failure->getCode();
    if ($failure instanceof mysqli_sql_exception) { $record['sqlstate'] = $failure->getSqlState(); }
} finally {
    if ($db) { $db->close(); }
    $record['verified_at'] = gmdate('c');
    if ($output && is_file($output . '/php-result.json') && !is_link($output . '/php-result.json')) {
        file_put_contents($output . '/php-result.json', json_encode($record, JSON_THROW_ON_ERROR | JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }
    echo json_encode(['passed' => $record['passed'], 'schema' => $record['schema'] ?? null,
        'schema_created' => $record['schema_created'], 'error' => $record['error'] ?? null], JSON_THROW_ON_ERROR) . "\n";
}
exit($record['passed'] ? 0 : 1);
