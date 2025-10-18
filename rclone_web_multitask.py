#!/usr/bin/env python3
"""
Rclone Web Manager - Multi-Task Version  
No external dependencies required
"""

import sys

def check_environment():
    """Check Python version"""
    if sys.version_info < (3, 6):
        print("Error: Python 3.6+ required")
        sys.exit(1)
    print("Environment check passed")

check_environment()

import http.server
import socketserver
import json
import subprocess
import os
import threading
import shutil
from datetime import datetime

# 配置
CONFIG_FILE = '/tmp/rclone_web_config.json'
RCLONE_CONFIG_FILE = os.path.expanduser('~/.config/rclone/rclone.conf')
LOG_FILE = '/tmp/rclone_web.log'
SYNC_SCRIPT = '/usr/local/bin/rclone_sync_generated.sh'
PORT = 5000

# 默认配置
DEFAULT_CONFIG = {
    'tasks': [
        {
            'id': 'task_1',
            'name': '默认同步任务',
            'localPath': '/your/local/path',
            'remotePath': 's3remote:bucket/path',
            'maxAge': '0',
            'transfers': 64,
            'checkers': 128,
            'enabled': True
        }
    ],
    'scheduleTime': '02:00',
    'scheduleInterval': 'daily',
    's3_remotes': []
}

# 全局状态
sync_status = {
    'tasks': {}  # task_id -> {status, pid, progress}
}
logs = []
rclone_installed = False

def log_message(msg_type, message):
    """添加日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logs.insert(0, {
        'type': msg_type,
        'message': message,
        'timestamp': timestamp
    })
    if len(logs) > 100:
        logs.pop()
    
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{timestamp}] {msg_type.upper()}: {message}\n")

def check_rclone_installed():
    """检查rclone是否已安装"""
    return shutil.which('rclone') is not None

def install_rclone():
    """自动安装rclone"""
    global rclone_installed
    
    log_message('info', '正在检查rclone安装状态...')
    
    if check_rclone_installed():
        log_message('success', 'rclone已安装')
        rclone_installed = True
        return True
    
    log_message('warning', 'rclone未安装，开始自动安装...')
    
    try:
        # 使用官方安装脚本 - 添加超时
        log_message('info', '下载rclone安装脚本...')
        subprocess.run(
            'curl https://rclone.org/install.sh | sudo bash',
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if check_rclone_installed():
            log_message('success', 'rclone安装成功！')
            rclone_installed = True
            
            # 获取版本信息
            result = subprocess.run(['rclone', 'version'], capture_output=True, text=True, timeout=10)
            version_info = result.stdout.split('\n')[0] if result.stdout else 'Unknown'
            log_message('info', f'版本: {version_info}')
            return True
        else:
            log_message('error', 'rclone安装失败')
            return False
            
    except subprocess.TimeoutExpired:
        log_message('error', '安装超时')
        return False
    except subprocess.CalledProcessError as e:
        log_message('error', f'安装失败: {str(e)}')
        return False
    except Exception as e:
        log_message('error', f'安装错误: {str(e)}')
        return False

def load_config():
    """加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                
                # 向后兼容：旧格式转新格式
                if 'localPath' in config and 'tasks' not in config:
                    config = {
                        'tasks': [{
                            'id': 'task_1',
                            'name': '默认同步任务',
                            'localPath': config.get('localPath', ''),
                            'remotePath': config.get('remotePath', ''),
                            'maxAge': config.get('maxAge', '0'),
                            'transfers': config.get('transfers', 64),
                            'checkers': config.get('checkers', 128),
                            'enabled': True
                        }],
                        'scheduleTime': config.get('scheduleTime', '02:00'),
                        'scheduleInterval': config.get('scheduleInterval', 'daily'),
                        's3_remotes': config.get('s3_remotes', [])
                    }
                    save_config(config)
                
                return config
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """保存配置"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_s3_remotes():
    """从rclone配置文件加载S3远程"""
    s3_remotes = []
    
    if not os.path.exists(RCLONE_CONFIG_FILE):
        return s3_remotes
    
    try:
        with open(RCLONE_CONFIG_FILE, 'r') as f:
            content = f.read()
            
        current_remote = None
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                current_remote = line[1:-1]
            elif current_remote and line.startswith('type ='):
                remote_type = line.split('=')[1].strip()
                if remote_type == 's3':
                    s3_remotes.append(current_remote)
                current_remote = None
    except Exception as e:
        log_message('error', f'读取rclone配置失败: {str(e)}')
    
    return s3_remotes

def add_s3_remote(name, access_key, secret_key, endpoint, region='auto', provider='Other', force_path_style=True):
    """添加S3远程配置"""
    try:
        # 确保配置目录存在
        config_dir = os.path.dirname(RCLONE_CONFIG_FILE)
        os.makedirs(config_dir, exist_ok=True)
        
        # MinIO特殊配置
        extra_config = ""
        if provider == 'Minio':
            extra_config = "no_check_bucket = true\n"
            if region == 'auto':
                region = 'us-east-1'  # MinIO默认region
        
        # 使用rclone config命令添加配置
        config_content = f"""
