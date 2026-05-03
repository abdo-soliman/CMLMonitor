import os
import psutil
import tempfile
import subprocess

# 1. Dynamically resolve the OS temp directory and create an app-specific folder
APP_STATE_DIR = os.path.join(tempfile.gettempdir(), 'cmlmonitor')
os.makedirs(APP_STATE_DIR, exist_ok=True)

# 2. Map the PID files to this dynamic directory
PID_FILES = {
    'alert': os.path.join(APP_STATE_DIR, 'alert.pid'),
    'report': os.path.join(APP_STATE_DIR, 'report.pid')
}
SCRIPT_PATH = "cmlmonitor.py"


def get_running_process(process_type):
    """Reads the PID file and returns the process if it is actually running."""
    pid_file = PID_FILES.get(process_type)
    if not pid_file or not os.path.exists(pid_file):
        return None

    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        # Verify the PID belongs to a currently running process
        if psutil.pid_exists(pid):
            return psutil.Process(pid)
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return None


def start_process(process_type, cutoff_age):
    """Starts the process with specific CLI parameters if it isn't running."""
    if get_running_process(process_type) is not None:
        return False # Already running

    # Automatically generate the log path in the same state directory
    log_path = os.path.join(APP_STATE_DIR, f"{process_type}.log")

    cmd = [
        "python", 
        SCRIPT_PATH, 
        "--mode", process_type,
        "--cutoff", str(cutoff_age),
        "--log", log_path
    ]

    # Start the process in the background
    process = subprocess.Popen(cmd)

    # Save the PID to the dynamically generated file location
    with open(PID_FILES[process_type], 'w') as f:
        f.write(str(process.pid))

    return True


def stop_process(process_type):
    """Gracefully terminates the process and cleans up the PID file."""
    process = get_running_process(process_type)
    if process:
        try:
            process.terminate() # Graceful kill
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill() # Force kill if it hangs

    # Always clean up the file
    pid_file = PID_FILES.get(process_type)
    if pid_file and os.path.exists(pid_file):
        os.remove(pid_file)


def restart_process(process_type, cutoff_age):
    if get_running_process(process_type) is not None:
        stop_process(process_type)

    start_process(process_type, cutoff_age)


def stop_all():
    if get_running_process("alert") is not None:
        stop_process("alert")

    if get_running_process("report") is not None:
        stop_process("report")


def get_status():
    """Returns a dictionary showing which processes are currently running."""
    return {
        'alert_running': get_running_process('alert') is not None,
        'report_running': get_running_process('report') is not None
    }
