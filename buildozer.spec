[app]
title = Alias Online
package.name = aliasonline
package.domain = com.aliasonline

source.dir = .
source.include_exts = py,png,jpg,jpeg,webp,bmp,ttf,kv,atlas,txt,csv,json,md,env,local
source.exclude_dirs = venv,.git,__pycache__,bin,dist,build,.buildozer
source.exclude_patterns = *.pyc,*.pyo,data/*.db,data/_*.db

version = 1.1.0
requirements = python3,kivy==2.3.1,pyjnius,filetype
orientation = portrait
fullscreen = 0

android.api = 34
android.minapi = 24
android.sdk = 20
android.ndk = 25b
android.ndk_api = 24
android.accept_sdk_license = True
android.enable_androidx = True
android.permissions = INTERNET,ACCESS_NETWORK_STATE,VIBRATE,READ_MEDIA_IMAGES,RECORD_AUDIO
android.archs = arm64-v8a,armeabi-v7a,x86_64
android.debug_artifact = apk
android.release_artifact = apk
android.allow_backup = False

presplash.filename = image/lobby_minimal.png
presplash.color = #4fa4d6

[buildozer]
log_level = 2
warn_on_root = 1
