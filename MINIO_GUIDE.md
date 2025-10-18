# MinIO 配置指南

## 🎯 MinIO 特别说明

MinIO是一个开源的S3兼容对象存储服务，但在实现上与AWS S3有一些差异，特别是在checksum计算和小文件上传方面。

## ⚠️ MinIO已知问题

### 问题：小文件上传失败
**错误信息：**
```
failed to compute payload hash: failed to seek body to start, request stream is not seekable
```

**原因：**
- MinIO对checksum的处理与AWS S3不同
- 小文件（<5MB）更容易触发此问题
- buffer和stream处理机制差异

## ✅ MinIO专用配置

### 通过Web界面配置（推荐）

1. 打开 Rclone Web Manager
2. 在"S3 远程管理"点击"添加 S3 远程"
3. 填写配置：
   ```
   远程名称: minio
   Access Key: minioadmin（或你的密钥）
   Secret Key: minioadmin（或你的密钥）
   Endpoint: localhost:9000（或你的MinIO地址）
   Region: us-east-1（MinIO默认）
   Provider: MinIO ⬅️ 重要！选择MinIO
   Force Path Style: ✅ 必须启用
   ```
4. 保存配置

### 手动配置文件

编辑 `~/.config/rclone/rclone.conf`：

```ini
[minio]
type = s3
provider = Minio
access_key_id = minioadmin
secret_access_key = minioadmin
endpoint = localhost:9000
region = us-east-1
acl = private
force_path_style = true
disable_checksum = true
no_check_bucket = true
```

**关键参数说明：**

| 参数 | 值 | 说明 |
|------|---|------|
| `provider` | `Minio` | 告诉rclone使用MinIO特定优化 |
| `force_path_style` | `true` | MinIO必须使用Path Style URL |
| `disable_checksum` | `true` | 禁用checksum计算，解决seekable问题 |
| `no_check_bucket` | `true` | 跳过bucket检查，提升性能 |
| `region` | `us-east-1` | MinIO默认region |

## 🚀 MinIO专用同步命令

### 基础同步
```bash
rclone sync /path/to/local minio:bucket \
    --s3-disable-checksum \
    --s3-no-check-bucket \
    --ignore-checksum \
    -v
```

### 优化后的同步（推荐）
```bash
rclone sync /path/to/local minio:bucket \
    --s3-upload-cutoff 5M \
    --s3-chunk-size 5M \
    --s3-upload-concurrency 4 \
    --s3-no-check-bucket \
    --s3-disable-checksum \
    --ignore-checksum \
    --buffer-size 0 \
    --transfers 32 \
    --checkers 64 \
    -v
```

### 参数说明

| 参数 | 值 | 说明 |
|------|---|------|
| `--s3-upload-cutoff` | `5M` | 大于5M才使用分块上传 |
| `--s3-chunk-size` | `5M` | 分块大小5MB |
| `--s3-upload-concurrency` | `4` | 并发上传数（降低避免错误）|
| `--s3-no-check-bucket` | - | 跳过bucket检查 |
| `--s3-disable-checksum` | - | 禁用checksum |
| `--ignore-checksum` | - | 忽略checksum验证 |
| `--buffer-size` | `0` | 禁用buffer避免seek |

## 🔍 常见MinIO部署配置

### 本地开发环境
```
Endpoint: localhost:9000
Access Key: minioadmin
Secret Key: minioadmin
Region: us-east-1
```

### Docker部署
```bash
docker run -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=admin" \
  -e "MINIO_ROOT_PASSWORD=password" \
  minio/minio server /data --console-address ":9001"
```

配置：
```
Endpoint: localhost:9000
Access Key: admin
Secret Key: password
Region: us-east-1
```

### 生产环境（带TLS）
```
Endpoint: minio.example.com
Access Key: your-access-key
Secret Key: your-secret-key
Region: us-east-1
```

## 📝 完整配置示例

### 示例1：本地MinIO
```ini
[local-minio]
type = s3
provider = Minio
access_key_id = minioadmin
secret_access_key = minioadmin
endpoint = http://localhost:9000
region = us-east-1
acl = private
force_path_style = true
disable_checksum = true
no_check_bucket = true
```

测试：
```bash
rclone lsd local-minio:
rclone sync /data local-minio:backup -v
```

### 示例2：远程MinIO集群
```ini
[prod-minio]
type = s3
provider = Minio
access_key_id = prod_access_key
secret_access_key = prod_secret_key
endpoint = https://minio.company.com
region = us-east-1
acl = private
force_path_style = true
disable_checksum = true
no_check_bucket = true
```

### 示例3：MinIO网关模式
```ini
[minio-gateway]
type = s3
provider = Minio
access_key_id = gateway_key
secret_access_key = gateway_secret
endpoint = https://gateway.minio.local
region = us-east-1
acl = private
force_path_style = true
disable_checksum = true
no_check_bucket = true
```

