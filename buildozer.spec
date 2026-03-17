[app]
title = Alias Online
package.name = aliasonline
package.domain = com.aliasonline

source.dir = .
source.include_exts = py,png,jpg,jpeg,ttf,kv,atlas
source.exclude_dirs = venv,.git,__pycache__,bin,dist,build,.buildozer
source.exclude_patterns = *.pyc,*.pyo

version = 0.1.0
requirements = python3,kivy==2.3.1
orientation = portrait
fullscreen = 1

android.permissions = INTERNET,ACCESS_NETWORK_STATE,VIBRATE,READ_EXTERNAL_STORAGE,READ_MEDIA_IMAGES
android.archs = arm64-v8a, armeabi-v7a
android.debug_artifact = apk
android.release_artifact = aab

presplash.filename = image/lobby.png

[buildozer]
log_level = 2
warn_on_root = 1
