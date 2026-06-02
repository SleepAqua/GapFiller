Android build instructions — YahtzeeSim

Prerequisites
- Install Android Studio (recommended) or have JDK + Gradle installed.

Build (Android Studio)
1. Open the `android_app` folder in Android Studio.
2. Let Gradle sync and install recommended SDK/NDK components.
3. Select a device or emulator and click Run to install the debug APK.

Build (command line)
1. From this folder run Gradle wrapper (if you don't have one, install Gradle or open in Android Studio):

```bash
./gradlew :app:assembleDebug
```

2. The debug APK will be in `app/build/outputs/apk/debug/app-debug.apk`.

Release
1. Configure signing in Gradle (create a keystore and set signing configs) then:

```bash
./gradlew :app:assembleRelease
```

Notes on performance
- The simulator uses coroutines and runs per-strategy chunks in parallel. For large runs (>= 1,000,000 games) use larger `chunk` sizes to reduce UI overhead and enable background processing.
- Consider using native C/C++ for extreme performance or benchmarking; current Kotlin implementation should use multiple cores via coroutines.

Usage in app
- Paste or edit strategy JSON in the editor, press "Start" to run a simulation, and watch the live animated bars.
- Use the Save/Load buttons to store strategy JSON to internal storage.