## 🐛 故障排查

### 问题1: Connection refused
```bash
# 检查MinIO是否运行
curl http://localhost:9000/minio/health/live

# 检查端口
netstat -tlnp | grep 9000

# 查看MinIO日志
docker logs minio
```

### 问题2: Access Denied
```bash
# 验证密钥
mc alias set test http://localhost:9000 minioadmin minioadmin

# 检查bucket权限
mc ls test/bucket-name
```

### 问题3: 小文件仍然失败

**临时方案：**
```bash
# 跳过问题文件
rclone sync /home minio:bucket --exclude "*.sh" --exclude "*.png" -v

# 单独上传小文件
for file in *.png *.sh; do
  rclone copy "$file" minio:bucket/ --s3-upload-concurrency 1 -v
done
```

**永久方案：**
确保配置文件中有：
```ini
disable_checksum = true
no_check_bucket = true
```

并使用专用参数：
```bash
rclone sync /home minio:bucket \
    --s3-disable-checksum \
    --ignore-checksum \
    --buffer-size 0 \
    -v
```

### 问题4: 速度很慢

**优化建议：**
```bash
# 增加并发
rclone sync /home minio:bucket \
    --transfers 64 \
    --checkers 128 \
    --s3-upload-concurrency 8 \
    -v

# 调整chunk大小
rclone sync /home minio:bucket \
    --s3-chunk-size 16M \
    -v
```

## 🎯 MinIO最佳实践

### 1. 创建专用用户
```bash
# 在MinIO中创建专用用户而非使用root
mc admin user add minio backup_user backup_password
mc admin policy attach minio readwrite --user backup_user
```

### 2. 设置生命周期规则
```bash
# 配置对象过期策略
mc ilm add minio/backup --expiry-days 30
```

### 3. 启用版本控制
```bash
# 启用bucket版本控制
mc version enable minio/backup
```

### 4. 监控和日志
```bash
# 启用审计日志
mc admin config set minio audit_webhook:1 endpoint="http://logger:9000"
```

## 📊 性能对比

| 场景 | 标准AWS S3 | MinIO | 说明 |
|------|-----------|-------|------|
| 小文件 (<1MB) | ✅ 正常 | ⚠️ 需特殊配置 | disable_checksum |
| 大文件 (>100MB) | ✅ 快速 | ✅ 快速 | 性能相当 |
| 多线程上传 | ✅ 支持 | ✅ 支持 | 降低并发数更稳定 |
| Checksum验证 | ✅ 完整 | ⚠️ 部分支持 | 建议禁用 |

## 🔗 相关资源

- MinIO官方文档: https://min.io/docs/
- MinIO GitHub: https://github.com/minio/minio
- Rclone MinIO指南: https://rclone.org/s3/#minio
- 社区支持: https://slack.min.io/

## 💡 快速测试

```bash
# 测试连接
rclone lsd minio:

# 测试上传小文件
echo "test" > test.txt
rclone copy test.txt minio:test-bucket/ -vv

# 测试上传大文件
dd if=/dev/zero of=bigfile bs=1M count=100
rclone copy bigfile minio:test-bucket/ -vv

# 测试同步
rclone sync /home/test minio:test-bucket -v
```
# ⏰ 定时任务功能 - 完整说明

## ✅ 新增功能概述

在原有的所有功能基础上，新增了**完整的定时任务系统**！

### 核心功能
- ⏰ 每个任务独立配置定时时间
- 📅 支持3种定时类型（每天/每周/间隔）
- 🚀 自动后台调度执行
- 🔄 任务编辑时保留定时配置
- 📊 显示下次执行时间

---

## 🎯 定时任务类型

### 1. 每天执行 (Daily)
- 设置固定时间
- 每天在指定时间自动执行
- 例如：每天凌晨 02:00 执行

### 2. 每周执行 (Weekly)
- 选择星期几
- 设置执行时间
- 例如：每周一 02:00 执行

### 3. 间隔执行 (Interval)
- 设置间隔分钟数
- 周期性重复执行
- 例如：每 60 分钟执行一次

---

## 📦 安装依赖

定时任务功能需要 `schedule` 模块：

```bash
# 方法1：使用pip安装
pip install schedule --break-system-packages

# 方法2：如果方法1失败
pip3 install schedule --break-system-packages

# 方法3：使用pip直接安装
python3 -m pip install schedule --break-system-packages
```

**注意：** 如果不安装 `schedule` 模块，程序仍然可以运行，但定时任务功能将不可用。

---

## 🚀 快速开始

### 1. 部署新版本

```bash
# 停止旧版本
pkill -9 -f rclone_web

# 备份
cd /root
cp rclone_web.py rclone_web.py.backup

# 替换
cp rclone_web_with_scheduler.py rclone_web.py

# 安装依赖
pip install schedule --break-system-packages

# 启动
./rclone_web.py
```

