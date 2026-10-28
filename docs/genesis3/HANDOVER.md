# GENESIS-3 Android successor handover

This alpha adds an offline Flutter Android companion without replacing the
GENESIS-2 Python laboratory. Start with the private repository's
`genesis3-android-alpha` branch and the GENESIS-3 release assets; the existing
`genesis2-checkpoint` branch and `v0.2.0+genesis2.checkpoint` tag remain the
desktop preservation checkpoint. See `docs/handover/START-HERE.md` for the
Python system and its recovery archive.

## Source and build

The mobile project is `android/dragonhydra_mobile/`. Dart UI and computations
are in `lib/main.dart` and `lib/simulation.dart`; public source fetching is in
`lib/public_sources.dart`; credential connection tests are in
`lib/connections.dart`. Android Keystore encryption and platform URL opening
are implemented in `android/app/src/main/kotlin/.../SecureConnections.kt`.
Tests are in `test/`; the bundled snapshot and provider registry are in
`assets/`. The fixture exporter and evidence tests are in `android/fixtures/`.

The observed development toolchain is Flutter 3.47.8, Dart 3.13.7, Android SDK
build tools 36.0.0, JDK 21.0.8 and Gradle wrapper 9.3.1. The requested debug
ARM64 build uses the local debug signing key, suitable for test installation;
it is not a production signing identity. Signing keys and credentials are not
release source. To build, configure the Flutter and Android SDK paths on the
successor machine and execute:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRA\android\dragonhydra_mobile'
flutter pub get
flutter analyze
flutter test
flutter build apk --debug --target-platform android-arm64
```

The generated APK is normally `build/app/outputs/flutter-apk/app-debug.apk`.
The artifact published with the release is renamed
`DRAGONHYDRA-GENESIS3-ANDROID-ARM64.apk`. Consult the release build and test
reports for the final observed build, manifest, ABI, signature, emulator and
device verification. The final ARM64 APK built and its v2 debug signature was
verified; `flutter analyze` passed and 10 Flutter tests passed. It installed and
launched on an API-37 x86_64 emulator using ARM64 translation. With emulator
Wi-Fi and mobile data disabled, Home rendered the bundled snapshot. A synthetic
provider key was saved, its preference contained no plaintext key, and the key
was removed successfully. This does not verify real-device Keystore behavior.
The Vivo V2450 was not connected or tested.

## Current capabilities and evidence

The app starts without an account and presents an archived football forecast,
historical fixture results, source-labelled historic odds, a binary-odds and
bankroll research calculator, a read-only cognitive-memory view and provider
directory. The calculator is conditional on user input; it is not automatic
betting or a validated prediction of future performance. The app does not run
Python model training or desktop database services. The bundled asset is a
read-only JSON snapshot, not a mobile SQLite database; no local evidence store
or incremental synchronization is implemented.

The forecast and odds are from **different fixtures**. Historic source labels
do not establish quote times, simultaneous availability, verified provider
independence or settlement scope. Forecast probabilities are uncalibrated and
the stored decision cutoff is unknown. Present-knowledge holdout metrics are
not a historical operational replay. The original data source identifiers,
receipt clocks, hashes, evidence IDs, transformations and model records are
retained in the asset. See [OFFLINE-DATA.md](OFFLINE-DATA.md) for the exporter,
source attribution, data rights, provenance and verification commands.

## Providers, accounts and secrets

The [provider registry](../../android/dragonhydra_mobile/assets/provider-manifest.json)
and [provider evidence](PROVIDERS.md) separate documentation, implemented
adapters, credential configuration, genuine requests and durable imports.
OpenFootball and StatsBomb public endpoints were exercised by the Dart adapter
on Windows; mobile fetches are bounded and in memory only. A fetch is not a
durable database import. API-FOOTBALL, football-data.org and The Odds API have key entry,
Android Keystore-backed credential encryption and read-only connection tests;
mocked tests do not constitute successful user authentication. Credentials
must be supplied by the user through the respective provider's official
registration workflow and saved on the device. The app does not bundle keys. The
Odds API requires a query-string credential, which provider or intermediary logs
may retain; use restricted keys where available. No authenticated live request
was verified for these three providers.

Other catalog entries are discovery and documentation, not working authorized
adapters unless the manifest and final release report say otherwise. ADMIRAL
has no verified user-accessible official API. Betfair requires its own API
authorization; Pinnacle access is account-specific. Do not reuse website or
Google credentials as provider API authorization. Keystore behavior on the
actual Vivo remains to be tested.

Google Sign-In is not configured or verified. The OpenAI screen links to the
official API dashboard; no OpenAI key-entry flow, authenticated request, paid
call, model selection or report analysis is implemented. OpenAI Platform and
Codex CLI credentials are separate, and Codex credentials must not be extracted.
No Codex installation or configuration was changed.

## Next work

1. Test installation, navigation, layout, offline behavior, Keystore storage,
   key removal and provider errors on the actual ARM64 phone. Record Android
   version and device results; do not claim device compatibility beforehand.
2. Implement an append-only mobile evidence store with raw response bytes,
   source/revision IDs, receipt/persistence/earliest-usable clocks and hashes.
   Verify corrections, duplicates and exact cutoff behavior before using fetched
   records as research evidence.
3. Add authenticated provider data adapters and synchronization incrementally under
   their official terms. Verify genuine user-authorized
   responses and quota handling without logging credentials. Keep provider
   state distinct from availability and entitlement to each data product.
4. Establish verified cross-provider event, line and settlement mappings;
   expose overround or model-versus-market comparisons only for compatible
   evidence with valid timing. Keep source and derived provenance intact.
5. Treat Google Sign-In and optional OpenAI analysis as separate projects with
   supported authorization, explicit consent, schema validation and paid-usage
   controls. Verify neural modeling separately in the Python laboratory.
