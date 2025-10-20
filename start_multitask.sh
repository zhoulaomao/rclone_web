#!/usr/bin/env python3
"""
Rclone Web Manager - Multi-Task Version with Password Protection
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
import time
import hashlib
import base64
import secrets
from urllib.parse import parse_qs, urlparse

# 尝试导入schedule模块
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False
    print("警告: schedule模块未安装，定时任务功能不可用")
    print("安装方法: pip install schedule --break-system-packages")

# 配置
CONFIG_FILE = '/tmp/rclone_web_config.json'
RCLONE_CONFIG_FILE = os.path.expanduser('~/.config/rclone/rclone.conf')
LOG_FILE = '/tmp/rclone_web.log'
SYNC_SCRIPT = '/usr/local/bin/rclone_sync_generated.sh'
AUTH_FILE = '/tmp/rclone_web_auth.json'
PORT = 5000

# 认证相关函数（需要在配置之前定义）
def hash_password(password):
    """加密密码"""
    return hashlib.sha256(password.encode()).hexdigest()

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
            'enabled': True,
            'schedule': {
                'enabled': False,
                'type': 'daily',  # daily, weekly, interval
                'time': '02:00',  # HH:MM 格式
                'interval': 60,   # 分钟（当type=interval时使用）
                'weekday': 'monday'  # 星期（当type=weekly时使用）
            }
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
scheduler_thread = None
scheduler_running = False
scheduled_jobs = {}  # task_id -> schedule.Job
active_sessions = {}  # session_id -> {username, created_at, last_access}

def generate_session_id():
    """生成会话ID"""
    return secrets.token_urlsafe(32)

def load_auth():
    """加载认证配置"""
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    # 创建默认认证文件
    auth = {
        'username': 'admin',
        'password_hash': hash_password('admin123')
    }
    save_auth(auth)
    return auth

def save_auth(auth):
    """保存认证配置"""
    with open(AUTH_FILE, 'w') as f:
        json.dump(auth, f, indent=2)

def verify_credentials(username, password):
    """验证用户名和密码"""
    auth = load_auth()
    return (username == auth['username'] and 
            hash_password(password) == auth['password_hash'])

def create_session(username):
    """创建会话"""
    session_id = generate_session_id()
    active_sessions[session_id] = {
        'username': username,
        'created_at': time.time(),
        'last_access': time.time()
    }
    return session_id

def verify_session(session_id):
    """验证会话"""
    if not session_id or session_id not in active_sessions:
        return False
    
    session = active_sessions[session_id]
    # 检查会话是否过期(24小时)
    if time.time() - session['last_access'] > 86400:
        del active_sessions[session_id]
        return False
    
    # 更新最后访问时间
    session['last_access'] = time.time()
    return True

def delete_session(session_id):
    """删除会话"""
    if session_id in active_sessions:
        del active_sessions[session_id]

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
                if line.strip().startswith('['):
                    skip = (line.strip() == f'[{name}]')
                if not skip:
                    new_lines.append(line)
            existing_config = '\n'.join(new_lines)
        
        # 添加新配置
        with open(RCLONE_CONFIG_FILE, 'w') as f:
            f.write(existing_config.rstrip() + '\n' + config_content + '\n')
        
        log_message('success', f'S3配置 "{name}" 添加成功')
        return True
    except Exception as e:
        log_message('error', f'添加S3配置失败: {str(e)}')
        return False

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
            if line.strip().startswith('['):
                skip = (line.strip() == f'[{name}]')
            if not skip:
                new_lines.append(line)
        
        with open(RCLONE_CONFIG_FILE, 'w') as f:
            f.writelines(new_lines)
        
        log_message('success', f'S3配置 "{name}" 已删除')
        return True
    except Exception as e:
        log_message('error', f'删除S3配置失败: {str(e)}')
        return False

def get_s3_config(name):
    """获取S3配置详情"""
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

def run_sync_task(task):
    """运行同步任务"""
    if not rclone_installed:
        log_message('error', '无法运行同步：rclone未安装')
        return False
    
    task_id = task['id']
    local_path = task['localPath']
    remote_path = task['remotePath']
    max_age = task.get('maxAge', '0')
    transfers = task.get('transfers', 64)
    checkers = task.get('checkers', 128)
    
    # 确保本地路径存在
    if not os.path.exists(local_path):
        try:
            os.makedirs(local_path, exist_ok=True)
            log_message('info', f'任务 {task["name"]}: 创建目录 {local_path}')
        except Exception as e:
            log_message('error', f'任务 {task["name"]}: 创建目录失败: {str(e)}')
            return False
    
    # 构建rclone命令
    cmd = [
        'rclone', 'sync',
        local_path,
        remote_path,
        '--transfers', str(transfers),
        '--checkers', str(checkers),
        '--progress',
        '--stats', '1s',
        '--stats-one-line',
        '-v'
    ]
    
    if max_age != '0':
        cmd.extend(['--max-age', max_age])
    
    log_message('info', f'任务 {task["name"]}: 开始同步')
    log_message('info', f'命令: {" ".join(cmd)}')
    
    # 设置任务状态
    sync_status['tasks'][task_id] = {
        'status': 'running',
        'pid': None,
        'progress': '0%',
        'start_time': datetime.now().isoformat()
    }
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        sync_status['tasks'][task_id]['pid'] = process.pid
        
        # 在后台线程中处理输出
        def monitor_output():
            try:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        # 解析进度信息
                        if 'Transferred:' in line:
                            sync_status['tasks'][task_id]['progress'] = line
                        log_message('info', f'任务 {task["name"]}: {line}')
                
                process.wait()
                
                if process.returncode == 0:
                    sync_status['tasks'][task_id]['status'] = 'completed'
                    log_message('success', f'任务 {task["name"]}: 同步完成')
                else:
                    sync_status['tasks'][task_id]['status'] = 'failed'
                    log_message('error', f'任务 {task["name"]}: 同步失败 (退出码: {process.returncode})')
            except Exception as e:
                sync_status['tasks'][task_id]['status'] = 'failed'
                log_message('error', f'任务 {task["name"]}: {str(e)}')
        
        thread = threading.Thread(target=monitor_output, daemon=True)
        thread.start()
        
        return True
    except Exception as e:
        sync_status['tasks'][task_id]['status'] = 'failed'
        log_message('error', f'任务 {task["name"]}: 启动失败: {str(e)}')
        return False

def stop_sync_task(task_id):
    """停止同步任务"""
    if task_id not in sync_status['tasks']:
        return False
    
    task_status = sync_status['tasks'][task_id]
    pid = task_status.get('pid')
    
    if not pid:
        return False
    
    try:
        os.kill(pid, 9)
        task_status['status'] = 'stopped'
        log_message('info', f'任务已停止 (PID: {pid})')
        return True
    except:
        return False

def schedule_task(task):
    """添加定时任务"""
    if not SCHEDULE_AVAILABLE:
        log_message('error', '定时任务功能不可用：schedule模块未安装')
        return False
    
    task_id = task['id']
    schedule_config = task.get('schedule', {})
    
    if not schedule_config.get('enabled', False):
        return False
    
    # 清除已有的任务
    if task_id in scheduled_jobs:
        schedule.cancel_job(scheduled_jobs[task_id])
        del scheduled_jobs[task_id]
    
    schedule_type = schedule_config.get('type', 'daily')
    
    try:
        if schedule_type == 'daily':
            time_str = schedule_config.get('time', '02:00')
            job = schedule.every().day.at(time_str).do(lambda: run_sync_task(task))
            log_message('info', f'任务 {task["name"]}: 添加每日定时任务 ({time_str})')
        
        elif schedule_type == 'weekly':
            time_str = schedule_config.get('time', '02:00')
            weekday = schedule_config.get('weekday', 'monday').lower()
            job = getattr(schedule.every(), weekday).at(time_str).do(lambda: run_sync_task(task))
            log_message('info', f'任务 {task["name"]}: 添加每周定时任务 ({weekday} {time_str})')
        
        elif schedule_type == 'interval':
            interval = schedule_config.get('interval', 60)
            job = schedule.every(interval).minutes.do(lambda: run_sync_task(task))
            log_message('info', f'任务 {task["name"]}: 添加间隔定时任务 (每{interval}分钟)')
        
        else:
            log_message('error', f'任务 {task["name"]}: 未知的定时类型: {schedule_type}')
            return False
        
        scheduled_jobs[task_id] = job
        return True
    
    except Exception as e:
        log_message('error', f'任务 {task["name"]}: 添加定时任务失败: {str(e)}')
        return False

def run_scheduler():
    """运行定时任务调度器"""
    global scheduler_running
    while scheduler_running:
        schedule.run_pending()
        time.sleep(1)

def start_scheduler():
    """启动定时任务调度器"""
    global scheduler_thread, scheduler_running
    
    if not SCHEDULE_AVAILABLE:
        return False
    
    if scheduler_running:
        return True
    
    scheduler_running = True
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    log_message('info', '定时任务调度器已启动')
    return True

def stop_scheduler():
    """停止定时任务调度器"""
    global scheduler_running
    scheduler_running = False
    log_message('info', '定时任务调度器已停止')

def update_scheduled_tasks(config):
    """更新所有定时任务"""
    if not SCHEDULE_AVAILABLE:
        return
    
    # 清除所有已有任务
    for job in scheduled_jobs.values():
        schedule.cancel_job(job)
    scheduled_jobs.clear()
    
    # 添加新的定时任务
    for task in config.get('tasks', []):
        if task.get('enabled', False):
            schedule_task(task)

class RcloneWebHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP请求处理器 - 添加认证"""
    
    def get_session_id(self):
        """从Cookie获取session ID"""
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            return None
        
        cookies = {}
        for cookie in cookie_header.split(';'):
            if '=' in cookie:
                key, value = cookie.strip().split('=', 1)
                cookies[key] = value
        
        return cookies.get('session_id')
    
    def check_auth(self):
        """检查认证状态"""
        # 登录页面和登录API不需要认证
        if self.path in ['/', '/login', '/api/login']:
            return True
        
        session_id = self.get_session_id()
        return verify_session(session_id)
    
    def send_json_response(self, data, status=200):
        """发送JSON响应"""
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_redirect(self, location):
        """发送重定向响应"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def do_GET(self):
        """处理GET请求"""
        # 显示登录页面
        if self.path == '/' or self.path == '/login':
            session_id = self.get_session_id()
            if verify_session(session_id):
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(get_main_page().encode())
            else:
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(get_login_page().encode())
            return
        
        # 检查认证
        if not self.check_auth():
            self.send_json_response({'error': 'Unauthorized'}, 401)
            return
        
        # API路由
        if self.path == '/api/config':
            config = load_config()
            self.send_json_response(config)
        
        elif self.path == '/api/status':
            self.send_json_response({
                'rclone_installed': rclone_installed,
                'tasks': sync_status['tasks'],
                'scheduler_running': scheduler_running,
                'schedule_available': SCHEDULE_AVAILABLE
            })
        
        elif self.path == '/api/logs':
            self.send_json_response({
                'logs': [{
                    'time': log['timestamp'],
                    'level': log['type'],
                    'message': log['message']
                } for log in logs]
            })
        
        elif self.path == '/api/s3/list':
            remotes = load_s3_remotes()
            self.send_json_response({'remotes': remotes})
        
        else:
            self.send_json_response({'error': 'Not found'}, 404)
    
    def do_POST(self):
        """处理POST请求"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}
        
        # 登录API不需要认证
        if self.path == '/api/login':
            username = data.get('username', '')
            password = data.get('password', '')
            
            if verify_credentials(username, password):
                session_id = create_session(username)
                log_message('info', f'用户登录: {username}')
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Set-Cookie', f'session_id={session_id}; Path=/; HttpOnly; Max-Age=86400')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': '登录成功'
                }).encode())
            else:
                log_message('warning', f'登录失败: {username}')
                self.send_json_response({
                    'success': False,
                    'message': '用户名或密码错误'
                }, 401)
            return
        
        # 登出API不需要特殊认证，但需要清除session
        if self.path == '/api/logout':
            session_id = self.get_session_id()
            if session_id:
                delete_session(session_id)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Set-Cookie', 'session_id=; Path=/; HttpOnly; Max-Age=0')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'message': '已登出'
            }).encode())
            return
        
        # 其他API需要认证
        if not self.check_auth():
            self.send_json_response({'error': 'Unauthorized'}, 401)
            return
        
        # 修改密码
        if self.path == '/api/change_password':
            old_password = data.get('oldPassword', '')
            new_password = data.get('newPassword', '')
            
            auth = load_auth()
            if hash_password(old_password) != auth['password_hash']:
                self.send_json_response({
                    'success': False,
                    'message': '原密码错误'
                })
                return
            
            if len(new_password) < 6:
                self.send_json_response({
                    'success': False,
                    'message': '新密码长度至少6位'
                })
                return
            
            auth['password_hash'] = hash_password(new_password)
            save_auth(auth)
            
            log_message('info', '密码已修改')
            self.send_json_response({
                'success': True,
                'message': '密码修改成功'
            })
        
        elif self.path == '/api/config':
            save_config(data)
            update_scheduled_tasks(data)
            self.send_json_response({'success': True})
        
        elif self.path.startswith('/api/sync/'):
            task_id = self.path.split('/')[-1]
            config = load_config()
            task = next((t for t in config['tasks'] if t['id'] == task_id), None)
            
            if task:
                success = run_sync_task(task)
                self.send_json_response({'success': success})
            else:
                self.send_json_response({'success': False, 'message': '任务不存在'})
        
        elif self.path.startswith('/api/stop/'):
            task_id = self.path.split('/')[-1]
            success = stop_sync_task(task_id)
            self.send_json_response({'success': success})
        
        elif self.path == '/api/logs/clear':
            logs.clear()
            self.send_json_response({'success': True})
        
        elif self.path == '/api/rclone/install':
            success = install_rclone()
            self.send_json_response({
                'success': success,
                'message': 'rclone安装成功' if success else 'rclone安装失败'
            })
        
        elif self.path == '/api/s3/add':
            name = data.get('name')
            access_key = data.get('accessKey')
            secret_key = data.get('secretKey')
            endpoint = data.get('endpoint')
            region = data.get('region', 'auto')
            provider = data.get('provider', 'Other')
            force_path_style = data.get('forcePathStyle', True)
            
            if not all([name, access_key, secret_key, endpoint]):
                self.send_json_response({
                    'success': False,
                    'message': '请填写所有必填项'
                })
                return
            
            success = add_s3_remote(name, access_key, secret_key, endpoint, 
                                  region, provider, force_path_style)
            self.send_json_response({
                'success': success,
                'message': 'S3配置添加成功' if success else 'S3配置添加失败'
            })
        
        elif self.path == '/api/s3/delete':
            name = data.get('name')
            success = delete_s3_remote(name)
            self.send_json_response({
                'success': success,
                'message': 'S3配置删除成功' if success else 'S3配置删除失败'
            })
        
        elif self.path == '/api/s3/get':
            name = data.get('name')
            config = get_s3_config(name)
            if config:
                self.send_json_response({
                    'success': True,
                    'config': config
                })
            else:
                self.send_json_response({
                    'success': False,
                    'message': '配置不存在'
                })
        
        elif self.path == '/api/s3/update':
            name = data.get('name')
            access_key = data.get('accessKey')
            secret_key = data.get('secretKey')
            endpoint = data.get('endpoint')
            region = data.get('region', 'auto')
            provider = data.get('provider', 'Other')
            force_path_style = data.get('forcePathStyle', True)
            
            # 先删除旧配置，再添加新配置
            delete_s3_remote(name)
            success = add_s3_remote(name, access_key, secret_key, endpoint,
                                  region, provider, force_path_style)
            
            self.send_json_response({
                'success': success,
                'message': 'S3配置更新成功' if success else 'S3配置更新失败'
            })
        
        else:
            self.send_json_response({'error': 'Not found'}, 404)
    
    def log_message(self, format, *args):
        """禁用默认的日志输出"""
        pass

