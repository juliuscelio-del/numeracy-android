GNHS NUMERACY DRILL - ANDROID / PHONE
=====================================
Start screen: TEACHER (PIN, this phone runs the drill) or STUDENT (type the teacher's address to join).
The phone can be the teacher's server (same Wi-Fi, or its own hotspot) or just a student.
Data is saved inside the app. Keep the app open and the screen on while the class works.

BUILD THE APK ON GITHUB (no Android tools needed)
  1. Create a new repository on github.com and upload THIS folder (with the hidden .github folder):
       cd <this folder>
       git init && git add . && git commit -m "android"
       git branch -M main
       git remote add origin https://github.com/<you>/<repo>.git
       git push -u origin main
  2. Open the Actions tab. The first build takes 20-40 minutes (it downloads the Android tools).
  3. Download "Android-apk" under Artifacts, unzip it: that is the .apk.

INSTALL
  Copy the .apk to the phone, open it, allow "install unknown apps" for your file manager.
