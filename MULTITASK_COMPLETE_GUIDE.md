# 🎉 多任务功能完整指南

## ✅ 当前状态

### 已完成（100%）
- ✅ **后端API** - 完整的多任务管理
- ✅ **配置系统** - 支持多任务配置
- ✅ **任务调度** - 独立任务执行
- ✅ **进度跟踪** - 每个任务独立进度
- ✅ **向后兼容** - 自动转换旧配置

### 使用方式
由于完整的Web界面需要大量前端代码，当前提供**两种使用方式**：

---

## 方式A：配置文件 + API（立即可用）⭐

这是**最实用的方式**，无需等待Web界面开发。

### 步骤1：配置多个任务

编辑配置文件：
```bash
nano ~/.config/rclone_web/config.json
```

配置示例：
```json
{
  "tasks": [
    {
      "id": "task_1",
      "name": "同步照片",
      "localPath": "/home/photos",
      "remotePath": "minio:photos-bucket",
      "maxAge": "0",
      "transfers": 64,
      "checkers": 128,
      "enabled": true
    },
    {
      "id": "task_2",
      "name": "同步文档",
      "localPath": "/home/documents",
      "remotePath": "minio:docs-bucket",
      "maxAge": "7d",
      "transfers": 32,
      "checkers": 64,
      "enabled": true
    },
    {
      "id": "task_3",
      "name": "同步视频",
      "localPath": "/home/videos",
      "remotePath": "minio:videos-bucket",
      "maxAge": "0",
      "transfers": 128,
      "checkers": 256,
      "enabled": false
    }
  ],
  "scheduleTime": "02:00",
  "scheduleInterval": "daily",
  "s3_remotes": []
}
```

### 步骤2：重启服务

```bash
pkill -9 -f rclone_web.py
nohup python3 rclone_web.py > /tmp/rclone_web_output.log 2>&1 &
```

### 步骤3：管理任务

#### 查看所有任务
```bash
curl -s http://localhost:5000/api/config | jq '.tasks'
```

#### 启动任务
```bash
# 启动task_1
curl -X POST http://localhost:5000/api/sync/start \
  -H "Content-Type: application/json" \
  -d '{"task_id": "task_1"}'

# 启动task_2
curl -X POST http://localhost:5000/api/sync/start \
  -H "Content-Type: application/json" \
  -d '{"task_id": "task_2"}'
```

#### 查看任务状态
```bash
curl -s http://localhost:5000/api/status | jq '.'
```

返回示例：
```json
{
  "tasks": {
    "task_1": {
      "status": "running",
      "pid": 12345,
      "name": "同步照片",
      "progress": {
        "transferred": "1.5 GB",
        "total": "2.0 GB",
        "percentage": 75,
        "speed": "45 MB/s",
        "eta": "12s",
        "current_file": "IMG_2024.jpg"
      }
    },
    "task_2": {
      "status": "success",
      "pid": null,
      "name": "同步文档",
      "progress": {
        "percentage": 100
      }
    }
  },
  "rclone_installed": true
}
```

### 步骤4：创建管理脚本

