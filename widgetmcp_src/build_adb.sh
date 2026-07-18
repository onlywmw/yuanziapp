#!/bin/bash
# ADB 构建: 在源码目录直接运行即可
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== 1. aapt2 ==="
rm -rf comp gen classes && mkdir comp gen classes
find res -type f | while read f; do aapt2 compile -o comp "$f" 2>&1; done
aapt2 link -o base.apk --manifest AndroidManifest.xml -I android.jar --java gen --version-code 1 --version-name 1.0.0 comp/*.flat

echo "=== 2. kotlinc ==="
CP=android.jar
for jar in libs/*.jar; do CP="$CP:$jar"; done
kotlinc -cp "$CP" -d classes -jvm-target 17 \
  gen/com/nous/widgetmcp/R.java \
  $(find java -name "*.kt" | sort)

echo "=== 3. d8 ==="
d8 --lib android.jar --min-api 26 $(find classes -name "*.class") libs/*.jar --output .

echo "=== 4. pack+sign ==="
rm -rf apk_out && mkdir apk_out && cd apk_out
unzip -o ../base.apk >/dev/null && cp ../classes.dex . && rm -rf META-INF
zip -r -0 ../u.apk resources.arsc >/dev/null
zip -r ../u.apk AndroidManifest.xml classes.dex res/ >/dev/null
zipalign -p -f 4 ../u.apk ../ua.apk
apksigner sign --ks ~/.android/debug.keystore --ks-pass pass:android ../ua.apk

echo "=== 5. install ==="
cd "$DIR"
# proot 内看不到 /data/local/tmp，经 Termux home 中转
OUT="/data/data/com.termux/files/home/ua.apk"
su -c "cp $PWD/ua.apk $OUT && chmod 644 $OUT"
# 覆盖安装保留用户数据（key/绑定），不卸载
su -c "pm install -r $OUT"
su -c "rm -f $OUT"
su -c "am force-stop com.nous.widgetmcp; am start -n com.nous.widgetmcp/.MainActivity"
echo "DONE → $(ls -la ua.apk)"