[{name}]
type = s3
provider = {provider}
access_key_id = {access_key}
secret_access_key = {secret_key}
endpoint = {endpoint}
region = {region}
acl = private
force_path_style = {str(force_path_style).lower()}
disable_checksum = true
{extra_config}"""
        
        # 读取现有配置
        existing_config = ""
        if os.path.exists(RCLONE_CONFIG_FILE):
            with open(RCLONE_CONFIG_FILE, 'r') as f:
                existing_config = f.read()
        
        # 检查是否已存在同名配置
        if f'[{name}]' in existing_config:
            # 删除旧配置
            lines = existing_config.split('\n')
            new_lines = []
            skip = False
            for line in lines:
                if line.strip().startswith('[') and line.strip().endswith(']'):
                    if line.strip() == f'[{name}]':
                        skip = True
                    else:
                        skip = False
                if not skip:
                    new_lines.append(line)
            existing_config = '\n'.join(new_lines)
        
        # 添加新配置
        with open(RCLONE_CONFIG_FILE, 'w') as f:
            f.write(existing_config.strip() + '\n' + config_content.strip() + '\n')
        
        log_message('success', f'S3远程 "{name}" 配置成功')
        return True
        
    except Exception as e:
        log_message('error', f'S3配置失败: {str(e)}')
        return False
        
        # 读取现有配置
        existing_config = ""
        if os.path.exists(RCLONE_CONFIG_FILE):
            with open(RCLONE_CONFIG_FILE, 'r') as f:
                existing_config = f.read()
        
        # 检查是否已存在同名配置
        if f'[{name}]' in existing_config:
            # 删除旧配置
            lines = existing_config.split('\n')
            new_lines = []
            skip = False
            for line in lines:
                if line.strip().startswith('[') and line.strip().endswith(']'):
                    if line.strip() == f'[{name}]':
                        skip = True
                    else:
                        skip = False
                if not skip:
                    new_lines.append(line)
            existing_config = '\n'.join(new_lines)
        
        # 添加新配置
        with open(RCLONE_CONFIG_FILE, 'w') as f:
            f.write(existing_config.strip() + '\n' + config_content.strip() + '\n')
        
        log_message('success', f'S3远程 "{name}" 配置成功')
        return True
        
    except Exception as e:
        log_message('error', f'S3配置失败: {str(e)}')
        return False

def get_s3_remote_config(name):
    """获取S3远程配置详情"""
    try:
        if not os.path.exists(RCLONE_CONFIG_FILE):
            return None
        
        with open(RCLONE_CONFIG_FILE, 'r') as f:
            content = f.read()
        
        config = {}
        in_section = False
        
        for line in content.split('\n'):
            line = line.strip()
            if line == f'[{name}]':
                in_section = True
                config['name'] = name
                continue
            elif line.startswith('[') and line.endswith(']'):
                if in_section:
                    break
                in_section = False
            elif in_section and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
        
        return config if config else None
        
    except Exception as e:
        log_message('error', f'读取S3配置失败: {str(e)}')
        return None

def delete_s3_remote(name):
    """删除S3远程配置"""
    try:
        if not os.path.exists(RCLONE_CONFIG_FILE):
            return False
        
        with open(RCLONE_CONFIG_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        skip = False
        for line in lines:
            if line.strip().startswith('[') and line.strip().endswith(']'):
                if line.strip() == f'[{name}]':
                    skip = True
                else:
                    skip = False
            if not skip:
                new_lines.append(line)
        
        with open(RCLONE_CONFIG_FILE, 'w') as f:
            f.writelines(new_lines)
        
        log_message('success', f'S3远程 "{name}" 已删除')
        return True
        
    except Exception as e:
        log_message('error', f'删除S3配置失败: {str(e)}')
        return False

def list_s3_buckets(remote_name):
    """列出S3存储桶"""
    try:
        result = subprocess.run(
            ['rclone', 'lsd', f'{remote_name}:'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            buckets = []
            for line in result.stdout.split('\n'):
                if line.strip():
                    # 格式: -1 2024-01-01 00:00:00        -1 bucket-name
                    parts = line.split()
                    if len(parts) >= 4:
                        buckets.append(parts[-1])
            return {'success': True, 'buckets': buckets}
        else:
            return {'success': False, 'error': result.stderr}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

def generate_sync_script(config):
    """生成同步脚本"""
    max_age = config['maxAge']
    max_age_line = f'    --max-age "$MAX_AGE" \\\n' if max_age and max_age != '0' else ''
    age_display = '不限制' if not max_age or max_age == '0' else max_age
    
    script = f'''#!/bin/bash
# Rclone增量同步脚本（自动生成）
# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

LOCAL_PATH="{config['localPath']}"
REMOTE_PATH="{config['remotePath']}"
MAX_AGE="{config['maxAge']}"
TRANSFERS={config['transfers']}
CHECKERS={config['checkers']}

LOG_DIR="/var/log/rclone"
LOG_FILE="$LOG_DIR/rclone_$(date +%Y%m%d_%H%M%S).log"
LOCKFILE="/var/run/rclone_sync.lock"

mkdir -p "$LOG_DIR"

if [ -e "$LOCKFILE" ]; then
    PID=$(cat "$LOCKFILE" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "已有同步任务在运行 (PID: $PID)"
        exit 1
    else
        rm -f "$LOCKFILE"
    fi
fi

echo $$ > "$LOCKFILE"

cleanup() {{
    rm -f "$LOCKFILE"
}}
trap cleanup EXIT INT TERM

echo "========================================" | tee -a "$LOG_FILE"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "本地路径: $LOCAL_PATH" | tee -a "$LOG_FILE"
echo "远程路径: $REMOTE_PATH" | tee -a "$LOG_FILE"
echo "文件年龄限制: {age_display}" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

rclone sync "$LOCAL_PATH" "$REMOTE_PATH" \\
{max_age_line}    --update \\
    --transfers "$TRANSFERS" \\
    --checkers "$CHECKERS" \\
    --s3-upload-cutoff 5M \\
    --s3-chunk-size 5M \\
    --s3-upload-concurrency 4 \\
    --s3-no-check-bucket \\
    --s3-disable-checksum \\
    --ignore-checksum \\
    --buffer-size 0 \\
    --use-server-modtime \\
    --log-file="$LOG_FILE" \\
    --log-level INFO \\
    --stats 1s \\
    --stats-one-line \\
    --progress \\
    2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${{PIPESTATUS[0]}}

echo "========================================" | tee -a "$LOG_FILE"
echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "退出码: $EXIT_CODE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

exit $EXIT_CODE
'''
    return script

def run_sync(task_config, task_id='task_1'):
    """执行同步任务"""
    global sync_status
    
    try:
        if not rclone_installed:
            log_message('error', 'rclone未安装，无法执行同步')
            return
        
        # 初始化任务状态
        sync_status['tasks'][task_id] = {
            'status': 'running',
            'pid': None,
            'progress': {
                'transferred': '0 B',
                'total': '0 B',
                'percentage': 0,
                'speed': '0 B/s',
                'eta': '-',
                'current_file': ''
            },
            'name': task_config.get('name', task_id)
        }
        
        script_content = generate_sync_script(task_config)
        script_path = f'/tmp/rclone_sync_{task_id}.sh'
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)
        
        log_message('info', f'开始同步任务: {task_config.get("name", task_id)}')
        log_message('info', f'本地路径: {task_config["localPath"]}')
        log_message('info', f'远程路径: {task_config["remotePath"]}')
        
        process = subprocess.Popen(
            [script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        sync_status['tasks'][task_id]['pid'] = process.pid
        
        import re
        for line in process.stdout:
            line = line.strip()
            if line:
                # 解析进度信息
                if 'Transferred:' in line and '/' in line:
                    try:
                        parts = line.split('Transferred:')[1].strip()
                        if '/' in parts:
                            transferred_total = parts.split(',')[0].strip()
                            transferred, total = transferred_total.split('/')
                            sync_status['tasks'][task_id]['progress']['transferred'] = transferred.strip()
                            sync_status['tasks'][task_id]['progress']['total'] = total.strip()
                            
                            if '%' in parts:
                                percentage = re.search(r'(\d+)%', parts)
                                if percentage:
                                    sync_status['tasks'][task_id]['progress']['percentage'] = int(percentage.group(1))
                            
                            speed_match = re.search(r'([\d.]+\s*[KMGT]?i?B/s)', parts)
                            if speed_match:
                                sync_status['tasks'][task_id]['progress']['speed'] = speed_match.group(1)
                            
                            eta_match = re.search(r'ETA\s+(\S+)', parts)
                            if eta_match:
                                sync_status['tasks'][task_id]['progress']['eta'] = eta_match.group(1)
                    except:
                        pass
                
                if line.startswith('*') or 'Transferring:' in line:
                    try:
                        filename = re.search(r'\*\s+(.+?):', line)
                        if filename:
                            sync_status['tasks'][task_id]['progress']['current_file'] = filename.group(1).strip()
                    except:
                        pass
                
                log_message('info', line)
        
        process.wait()
        
        if process.returncode == 0:
            sync_status['tasks'][task_id]['status'] = 'success'
            sync_status['tasks'][task_id]['progress']['percentage'] = 100
            log_message('success', f'任务 {task_config.get("name", task_id)} 同步成功！')
        else:
            sync_status['tasks'][task_id]['status'] = 'error'
            log_message('error', f'任务 {task_config.get("name", task_id)} 同步失败，退出码: {process.returncode}')
    
    except Exception as e:
        if task_id in sync_status['tasks']:
            sync_status['tasks'][task_id]['status'] = 'error'
        log_message('error', f'执行错误: {str(e)}')
    finally:
        if task_id in sync_status['tasks']:
            sync_status['tasks'][task_id]['pid'] = None

class RcloneWebHandler(http.server.SimpleHTTPRequestHandler):
    """Web请求处理器"""
    
    def do_GET(self):
        """处理GET请求"""
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        
        elif self.path == '/api/config':
            config = load_config()
            config['s3_remotes'] = load_s3_remotes()
            self.send_json(config)
        
        elif self.path == '/api/status':
            self.send_json({
                'tasks': sync_status['tasks'],
                'rclone_installed': rclone_installed
            })
        
        elif self.path == '/api/logs':
            self.send_json({'logs': logs})
        
        elif self.path == '/api/remotes' or self.path == '/api/s3/remotes':
            remotes = load_s3_remotes()
            self.send_json({'remotes': remotes})
        
        elif self.path.startswith('/api/s3/config/'):
            remote_name = self.path.split('/')[-1]
            config = get_s3_remote_config(remote_name)
            if config:
                self.send_json({'success': True, 'config': config})
            else:
                self.send_json({'success': False, 'error': '配置不存在'})
        
        elif self.path.startswith('/api/s3/buckets/'):
            remote_name = self.path.split('/')[-1]
            result = list_s3_buckets(remote_name)
            self.send_json(result)
        
        elif self.path.startswith('/api/download/'):
            self.handle_download()
        
        else:
            self.send_error(404)
    
    def do_POST(self):
        """处理POST请求"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/config':
            try:
                config = json.loads(post_data.decode())
                save_config(config)
                log_message('success', '配置已保存')
                self.send_json({'success': True, 'message': '配置已保存'})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        elif self.path == '/api/sync/start':
            try:
                data = json.loads(post_data.decode())
                task_id = data.get('task_id', 'task_1')
                
                # 检查任务是否已在运行
                if task_id in sync_status['tasks'] and sync_status['tasks'][task_id].get('status') == 'running':
                    self.send_json({'success': False, 'message': '该任务已在运行'})
                    return
                
                # 加载配置
                config = load_config()
                task_config = None
                
                # 查找对应的任务配置
                for task in config.get('tasks', []):
                    if task['id'] == task_id:
                        task_config = task
                        break
                
                if not task_config:
                    self.send_json({'success': False, 'message': '任务不存在'})
                    return
                
                if not task_config.get('enabled', True):
                    self.send_json({'success': False, 'message': '任务已禁用'})
                    return
                
                # 启动同步任务
                threading.Thread(target=run_sync, args=(task_config, task_id), daemon=True).start()
                self.send_json({'success': True, 'message': f'任务 {task_config.get("name", task_id)} 已启动'})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        elif self.path == '/api/logs/clear':
            logs.clear()
            log_message('info', '日志已清空')
            self.send_json({'success': True})
        
        elif self.path == '/api/rclone/install':
            if rclone_installed:
                self.send_json({'success': True, 'message': 'rclone已安装'})
            else:
                threading.Thread(target=install_rclone, daemon=True).start()
                self.send_json({'success': True, 'message': '开始安装rclone...'})
        
        elif self.path == '/api/s3/add':
            try:
                data = json.loads(post_data.decode())
                success = add_s3_remote(
                    data['name'],
                    data['accessKey'],
                    data['secretKey'],
                    data['endpoint'],
                    data.get('region', 'auto'),
                    data.get('provider', 'Other'),
                    data.get('forcePathStyle', True)
                )
                if success:
                    self.send_json({'success': True, 'message': 'S3配置已添加'})
                else:
                    self.send_json({'success': False, 'message': '添加失败'})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        elif self.path == '/api/s3/delete':
            try:
                data = json.loads(post_data.decode())
                success = delete_s3_remote(data['name'])
                if success:
                    self.send_json({'success': True, 'message': 'S3配置已删除'})
                else:
                    self.send_json({'success': False, 'message': '删除失败'})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        elif self.path == '/api/task/add':
            try:
                data = json.loads(post_data.decode())
                config = load_config()
                
                # 生成新的任务ID
                existing_ids = [task['id'] for task in config.get('tasks', [])]
                task_num = 1
                while f'task_{task_num}' in existing_ids:
                    task_num += 1
                
                new_task = {
                    'id': f'task_{task_num}',
                    'name': data.get('name', f'任务{task_num}'),
                    'localPath': data.get('localPath', ''),
                    'remotePath': data.get('remotePath', ''),
                    'maxAge': data.get('maxAge', '0'),
                    'transfers': int(data.get('transfers', 64)),
                    'checkers': int(data.get('checkers', 128)),
                    'enabled': data.get('enabled', True)
                }
                
                if 'tasks' not in config:
                    config['tasks'] = []
                config['tasks'].append(new_task)
                save_config(config)
                
                log_message('success', f'已添加任务: {new_task["name"]}')
                self.send_json({'success': True, 'message': '任务已添加', 'task': new_task})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        elif self.path == '/api/task/update':
            try:
                data = json.loads(post_data.decode())
                task_id = data.get('id')
                config = load_config()
                
                # 查找并更新任务
                updated = False
                for i, task in enumerate(config.get('tasks', [])):
                    if task['id'] == task_id:
                        config['tasks'][i] = {
                            'id': task_id,
                            'name': data.get('name', task['name']),
                            'localPath': data.get('localPath', task['localPath']),
                            'remotePath': data.get('remotePath', task['remotePath']),
                            'maxAge': data.get('maxAge', task.get('maxAge', '0')),
                            'transfers': int(data.get('transfers', task.get('transfers', 64))),
                            'checkers': int(data.get('checkers', task.get('checkers', 128))),
                            'enabled': data.get('enabled', task.get('enabled', True))
                        }
                        updated = True
                        break
                
                if updated:
                    save_config(config)
                    log_message('success', f'已更新任务: {data.get("name")}')
                    self.send_json({'success': True, 'message': '任务已更新'})
                else:
                    self.send_json({'success': False, 'message': '任务不存在'})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        elif self.path == '/api/task/delete':
            try:
                data = json.loads(post_data.decode())
                task_id = data.get('id')
                config = load_config()
                
                # 删除任务
                original_len = len(config.get('tasks', []))
                config['tasks'] = [task for task in config.get('tasks', []) if task['id'] != task_id]
                
                if len(config['tasks']) < original_len:
                    save_config(config)
                    log_message('success', f'已删除任务: {task_id}')
                    self.send_json({'success': True, 'message': '任务已删除'})
                else:
                    self.send_json({'success': False, 'message': '任务不存在'})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        elif self.path == '/api/task/toggle':
            try:
                data = json.loads(post_data.decode())
                task_id = data.get('id')
                config = load_config()
                
                # 切换任务启用状态
                updated = False
                for task in config.get('tasks', []):
                    if task['id'] == task_id:
                        task['enabled'] = not task.get('enabled', True)
                        updated = True
                        break
                
                if updated:
                    save_config(config)
                    self.send_json({'success': True, 'message': '任务状态已更新'})
                else:
                    self.send_json({'success': False, 'message': '任务不存在'})
            except Exception as e:
                self.send_json({'success': False, 'message': str(e)})
        
        else:
            self.send_error(404)
    
    def send_json(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def handle_download(self):
        """处理文件下载"""
        filename = self.path.split('/')[-1]
        config = load_config()
        
        content = ''
        
        if filename == 'script.sh':
            content = generate_sync_script(config)
        elif filename == 'crontab.txt':
            hour, minute = config['scheduleTime'].split(':')
            if config['scheduleInterval'] == 'daily':
                cron = f"{minute} {hour} * * *"
            elif config['scheduleInterval'] == '6hours':
                cron = f"{minute} */6 * * *"
            elif config['scheduleInterval'] == '12hours':
                cron = f"{minute} */12 * * *"
            else:
                cron = f"{minute} {hour} * * *"
            content = f"# Rclone增量同步定时任务\n{cron} {SYNC_SCRIPT} >> /var/log/rclone/cron.log 2>&1\n"
        elif filename == 'rclone.conf':
            if os.path.exists(RCLONE_CONFIG_FILE):
                with open(RCLONE_CONFIG_FILE, 'r') as f:
                    content = f.read()
        
        if content:
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content.encode())
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        """禁止打印访问日志到终端"""
        pass