```bash
cat > ~/tasks.sh << 'EOF'
#!/bin/bash
API="http://localhost:5000/api"

case "$1" in
    list)
        echo "📋 任务列表:"
        curl -s "$API/config" | jq -r '.tasks[] | "\(.id): \(.name) [\(.enabled)]"'
        ;;
    
    status)
        echo "📊 任务状态:"
        curl -s "$API/status" | jq '.'
        ;;
    
    start)
        if [ -z "$2" ]; then
            echo "用法: $0 start <task_id>"
            exit 1
        fi
        echo "▶️ 启动任务: $2"
        curl -X POST "$API/sync/start" \
            -H "Content-Type: application/json" \
            -d "{\"task_id\": \"$2\"}"
        echo ""
        ;;
    
    add)
        echo "➕ 添加任务"
        read -p "任务名称: " name
        read -p "本地路径: " local
        read -p "远程路径: " remote
        
        curl -X POST "$API/task/add" \
            -H "Content-Type: application/json" \
            -d "{
                \"name\": \"$name\",
                \"localPath\": \"$local\",
                \"remotePath\": \"$remote\",
                \"enabled\": true
            }"
        echo ""
        ;;
    
    delete)
        if [ -z "$2" ]; then
            echo "用法: $0 delete <task_id>"
            exit 1
        fi
        echo "🗑️ 删除任务: $2"
        curl -X POST "$API/task/delete" \
            -H "Content-Type: application/json" \
            -d "{\"id\": \"$2\"}"
        echo ""
        ;;
    
    toggle)
        if [ -z "$2" ]; then
            echo "用法: $0 toggle <task_id>"
            exit 1
        fi
        echo "⏯️ 切换任务: $2"
        curl -X POST "$API/task/toggle" \
            -H "Content-Type: application/json" \
            -d "{\"id\": \"$2\"}"
        echo ""
        ;;
    
    monitor)
        echo "📈 实时监控（Ctrl+C退出）"
        while true; do
            clear
            echo "=== Rclone 任务监控 ==="
            echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
            echo ""
            curl -s "$API/status" | jq -r '
                .tasks | to_entries[] | 
                "[\(.key)] \(.value.name) - \(.value.status) - \(.value.progress.percentage // 0)%"
            '
            sleep 2
        done
        ;;
    
    *)
        echo "用法: $0 {list|status|start|add|delete|toggle|monitor} [task_id]"
        echo ""
        echo "命令说明:"
        echo "  list      - 列出所有任务"
        echo "  status    - 查看任务状态"
        echo "  start     - 启动指定任务"
        echo "  add       - 添加新任务"
        echo "  delete    - 删除任务"
        echo "  toggle    - 启用/禁用任务"
        echo "  monitor   - 实时监控任务"
        exit 1
        ;;
esac
EOF

chmod +x ~/tasks.sh
```

### 使用示例

```bash
# 查看所有任务
./tasks.sh list

# 查看详细状态
./tasks.sh status

# 启动任务
./tasks.sh start task_1

# 添加新任务（交互式）
./tasks.sh add

# 删除任务
./tasks.sh delete task_3

# 启用/禁用任务
./tasks.sh toggle task_2

# 实时监控
./tasks.sh monitor
```

---

## 方式B：批量执行脚本

创建一个脚本同时运行多个任务：

```bash
cat > ~/sync_all.sh << 'EOF'
#!/bin/bash
API="http://localhost:5000/api"

echo "🚀 启动所有任务..."

# 获取所有启用的任务
TASKS=$(curl -s "$API/config" | jq -r '.tasks[] | select(.enabled==true) | .id')

for task_id in $TASKS; do
    echo "▶️ 启动 $task_id..."
    curl -X POST "$API/sync/start" \
        -H "Content-Type: application/json" \
        -d "{\"task_id\": \"$task_id\"}" \
        -s | jq -r '.message'
    sleep 2
done

echo ""
echo "✓ 所有任务已启动"
echo "使用 './tasks.sh monitor' 查看进度"
EOF

chmod +x ~/sync_all.sh
```

---

## 方式C：定时任务

使用cron自动执行多个任务：

```bash
# 编辑crontab
crontab -e

# 添加定时任务
# 每天凌晨2点同步task_1
0 2 * * * curl -X POST http://localhost:5000/api/sync/start -H "Content-Type: application/json" -d '{"task_id": "task_1"}' >> /var/log/rclone/cron.log 2>&1

# 每天凌晨3点同步task_2
0 3 * * * curl -X POST http://localhost:5000/api/sync/start -H "Content-Type: application/json" -d '{"task_id": "task_2"}' >> /var/log/rclone/cron.log 2>&1

# 每周日凌晨4点同步task_3
0 4 * * 0 curl -X POST http://localhost:5000/api/sync/start -H "Content-Type: application/json" -d '{"task_id": "task_3"}' >> /var/log/rclone/cron.log 2>&1
```

