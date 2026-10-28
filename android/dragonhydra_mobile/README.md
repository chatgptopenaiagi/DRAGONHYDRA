# DRAGONHYDRA Android alpha

Flutter companion for offline exploration of the GENESIS-2 football research
snapshot. It includes an archived forecast, historical odds, conditional
simulation, cognitive memory and a provider catalog. It does not run Python
training or place bets. Data origin and cutoff limitations are shown in-app.

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
