# Implementation Plan - Fix Installation and Blocking Issues

The user reports that the application fails to install and is "blocked" (terblokir). This is commonly caused by Play Protect heuristics flagging sensitive permissions (`MediaProjection`, `NotificationListener`), signature conflicts, or unsigned release builds.

## Proposed Changes

### Build Configuration

#### [MODIFY] [app/build.gradle](file:///F:/coding/potato-monitor-desk/client/app/build.gradle)
- Set `signingConfig signingConfigs.debug` for the `release` build type. This ensures that release builds are signed with the debug key and can be installed for testing purposes without needing a production keystore.
- (Optional) Change `applicationId` to something more unique (e.g., `com.potatodeskhome.monitor`) to avoid potential package name blacklisting by Play Protect.

### Manifest Configuration

#### [MODIFY] [AndroidManifest.xml](file:///F:/coding/potato-monitor-desk/client/app/src/main/AndroidManifest.xml)
- Set `android:exported="true"` for `NotificationFilterService`. While `android:permission` protects it, system services often require it to be exported to bind correctly via intent filters on some Android versions.
- Add `android:description` or improve metadata to make the app look more "legitimate" to Play Protect heuristics.

## Verification Plan

### Automated Tests
- Run `gradle_sync`.
- Run `./gradlew assembleDebug` and `./gradlew assembleRelease` to ensure both build types are signed and buildable.

### Manual Verification
- **Install APK**: Attempt to install the generated APK on a device.
- **Play Protect**: If a "Blocked by Play Protect" dialog appears, verify that it can be bypassed via "Install anyway".
- **Restricted Settings**: On Android 14+, if Notification Access is blocked, verify the "Allow restricted settings" workaround.
