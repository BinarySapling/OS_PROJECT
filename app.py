from flask import Flask, render_template, request
from flask_socketio import SocketIO
import psutil
import threading
import time
import logging

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins=["http://localhost:5000", "http://127.0.0.1:5000"])

logging.basicConfig(level=logging.INFO)

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logging.error(f"Failed to serve index.html: {e}")
        return "Oops, something broke on the server!", 500

def get_system_data():
    process_list = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                process_list.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'cpu': round(proc.info['cpu_percent'], 1),
                    'memory': round(proc.info['memory_percent'], 1),
                    'state': proc.info['status']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logging.warning(f"Skipped a process: {e}")
    except Exception as e:
        logging.error(f"Process iteration blew up: {e}")
        return {'error': 'Couldn’t fetch processes'}

    try:
        total_cpu = round(psutil.cpu_percent(), 1)
        mem = psutil.virtual_memory()
        total_memory_used = round(mem.used / (1024 ** 3), 2)
        total_memory_total = round(mem.total / (1024 ** 3), 2)
        total_memory_percent = round(mem.percent, 1)
    except Exception as e:
        logging.error(f"System stats failed: {e}")
        return {'error': 'Couldn’t grab system stats'}

    return {
        'total_cpu': total_cpu,
        'total_memory': total_memory_percent,
        'total_memory_used': total_memory_used,
        'total_memory_total': total_memory_total,
        'processes': process_list
    }

def background_update():
    while True:
        try:
            data = get_system_data()
            if 'error' not in data:
                socketio.sleep(0.1)
                socketio.emit('update', data)
            else:
                socketio.emit('message', {'msg': 'Data fetch failed, check logs!', 'status': 'error'})
        except Exception as e:
            logging.error(f"Background update crashed: {e}")
            socketio.emit('message', {'msg': 'Update loop died, sorry!', 'status': 'error'})
        time.sleep(1)

try:
    update_thread = threading.Thread(target=background_update, daemon=True)
    update_thread.start()
except Exception as e:
    logging.error(f"Couldn’t start update thread: {e}")

@socketio.on('connect')
def handle_connect():
    try:
        logging.info(f"Client connected: {request.sid}")
        socketio.emit('message', {'msg': 'Hey, you’re in! Connection’s good.', 'status': 'success'})
        # Send initial data right away
        data = get_system_data()
        if 'error' not in data:
            socketio.emit('update', data)
    except Exception as e:
        logging.error(f"Connect event failed: {e}")

@socketio.on('kill_process')
def handle_kill_process(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            raise ValueError("PID has to be positive, dude.")
        
        proc = psutil.Process(pid)
        proc.terminate()
        time.sleep(0.1)
        if proc.is_running():
            proc.kill()
            socketio.emit('message', {'msg': f'Had to force-kill {pid}. It’s gone now.', 'status': 'success'})
        else:
            socketio.emit('message', {'msg': f'Process {pid} is toast!', 'status': 'success'})
    except ValueError as e:
        socketio.emit('message', {'msg': f'Bad PID: {e}', 'status': 'error'})
    except psutil.NoSuchProcess:
        socketio.emit('message', {'msg': f'Huh, {pid} doesn’t exist. Weird.', 'status': 'error'})
    except psutil.AccessDenied:
        socketio.emit('message', {'msg': f'Can’t kill {pid}—no permission, sorry!', 'status': 'error'})
    except Exception as e:
        socketio.emit('message', {'msg': f'Something went wrong: {e}', 'status': 'error'})

if __name__ == '__main__':
    try:
        socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logging.error(f"Server failed to start: {e}")
        print("Server crashed on startup—check the logs!")