def get_login_page():
    """获取登录页面HTML"""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rclone Web Manager - 登录</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .login-header h1 {
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }
        
        .login-header p {
            color: #666;
            font-size: 14px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
        }
        
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e1e1e1;
            border-radius: 5px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .login-button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: transform 0.2s;
        }
        
        .login-button:hover {
            transform: translateY(-2px);
        }
        
        .login-button:active {
            transform: translateY(0);
        }
        
        .error-message {
            background: #fee;
            color: #c33;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: none;
        }
        
        .default-info {
            margin-top: 20px;
            padding: 15px;
            background: #f0f7ff;
            border-left: 4px solid #667eea;
            border-radius: 5px;
        }
        
        .default-info h3 {
            color: #667eea;
            font-size: 14px;
            margin-bottom: 8px;
        }
        
        .default-info p {
            color: #666;
            font-size: 13px;
            line-height: 1.6;
        }
        
        .default-info code {
            background: #e1e1e1;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>🔐 Rclone Web Manager</h1>
            <p>请登录以继续</p>
        </div>
        
        <div class="error-message" id="errorMessage"></div>
        
        <form id="loginForm" onsubmit="return handleLogin(event)">
            <div class="form-group">
                <label for="username">用户名</label>
                <input type="text" id="username" name="username" required autocomplete="username">
            </div>
            
            <div class="form-group">
                <label for="password">密码</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            
            <button type="submit" class="login-button">登录</button>
        </form>
        
        <div class="default-info">
            <h3>📝 默认登录信息</h3>
            <p>
                用户名: <code>admin</code><br>
                密码: <code>admin123</code><br>
                <small>登录后请立即修改密码</small>
            </p>
        </div>
    </div>
    
    <script>
        async function handleLogin(event) {
            event.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const errorDiv = document.getElementById('errorMessage');
            
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                
                const result = await res.json();
                
                if (result.success) {
                    window.location.href = '/';
                } else {
                    errorDiv.textContent = result.message || '登录失败';
                    errorDiv.style.display = 'block';
                }
            } catch (error) {
                errorDiv.textContent = '网络错误，请重试';
                errorDiv.style.display = 'block';
            }
            
            return false;
        }
    </script>
