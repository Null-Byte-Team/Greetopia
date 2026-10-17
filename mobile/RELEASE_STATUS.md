# Native release status

This delivery contains the shared React application, Capacitor configuration, Android/iOS platform-specific styling, PWA install support, and build instructions. It does **not** contain a built APK or signed IPA.

The current execution environment has no Android SDK/Gradle installation and no macOS/Xcode environment, so producing a tested APK and a signed iOS IPA here is not possible. The iOS IPA additionally requires valid Apple signing/provisioning. Do not publish the website download links until real release artifacts have been generated and tested.

After installing dependencies, run `npm run mobile:init` in `frontend`, then follow `README.md` for Android Studio and Xcode release steps. Set `VITE_ANDROID_DOWNLOAD_URL` and `VITE_IOS_DOWNLOAD_URL` to the hosted artifacts before building/deploying the website so its Download app dialog serves the actual files.