### 2. 后台运行

```bash
nohup ./rclone_web.py > /tmp/rclone_web.log 2>&1 &
```

---

## 🎨 使用指南

### 添加定时任务

1. **打开Web界面**
   ```
   http://你的服务器IP:5000
   ```

2. **添加/编辑任务**
   - 点击"添加任务"按钮
   - 填写基本信息（名称、路径等）

3. **配置定时任务**
   - 勾选"⏰ 启用定时任务"复选框
   - 选择定时类型：
     - 每天：选择执行时间
     - 每周：选择星期和时间
     - 间隔：设置间隔分钟数

4. **保存任务**
   - 点击"💾 保存任务"
   - 定时任务自动生效

### 示例配置

#### 示例1：每天凌晨2点同步
```
✅ 启用定时任务
定时类型：每天
执行时间：02:00
```

#### 示例2：每周一早上8点同步
```
✅ 启用定时任务
定时类型：每周
星期：星期一
执行时间：08:00
```

#### 示例3：每小时同步一次
```
✅ 启用定时任务
定时类型：间隔时间
间隔：60 分钟
```

---

## 📊 任务状态显示

### 任务卡片信息

启用定时任务后，任务卡片会显示：

```
┌──────────────────────────────────────┐
│ 📦 我的备份任务          [待机]       │
├──────────────────────────────────────┤
│ 本地: /home/user/data                 │
│ 远程: minio:bucket/backup             │
│ 年龄限制: 0 (全部文件)                 │
│ 并发: 16 / 32                        │
│ ⏰ 定时: 每天 02:00                   │
├──────────────────────────────────────┤
│ [▶️ 启动] [✏️ 编辑] [⏸️ 禁用] [🗑️ 删除] │
└──────────────────────────────────────┘
```

---

## 🔧 API接口

### 新增的API端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/scheduler/start` | POST | 启动调度器 |
| `/api/scheduler/stop` | POST | 停止调度器 |
| `/api/scheduler/reload` | POST | 重新加载定时任务 |
| `/api/status` | GET | 获取状态（含调度器信息）|

### API使用示例

#### 1. 查看调度器状态

```bash
curl http://localhost:5000/api/status | jq '.scheduler'
```

**响应示例：**
```json
{
  "available": true,
  "running": true,
  "active_schedules": 2,
  "schedules": {
    "task_1": {
      "next_run": "2025-10-19 02:00:00"
    },
    "task_2": {
      "next_run": "2025-10-18 15:00:00"
    }
  }
}
```

#### 2. 手动重新加载定时任务

```bash
curl -X POST http://localhost:5000/api/scheduler/reload
```

#### 3. 添加带定时任务的任务

```bash
curl -X POST http://localhost:5000/api/task/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "自动备份",
    "localPath": "/data",
    "remotePath": "minio:backup",
    "maxAge": "0",
    "transfers": 16,
    "checkers": 32,
    "enabled": true,
    "schedule": {
      "enabled": true,
      "type": "daily",
      "time": "02:00",
      "interval": 60,
      "weekday": "monday"
    }
  }'
```

---

## 📝 配置文件格式

### 任务配置示例

```json
{
  "tasks": [
    {
      "id": "task_1",
      "name": "每日备份",
      "localPath": "/home/data",
      "remotePath": "minio:backup",
      "maxAge": "0",
      "transfers": 16,
      "checkers": 32,
      "enabled": true,
      "schedule": {
        "enabled": true,
        "type": "daily",
        "time": "02:00",
        "interval": 60,
        "weekday": "monday"
      }
    }
  ]
}
```

### schedule 字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| enabled | boolean | 是否启用定时 | true |
| type | string | 定时类型 | "daily" / "weekly" / "interval" |
| time | string | 执行时间（HH:MM） | "02:00" |
| interval | int | 间隔分钟数 | 60 |
| weekday | string | 星期（仅weekly） | "monday" |

---

## 🎯 工作原理

### 调度器架构

```
程序启动
    ↓
检测 schedule 模块
    ↓
启动调度器线程
    ↓
读取所有任务配置
    ↓
为启用定时的任务创建调度
    ↓
后台循环检查 (每秒)
    ↓
到时间 → 执行任务
    ↓
继续循环...
```

### 任务执行逻辑

1. 调度器到达预定时间
2. 检查任务是否正在运行
3. 如果未运行，启动任务线程
4. 如果正在运行，跳过本次执行
5. 记录日志

---

## 🐛 故障排查

### 问题1：定时任务不执行

**检查步骤：**

