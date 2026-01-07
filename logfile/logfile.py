"""logfile - SDK Application that writes log to files on flash available for download via HTTP/Remote Connect.

Never lose another log!  Remote Syslog!
No more logs rolling over, no more physical USB flash drives,
and you can recover logs after a reboot.  Via Remote Connect!

Log files will be created with filenames containing the router MAC address and timestamp.  Example:
Log - 0030443B3877.2022-11-11 09:52:25.txt

When the log file reaches the maximum file size (Default 10MB) it will start a new log file.
When the total size of log files exceeds the maximum storage (default 100MB) it will delete the oldest logs.

Use Remote Connect LAN Manager to connect to 127.0.0.1 port 8000 HTTP.
Or forward the LAN zone to the ROUTER zone for local access on http://{ROUTER IP}:8000.

"""

import cp
from subprocess import Popen, PIPE
import datetime
import time
import os
import tarfile

MB = 2**20

# Default values
DEFAULT_MAX_FILE_SIZE_MB = 10
DEFAULT_MAX_TOTAL_STORAGE_MB = 100

# Get config values from appdata, or use defaults
def get_config_value(key, default):
    """Get a config value from sdk/appdata, or return the default."""
    try:
        appdata = cp.get('/config/system/sdk/appdata')
        if appdata:
            for item in appdata:
                if item.get('name') == key:
                    value = item.get('value')
                    if value:
                        return int(value)
        return default
    except Exception as e:
        cp.log(f'Error reading config {key}: {e}')
        return default

max_file_size = get_config_value('logfile_max_file_size_MB', DEFAULT_MAX_FILE_SIZE_MB) * MB
max_total_storage = get_config_value('logfile_max_total_storage_MB', DEFAULT_MAX_TOTAL_STORAGE_MB) * MB

cp.log(f'Max log file size: {max_file_size/MB}MB, Max total log storage: {max_total_storage/MB}MB')

def compress_files():
    logfiles = [f for f in os.listdir('logs') if f.endswith('.txt') and os.path.isfile(os.path.join('logs', f))]
    for logfile in logfiles:
        path = os.path.join('logs', logfile)
        try:
            original_mtime = os.path.getmtime(path)
            with tarfile.open(f'{path}.tar.gz', 'w:gz') as tar:
                tar.add(path, arcname=os.path.basename(path))
            os.utime(f'{path}.tar.gz', (original_mtime, original_mtime))
            os.remove(path)
        except Exception as e:
            cp.log(f'Compression failed for {logfile}: {e}')
            if os.path.exists(f'{path}.tar.gz'):
                os.remove(f'{path}.tar.gz')

def write_logs():
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logfile = f'logs/Log - {mac} {timestamp}'
    if os.path.exists(f'{logfile}.txt'):
        i = 1
        while True:
            suffix = f'({i})'
            if not os.path.exists(f'{logfile} {suffix}.txt'):
                logfile = f'{logfile} {suffix}.txt'
                cp.log(f'LOGFILE {logfile}')
                break
            else:
                cp.log('NOPE!')
                i += 1
    else:
        logfile += '.txt'
    f = open(logfile, 'wt')
    try:
        cmd = ['/usr/bin/tail', '/var/log/messages', '-n1', '-F']
        tail = Popen(cmd, stdout=PIPE, stderr=PIPE)
        for line in iter(tail.stdout.readline, ''):
            if tail.returncode:
                break
            line = line.decode('utf-8').split(' ')
            try:
                line[0] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(line[0])))
            except:
                pass
            line = ' '.join(line)
            f.write(line)
            f.flush()
            os.sync()
            if f.tell() > max_file_size:
                f.close()
                compress_files()
                time.sleep(1)
                return
    except Exception as e:
        cp.log(f'Exception! {e}')

def rotate_files():
    logfiles = [f for f in os.listdir('logs') if os.path.isfile(os.path.join('logs', f))]
    logfiles = sorted(logfiles, key=lambda f: os.path.getmtime(os.path.join('logs', f)), reverse=True)
    total_size = sum(os.path.getsize(os.path.join('logs', f)) for f in logfiles)
    while total_size > max_total_storage and logfiles:
        oldest = logfiles.pop()
        oldest_path = os.path.join('logs', oldest)
        total_size -= os.path.getsize(oldest_path)
        os.remove(oldest_path)

cp.log(f'Download logs via NCM LAN Manager - HTTP 127.0.0.1 port 8000')
mac = cp.get('status/product_info/mac0').replace(':', '').upper()

while True:
    compress_files()
    rotate_files()
    write_logs()
