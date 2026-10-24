[app]
title = Numeracy Drill
package.name = gnhsnumeracy
package.domain = ph.edu.gnhs
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.3.0,pyjnius,android
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WAKE_LOCK
android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.extra_manifest_application_arguments = ./extra_manifest_application_arguments.xml

[buildozer]
log_level = 2
warn_on_root = 1
