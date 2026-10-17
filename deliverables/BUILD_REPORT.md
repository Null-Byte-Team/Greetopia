# Greetopia — Android APK Build Report

**Application Name:** Greetopia  
**Package Identifier:** `com.greetopia.plantcare`  
**Version:** 1.0 (Version Code: 1)  
**Build Target:** Android 15 (API Level 35)  
**Minimum SDK:** Android 6.0 Marshmallow (API Level 23)  
**Build Type:** Debug (`assembleDebug`)  
**Signing Status:** Android Debug Keystore signed (valid for device installation & side-loading)  
**Date of Build:** October 17, 2026  

---

## 1. Deliverable Artifacts

| File Name | Path | Size | SHA-256 Checksum |
| :--- | :--- | :--- | :--- |
| **Greetopia-debug.apk** | `D:\Greetopia\deliverables\Greetopia-debug.apk` | **4,279,339 bytes** (~4.08 MB) | `20db4bae2c776a29796e8e3a2afeb26580102f7f64bdc79a9fe7f488a7ff998a` |
| **Website Direct Download** | `D:\Greetopia\frontend\public\downloads\greetopia.apk` | **4,279,339 bytes** (~4.08 MB) | `20db4bae2c776a29796e8e3a2afeb26580102f7f64bdc79a9fe7f488a7ff998a` |
| **Production Dist Download** | `D:\Greetopia\frontend\dist\downloads\greetopia.apk` | **4,279,339 bytes** (~4.08 MB) | `20db4bae2c776a29796e8e3a2afeb26580102f7f64bdc79a9fe7f488a7ff998a` |

---

## 2. Environment & Toolchain Details

- **Host Operating System:** Windows 10/11 x64
- **Node.js:** v22.14.0
- **npm:** 10.9.2
- **Java / JDK:** Eclipse Adoptium OpenJDK 21.0.12.1+1 LTS (`C:\Users\Ghost_Byte55\jdk-21\jdk-21.0.12.1+1`)
- **Android SDK:** `C:\Users\Ghost_Byte55\AppData\Local\Android\Sdk`
  - Platforms: `android-35`, `android-37.0`
  - Build Tools: `34.0.0`, `36.0.0`
  - Platform Tools: `adb` v35.0.2
- **Gradle:** 8.11.1 (via project `gradlew.bat` wrapper)
- **Capacitor:** v7.4.3 (`@capacitor/core`, `@capacitor/cli`, `@capacitor/android`)
- **Frontend Stack:** React 19, TypeScript 5.8, Vite 6.4

---

## 3. Build Process Executed

1. **Frontend Compilation:**
   ```bash
   cd D:\Greetopia\frontend
   npm run build
   ```
   Compiles React/TypeScript into optimized static bundle in `dist/`.

2. **Capacitor Android Project Generation & Asset Sync:**
   ```bash
   npx cap add android
   npx cap sync android
   ```
   Copies web bundle into `android/app/src/main/assets/public/` and writes `capacitor.config.json`.

3. **Android Native Compilation:**
   ```bash
   cd D:\Greetopia\frontend\android
   gradlew.bat assembleDebug
   ```
   Uses JDK 21 to compile Capacitor Android modules, desugar Java bytecode, execute `d8` DEX generation, merge Android resources, and assemble `app-debug.apk`.

4. **Deliverables Placement & Website Download Integration:**
   - Saved primary build deliverable to `deliverables/Greetopia-debug.apk`.
   - Placed copy in `frontend/public/downloads/greetopia.apk` and `frontend/dist/downloads/greetopia.apk`.
   - Updated website UI (`frontend/src/App.tsx`) to link the download button directly to `/downloads/greetopia.apk` with `download="Greetopia.apk"`.

---

## 4. Verification & Static Analysis Results

Inspected with Android Asset Packaging Tool (`aapt dump badging`):
- **Application Label:** `Greetopia`
- **Package Name:** `com.greetopia.plantcare`
- **Launcher Icon:** Adaptive icon present (`res/mipmap-anydpi-v26/ic_launcher.xml`, `ic_launcher_round.xml`, PNG fallbacks for `mdpi`, `hdpi`, `xhdpi`, `xxhdpi`, `xxxhdpi`)
- **Splash Screen:** Splash screen drawables packaged for portrait and landscape (`drawable-port-*`, `drawable-land-*`)
- **Android Permissions:**
  - `android.permission.INTERNET`
  - `com.greetopia.plantcare.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`
  - **No excessive or invasive permissions requested.**
- **Secret & Credential Leak Check:** Verified 448 packaged files; verified zero `.env` files, no Gemini API keys, passwords, or MQTT credentials bundled into APK.
- **Backend Connectivity URL:** Configured with fallback to `https://greetopia.vercel.app/api/v1` in `frontend/src/api.ts` (replaces unreachable mobile `localhost:5000`).

---

## 5. Website Download Integration

The website's download button in `App.tsx` is integrated:
```tsx
const androidDownload = (import.meta.env.VITE_ANDROID_DOWNLOAD_URL as string | undefined) || '/downloads/greetopia.apk';
```
```tsx
<a className="download-choice" href={androidDownload} download="Greetopia.apk">
  <Download size={14} /> APK
</a>
```
When deployed to Vercel or any static host, users navigating to the website can click **"Download app"** → **"APK"** to directly download the compiled Android APK.

---

## 6. How to Install on Android Device

1. Download `Greetopia-debug.apk` directly to your Android device or transfer via USB:
   ```bash
   adb install D:\Greetopia\deliverables\Greetopia-debug.apk
   ```
2. If opening directly on Android:
   - Tap the downloaded `.apk` file.
   - Allow "Install unknown apps" for your browser / file manager if prompted.
   - Tap **Install**.
3. Launch **Greetopia** from your home screen or app drawer.
