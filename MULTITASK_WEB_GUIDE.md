# 🎉 多任务Web界面 - 使用指南

## ✅ 开发完成！

完整的多任务Web界面已经开发完成！现在可以通过浏览器图形化管理所有同步任务。

---

## 🚀 快速开始

### 步骤1：停止旧服务

```bash
pkill -9 -f rclone_web.py
```

### 步骤2：启动多任务版本

```bash
cd /mnt/user-data/outputs
nohup python3 rclone_web_multitask.py > /tmp/rclone_web_output.log 2>&1 &
```

### 步骤3：访问Web界面

打开浏览器访问：
```
http://你的服务器IP:5000
```

或本地访问：
```
http://localhost:5000
```

---

## 🎯 功能特性

### ✨ 任务管理
- ✅ **添加任务** - 点击"➕ 添加任务"按钮
- ✅ **编辑任务** - 点击任务卡片的"✏️ 编辑"按钮
- ✅ **删除任务** - 点击"🗑️ 删除"按钮
- ✅ **启用/禁用** - 点击"⏸️ 禁用"或"▶️ 启用"按钮
- ✅ **启动同步** - 点击"▶️ 启动"按钮

### 📊 实时进度
每个任务都会显示：
- ⏱️ 当前状态（待机/运行中/成功/错误）
- 📈 进度百分比（0-100%）
- 💾 已传输/总大小
- 🚀 传输速度（MB/s）
- ⏰ 剩余时间估算
- 📁 当前正在传输的文件

### 🎨 界面特点
- 📱 响应式设计（支持手机/平板/电脑）
- 🎨 现代化UI设计
- 🔄 自动刷新（2秒更新一次）
- 🎯 状态色彩编码：
  - 灰色 = 待机
  - 绿色 = 运行中/成功
  - 红色 = 错误

### ☁️ S3管理
- ✅ 添加S3远程配置
- ✅ MinIO专用选项
- ✅ 删除S3配置
- ✅ 自动加载现有配置

---

## 📋 使用流程示例

### 1️⃣ 首次使用

1. **添加S3配置**
   - 点击"➕ 添加 S3 远程"
   - 填写MinIO信息：
     - 远程名称：`minio`
     - Access Key：`minioadmin`
     - Secret Key：`minioadmin`
     - Endpoint：`localhost:9000`
     - Provider：选择`MinIO`
   - 点击"✅ 添加配置"

2. **创建第一个任务**
   - 点击"➕ 添加任务"
   - 填写信息：
     - 任务名称：`同步照片`
     - 本地路径：`/home/photos`
     - 远程路径：`minio:photos-bucket`
     - 最大文件年龄：`0`（同步所有文件）
     - 并发传输数：`64`
     - 检查线程数：`128`
   - 勾选"启用此任务"
   - 点击"💾 保存任务"

3. **启动同步**
   - 在任务卡片中点击"▶️ 启动"
   - 观察实时进度更新

### 2️⃣ 管理多个任务

```
任务1：同步照片
├─ 本地: /home/photos
├─ 远程: minio:photos-bucket
└─ 状态: 运行中 75%

任务2：同步文档
├─ 本地: /home/documents
├─ 远程: minio:docs-bucket
└─ 状态: 待机

任务3：同步视频
├─ 本地: /home/videos
├─ 远程: minio:videos-bucket
└─ 状态: 已禁用
```

### 3️⃣ 编辑任务

1. 点击任务的"✏️ 编辑"按钮
2. 修改需要的参数
3. 点击"💾 保存任务"
4. 任务配置立即更新

### 4️⃣ 查看进度