```bash
# 1. 查看日志
tail -f /tmp/rclone_web.log | grep -i "schedule"

# 2. 检查调度器状态
curl http://localhost:5000/api/status | jq '.scheduler'

# 3. 检查schedule模块
python3 -c "import schedule; print('OK')"
```

**可能原因：**
- schedule模块未安装
- 任务的schedule.enabled = false
- 调度器未启动

**解决方法：**
```bash
# 安装schedule
pip install schedule --break-system-packages

# 重新加载调度
curl -X POST http://localhost:5000/api/scheduler/reload

# 重启程序
pkill -9 -f rclone_web && ./rclone_web.py
```

### 问题2：定时冲突（多个任务同时执行）

**现象：** 多个任务设置了相同的执行时间

**解决：**
- 每个任务设置不同的执行时间
- 或者增加任务间隔

### 问题3：间隔任务执行过于频繁

**原因：** 间隔时间设置过短

**建议：**
- 最小间隔：5分钟
- 常用间隔：30-60分钟
- 避免小于1分钟的间隔

---

## 💡 最佳实践

### 1. 时间设置建议

```bash
# 避免高峰时段
❌ 09:00 - 18:00 (工作时间)
✅ 01:00 - 05:00 (凌晨时段)

# 错开多个任务
任务1: 02:00
任务2: 02:30
任务3: 03:00
```

### 2. 间隔任务建议

```bash
# 小文件同步
✅ 15-30 分钟

# 大文件同步
✅ 60-120 分钟

# 完整备份
✅ 每天一次
```

### 3. 资源考虑

- 避免所有任务同时执行
- 考虑网络带宽限制
- 考虑服务器负载

---

## 📊 监控与日志

### 查看定时任务日志

```bash
# 实时查看
tail -f /tmp/rclone_web.log

# 查看定时相关
grep "定时任务" /tmp/rclone_web.log

# 查看今天的日志
grep "$(date +%Y-%m-%d)" /tmp/rclone_web.log
```

### 日志示例

```
[2025-10-18 14:00:00] INFO: 定时任务调度器已启动
[2025-10-18 14:00:00] SUCCESS: 定时任务已设置: 每日备份 - daily 02:00
[2025-10-18 14:00:00] INFO: 定时任务设置完成，共 2 个任务
[2025-10-19 02:00:00] INFO: 定时任务触发: 每日备份
[2025-10-19 02:00:01] INFO: 开始同步任务: 每日备份
```

---

## 🎊 功能对比

| 功能 | 原版本 | 带定时版本 |
|------|--------|-----------|
| 手动执行 | ✅ | ✅ |
| S3配置编辑 | ✅ | ✅ |
| 进度显示 | ✅ | ✅ |
| **定时执行** | ❌ | ✅ **新增** |
| **每天定时** | ❌ | ✅ **新增** |
| **每周定时** | ❌ | ✅ **新增** |
| **间隔定时** | ❌ | ✅ **新增** |
| **调度器管理** | ❌ | ✅ **新增** |
| 自动后台运行 | ⚠️ 手动 | ✅ **自动** |

---

## 🔄 升级步骤

### 从旧版本升级

```bash
# 1. 备份当前版本
cp /root/rclone_web.py /root/rclone_web_old.py

# 2. 备份配置
cp /tmp/rclone_web_config.json /tmp/rclone_web_config.json.backup

# 3. 停止服务
pkill -9 -f rclone_web

# 4. 安装依赖
pip install schedule --break-system-packages

# 5. 替换文件
cp rclone_web_with_scheduler.py /root/rclone_web.py

# 6. 启动新版本
cd /root
./rclone_web.py

# 7. 访问Web界面，为任务配置定时
```

### 配置迁移

旧配置文件自动兼容！只需：
1. 启动新版本
2. 编辑每个任务
3. 启用并配置定时任务
4. 保存

---

## 🎯 总结

### 新增内容

1. ✅ **定时任务系统** - 完整的调度功能
2. ✅ **3种定时类型** - 每天/每周/间隔
3. ✅ **独立配置** - 每个任务单独设置
4. ✅ **自动执行** - 后台自动调度
5. ✅ **状态显示** - 显示定时信息
6. ✅ **调度器API** - 完整的管理接口
7. ✅ **日志记录** - 详细的执行日志

### 代码修改统计

- 新增函数：8个
- 新增API：3个
- 修改函数：5个
- 新增HTML：~50行
- 新增JavaScript：~100行
- 总计：~400行新代码

### 立即开始

```bash
# 安装依赖
pip install schedule --break-system-packages

# 启动程序
./rclone_web_with_scheduler.py

# 访问
http://你的服务器IP:5000
```

---

**现在你的Rclone Web Manager拥有完整的定时任务功能了！** 🎉

设置好定时后，任务会在指定时间自动执行，无需手动操作！

**使用新版本的Web界面，选择Provider为MinIO，即可自动应用这些优化配置！** 🎉