</body>
</html>"""

def get_main_page():
    """获取主页面HTML (保持原有功能，添加登出和修改密码功能)"""
    # 这里返回原来的完整页面，但添加以下功能：
    # 1. 顶部添加登出按钮
    # 2. 设置中添加修改密码功能
    
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rclone Web Manager</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 40px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header h1 {
            font-size: 24px;
            font-weight: 600;
        }
        
        .header-buttons {
            display: flex;
            gap: 10px;
        }
        
        .logout-btn {
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        
        .logout-btn:hover {
            background: rgba(255,255,255,0.3);
        }
        
        .container {
            max-width: 1400px;
            margin: 30px auto;
            padding: 0 20px;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            background: white;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .tab {
            padding: 12px 24px;
            background: #f0f0f0;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
        }
        
        .tab:hover {
            background: #e0e0e0;
        }
        
        .tab.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .card {
            background: white;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .card-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #555;
        }
        
        .form-group input[type="text"],
        .form-group input[type="number"],
        .form-group input[type="password"] {
            width: 100%;
            padding: 10px;
            border: 2px solid #e1e1e1;
            border-radius: 5px;
            font-size: 14px;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .button {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s;
        }
        
        .button-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .button-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .button-success {
            background: #10b981;
            color: white;
        }
        
        .button-danger {
            background: #ef4444;
            color: white;
        }
        
        .button-warning {
            background: #f59e0b;
            color: white;
        }
        
        .button-secondary {
            background: #6b7280;
            color: white;
        }
        
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .status-running {
            background: #dbeafe;
            color: #1e40af;
        }
        
        .status-completed {
            background: #d1fae5;
            color: #065f46;
        }
        
        .status-failed {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .status-stopped {
            background: #f3f4f6;
            color: #374151;
        }
        
        .task-card {
            background: #f9fafb;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
        }
        
        .task-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .task-name {
            font-size: 16px;
            font-weight: 600;
            color: #111827;
        }
        
        .task-actions {
            display: flex;
            gap: 8px;
        }
        
        .task-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-bottom: 15px;
        }
        
        .info-item {
            display: flex;
            flex-direction: column;
        }
        
        .info-label {
            font-size: 12px;
            color: #6b7280;
            margin-bottom: 4px;
        }
        
        .info-value {
            font-size: 14px;
            color: #111827;
            font-family: monospace;
        }
        
        .logs-container {
            background: #1f2937;
            color: #f3f4f6;
            padding: 20px;
            border-radius: 8px;
            height: 400px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 13px;
        }
        
        .log-entry {
            margin-bottom: 8px;
            line-height: 1.5;
        }
        
        .log-time {
            color: #9ca3af;
            margin-right: 10px;
        }
        
        .log-success {
            color: #34d399;
        }
        
        .log-error {
            color: #f87171;
        }
        
        .log-warning {
            color: #fbbf24;
        }
        
        .log-info {
            color: #60a5fa;
        }
        
        .s3-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
        }
        
        .s3-item {
            background: #f9fafb;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            padding: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .s3-name {
            font-weight: 600;
            color: #111827;
        }
        
        .s3-actions {
            display: flex;
            gap: 8px;
        }
        
        .hidden {
            display: none !important;
        }
        
        .install-banner {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
        }
        
        .install-banner h3 {
            color: #92400e;
            margin-bottom: 10px;
        }
        
        .install-banner p {
            color: #78350f;
            margin-bottom: 15px;
        }
        
        @media (max-width: 768px) {
            .header {
                padding: 15px 20px;
            }
            
            .header h1 {
                font-size: 20px;
            }
            
            .container {
                margin: 20px auto;
            }
            
            .tabs {
                flex-wrap: wrap;
            }
            
            .task-info {
                grid-template-columns: 1fr;
            }
        }
        
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 15px;
        }
        
        .checkbox-group input[type="checkbox"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        
        .schedule-config {
            background: #f9fafb;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            padding: 15px;
            margin-top: 10px;
        }
        
        .schedule-type {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
        }
        
        .schedule-type label {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .password-section {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
        }
        
        .password-section h3 {
            color: #92400e;
            margin-bottom: 15px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Rclone Web Manager</h1>
        <div class="header-buttons">
            <button class="logout-btn" onclick="handleLogout()">🚪 登出</button>
        </div>
    </div>
    
    <div class="container">
        <div id="installBanner" class="install-banner hidden">
            <h3>⚠️ Rclone 未安装</h3>
            <p>Rclone 尚未安装，请点击下方按钮自动安装。</p>
            <button class="button button-warning" onclick="installRclone()">安装 Rclone</button>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="switchTab('tasks')">📋 同步任务</button>
            <button class="tab" onclick="switchTab('s3')">☁️ S3配置</button>
            <button class="tab" onclick="switchTab('logs')">📝 运行日志</button>
            <button class="tab" onclick="switchTab('settings')">⚙️ 设置</button>
        </div>
        
        <!-- 任务管理标签 -->
        <div id="tasks" class="tab-content active">
            <div class="card">
                <div class="card-title">同步任务列表</div>
                <div id="tasksList"></div>
                <button class="button button-primary" onclick="addNewTask()">+ 添加新任务</button>
            </div>
        </div>
        
        <!-- S3配置标签 -->
        <div id="s3" class="tab-content">
            <div class="card">
                <div class="card-title">S3 远程配置</div>
                <div id="s3List" class="s3-list"></div>
                <button class="button button-primary" style="margin-top: 20px;" onclick="showS3Form()">+ 添加 S3 配置</button>
                
                <div id="s3Form" class="hidden" style="margin-top: 20px;">
                    <h3>添加/编辑 S3 配置</h3>
                    <div class="form-group">
                        <label>名称 *</label>
                        <input type="text" id="s3Name" placeholder="例如: mys3">
                    </div>
                    <div class="form-group">
                        <label>Access Key ID *</label>
                        <input type="text" id="s3AccessKey">
                    </div>
                    <div class="form-group">
                        <label>Secret Access Key *</label>
                        <input type="password" id="s3SecretKey">
                    </div>
                    <div class="form-group">
                        <label>Endpoint *</label>
                        <input type="text" id="s3Endpoint" placeholder="例如: s3.amazonaws.com">
                    </div>
                    <div class="form-group">
                        <label>Region</label>
                        <input type="text" id="s3Region" value="auto">
                    </div>
                    <div class="form-group">
                        <label>Provider</label>
                        <select id="s3Provider" style="width: 100%; padding: 10px; border: 2px solid #e1e1e1; border-radius: 5px;">
                            <option value="Other">Other</option>
                            <option value="AWS">AWS</option>
                            <option value="Minio">Minio</option>
                            <option value="Alibaba">Alibaba Cloud (Aliyun)</option>
                            <option value="Tencent">Tencent Cloud (COS)</option>
                        </select>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" id="s3ForcePathStyle" checked>
                        <label>Force Path Style</label>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <button class="button button-success" onclick="submitS3Form()">保存</button>
                        <button class="button button-secondary" onclick="cancelS3Form()">取消</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 日志标签 -->
        <div id="logs" class="tab-content">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div class="card-title" style="margin: 0;">运行日志</div>
                    <button class="button button-secondary" onclick="clearLogs()">清空日志</button>
                </div>
                <div id="logsContainer" class="logs-container"></div>
            </div>
        </div>
        
        <!-- 设置标签 -->
        <div id="settings" class="tab-content">
            <div class="card">
                <div class="card-title">密码设置</div>
                <div class="password-section">
                    <h3>修改登录密码</h3>
                    <div class="form-group">
                        <label>原密码</label>
                        <input type="password" id="oldPassword">
                    </div>
                    <div class="form-group">
                        <label>新密码 (至少6位)</label>
                        <input type="password" id="newPassword">
                    </div>
                    <div class="form-group">
                        <label>确认新密码</label>
                        <input type="password" id="confirmPassword">
                    </div>
                    <button class="button button-primary" onclick="changePassword()">修改密码</button>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">系统信息</div>
                <div class="info-item">
                    <div class="info-label">配置文件</div>
                    <div class="info-value">/tmp/rclone_web_config.json</div>
                </div>
                <div class="info-item" style="margin-top: 10px;">
                    <div class="info-label">日志文件</div>
                    <div class="info-value">/tmp/rclone_web.log</div>
                </div>
                <div class="info-item" style="margin-top: 10px;">
                    <div class="info-label">Rclone状态</div>
                    <div class="info-value" id="rcloneStatus">检查中...</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let config = {};
        let currentTab = 'tasks';
        
        function switchTab(tabName) {
            currentTab = tabName;
            
            // 更新标签样式
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // 更新内容显示
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(tabName).classList.add('active');
            
            // 加载对应数据
            if (tabName === 's3') {
                loadS3Remotes();
            }
        }
        
        async function loadConfig() {
            const res = await fetch('/api/config');
            config = await res.json();
            renderTasks();
        }
        
        function renderTasks() {
            const container = document.getElementById('tasksList');
            if (!config.tasks || config.tasks.length === 0) {
                container.innerHTML = '<p style="color: #6b7280;">暂无同步任务</p>';
                return;
            }
            
            container.innerHTML = config.tasks.map((task, index) => `
                <div class="task-card">
                    <div class="task-header">
                        <div class="task-name">${task.name || '未命名任务'}</div>
                        <div class="task-actions">
                            <button class="button button-success" onclick="runTask('${task.id}')">▶ 运行</button>
                            <button class="button button-danger" onclick="stopTask('${task.id}')">⏹ 停止</button>
                            <button class="button button-primary" onclick="editTask(${index})">✏️ 编辑</button>
                            <button class="button button-danger" onclick="deleteTask(${index})">🗑️ 删除</button>
                        </div>
                    </div>
                    <div class="task-info">
                        <div class="info-item">
                            <div class="info-label">本地路径</div>
                            <div class="info-value">${task.localPath}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">远程路径</div>
                            <div class="info-value">${task.remotePath}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">状态</div>
                            <div class="info-value">
                                <span class="status-badge status-${getTaskStatus(task.id).status || 'stopped'}">
                                    ${getTaskStatus(task.id).status || '未运行'}
                                </span>
                            </div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">定时任务</div>
                            <div class="info-value">${task.schedule?.enabled ? '✓ 已启用' : '✗ 未启用'}</div>
                        </div>
                    </div>
                    ${getTaskStatus(task.id).progress ? 
                        `<div style="margin-top: 10px; padding: 10px; background: #e5e7eb; border-radius: 5px;">
                            <small style="font-family: monospace; color: #374151;">${getTaskStatus(task.id).progress}</small>
                        </div>` : ''}
                </div>
            `).join('');
        }
        
        function getTaskStatus(taskId) {
            return window.syncStatus?.tasks?.[taskId] || {};
        }
        
        function addNewTask() {
            const newTask = {
                id: 'task_' + Date.now(),
                name: '新任务',
                localPath: '/path/to/local',
                remotePath: 's3remote:bucket/path',
                maxAge: '0',
                transfers: 64,
                checkers: 128,
                enabled: true,
                schedule: {
                    enabled: false,
                    type: 'daily',
                    time: '02:00',
                    interval: 60,
                    weekday: 'monday'
                }
            };
            
            config.tasks.push(newTask);
            saveConfig();
        }
        
        function editTask(index) {
            const task = config.tasks[index];
            const name = prompt('任务名称:', task.name);
            if (name === null) return;
            
            const localPath = prompt('本地路径:', task.localPath);
            if (localPath === null) return;
            
            const remotePath = prompt('远程路径:', task.remotePath);
            if (remotePath === null) return;
            
            task.name = name;
            task.localPath = localPath;
            task.remotePath = remotePath;
            
            saveConfig();
        }
        
        function deleteTask(index) {
            if (confirm('确定要删除这个任务吗？')) {
                config.tasks.splice(index, 1);
                saveConfig();
            }
        }
        
        async function runTask(taskId) {
            try {
                const res = await fetch('/api/sync/' + taskId, { method: 'POST' });
                const result = await res.json();
                if (result.success) {
                    alert('任务已启动');
                } else {
                    alert('启动失败');
                }
            } catch (error) {
                alert('启动失败: ' + error.message);
            }
        }
        
        async function stopTask(taskId) {
            if (!confirm('确定要停止这个任务吗？')) return;
            
            try {
                const res = await fetch('/api/stop/' + taskId, { method: 'POST' });
                const result = await res.json();
                if (result.success) {
                    alert('任务已停止');
                } else {
                    alert('停止失败');
                }
            } catch (error) {
                alert('停止失败: ' + error.message);
            }
        }
        
        async function saveConfig() {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            loadConfig();
        }
        
        async function updateStatus() {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            window.syncStatus = data;
            
            // 更新安装横幅
            const banner = document.getElementById('installBanner');
            if (!data.rclone_installed) {
                banner.classList.remove('hidden');
            } else {
                banner.classList.add('hidden');
            }
            
            // 更新Rclone状态
            const statusEl = document.getElementById('rcloneStatus');
            if (statusEl) {
                statusEl.textContent = data.rclone_installed ? '✓ 已安装' : '✗ 未安装';
                statusEl.style.color = data.rclone_installed ? '#10b981' : '#ef4444';
            }
            
            // 更新任务状态
            if (currentTab === 'tasks') {
                renderTasks();
            }
        }
        
        async function loadS3Remotes() {
            const res = await fetch('/api/s3/list');
            const data = await res.json();
            const container = document.getElementById('s3List');
            
            if (!data.remotes || data.remotes.length === 0) {
                container.innerHTML = '<p style="color: #6b7280;">暂无 S3 配置</p>';
                return;
            }
            
            container.innerHTML = data.remotes.map(remote => `
                <div class="s3-item">
                    <div class="s3-name">📦 ${remote}</div>
                    <div class="s3-actions">
                        <button class="button button-primary" onclick="editS3('${remote}')">✏️</button>
                        <button class="button button-danger" onclick="deleteS3('${remote}')">🗑️</button>
                    </div>
                </div>
            `).join('');
        }
        
        function showS3Form() {
            document.getElementById('s3Form').classList.remove('hidden');
            document.getElementById('s3Name').readOnly = false;
            window.s3EditMode = null;
        }
        
        async function submitS3Form() {
            const data = {
                name: document.getElementById('s3Name').value,
                accessKey: document.getElementById('s3AccessKey').value,
                secretKey: document.getElementById('s3SecretKey').value,
                endpoint: document.getElementById('s3Endpoint').value,
                region: document.getElementById('s3Region').value,
                provider: document.getElementById('s3Provider').value,
                forcePathStyle: document.getElementById('s3ForcePathStyle').checked
            };
            
            if (!data.name || !data.accessKey || !data.secretKey || !data.endpoint) {
                alert('请填写所有必填项');
                return;
            }
            
            const url = window.s3EditMode ? '/api/s3/update' : '/api/s3/add';
            if (window.s3EditMode) {
                data.name = window.s3EditMode;
            }
            
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                
                if (result.success) {
                    alert('S3配置保存成功！');
                    cancelS3Form();
                    loadS3Remotes();
                } else {
                    alert('保存失败: ' + result.message);
                }
            } catch (error) {
                alert('保存失败: ' + error.message);
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
        
        async function editS3(remoteName) {
            try {
                const res = await fetch('/api/s3/get', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: remoteName })
                });
                const result = await res.json();
                
                if (!result.success) {
                    alert('获取配置失败: ' + result.message);
                    return;
                }
                
                const config = result.config;
                document.getElementById('s3Name').value = config.name || remoteName;
                document.getElementById('s3Name').readOnly = true;
                document.getElementById('s3AccessKey').value = config.access_key_id || '';
                document.getElementById('s3SecretKey').value = config.secret_access_key || '';
                document.getElementById('s3Endpoint').value = config.endpoint || '';
                document.getElementById('s3Region').value = config.region || 'auto';
                document.getElementById('s3Provider').value = config.provider || 'Other';
                document.getElementById('s3ForcePathStyle').checked = config.force_path_style === 'true';
                
                document.getElementById('s3Form').classList.remove('hidden');
                window.s3EditMode = remoteName;
            } catch (error) {
                alert('获取配置失败: ' + error.message);
            }
        }
        
        function cancelS3Form() {
            document.getElementById('s3Form').classList.add('hidden');
            document.getElementById('s3Name').value = '';
            document.getElementById('s3Name').readOnly = false;
            document.getElementById('s3AccessKey').value = '';
            document.getElementById('s3SecretKey').value = '';
            document.getElementById('s3Endpoint').value = '';
            document.getElementById('s3Region').value = 'auto';
            document.getElementById('s3Provider').value = 'Other';
            document.getElementById('s3ForcePathStyle').checked = true;
            window.s3EditMode = null;
        }
        
        async function loadLogs() {
            const res = await fetch('/api/logs');
            const data = await res.json();
            const logsEl = document.getElementById('logsContainer');
            
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
        
        async function changePassword() {
            const oldPassword = document.getElementById('oldPassword').value;
            const newPassword = document.getElementById('newPassword').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!oldPassword || !newPassword || !confirmPassword) {
                alert('请填写所有字段');
                return;
            }
            
            if (newPassword !== confirmPassword) {
                alert('两次输入的新密码不一致');
                return;
            }
            
            if (newPassword.length < 6) {
                alert('新密码长度至少6位');
                return;
            }
            
            try {
                const res = await fetch('/api/change_password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        oldPassword: oldPassword,
                        newPassword: newPassword
                    })
                });
                
                const result = await res.json();
                
                if (result.success) {
                    alert('密码修改成功！请重新登录。');
                    handleLogout();
                } else {
                    alert(result.message || '密码修改失败');
                }
            } catch (error) {
                alert('密码修改失败: ' + error.message);
            }
            
            // 清空输入框
            document.getElementById('oldPassword').value = '';
            document.getElementById('newPassword').value = '';
            document.getElementById('confirmPassword').value = '';
        }
        
        async function handleLogout() {
            try {
                await fetch('/api/logout', { method: 'POST' });
                window.location.href = '/login';
            } catch (error) {
                alert('登出失败: ' + error.message);
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
</html>"""