运行中的任务会显示：
```
┌─────────────────────────────────┐
│ 同步照片                        │
│ 状态: 运行中                    │
├─────────────────────────────────┤
│ 本地: /home/photos              │
│ 远程: minio:photos-bucket       │
│ 并发: 64 / 128                  │
├─────────────────────────────────┤
│ ████████████░░░░░░ 65%          │
│                                 │
│ 已传输: 1.2 GB / 1.9 GB         │
│ 速度: 38.5 MB/s                 │
│ 剩余时间: 19s                   │
│ 当前文件: IMG_2024.jpg          │
├─────────────────────────────────┤
│ [运行中...] [✏️ 编辑] [⏸️ 禁用] [🗑️ 删除] │
└─────────────────────────────────┘
```

---

## 🎬 完整操作视频流程

### 场景：配置3个任务并执行

```bash
# 1. 启动服务
pkill -9 -f rclone_web.py
cd /mnt/user-data/outputs
nohup python3 rclone_web_multitask.py > /tmp/rclone_web_output.log 2>&1 &

# 2. 打开浏览器
# 访问 http://localhost:5000

# 3. 在Web界面操作：

# 添加任务1 - 同步照片
➕ 添加任务
名称: "同步照片"
本地: "/home/photos"
远程: "minio:photos-bucket"
💾 保存

# 添加任务2 - 同步文档
➕ 添加任务
名称: "同步文档"
本地: "/home/documents"
远程: "minio:docs-bucket"
💾 保存

# 添加任务3 - 同步视频
➕ 添加任务
名称: "同步视频"
本地: "/home/videos"
远程: "minio:videos-bucket"
💾 保存

# 4. 启动所有任务
点击每个任务的 ▶️ 启动 按钮

# 5. 观察进度
每2秒自动刷新，实时显示进度
```

---

## 🔧 高级功能

### 批量操作

虽然Web界面不直接支持批量操作，但可以配合API：

```bash
# 启动所有启用的任务
curl -s http://localhost:5000/api/config | \
jq -r '.tasks[] | select(.enabled==true) | .id' | \
while read task_id; do
    echo "启动 $task_id"
    curl -X POST http://localhost:5000/api/sync/start \
        -H "Content-Type: application/json" \
        -d "{\"task_id\": \"$task_id\"}"
    sleep 2
done
```

### 自定义刷新频率

编辑 `rclone_web_multitask.py`，找到最后的：
```javascript
setInterval(updateStatus, 2000);  // 改为其他值，如5000（5秒）
```

### 添加声音提示

在任务完成时播放提示音（需修改代码）：
```javascript
if (status.status === 'success' && prevStatus === 'running') {
    new Audio('/success.mp3').play();
}
```

---

## 📊 任务状态说明

| 状态 | 图标/颜色 | 说明 |
|------|----------|------|
| 待机 | 灰色 | 任务未运行，可以启动 |
| 运行中 | 绿色闪烁 | 任务正在同步，显示进度 |
| 成功 | 绿色 | 任务完成，100%同步 |
| 错误 | 红色 | 任务失败，查看日志 |
| 已禁用 | 灰色 | 任务被禁用，不能启动 |

---

## 🐛 故障排查

### 问题1：页面显示空白

**检查：**
```bash
# 查看日志
tail -f /tmp/rclone_web_output.log

# 检查端口
netstat -tlnp | grep 5000

# 检查进程
ps aux | grep rclone_web
```

**解决：**
```bash
# 重启服务
pkill -9 -f rclone_web
nohup python3 rclone_web_multitask.py > /tmp/rclone_web_output.log 2>&1 &
```

### 问题2：任务列表为空

**原因：** 配置文件格式错误或不存在

**解决：**
```bash
# 检查配置
cat ~/.config/rclone_web/config.json

# 手动创建配置
mkdir -p ~/.config/rclone_web
cat > ~/.config/rclone_web/config.json << 'EOF'
{
  "tasks": [],
  "scheduleTime": "02:00",
  "scheduleInterval": "daily",
  "s3_remotes": []
}
EOF
```

### 问题3：任务启动失败

**查看详细日志：**
```bash
tail -50 /var/log/rclone/rclone_*.log
```

**常见原因：**
- MinIO未运行
- 路径不存在
- 权限不足
- S3配置错误

### 问题4：进度不更新

