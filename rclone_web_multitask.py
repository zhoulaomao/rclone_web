#!/usr/bin/env python3
"""
Rclone Web Manager - Fixed S3 API Version
"""

import http.server
import socketserver
import json
import os
import threading
import subprocess
import shutil
from datetime import datetime

# Configuration
CONFIG_FILE = os.path.expanduser('~/.config/rclone_web/config.json')
RCLONE_CONFIG_FILE = os.path.expanduser('~/.config/rclone/rclone.conf')
LOG_FILE = '/tmp/rclone_web.log'
PORT = 5000

# Default config
DEFAULT_CONFIG = {
    'tasks': [],
    'scheduleTime': '02:00',
    'scheduleInterval': 'daily',
    's3_remotes': []
}

# Global state
sync_status = {'tasks': {}}
logs = []
rclone_installed = False

def log_message(msg_type, message):
    """Add log message"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logs.insert(0, {
        'level': msg_type,
        'message': message,
        'time': timestamp
    })
    if len(logs) > 100:
        logs.pop()
    
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(f"[{timestamp}] {msg_type.upper()}: {message}\n")
    except:
        pass

def check_rclone_installed():
    """Check if rclone is installed"""
    return shutil.which('rclone') is not None

def install_rclone():
    """Auto install rclone"""
    global rclone_installed
    
    log_message('info', 'Checking rclone...')
    
    if check_rclone_installed():
        log_message('success', 'rclone is installed')
        rclone_installed = True
        return True
    
    log_message('warning', 'rclone not found, installing...')
    
    try:
        subprocess.run(
            'curl https://rclone.org/install.sh | sudo bash',
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if check_rclone_installed():
            log_message('success', 'rclone installed successfully!')
            rclone_installed = True
            return True
        else:
            log_message('error', 'rclone installation failed')
            return False
            
    except Exception as e:
        log_message('error', f'rclone installation error: {str(e)}')
        return False

def load_config():
    """Load configuration"""
    config_dir = os.path.dirname(CONFIG_FILE)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            return config
        except Exception as e:
            log_message('error', f'Failed to load config: {str(e)}')
            return DEFAULT_CONFIG.copy()
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save configuration"""
    try:
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        log_message('error', f'Failed to save config: {str(e)}')
        return False

