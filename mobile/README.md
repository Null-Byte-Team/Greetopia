# Greetopia mobile apps

The Android and iOS apps use the same React UI and API as the website through Capacitor. Native platform styling is applied with `platform-android` and `platform-ios` root classes. The native platform folders are generated after dependencies install by running `npm run mobile:init` (or `npx cap add android` and `npx cap add ios`). iOS build/signing requires macOS/Xcode.

## Required before building

1. Deploy the FastAPI backend to an HTTPS URL reachable from the phone.
2. In `frontend/.env`, set `VITE_API_BASE=https://YOUR_API_HOST/api/v1`. Do not use localhost for a phone build.
3. Run `npm install` in `frontend`.
4. Run `npm run mobile:init` once to generate the Android and iOS platform projects.
5. Run `npm run cap:sync` to build the shared UI and sync it into native projects.
6. Android: run `npm run android:open`, then use Android Studio to build a debug APK or signed release APK.
7. iOS: on macOS with Xcode, run `npm run ios:open`, configure signing/team, then archive and export a signed IPA. An IPA cannot be built or installed as a normal download without Apple signing/provisioning.

## Gemini keys

Put Gemini credentials only in the backend environment (`backend/.env` or the deployment secret manager). `GEMINI_CHAT_API_KEY` is used for chat; `GEMINI_ANDROID_API_KEY` and `GEMINI_IOS_API_KEY` can separately meter photo-analysis calls originating from the respective apps; `GEMINI_API_KEY` is a general fallback for camera/server analysis. The browser/mobile app must call the backend. Do not put any Gemini key in `VITE_*`, TypeScript, an Android resource, or an iOS plist. Mobile binaries can be reverse-engineered. The platform header is only a routing hint, not authentication.

## Website download button

The website's **Download app** button supports hosted release links using `VITE_ANDROID_DOWNLOAD_URL` and `VITE_IOS_DOWNLOAD_URL`. These are intentionally blank until real, signed release files have been built and hosted. It can offer PWA installation in supported Android browsers. For iPhone, deploy over HTTPS and use Share → Add to Home Screen until a signed native release is available.

## Styling

- Android: Material-inspired rounded surfaces, dynamic accent colors, larger touch targets and Android-style navigation.
- iOS: translucent glass panels, backdrop blur, safe-area spacing, soft highlights and iOS-like rounded controls.

These styles are a platform adaptation of the existing Greetopia UI, not a claim that the apps are official Google or Apple designs.