**原因：** 浏览器缓存或JavaScript错误

**解决：**
1. 按 `Ctrl + Shift + R` 强制刷新
2. 清空浏览器缓存
3. 按 `F12` 打开开发者工具查看错误

---

## 🔄 从旧版本升级

### 如果你之前使用单任务版本：

```bash
# 1. 备份旧配置
cp ~/.config/rclone_web/config.json ~/.config/rclone_web/config.json.backup

# 2. 停止旧服务
pkill -9 -f rclone_web.py

# 3. 启动新版本
nohup python3 rclone_web_multitask.py > /tmp/rclone_web_output.log 2>&1 &

# 4. 访问Web界面
# 旧配置会自动转换为第一个任务
```

**自动转换：**
```
旧配置:
{
  "localPath": "/home",
  "remotePath": "minio:bucket"
}

自动转换为:
{
  "tasks": [
    {
      "id": "task_1",
      "name": "默认同步任务",
      "localPath": "/home",
      "remotePath": "minio:bucket",
      "enabled": true
    }
  ]
}
```

---

## 🎯 最佳实践

### 1. 任务命名
使用清晰的名称：
- ✅ "每日备份 - 照片"
- ✅ "每周备份 - 文档"
- ❌ "task1"
- ❌ "备份"

### 2. 并发设置
根据网络和系统调整：
- 本地MinIO：`transfers=128, checkers=256`
- 远程S3：`transfers=64, checkers=128`
- 慢速网络：`transfers=32, checkers=64`

### 3. 文件年龄
合理使用maxAge：
- `0` - 同步所有文件
- `24h` - 仅最近24小时修改的
- `7d` - 仅最近7天修改的
- `30d` - 仅最近30天修改的

### 4. 任务优先级
按重要性排序：
1. 重要文档（小文件，高频）
2. 照片视频（大文件，中频）
3. 归档数据（大文件，低频）

---

## 📝 配置示例

### 完整的3任务配置

```json
{
  "tasks": [
    {
      "id": "task_1",
      "name": "🖼️ 同步照片库",
      "localPath": "/home/photos",
      "remotePath": "minio:backup-photos",
      "maxAge": "0",
      "transfers": 64,
      "checkers": 128,
      "enabled": true
    },
    {
      "id": "task_2",
      "name": "📄 同步工作文档",
      "localPath": "/home/documents",
      "remotePath": "minio:backup-docs",
      "maxAge": "30d",
      "transfers": 32,
      "checkers": 64,
      "enabled": true
    },
    {
      "id": "task_3",
      "name": "🎬 同步视频归档",
      "localPath": "/home/videos/archive",
      "remotePath": "minio:backup-videos",
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

---

## 🎉 总结

### ✅ 已完成的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 多任务管理 | ✅ | 图形化增删改查 |
| 实时进度 | ✅ | 每个任务独立显示 |
| 任务控制 | ✅ | 启动/停止/启用/禁用 |
| S3配置 | ✅ | MinIO专门支持 |
| 自动刷新 | ✅ | 2秒更新一次 |
| 响应式设计 | ✅ | 支持各种设备 |
| 日志查看 | ✅ | 实时日志显示 |
| 向后兼容 | ✅ | 自动转换旧配置 |

### 🚀 现在可以：

1. ✅ 通过Web界面管理所有任务
2. ✅ 实时查看每个任务的进度
3. ✅ 同时运行多个同步任务
4. ✅ 图形化配置S3和MinIO
5. ✅ 随时添加/编辑/删除任务

---

**开始使用全新的多任务Web界面吧！** 🎊

文件位置：`/mnt/user-data/outputs/rclone_web_multitask.py`

```bash
# 立即启动
cd /mnt/user-data/outputs
pkill -9 -f rclone_web.py
nohup python3 rclone_web_multitask.py > /tmp/rclone_web_output.log 2>&1 &

# 访问
http://localhost:5000
```

享受全新的多任务体验！🎉
