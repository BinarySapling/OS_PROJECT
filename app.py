from flask import Flask, render_template, request
from flask_socketio import SocketIO
import psutil
import threading
import time
import logging

my_app = Flask(__name__)
realtime_io = SocketIO(my_app, cors_allowed_origins=["http://localhost:5000", "http://127.0.0.1:5000"])

logging.basicConfig(level=logging.INFO)

@my_app.route('/')
def home_page():
    try:
        return render_template('index.html')
    except Exception as whoops:
        logging.error(f"Couldn’t load the page: {whoops}")
        return "Yikes, server’s having a bad day!", 500

def grab_system_info():
    active_procs = []
    try:
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                active_procs.append({
                    'pid': p.info['pid'],
                    'name': p.info['name'],
                    'cpu': round(p.info['cpu_percent'], 1),
                    'memory': round(p.info['memory_percent'], 1),
                    'state': p.info['status']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied) as glitch:
                logging.warning(f"Missed a process: {glitch}")
    except Exception as oof:
        logging.error(f"Process grab went kaput: {oof}")
        return {'error': 'Processes are hiding from me!'}

    try:
        cpu_usage = round(psutil.cpu_percent(), 1)
        ram = psutil.virtual_memory()
        ram_used = round(ram.used / (1024 ** 3), 2)
        ram_total = round(ram.total / (1024 ** 3), 2)
        ram_percent = round(ram.percent, 1)
    except Exception as dang:
        logging.error(f"Stats fetch flopped: {dang}")
        return {'error': 'System stats are playing hard to get'}

    return {
        'total_cpu': cpu_usage,
        'total_memory': ram_percent,
        'total_memory_used': ram_used,
        'total_memory_total': ram_total,
        'processes': active_procs
    }

def keep_it_fresh():
    while True:
        try:
            latest_data = grab_system_info()
            if 'error' not in latest_data:
                realtime_io.sleep(0.1)
                realtime_io.emit('update', latest_data)
            else:
                realtime_io.emit('message', {'msg': 'Data grab failed—check the logs!', 'status': 'error'})
        except Exception as uhoh:
            logging.error(f"Update loop took a dive: {uhoh}")
            realtime_io.emit('message', {'msg': 'Updates crashed, oops!', 'status': 'error'})
        time.sleep(1)

try:
    updater = threading.Thread(target=keep_it_fresh, daemon=True)
    updater.start()
except Exception as thread_trouble:
    logging.error(f"Thread didn’t wanna start: {thread_trouble}")

@realtime_io.on('connect')
def new_guest():
    try:
        logging.info(f"New buddy joined: {request.sid}")
        realtime_io.emit('message', {'msg': 'Yo, welcome aboard!', 'status': 'success'})
        fresh_stats = grab_system_info()
        if 'error' not in fresh_stats:
            realtime_io.emit('update', fresh_stats)
    except Exception as bummer:
        logging.error(f"Welcome wagon broke down: {bummer}")

@realtime_io.on('kill_process')
def zap_process(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            raise ValueError("Gimme a real PID, man!")
        
        target = psutil.Process(pid)
        target.terminate()
        time.sleep(0.1)
        if target.is_running():
            target.kill()
            realtime_io.emit('message', {'msg': f'{pid} wouldn’t quit, so I forced it out!', 'status': 'success'})
        else:
            realtime_io.emit('message', {'msg': f'{pid} got smoked!', 'status': 'success'})
    except ValueError as nope:
        realtime_io.emit('message', {'msg': f'PID’s junk: {nope}', 'status': 'error'})
    except psutil.NoSuchProcess:
        realtime_io.emit('message', {'msg': f'{pid} ain’t even there, weird.', 'status': 'error'})
    except psutil.AccessDenied:
        realtime_io.emit('message', {'msg': f'No dice killing {pid}—locked down tight.', 'status': 'error'})
    except Exception as ouch:
        realtime_io.emit('message', {'msg': f'Mess-up alert: {ouch}', 'status': 'error'})

if __name__ == '__main__':
    try:
        realtime_io.run(my_app, debug=True, host='0.0.0.0', port=5000)
    except Exception as crash:
        logging.error(f"Launch failed hard: {crash}")
        print("Server’s toast—peek at the logs!")