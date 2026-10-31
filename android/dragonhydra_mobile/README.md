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

## Production signing preparation

An authorized publisher signing identity has not been supplied. The current
production preflight therefore reports `requires_signing_configuration`, exits
with code 2, and creates no key, APK or build files:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRA'
& '.\runtime\server-env\Scripts\python.exe' -B scripts\prepare_android_production.py
```

For a future authorized publisher identity, supply these values through the
protected environment of the build process. Do not put passwords in command
arguments, a checked-in `key.properties`, source files or shell history.

| Environment variable | Required value |
|---|---|
| `DRAGONHYDRA_ANDROID_KEYSTORE` | Absolute path to that existing keystore |
| `DRAGONHYDRA_ANDROID_KEY_ALIAS` | Its publisher private-key alias |
| `DRAGONHYDRA_ANDROID_STORE_PASSWORD` | Keystore password |
| `DRAGONHYDRA_ANDROID_KEY_PASSWORD` | Private-key password |
| `DRAGONHYDRA_ANDROID_CERT_SHA256` | Independently confirmed public certificate SHA-256, 64 hex characters or colon-separated bytes |

The read-only preflight checks the certificate and private-key entry using the
existing JDK 21 keytool with `-storepass:env`; it does not verify the private-key
password or create an identity. Environment password options are documented in
the [JDK keytool reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html#common-command-options).

The Gradle production profile requires a separate explicit
`DRAGONHYDRA_ANDROID_PRODUCTION_SIGNING=1`. It opens the existing private key,
checks the key password, certificate validity and exact expected fingerprint,
and rejects the actual established debug certificate or Android Debug subject.
Keystore filenames and aliases are labels, so they do not determine key identity.
Production configuration fails before compilation if those checks fail; it does
not fall back to debug signing. Keep Gradle configuration caching disabled and
use a disposable build process for publisher credentials. Without that opt-in,
the existing development signing path remains unchanged. No production APK was
built or uploaded in this preparation increment.

Android signing and update compatibility depend on the distribution identity.
The existing debug-signed alpha does not establish compatibility with a new
publisher certificate; review that transition before a production release.
See [Android signing configuration](https://developer.android.com/build/build-variants#signing)
and [app signing and update keys](https://developer.android.com/studio/publish/app-signing).

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