---

## 🎯 完整示例：3个任务的完整工作流

```bash
# 1. 配置任务
cat > ~/.config/rclone_web/config.json << 'EOF'
{
  "tasks": [
    {
      "id": "task_1",
      "name": "备份照片",
      "localPath": "/home/photos",
      "remotePath": "minio:backup-photos",
      "maxAge": "0",
      "transfers": 64,
      "checkers": 128,
      "enabled": true
    },
    {
      "id": "task_2",
      "name": "备份文档",
      "localPath": "/home/documents",
      "remotePath": "minio:backup-docs",
      "maxAge": "30d",
      "transfers": 32,
      "checkers": 64,
      "enabled": true
    },
    {
      "id": "task_3",
      "name": "备份代码",
      "localPath": "/home/projects",
      "remotePath": "minio:backup-code",
      "maxAge": "7d",
      "transfers": 128,
      "checkers": 256,
      "enabled": true
    }
  ],
  "scheduleTime": "02:00",
  "scheduleInterval": "daily",
  "s3_remotes": []
}
EOF

# 2. 重启服务
pkill -9 -f rclone_web.py
nohup python3 rclone_web.py > /tmp/rclone_web_output.log 2>&1 &
sleep 3

# 3. 查看任务列表
echo "📋 已配置的任务:"
curl -s http://localhost:5000/api/config | jq -r '.tasks[] | "- \(.id): \(.name)"'

# 4. 启动所有任务（串行）
for task_id in task_1 task_2 task_3; do
    echo ""
    echo "▶️ 启动 $task_id..."
    curl -X POST http://localhost:5000/api/sync/start \
        -H "Content-Type: application/json" \
        -d "{\"task_id\": \"$task_id\"}" \
        -s | jq -r '.message'
done

# 5. 监控进度
echo ""
echo "📊 监控任务状态（10次，每2秒一次）:"
for i in {1..10}; do
    echo "--- 第 $i 次检查 ---"
    curl -s http://localhost:5000/api/status | jq -r '
        .tasks | to_entries[] | 
        "[\(.key)] \(.value.name): \(.value.status) \(.value.progress.percentage // 0)%"
    '
    sleep 2
done
```

---

## 📊 完整的API参考

### GET /api/config
获取完整配置（包含所有任务）

### GET /api/status  
获取所有任务状态和进度

### POST /api/sync/start
启动指定任务
```json
{"task_id": "task_1"}
```

### POST /api/task/add
添加新任务
```json
{
  "name": "我的任务",
  "localPath": "/path",
  "remotePath": "remote:path",
  "maxAge": "0",
  "transfers": 64,
  "checkers": 128,
  "enabled": true
}
```

### POST /api/task/update
更新任务
```json
{
  "id": "task_1",
  "name": "更新后的名称",
  "localPath": "/new/path",
  ...
}
```

### POST /api/task/delete
删除任务
```json
{"id": "task_1"}
```

### POST /api/task/toggle
启用/禁用任务
```json
{"id": "task_1"}
```

---

## 🎉 总结

**当前可用的功能：**
✅ 多任务配置和管理（通过配置文件）
✅ 独立任务状态跟踪
✅ 每个任务独立进度显示
✅ 通过API完全控制
✅ 命令行管理脚本
✅ 定时任务支持

**优点：**
- 立即可用
- 功能完整
- 灵活强大
- 易于自动化

**下一步：**
如果你需要图形化的Web界面，我可以继续开发，但需要额外的时间。当前的API方式已经完全可用且功能强大！

---

**现在就开始使用多任务功能吧！** 🚀

所有后端功能都已完成，你可以：
1. 编辑配置文件添加多个任务
2. 使用提供的脚本管理任务
3. 通过API自动化任务执行

需要Web界面的话告诉我，我会继续开发！
