# DRAGONHYDRA Android alpha

Flutter companion for offline exploration of the GENESIS-2 football research
snapshot. It includes an archived forecast, historical odds, conditional
simulation, cognitive memory and a provider catalog. It does not run Python
training or place bets. Data origin and cutoff limitations are shown in-app.

The Home screen's **Connect to DRAGONHYDRA server** action opens a configurable
API v1 client. Enter the root HTTPS address of your server or public read-only
gateway. Enter a server-issued pairing token only for an authenticated private
endpoint. Successful connection shows retained canonical matches; select one to
open its teams, standings and available statistical probabilities. Connection
failures and rejected authentication have a visible retry action. The address
and token use the existing Android Keystore-backed encrypted settings.

On a phone, `localhost` refers to the phone. Use the configured LAN HTTPS server
address for ordinary use. HTTP is permitted only for explicit development
forwarding to `127.0.0.1`, `localhost` or the Android emulator host `10.0.2.2`.
No temporary tunnel address or developer pairing token is embedded in the APK.
The original offline screens remain available without a server or account.

Build metadata is provided through `DRAGONHYDRA_SOURCE_SHA` and
`DRAGONHYDRA_VERSION` Dart defines and shown in Settings/About. The established
`ai.dragonhydra.mobile` application ID remains unchanged. The earlier Android
alpha used a local Android Debug certificate. Until an authorized production
keystore exists, a newly built APK can be distributed only as an explicitly
development-signed prerelease after the same certificate and upgrade behavior
have been verified. The build script refuses a missing existing debug keystore
and verifies the final APK rather than silently accepting a replacement signer.

From PowerShell 7 with Flutter 3.47.8, Android SDK build-tools 36.0.0 and JDK
21 configured:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRA\android\dragonhydra_mobile'
flutter pub get
flutter analyze
flutter test
flutter build apk --debug --target-platform android-arm64
```

The output is `build/app/outputs/flutter-apk/app-debug.apk`. It is a debug-signed
ARM64 test build, not a production release. The Gradle wrapper selects the
9.3.1 binary distribution. Read `../../docs/genesis3/HANDOVER.md` and
`../../docs/genesis3/PROVIDERS.md` for actual verification, data provenance,
credentials and known gaps.
