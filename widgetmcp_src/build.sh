#!/bin/bash
# 一键构建: 从 proot 源码 → 编译 → 安装
# 用法: bash /root/widget-mcp/build.sh
set -e

SRC=/root/widget-mcp/app/src/main
BUILD=/data/data/com.termux/files/home/widget_build
DEVICE_IP=127.0.0.1
SSH_PORT=8022

echo "=== 1. sync ==="
cd "$SRC"
tar czf /tmp/src.tar.gz \
  AndroidManifest.xml \
  java/com/nous/widgetmcp/domain/contract/*.kt \
  java/com/nous/widgetmcp/domain/usecase/*.kt \
  java/com/nous/widgetmcp/data/repo/*.kt \
  java/com/nous/widgetmcp/widget/*.kt \
  java/com/nous/widgetmcp/hermes/*.kt \
  java/com/nous/widgetmcp/*.kt \
  res/

cat /tmp/src.tar.gz | ssh -p $SSH_PORT $DEVICE_IP "cd $BUILD && tar xzf -"

echo "=== 2. aapt2 ==="
ssh -p $SSH_PORT $DEVICE_IP "cd $BUILD && rm -rf comp gen classes && mkdir comp gen classes && \
  find res -type f | while read f; do aapt2 compile -o comp \"\$f\" 2>&1; done && \
  aapt2 link -o base.apk --manifest AndroidManifest.xml -I android.jar --java gen comp/*.flat"

echo "=== 3. kotlinc ==="
ssh -p $SSH_PORT $DEVICE_IP "cd $BUILD && \
  CP=android.jar && \
  for jar in libs/*.jar; do CP=\"\$CP:\$jar\"; done && \
  kotlinc -cp \"\$CP\" -d classes -jvm-target 17 \
    gen/com/nous/widgetmcp/R.java \
    \$(find java -name '*.kt' | sort)"

echo "=== 4. d8 ==="
ssh -p $SSH_PORT $DEVICE_IP "cd $BUILD && \
  d8 --lib android.jar --min-api 26 \
    \$(find classes -name '*.class') libs/*.jar --output ."

echo "=== 5. pack + sign ==="
ssh -p $SSH_PORT $DEVICE_IP "cd $BUILD && \
  rm -rf apk_out && mkdir apk_out && cd apk_out && \
  unzip -o ../base.apk >/dev/null && cp ../classes.dex . && rm -rf META-INF && \
  zip -r -0 ../u.apk resources.arsc >/dev/null && \
  zip -r ../u.apk AndroidManifest.xml classes.dex res/ >/dev/null && \
  zipalign -p -f 4 ../u.apk ../ua.apk && \
  apksigner sign --ks ~/.android/debug.keystore --ks-pass pass:android ../ua.apk"

echo "=== 6. install ==="
ssh -p $SSH_PORT $DEVICE_IP "su -c 'pm uninstall com.nous.widgetmcp' 2>/dev/null; \
  su -c 'pm install -r $BUILD/ua.apk' && \
  su -c 'am force-stop com.nous.widgetmcp; am start -n com.nous.widgetmcp/.MainActivity'"

echo "=== DONE ==="