def main():
    """主函数"""
    global rclone_installed
    
    print("=" * 60)
    print("🚀 Rclone Web管理器启动中 (带密码保护版本)...")
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
    
    # 显示登录信息
    auth = load_auth()
    print("\n" + "=" * 60)
    print("🔐 认证信息:")
    print(f"   用户名: {auth['username']}")
    print(f"   默认密码: admin123")
    print("   ⚠️  首次登录后请立即修改密码！")
    print("=" * 60 + "\n")
    
    print(f"✓ 访问地址: http://localhost:{PORT}")
    print(f"✓ 或使用: http://你的服务器IP:{PORT}")
    print(f"✓ 配置文件: {CONFIG_FILE}")
    print(f"✓ 认证文件: {AUTH_FILE}")
    print(f"✓ 日志文件: {LOG_FILE}")
    print("=" * 60)
    print("按 Ctrl+C 停止服务\n")
    
    log_message('info', 'Web服务器启动 (带密码保护)')
    if rclone_installed:
        log_message('success', 'Rclone已就绪')
    else:
        log_message('warning', 'Rclone未安装，请手动安装')
    
    # 启动定时任务调度器
    if SCHEDULE_AVAILABLE:
        print("✓ 启动定时任务调度器...")
        if start_scheduler():
            print("✓ 定时任务调度器已启动\n")
        else:
            print("⚠️  定时任务调度器启动失败\n")
    else:
        print("⚠️  定时任务功能不可用（schedule模块未安装）")
        print("💡 安装方法: pip install schedule --break-system-packages\n")
    
    Handler = RcloneWebHandler
    
    # 使用 ThreadingTCPServer 支持并发请求
    class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
    
    with ThreadingTCPServer(("", PORT), Handler) as httpd:
        try:
            print("✓ 服务器已启动（支持并发请求，带密码保护）\n")
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n✓ 正在停止服务器...")
            stop_scheduler()
            print("✓ 服务器已停止")
            log_message('info', 'Web服务器停止')

if __name__ == "__main__":
    main()
