#!/bin/bash
# 多任务Web界面 - 快速启动脚本

echo "=========================================="
echo "🚀 Rclone Multi-Task Web Manager"
echo "=========================================="
echo ""

# 停止旧服务
echo "1️⃣ 停止旧服务..."
pkill -9 -f rclone_web.py 2>/dev/null
sleep 2
echo "✓ 已停止"
echo ""

# 检查文件
if [ ! -f "rclone_web_multitask.py" ]; then
    echo "❌ 错误: 找不到 rclone_web_multitask.py"
    echo "请确保在正确的目录中运行此脚本"
    exit 1
fi

# 语法检查
echo "2️⃣ 检查文件..."
if python3 -m py_compile rclone_web_multitask.py 2>/dev/null; then
    echo "✓ 文件检查通过"
else
    echo "❌ 文件有错误，请检查"
    exit 1
fi
echo ""

# 检查配置目录
echo "3️⃣ 检查配置..."
CONFIG_DIR="$HOME/.config/rclone_web"
CONFIG_FILE="$CONFIG_DIR/config.json"

if [ ! -d "$CONFIG_DIR" ]; then
    echo "创建配置目录..."
    mkdir -p "$CONFIG_DIR"
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "创建默认配置..."
    cat > "$CONFIG_FILE" << 'EOF'
{
  "tasks": [],
  "scheduleTime": "02:00",
  "scheduleInterval": "daily",
  "s3_remotes": []
}
EOF
fi
echo "✓ 配置就绪"
echo ""

# 启动服务
echo "4️⃣ 启动服务..."
nohup python3 rclone_web_multitask.py > /tmp/rclone_web_output.log 2>&1 &
NEW_PID=$!
sleep 3
echo "✓ 服务已启动 (PID: $NEW_PID)"
echo ""

# 检查状态
echo "5️⃣ 检查服务状态..."
if ps -p $NEW_PID > /dev/null 2>&1; then
    echo "✓ 服务运行正常"
    
    # 等待端口监听
    for i in {1..10}; do
        if netstat -tlnp 2>/dev/null | grep -q ":5000"; then
            echo "✓ 端口5000已监听"
            break
        fi
        sleep 1
    done
    
    if ! netstat -tlnp 2>/dev/null | grep -q ":5000"; then
        echo "⚠️ 警告: 端口5000未监听"
    fi
else
    echo "❌ 服务启动失败"
    echo ""
    echo "查看错误日志:"
    tail -20 /tmp/rclone_web_output.log
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ 启动成功！"
echo "=========================================="
echo ""
echo "📊 服务信息:"
echo "  进程ID: $NEW_PID"
echo "  端口: 5000"
echo "  日志: /tmp/rclone_web_output.log"
echo "  配置: $CONFIG_FILE"
echo ""
echo "🌐 访问地址:"
echo "  本地: http://localhost:5000"
echo "  远程: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "📝 常用命令:"
echo "  查看日志: tail -f /tmp/rclone_web_output.log"
echo "  停止服务: pkill -9 -f rclone_web"
echo "  查看状态: ps aux | grep rclone_web"
echo "  测试API: curl http://localhost:5000/api/status"
echo ""
echo "📖 使用指南: cat MULTITASK_WEB_GUIDE.md"
echo ""
