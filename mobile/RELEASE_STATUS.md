# Native release status

The source contains the Capacitor configuration and Android project. **The APK that was previously committed under `deliverables/` pointed to a serverless backend that cannot send pump commands and must not be distributed.**
Rebuild after setting `VITE_API_BASE` to your HTTPS backend (native builds fail fast if it is missing): `npm run build && npx cap sync android`, then build in Android Studio.
Android app data backup is disabled (`allowBackup=false`). iOS requires macOS/Xcode and Apple signing; no IPA is provided.
