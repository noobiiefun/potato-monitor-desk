# Add project specific ProGuard rules here.
# By default, the flags in this file are appended to flags specified
# in F:\android studio\sdk/tools/proguard/proguard-android.txt
# You can edit the include path and order by changing the proguardFiles
# directive in build.gradle.

# Media3 rules (usually bundled, but added for safety)
-keep class androidx.media3.common.** { *; }
-keep class androidx.media3.extractor.** { *; }

# RootEncoder rules
-keep class com.pedro.** { *; }
-keep class com.github.pedroSG94.** { *; }

# Keep native methods and classes with native methods
-keepclasseswithmembernames class * {
    native <methods>;
}
