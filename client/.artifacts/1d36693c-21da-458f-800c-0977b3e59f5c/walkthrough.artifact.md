# Walkthrough - Installation and Blocking Fixes

I have applied changes to ensure the application can be installed and to reduce the likelihood of it being blocked by system heuristics, while maintaining all its core functionalities (TCP streaming and RTMP live streaming).

## Changes Made

### Signing Configuration
- **[app/build.gradle](file:///F:/coding/potato-monitor-desk/client/app/build.gradle)**: Configured the `release` build type to use the `debug` signing key.
    > [!NOTE]
    > This allows you to install the "Release" version of the APK for testing without needing a production keystore. Unsigned APKs are often blocked from installation by Android's security settings.

### Manifest and Resources
- **[AndroidManifest.xml](file:///F:/coding/potato-monitor-desk/client/app/src/main/AndroidManifest.xml)**:
    - Set `android:exported="true"` for `NotificationFilterService` to ensure the system can bind to it correctly.
    - Added `android:description` to provide a clear explanation of why the Notification Listener is needed.
- **[strings.xml](file:///F:/coding/potato-monitor-desk/client/app/src/main/res/values/strings.xml)**: Added a descriptive string for the notification filter service to improve "legitimacy" in the eyes of security scanners.

## How to Install and Bypass Blocking

Even with these fixes, because your app uses sensitive APIs (`MediaProjection` and `NotificationListener`), Google Play Protect might still show a warning. Here is how to handle it:

1. **Play Protect Warning**: If you see a "Blocked by Play Protect" popup:
    - Tap on **"More details"** (or the small arrow).
    - Select **"Install anyway"**.
2. **Notification Access (Android 13+)**: If the system says "Restricted setting" when you try to enable Notification Access:
    - Go to **Settings > Apps > Potato Monitor Desk**.
    - Tap the **three dots** in the top right corner.
    - Select **"Allow restricted settings"**.
    - Now you can go back and enable the Notification Access.

## Verification Results
- **Build Status**: Both `assembleDebug` and `assembleRelease` tasks finished successfully.
- **Functionality**: The logic for TCP reception and RTMP streaming remains untouched.
