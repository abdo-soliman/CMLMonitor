import os
import sys
import time
import signal
import subprocess
from gunicorn.app.base import BaseApplication

work_dir = os.getenv("WORK_DIR", ".")
os.chdir(work_dir)

from app import app


class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.options = options
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }

        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def start_valkey():
    """Starts Valkey server in the background."""
    valkey_port = os.getenv("VALKEY_PORT", "6379")
    print(f"Starting Valkey server on port {valkey_port}...")
    
    # Launch valkey-server directly
    proc = subprocess.Popen(
        ["valkey-server", "--port", valkey_port, "--protected-mode", "no", "--daemonize", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT
    )
    # Give Valkey a second to bind to the port
    time.sleep(1.5)
    return proc


def start_poller():
    """Starts cml_poll.py background worker using the current Python executable."""
    print("Starting background poller process (cml_poll.py)...")
    proc = subprocess.Popen(
        [sys.executable, "cml_poll.py"]
    )
    return proc


if __name__ == "__main__":
    valkey_process = None
    poller_process = None

    def cleanup(signum=None, frame=None):
        """Cleanly terminates sub-processes when CML stops or restarts the application."""
        print("\nShutting down background services...")
        processes = [
            ("CML Poller", poller_process),
            ("Valkey Server", valkey_process)
        ]

        for name, proc in processes:
            if proc and proc.poll() is None:
                print(f"Stopping {name} (PID: {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        
        sys.exit(0)

    # Register signal handlers for SIGTERM (sent by CML stop) and SIGINT (Ctrl+C)
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        # 1. Start Valkey
        valkey_process = start_valkey()

        # 2. Start CML Background Poller
        poller_process = start_poller()

        # 3. Launch Gunicorn Application
        PORT = int(os.environ["CDSW_APP_PORT"])
        options = {
            'bind': f'127.0.0.1:{PORT}',
            'workers': 5,
            'timeout': 90,
            'accesslog': '-',
            'errorlog': '-'
        }

        print(f"Starting Gunicorn server on {options['bind']} with {options['workers']} workers ...")
        StandaloneApplication(app, options).run()

    except Exception as e:
        print(f"Fatal error starting application: {e}")
    finally:
        cleanup()
