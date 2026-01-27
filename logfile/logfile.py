"""logfile - SDK Application that writes log to files on flash available for download via HTTP/Remote Connect.

Never lose another log!  Remote Syslog!
No more logs rolling over, no more physical USB flash drives,
and you can recover logs after a reboot.  Via Remote Connect!

Log files will be created with filenames containing the router MAC address and timestamp.  Example:
Log - 0030443B3877.2026-01-26 09:52:25.txt
Log - 0030443B3877.2026-01-26 09:52:25.txt.tar.gz (after rotation)

When the log file reaches the maximum file size (default 10MB) it will start a new log file.
Rotated logs are compressed to .tar.gz to save space.
When the total size of log files exceeds the maximum storage (default 50MB) it will delete the oldest logs.

Settings can be configured via /config/system/sdk/appdata:
  - logfile_max_file_size_MB: max size of a single log file before rotation
  - logfile_max_total_storage_MB: max total storage for all logs before deleting oldest

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

# default values
DEFAULT_MAX_FILE_SIZE_MB = 10
DEFAULT_MAX_TOTAL_STORAGE_MB = 50

# Get config values from appdata, or use defaults
#
# To override, go to: Router/Group page -> Configuration -> Edit -> System -> SDK Data
# Add fields for:
#   `logfile_max_file_size_MB`
#   `logfile_max_total_storage_MB`
def get_config_value(key, default):
    """Get a config value from sdk/appdata, or return the default."""
    try:
        appdata = cp.get('/config/system/sdk/appdata')
        if appdata:
            for item in appdata:
                if item.get('name') == key:
                    value = item.get('value')
                    if value:
                        return float(value)
        return default
    except Exception as e:
        cp.log(f'Error reading config {key}: {e}')
        return default

def compress_files():
    # find any .txt file and compress it
    logfiles = [f for f in os.listdir('logs') if f.endswith('.txt') and os.path.isfile(os.path.join('logs', f))]
    for logfile in logfiles:
        path = os.path.join('logs', logfile)
        try:
            original_mtime = os.path.getmtime(path)

            # target compressed is to add .tar.gz, but add file indexing if needed to deconflict
            tarball_path = f'{path}.tar.gz'
            if os.path.exists(tarball_path):
                i = 0
                while True:
                    tarball_path = f'{path}.{i:03d}.tar.gz'
                    if not os.path.exists(tarball_path):
                        break
                    i += 1

            with tarfile.open(tarball_path, 'w:gz') as tar:
                tar.add(path, arcname=os.path.basename(path))

            # update modified time on the tar file to preserve notion of "oldest"
            os.utime(tarball_path, (original_mtime, original_mtime))

            # remove original file
            os.remove(path)
        except Exception as e:
            cp.log(f'Compression failed for {logfile}: {e}')
            if os.path.exists(tarball_path):
                os.remove(tarball_path)

def write_logs(mac, max_file_size):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logfile = f'Log - {mac} {timestamp}.txt'
    logpath = os.path.join('logs', logfile)
    f = open(logpath, 'wt')
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
                time.sleep(1)
                return
    except Exception as e:
        cp.log(f'Exception! {e}')

def rotate_files(max_total_storage):
    # get all files in log folder, sort by modify time (oldest first), and calculate total size
    logfiles = [f for f in os.listdir('logs') if os.path.isfile(os.path.join('logs', f))]
    logfiles = sorted(logfiles, key=lambda f: os.path.getmtime(os.path.join('logs', f)), reverse=True)
    total_size = sum(os.path.getsize(os.path.join('logs', f)) for f in logfiles)

    # iteratively delete oldest file until total size is under max
    while total_size > max_total_storage and logfiles:
        oldest = logfiles.pop()
        oldest_path = os.path.join('logs', oldest)
        total_size -= os.path.getsize(oldest_path)
        os.remove(oldest_path)

def main():
    cp.log(f'Starting logfile; download logs via NCM LAN Manager - HTTP 127.0.0.1 port 8000')

    max_file_size = get_config_value('logfile_max_file_size_MB', DEFAULT_MAX_FILE_SIZE_MB) * MB
    max_total_storage = get_config_value('logfile_max_total_storage_MB', DEFAULT_MAX_TOTAL_STORAGE_MB) * MB
    cp.log(f'Max log file size: {max_file_size/MB}MB, Max total log storage: {max_total_storage/MB}MB')

    mac = cp.get('status/product_info/mac0').replace(':', '').upper()
    if not os.path.exists('logs'):
        os.makedirs('logs')

    while True:
        compress_files()
        rotate_files(max_total_storage)
        write_logs(mac, max_file_size)

if __name__ == '__main__':
    main()