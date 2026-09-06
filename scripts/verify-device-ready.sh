#!/bin/bash
set -e

echo "=== V1-04 设备就绪验证 ==="
echo ""

echo "1. 检查设备连接..."
if adb devices | grep -q "device$"; then
  DEVICE_ID=$(adb devices | grep "device$" | awk '{print $1}')
  echo "  ✓ 设备已连接: $DEVICE_ID"
else
  echo "  ✗ 设备未连接"
  exit 1
fi

echo ""
echo "2. 检查 Companion APK..."
if adb shell pm list packages | grep -q "com.company.cloudctl.companion"; then
  VERSION=$(adb shell dumpsys package com.company.cloudctl.companion | grep versionName | head -1 | awk '{print $1}')
  echo "  ✓ Companion 已安装: $VERSION"
else
  echo "  ✗ Companion 未安装"
  exit 1
fi

echo ""
echo "3. 检查无障碍服务..."
if adb shell settings get secure enabled_accessibility_services | grep -q "cloudctl.companion"; then
  echo "  ✓ 无障碍服务已启用"
  ACCESSIBILITY_OK=true
else
  echo "  ⚠ 无障碍服务未启用（需要手动启用）"
  ACCESSIBILITY_OK=false
fi

echo ""
echo "4. 检查目标应用..."
APPS_INSTALLED=0

if adb shell pm list packages | grep -q "idlefish"; then
  echo "  ✓ 闲鱼已安装"
  APPS_INSTALLED=$((APPS_INSTALLED + 1))
else
  echo "  ⚠ 闲鱼未安装"
fi

if adb shell pm list packages | grep -q "xingin.xhs"; then
  echo "  ✓ 小红书已安装"
  APPS_INSTALLED=$((APPS_INSTALLED + 1))
else
  echo "  ⚠ 小红书未安装"
fi

if adb shell pm list packages | grep -q "ss.android.ugc.aweme"; then
  echo "  ✓ 抖音已安装"
  APPS_INSTALLED=$((APPS_INSTALLED + 1))
else
  echo "  ⚠ 抖音未安装"
fi

if adb shell pm list packages | grep -q "tencent.mm"; then
  echo "  ✓ 微信已安装"
  APPS_INSTALLED=$((APPS_INSTALLED + 1))
else
  echo "  ⚠ 微信未安装"
fi

echo "  → 已安装: $APPS_INSTALLED/4"

echo ""
echo "5. 检查 Control API..."
if curl -s -f http://127.0.0.1:8000/health > /dev/null 2>&1; then
  echo "  ✓ Control API 运行中"
  API_OK=true
else
  echo "  ⚠ Control API 未运行"
  echo "     启动命令: python -m cloudctl_api"
  API_OK=false
fi

echo ""
echo "6. 检查端口转发..."
if adb reverse --list 2>/dev/null | grep -q "tcp:8000"; then
  echo "  ✓ ADB 端口转发已设置"
else
  echo "  ⚠ ADB 端口转发未设置"
  echo "     设置命令: adb reverse tcp:8000 tcp:8000"
fi

echo ""
echo "=== 验证完成 ==="
echo ""

# 输出就绪状态
READY_COUNT=0
TOTAL_COUNT=4

[ "$ACCESSIBILITY_OK" = true ] && READY_COUNT=$((READY_COUNT + 1))
[ $APPS_INSTALLED -gt 0 ] && READY_COUNT=$((READY_COUNT + 1))
[ "$API_OK" = true ] && READY_COUNT=$((READY_COUNT + 1))
READY_COUNT=$((READY_COUNT + 1))  # 设备连接和 APK 已确认

echo "就绪度: $READY_COUNT/4"
echo ""

if [ "$ACCESSIBILITY_OK" = true ] && [ $APPS_INSTALLED -gt 0 ] && [ "$API_OK" = true ]; then
  echo "✅ 设备已就绪，可以开始测试"
  exit 0
else
  echo "⚠️  设备未完全就绪，请完成上述待办项"
  exit 1
fi