def add_s3_remote(name, access_key, secret_key, endpoint, region='us-east-1', provider='Minio', force_path_style=True):
    """Add S3 remote configuration to rclone"""
    try:
        # Create rclone config directory if not exists
        config_dir = os.path.dirname(RCLONE_CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        
        # Read existing config
        existing_config = ""
        if os.path.exists(RCLONE_CONFIG_FILE):
            with open(RCLONE_CONFIG_FILE, 'r') as f:
                existing_config = f.read()
        
        # Check if remote already exists
        if f"[{name}]" in existing_config:
            log_message('warning', f'S3 remote {name} already exists, updating...')
            # Remove old config for this remote
            lines = existing_config.split('\n')
            new_lines = []
            skip = False
            for line in lines:
                if line.strip() == f"[{name}]":
                    skip = True
                elif line.strip().startswith('[') and line.strip().endswith(']'):
                    skip = False
                
                if not skip:
                    new_lines.append(line)
            
            existing_config = '\n'.join(new_lines).strip()
        
        # Prepare new config section
        new_config = f"""

[{name}]
type = s3
provider = {provider}
access_key_id = {access_key}
secret_access_key = {secret_key}
endpoint = {endpoint}
region = {region}
location_constraint = {region}
acl = private
"""
        
        # Add force_path_style for MinIO
        if force_path_style:
            new_config += "force_path_style = true\n"
        
        # Write combined config
        with open(RCLONE_CONFIG_FILE, 'w') as f:
            if existing_config:
                f.write(existing_config)
            f.write(new_config)
        
        log_message('success', f'S3 remote {name} added successfully')
        return True
        
    except Exception as e:
        log_message('error', f'Failed to add S3 remote: {str(e)}')
        return False

def delete_s3_remote(name):
    """Delete S3 remote from rclone config"""
    try:
        if not os.path.exists(RCLONE_CONFIG_FILE):
            return True
        
        with open(RCLONE_CONFIG_FILE, 'r') as f:
            lines = f.readlines()
        
        # Remove the remote section
        new_lines = []
        skip = False
        for line in lines:
            if line.strip() == f"[{name}]":
                skip = True
            elif line.strip().startswith('[') and line.strip().endswith(']'):
                skip = False
            
            if not skip:
                new_lines.append(line)
        
        with open(RCLONE_CONFIG_FILE, 'w') as f:
            f.writelines(new_lines)
        
        log_message('success', f'S3 remote {name} deleted')
        return True
        
    except Exception as e:
        log_message('error', f'Failed to delete S3 remote: {str(e)}')
        return False

def get_s3_remotes():
    """Get list of S3 remotes from rclone"""
    try:
        if not check_rclone_installed():
            return []
        
        result = subprocess.run(
            ['rclone', 'listremotes'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            remotes = [r.strip(':') for r in result.stdout.strip().split('\n') if r]
            return remotes
        return []
        
    except Exception as e:
        log_message('error', f'Failed to get S3 remotes: {str(e)}')
        return []

def start_sync(task_id):
    """Start sync for a task"""
    config = load_config()
    task = next((t for t in config['tasks'] if t['id'] == task_id), None)
    
    if not task:
        log_message('error', f'Task {task_id} not found')
        return
    
    if not task.get('enabled', True):
        log_message('warning', f'Task {task_id} is disabled')
        return
    
    # Check if already running
    if task_id in sync_status['tasks'] and sync_status['tasks'][task_id].get('status') == 'running':
        log_message('warning', f'Task {task_id} is already running')
        return
    
    sync_status['tasks'][task_id] = {
        'status': 'running',
        'pid': None,
        'name': task.get('name', task_id),
        'progress': {'percentage': 0}
    }
    
    log_message('info', f'Starting sync: {task.get("name", task_id)}')
    
    # Build rclone command
    cmd = [
        'rclone', 'copy',
        task['localPath'],
        task['remotePath'],
        '--progress',
        '--stats', '1s',
        f'--transfers={task.get("transfers", 64)}',
        f'--checkers={task.get("checkers", 128)}'
    ]
    
    if task.get('maxAge', '0') != '0':
        cmd.extend(['--max-age', task['maxAge']])
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        sync_status['tasks'][task_id]['pid'] = process.pid
        
        # Monitor progress
        for line in process.stdout:
            if task_id in sync_status['tasks']:
                sync_status['tasks'][task_id]['progress']['last_line'] = line.strip()
                # Try to parse percentage
                if 'Transferred:' in line and '%' in line:
                    try:
                        parts = line.split(',')
                        for part in parts:
                            if '%' in part:
                                pct = part.split('%')[0].strip().split()[-1]
                                sync_status['tasks'][task_id]['progress']['percentage'] = int(pct)
                                break
                    except:
                        pass
        
        process.wait()
        
        if process.returncode == 0:
            sync_status['tasks'][task_id]['status'] = 'success'
            sync_status['tasks'][task_id]['progress']['percentage'] = 100
            log_message('success', f'Task {task.get("name", task_id)} completed')
        else:
            sync_status['tasks'][task_id]['status'] = 'error'
            log_message('error', f'Task {task.get("name", task_id)} failed')
            
    except Exception as e:
        sync_status['tasks'][task_id]['status'] = 'error'
        log_message('error', f'Task {task.get("name", task_id)} error: {str(e)}')

# HTTP Request Handler
class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
            
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            status = {
                'rclone_installed': rclone_installed,
                'tasks': sync_status['tasks']
            }
            self.wfile.write(json.dumps(status).encode())
            
        elif self.path == '/api/config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            config = load_config()
            self.wfile.write(json.dumps(config).encode())
            
        elif self.path == '/api/logs':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'logs': logs}).encode())
            
        elif self.path == '/api/s3/remotes':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            remotes = get_s3_remotes()
            self.wfile.write(json.dumps({'remotes': remotes}).encode())
            
        else:
            self.send_error(404)
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode())
        except:
            self.send_error(400)
            return
        
        response = {'success': False, 'message': 'Unknown error'}
        
        if self.path == '/api/sync/start':
            task_id = data.get('task_id')
            if task_id:
                thread = threading.Thread(target=start_sync, args=(task_id,), daemon=True)
                thread.start()
                response = {'success': True, 'message': 'Task started'}
            else:
                response = {'success': False, 'message': 'No task_id provided'}
        
        elif self.path == '/api/task/add':
            try:
                config = load_config()
                task = data.copy()
                task['id'] = f"task_{len(config['tasks']) + 1}"
                if 'schedule' not in task:
                    task['schedule'] = {'enabled': False}
                config['tasks'].append(task)
                save_config(config)
                response = {'success': True, 'message': 'Task added', 'task_id': task['id']}
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        elif self.path == '/api/task/update':
            try:
                config = load_config()
                task_id = data.get('id')
                for i, task in enumerate(config['tasks']):
                    if task['id'] == task_id:
                        config['tasks'][i].update(data)
                        break
                save_config(config)
                response = {'success': True, 'message': 'Task updated'}
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        elif self.path == '/api/task/delete':
            try:
                config = load_config()
                task_id = data.get('id')
                config['tasks'] = [t for t in config['tasks'] if t['id'] != task_id]
                save_config(config)
                response = {'success': True, 'message': 'Task deleted'}
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        elif self.path == '/api/task/toggle':
            try:
                config = load_config()
                task_id = data.get('id')
                for task in config['tasks']:
                    if task['id'] == task_id:
                        task['enabled'] = not task.get('enabled', True)
                        break
                save_config(config)
                response = {'success': True, 'message': 'Task toggled'}
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        elif self.path == '/api/s3/add':
            try:
                success = add_s3_remote(
                    data.get('name'),
                    data.get('access_key'),
                    data.get('secret_key'),
                    data.get('endpoint'),
                    data.get('region', 'us-east-1'),
                    data.get('provider', 'Minio'),
                    data.get('force_path_style', True)
                )
                response = {
                    'success': success,
                    'message': 'S3 remote added successfully' if success else 'Failed to add S3 remote'
                }
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        elif self.path == '/api/s3/delete':
            try:
                name = data.get('name')
                success = delete_s3_remote(name)
                response = {
                    'success': success,
                    'message': 'S3 remote deleted' if success else 'Failed to delete S3 remote'
                }
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        elif self.path == '/api/rclone/install':
            try:
                success = install_rclone()
                response = {
                    'success': success,
                    'message': 'rclone installed' if success else 'Installation failed'
                }
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        elif self.path == '/api/logs/clear':
            try:
                logs.clear()
                response = {'success': True, 'message': 'Logs cleared'}
            except Exception as e:
                response = {'success': False, 'message': str(e)}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, format, *args):
        pass

