[app]
title = Numeracy Drill
package.name = gnhsnumeracy
package.domain = ph.edu.gnhs
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.1
requirements = python3,kivy==2.3.0,pyjnius,android,openssl,certifi
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #FFFFFF

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WAKE_LOCK,REQUEST_INSTALL_PACKAGES
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.extra_manifest_application_arguments = ./extra_manifest_application_arguments.xml

# Release builds must produce an APK (newer Buildozer defaults to AAB)
android.release_artifact = apk

# Pin the Android build toolkit to a release that still uses Python 3.11 (the newest one needs Python 3.14 wheels that do not exist yet)
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
