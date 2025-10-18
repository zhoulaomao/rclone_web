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

---

**使用新版本的Web界面，选择Provider为MinIO，即可自动应用这些优化配置！** 🎉