# HTML页面

# HTML页面
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rclone Web Manager - 多任务版</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1600px; margin: 0 auto; }
        .header { background: white; padding: 30px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); margin-bottom: 20px; text-align: center; }
        .header h1 { color: #2d3748; font-size: 32px; margin-bottom: 10px; }
        .header p { color: #718096; }
        .panel { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); margin-bottom: 20px; }
        .panel h2 { color: #2d3748; font-size: 20px; margin-bottom: 20px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
        
        /* 任务卡片 */
        .task-card { background: #f7fafc; border: 2px solid #e2e8f0; border-radius: 10px; padding: 20px; margin-bottom: 15px; transition: all 0.3s; }
        .task-card:hover { border-color: #667eea; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        .task-card.running { border-color: #48bb78; background: #f0fff4; }
        .task-card.success { border-color: #48bb78; }
        .task-card.error { border-color: #f56565; background: #fff5f5; }
        .task-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .task-name { font-size: 18px; font-weight: 600; color: #2d3748; }
        .task-status { padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .task-status.idle { background: #e2e8f0; color: #4a5568; }
        .task-status.running { background: #48bb78; color: white; animation: pulse 1s infinite; }
        .task-status.success { background: #48bb78; color: white; }
        .task-status.error { background: #f56565; color: white; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
        
        .task-info { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; font-size: 13px; }
        .task-info-item { color: #4a5568; }
        .task-info-item strong { color: #2d3748; }
        
        /* 进度条 */
        .task-progress { margin: 15px 0; }
        .progress-bar { width: 100%; height: 25px; background: #e2e8f0; border-radius: 12px; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); transition: width 0.3s; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: 600; }
        .progress-details { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 10px; font-size: 11px; }
        .progress-detail { background: white; padding: 6px 10px; border-radius: 6px; border: 1px solid #e2e8f0; }
        .progress-detail strong { display: block; color: #718096; margin-bottom: 2px; }
        .progress-detail span { color: #2d3748; font-weight: 500; }
        
        /* 任务操作按钮 */
        .task-actions { display: flex; gap: 10px; }
        .btn-sm { padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; transition: all 0.2s; font-weight: 500; }
        .btn-start { background: #48bb78; color: white; }
        .btn-start:hover { background: #38a169; }
        .btn-edit { background: #667eea; color: white; }
        .btn-edit:hover { background: #5a67d8; }
        .btn-delete { background: #f56565; color: white; }
        .btn-delete:hover { background: #e53e3e; }
        .btn-toggle { background: #ed8936; color: white; }
        .btn-toggle:hover { background: #dd6b20; }
        .btn-sm:disabled { background: #cbd5e0; cursor: not-allowed; }
        
        /* 表单 */
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; color: #4a5568; margin-bottom: 5px; font-weight: 500; font-size: 14px; }
        .form-group input, .form-group select { width: 100%; padding: 10px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 14px; transition: border 0.3s; }
        .form-group input:focus, .form-group select:focus { outline: none; border-color: #667eea; }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        
        /* 按钮 */
        .btn-primary, .btn-secondary { width: 100%; padding: 15px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; transition: all 0.3s; font-weight: 600; margin-top: 10px; }
        .btn-primary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4); }
        .btn-secondary { background: #e2e8f0; color: #2d3748; }
        .btn-secondary:hover { background: #cbd5e0; }
        
        /* S3配置 */
        .s3-list { max-height: 200px; overflow-y: auto; border: 2px solid #e2e8f0; border-radius: 8px; padding: 10px; }
        .s3-item { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #f7fafc; border-radius: 5px; margin-bottom: 5px; }
        .badge { display: inline-block; padding: 4px 8px; background: #667eea; color: white; border-radius: 4px; font-size: 12px; }
        
        /* 日志 */
        .logs-container { background: #1a202c; padding: 15px; border-radius: 8px; height: 400px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 13px; }
        .log-entry { margin-bottom: 5px; line-height: 1.5; }
        .log-time { color: #718096; }
        .log-info { color: #63b3ed; }
        .log-success { color: #68d391; }
        .log-error { color: #fc8181; }
        
        .alert { padding: 15px; border-radius: 8px; margin-bottom: 15px; }
        .alert-warning { background: #fef5e7; border-left: 4px solid #f6ad55; color: #975a16; }
        .hidden { display: none; }
        
        @media (max-width: 768px) { .grid-2 { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Rclone Web Manager - 多任务版</h1>
            <p>多任务同步 | 实时进度 | S3配置</p>
        </div>
        
        <!-- 系统提示 -->
        <div id="rcloneAlert" class="alert alert-warning" style="display: none;">
            <strong>⚠️ Rclone未安装</strong><br>
            请点击下方按钮自动安装 Rclone
            <button class="btn-primary" onclick="installRclone()" style="margin-top: 10px; width: 200px;">📦 安装 Rclone</button>
        </div>
        
        <!-- 同步任务列表 -->
        <div class="panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="margin: 0;">📋 同步任务</h2>
                <button class="btn-sm btn-start" onclick="showTaskForm()">➕ 添加任务</button>
            </div>
            
            <div id="tasksList"></div>
            
            <div id="emptyTasks" style="text-align: center; padding: 40px; color: #718096; display: none;">
                <p style="font-size: 18px; margin-bottom: 10px;">📝 还没有任务</p>
                <p>点击"添加任务"创建第一个同步任务</p>
            </div>
        </div>
        
        <!-- 添加/编辑任务表单 -->
        <div id="taskFormPanel" class="panel hidden">
            <h2 id="taskFormTitle">➕ 添加任务</h2>
            <input type="hidden" id="taskFormMode" value="add">
            <input type="hidden" id="taskFormId" value="">
            
            <div class="form-group">
                <label>任务名称</label>
                <input type="text" id="taskName" placeholder="例如：同步照片到云端">
            </div>
            
            <div class="grid-2">
                <div class="form-group">
                    <label>本地路径</label>
                    <input type="text" id="taskLocalPath" placeholder="/path/to/local">
                </div>
                <div class="form-group">
                    <label>远程路径</label>
                    <input type="text" id="taskRemotePath" placeholder="minio:bucket/path">
                </div>
            </div>
            
            <div class="grid-2">
                <div class="form-group">
                    <label>最大文件年龄</label>
                    <input type="text" id="taskMaxAge" value="0" placeholder="0=全部, 24h, 7d">
                </div>
                <div class="form-group">
                    <label>并发传输数</label>
                    <input type="number" id="taskTransfers" value="64" min="1" max="256">
                </div>
            </div>
            
            <div class="form-group">
                <label>检查线程数</label>
                <input type="number" id="taskCheckers" value="128" min="1" max="512">
            </div>
            
            <div class="form-group">
                <label style="display: flex; align-items: center; cursor: pointer;">
                    <input type="checkbox" id="taskEnabled" checked style="width: auto; margin-right: 8px;">
                    <span>启用此任务</span>
                </label>
            </div>
            
            <button class="btn-primary" onclick="saveTask()">💾 保存任务</button>
            <button class="btn-secondary" onclick="hideTaskForm()">取消</button>
        </div>
        
        <!-- S3配置 -->
        <div class="panel">
            <h2>☁️ S3 远程管理</h2>
            <div id="s3List" class="s3-list"></div>
            <button class="btn-secondary" onclick="toggleS3Form()">➕ 添加 S3 远程</button>
        </div>
        
        <div id="s3Form" class="panel hidden">
            <h2 id="s3FormTitle">➕ 添加 S3 远程</h2>
            <input type="hidden" id="s3EditMode" value="false">
            <input type="hidden" id="s3OriginalName" value="">
            
            <div class="form-group">
                <label>远程名称</label>
                <input type="text" id="s3Name" placeholder="minio">
            </div>
            
            <div class="grid-2">
                <div class="form-group">
                    <label>Access Key</label>
                    <input type="text" id="s3AccessKey" placeholder="minioadmin">
                </div>
                <div class="form-group">
                    <label>Secret Key</label>
                    <input type="password" id="s3SecretKey" placeholder="minioadmin">
                </div>
            </div>
            
            <div class="grid-2">
                <div class="form-group">
                    <label>Endpoint</label>
                    <input type="text" id="s3Endpoint" placeholder="localhost:9000">
                </div>
                <div class="form-group">
                    <label>Region</label>
                    <input type="text" id="s3Region" value="us-east-1">
                </div>
            </div>
            
            <div class="form-group">
                <label>Provider</label>
                <select id="s3Provider">
                    <option value="AWS">AWS</option>
                    <option value="Minio" selected>MinIO</option>
                    <option value="Alibaba">阿里云</option>
                    <option value="Tencent">腾讯云</option>
                    <option value="Other">其他</option>
                </select>
            </div>
            
            <div class="form-group">
                <label style="display: flex; align-items: center; cursor: pointer;">
                    <input type="checkbox" id="s3ForcePathStyle" checked style="width: auto; margin-right: 8px;">
                    <span>Force Path Style（MinIO必需）</span>
                </label>
            </div>
            
            <button class="btn-primary" id="s3SubmitBtn" onclick="saveS3Remote()">✅ 添加配置</button>
            <button class="btn-secondary" onclick="toggleS3Form()">取消</button>
        </div>
        
        <!-- 日志 -->
        <div class="panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2 style="margin: 0;">📄 系统日志</h2>
                <button class="btn-sm btn-delete" onclick="clearLogs()">🗑️ 清空</button>
            </div>
            <div class="logs-container" id="logs"></div>
        </div>
    </div>

    <script>
        let config = {};
        let tasksStatus = {};
        
        async function loadConfig() {
            const res = await fetch('/api/config');
            config = await res.json();
            renderTasks();
            loadS3Remotes();
        }
        
        async function updateStatus() {
            const res = await fetch('/api/status');
            const data = await res.json();
            tasksStatus = data.tasks || {};
            
            // 更新Rclone状态
            if (!data.rclone_installed) {
                document.getElementById('rcloneAlert').style.display = 'block';
            }
            
            renderTasks();
        }
        
        function renderTasks() {
            const container = document.getElementById('tasksList');
            const emptyDiv = document.getElementById('emptyTasks');
            const tasks = config.tasks || [];
            
            if (tasks.length === 0) {
                container.innerHTML = '';
                emptyDiv.style.display = 'block';
                return;
            }
            
            emptyDiv.style.display = 'none';
            
            container.innerHTML = tasks.map(task => {
                const status = tasksStatus[task.id] || { status: 'idle', progress: {} };
                const progress = status.progress || {};
                const percentage = progress.percentage || 0;
                const isRunning = status.status === 'running';
                const isDisabled = !task.enabled;
                
                return `
                    <div class="task-card ${status.status}">
                        <div class="task-header">
                            <div class="task-name">${task.name || task.id}</div>
                            <span class="task-status ${status.status}">${getStatusText(status.status)}</span>
                        </div>
                        
                        <div class="task-info">
                            <div class="task-info-item"><strong>本地:</strong> ${task.localPath}</div>
                            <div class="task-info-item"><strong>远程:</strong> ${task.remotePath}</div>
                            <div class="task-info-item"><strong>年龄限制:</strong> ${task.maxAge || '0'}${task.maxAge && task.maxAge !== '0' ? '' : '（全部文件）'}</div>
                            <div class="task-info-item"><strong>并发:</strong> ${task.transfers} / ${task.checkers}</div>
                        </div>
                        
                        ${isRunning ? `
                        <div class="task-progress">
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${percentage}%">${percentage}%</div>
                            </div>
                            <div class="progress-details">
                                <div class="progress-detail">
                                    <strong>已传输</strong>
                                    <span>${progress.transferred || '0 B'} / ${progress.total || '0 B'}</span>
                                </div>
                                <div class="progress-detail">
                                    <strong>速度</strong>
                                    <span>${progress.speed || '0 B/s'}</span>
                                </div>
                                <div class="progress-detail">
                                    <strong>剩余时间</strong>
                                    <span>${progress.eta || '-'}</span>
                                </div>
                                <div class="progress-detail">
                                    <strong>当前文件</strong>
                                    <span title="${progress.current_file || ''}" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${progress.current_file || '-'}</span>
                                </div>
                            </div>
                        </div>
                        ` : ''}
                        
                        <div class="task-actions">
                            <button class="btn-sm btn-start" onclick="startTask('${task.id}')" ${isRunning || isDisabled ? 'disabled' : ''}>
                                ${isRunning ? '▶️ 运行中...' : '▶️ 启动'}
                            </button>
                            <button class="btn-sm btn-edit" onclick="editTask('${task.id}')" ${isRunning ? 'disabled' : ''}>✏️ 编辑</button>
                            <button class="btn-sm btn-toggle" onclick="toggleTask('${task.id}')">${task.enabled ? '⏸️ 禁用' : '▶️ 启用'}</button>
                            <button class="btn-sm btn-delete" onclick="deleteTask('${task.id}')" ${isRunning ? 'disabled' : ''}>🗑️ 删除</button>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        function getStatusText(status) {
            const map = {
                'idle': '待机',
                'running': '运行中',
                'success': '成功',
                'error': '错误'
            };
            return map[status] || '未知';
        }
        
        async function startTask(taskId) {
            try {
                const res = await fetch('/api/sync/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_id: taskId })
                });
                const result = await res.json();
                alert(result.message);
                if (result.success) updateStatus();
            } catch (error) {
                alert('启动失败: ' + error.message);
            }
        }
        
        function showTaskForm() {
            document.getElementById('taskFormPanel').classList.remove('hidden');
            document.getElementById('taskFormTitle').textContent = '➕ 添加任务';
            document.getElementById('taskFormMode').value = 'add';
            document.getElementById('taskFormId').value = '';
            document.getElementById('taskName').value = '';
            document.getElementById('taskLocalPath').value = '';
            document.getElementById('taskRemotePath').value = '';
            document.getElementById('taskMaxAge').value = '0';
            document.getElementById('taskTransfers').value = '64';
            document.getElementById('taskCheckers').value = '128';
            document.getElementById('taskEnabled').checked = true;
            document.getElementById('taskFormPanel').scrollIntoView({ behavior: 'smooth' });
        }
        
        function hideTaskForm() {
            document.getElementById('taskFormPanel').classList.add('hidden');
        }
        
        async function editTask(taskId) {
            const task = config.tasks.find(t => t.id === taskId);
            if (!task) return;
            
            document.getElementById('taskFormPanel').classList.remove('hidden');
            document.getElementById('taskFormTitle').textContent = '✏️ 编辑任务';
            document.getElementById('taskFormMode').value = 'edit';
            document.getElementById('taskFormId').value = task.id;
            document.getElementById('taskName').value = task.name || '';
            document.getElementById('taskLocalPath').value = task.localPath;
            document.getElementById('taskRemotePath').value = task.remotePath;
            document.getElementById('taskMaxAge').value = task.maxAge || '0';
            document.getElementById('taskTransfers').value = task.transfers;
            document.getElementById('taskCheckers').value = task.checkers;
            document.getElementById('taskEnabled').checked = task.enabled !== false;
            document.getElementById('taskFormPanel').scrollIntoView({ behavior: 'smooth' });
        }
        
        async function saveTask() {
            const mode = document.getElementById('taskFormMode').value;
            const taskData = {
                name: document.getElementById('taskName').value,
                localPath: document.getElementById('taskLocalPath').value,
                remotePath: document.getElementById('taskRemotePath').value,
                maxAge: document.getElementById('taskMaxAge').value,
                transfers: parseInt(document.getElementById('taskTransfers').value),
                checkers: parseInt(document.getElementById('taskCheckers').value),
                enabled: document.getElementById('taskEnabled').checked
            };
            
            if (!taskData.name || !taskData.localPath || !taskData.remotePath) {
                alert('请填写必填项：任务名称、本地路径、远程路径');
                return;
            }
            
            try {
                let url = '/api/task/add';
                if (mode === 'edit') {
                    url = '/api/task/update';
                    taskData.id = document.getElementById('taskFormId').value;
                }
                
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(taskData)
                });
                const result = await res.json();
                
                if (result.success) {
                    alert(mode === 'add' ? '任务添加成功！' : '任务更新成功！');
                    hideTaskForm();
                    await loadConfig();
                } else {
                    alert('保存失败: ' + result.message);
                }
            } catch (error) {
                alert('保存失败: ' + error.message);
            }
        }
        
        async function deleteTask(taskId) {
            if (!confirm('确定要删除这个任务吗？')) return;
            
            try {
                const res = await fetch('/api/task/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: taskId })
                });
                const result = await res.json();
                
                if (result.success) {
                    alert('任务已删除');
                    await loadConfig();
                } else {
                    alert('删除失败: ' + result.message);
                }
            } catch (error) {
                alert('删除失败: ' + error.message);
            }
        }
        
        async function toggleTask(taskId) {
            try {
                const res = await fetch('/api/task/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: taskId })
                });
                const result = await res.json();
                
                if (result.success) {
                    await loadConfig();
                } else {
                    alert('操作失败: ' + result.message);
                }
            } catch (error) {
                alert('操作失败: ' + error.message);
            }
        }
        
        async function loadS3Remotes() {
            const res = await fetch('/api/s3/remotes');
            const data = await res.json();
            const remotes = data.remotes || [];
            const listEl = document.getElementById('s3List');
            
            if (remotes.length === 0) {
                listEl.innerHTML = '<div style="color: #718096; text-align: center; padding: 20px;">暂无S3配置</div>';
            } else {
                listEl.innerHTML = remotes.map(remote => `
                    <div class="s3-item">
                        <span class="badge">${remote}</span>
                        <div>
                            <button class="btn-sm btn-delete" onclick="deleteS3('${remote}')" style="padding: 5px 10px; font-size: 11px;">删除</button>
                        </div>
                    </div>
                `).join('');
            }
        }
        
        function toggleS3Form() {
            const form = document.getElementById('s3Form');
            form.classList.toggle('hidden');
        }
        
        async function saveS3Remote() {
            const data = {
                name: document.getElementById('s3Name').value,
                access_key: document.getElementById('s3AccessKey').value,
                secret_key: document.getElementById('s3SecretKey').value,
                endpoint: document.getElementById('s3Endpoint').value,
                region: document.getElementById('s3Region').value,
                provider: document.getElementById('s3Provider').value,
                force_path_style: document.getElementById('s3ForcePathStyle').checked
            };
            
            if (!data.name || !data.access_key || !data.secret_key || !data.endpoint) {
                alert('请填写所有必填项');
                return;
            }
            
            try {
                const res = await fetch('/api/s3/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                
                if (result.success) {
                    alert('S3配置添加成功！');
                    toggleS3Form();
                    loadS3Remotes();
                } else {
                    alert('添加失败: ' + result.message);
                }
            } catch (error) {
                alert('添加失败: ' + error.message);
            }
        }
        
        async function deleteS3(name) {
            if (!confirm('确定要删除 S3 配置 "' + name + '" 吗？')) return;
            
            try {
                const res = await fetch('/api/s3/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name })
                });
                const result = await res.json();
                
                if (result.success) {
                    alert('S3配置已删除');
                    loadS3Remotes();
                } else {
                    alert('删除失败: ' + result.message);
                }
            } catch (error) {
                alert('删除失败: ' + error.message);
            }
        }
        
        async function loadLogs() {
            const res = await fetch('/api/logs');
            const data = await res.json();
            const logsEl = document.getElementById('logs');
            
            logsEl.innerHTML = data.logs.map(log => {
                const className = 'log-' + log.level;
                return `<div class="log-entry"><span class="log-time">${log.time}</span> <span class="${className}">${log.message}</span></div>`;
            }).join('');
            logsEl.scrollTop = logsEl.scrollHeight;
        }
        
        async function clearLogs() {
            await fetch('/api/logs/clear', { method: 'POST' });
            loadLogs();
        }
        
        async function installRclone() {
            if (!confirm('确定要安装 Rclone 吗？这可能需要几分钟时间。')) return;
            alert('开始安装 Rclone，请等待...');
            
            try {
                const res = await fetch('/api/rclone/install', { method: 'POST' });
                const result = await res.json();
                alert(result.message);
                if (result.success) {
                    location.reload();
                }
            } catch (error) {
                alert('安装失败: ' + error.message);
            }
        }
        
        // 初始化
        loadConfig();
        updateStatus();
        loadLogs();
        
        // 定时更新
        setInterval(updateStatus, 2000);
        setInterval(loadLogs, 3000);
    </script>
</body>
</html>
"""

def main():
    """主函数"""
    global rclone_installed
    
    print("=" * 60)
    print("🚀 Rclone Web管理器启动中...")
    print("=" * 60)
    
    # 检查并安装rclone
    rclone_installed = check_rclone_installed()
    
    if not rclone_installed:
        print("⚠️  Rclone未安装")
        print("💡 请在Web界面点击 '安装 Rclone' 按钮自动安装")
        print("   或手动运行: curl https://rclone.org/install.sh | sudo bash")
    else:
        print("✓ Rclone已安装")
        # 显示版本信息
        try:
            result = subprocess.run(['rclone', 'version'], capture_output=True, text=True, timeout=5)
            version_info = result.stdout.split('\n')[0] if result.stdout else 'Unknown'
            print(f"✓ {version_info}")
        except:
            pass
    
    print(f"✓ 访问地址: http://localhost:{PORT}")
    print(f"✓ 或使用: http://你的服务器IP:{PORT}")
    print(f"✓ 配置文件: {CONFIG_FILE}")
    print(f"✓ 日志文件: {LOG_FILE}")
    print("=" * 60)
    print("按 Ctrl+C 停止服务\n")
    
    log_message('info', 'Web服务器启动')
    if rclone_installed:
        log_message('success', 'Rclone已就绪')
    else:
        log_message('warning', 'Rclone未安装，请手动安装')
    
    Handler = RcloneWebHandler
    
    # 使用 ThreadingTCPServer 支持并发请求
    class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
    
    with ThreadingTCPServer(("", PORT), Handler) as httpd:
        try:
            print("✓ 服务器已启动（支持并发请求）\n")
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n✓ 服务器已停止")
            log_message('info', 'Web服务器停止')

if __name__ == "__main__":
    main()