# Minimal HTML (will be replaced with full UI)
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>Rclone Web Manager</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; }
        .btn { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        .btn:hover { background: #0056b3; }
        .status { margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 4px; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; }
        input, select { padding: 8px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; }
        .form-group { margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Rclone Web Manager - Fixed S3 API</h1>
        
        <div class="status" id="status">Loading...</div>
        
        <h2>Add S3 Remote</h2>
        <div class="form-group">
            <input type="text" id="s3Name" placeholder="Remote Name (e.g., minio)" style="width: 200px;">
            <input type="text" id="s3AccessKey" placeholder="Access Key" style="width: 200px;">
            <input type="password" id="s3SecretKey" placeholder="Secret Key" style="width: 200px;">
            <input type="text" id="s3Endpoint" placeholder="Endpoint (e.g., localhost:9000)" style="width: 250px;">
            <button class="btn" onclick="addS3Remote()">Add S3 Remote</button>
        </div>
        
        <h2>S3 Remotes</h2>
        <div id="s3Remotes">Loading...</div>
        
        <h2>System Logs</h2>
        <pre id="logs" style="height: 300px; overflow-y: auto;">Loading logs...</pre>
    </div>
    
    <script>
        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('status').innerHTML = 
                        '<strong>Rclone:</strong> ' + (data.rclone_installed ? 'Installed ✓' : 'Not installed ✗') +
                        '<br><strong>Tasks:</strong> ' + Object.keys(data.tasks).length;
                });
            
            fetch('/api/s3/remotes')
                .then(r => r.json())
                .then(data => {
                    const remotes = data.remotes || [];
                    if (remotes.length === 0) {
                        document.getElementById('s3Remotes').innerHTML = '<p>No S3 remotes configured</p>';
                    } else {
                        document.getElementById('s3Remotes').innerHTML = remotes.map(r => 
                            '<div style="padding: 10px; background: #f8f9fa; margin: 5px 0; border-radius: 4px;">' +
                            '<strong>' + r + '</strong> ' +
                            '<button class="btn" style="padding: 5px 10px; font-size: 12px;" onclick="deleteS3Remote(\'' + r + '\')">Delete</button>' +
                            '</div>'
                        ).join('');
                    }
                });
            
            fetch('/api/logs')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('logs').textContent = 
                        data.logs.map(l => '[' + l.time + '] ' + l.level.toUpperCase() + ': ' + l.message).join('\\n');
                });
        }
        
        async function addS3Remote() {
            const data = {
                name: document.getElementById('s3Name').value,
                access_key: document.getElementById('s3AccessKey').value,
                secret_key: document.getElementById('s3SecretKey').value,
                endpoint: document.getElementById('s3Endpoint').value,
                region: 'us-east-1',
                provider: 'Minio',
                force_path_style: true
            };
            
            if (!data.name || !data.access_key || !data.secret_key || !data.endpoint) {
                alert('Please fill all fields');
                return;
            }
            
            const res = await fetch('/api/s3/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await res.json();
            alert(result.message);
            
            if (result.success) {
                document.getElementById('s3Name').value = '';
                document.getElementById('s3AccessKey').value = '';
                document.getElementById('s3SecretKey').value = '';
                document.getElementById('s3Endpoint').value = '';
                updateStatus();
            }
        }
        
        async function deleteS3Remote(name) {
            if (!confirm('Delete S3 remote: ' + name + '?')) return;
            
            const res = await fetch('/api/s3/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name})
            });
            
            const result = await res.json();
            alert(result.message);
            updateStatus();
        }
        
        updateStatus();
        setInterval(updateStatus, 3000);
    </script>
</body>
</html>"""

def main():
    """Main function"""
    global rclone_installed
    
    print("\n" + "=" * 60)
    print("Rclone Web Manager - Fixed S3 API Version")
    print("=" * 60)
    
    # Check rclone
    rclone_installed = check_rclone_installed()
    if not rclone_installed:
        print("\nWARNING: rclone not installed")
        print("Visit http://localhost:5000 to install\n")
    else:
        print("\nOK: rclone is installed\n")
    
    # Load config
    load_config()
    
    print(f"Server starting on http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    log_message('info', 'Web server starting...')
    
    try:
        with socketserver.TCPServer(("", PORT), RequestHandler) as httpd:
            log_message('success', f'Web server started on port {PORT}')
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nStopping server...")
        log_message('info', 'Web server stopped')
    except Exception as e:
        print(f"\nError: {str(e)}")
        log_message('error', f'Server error: {str(e)}')

if __name__ == "__main__":
    main()
