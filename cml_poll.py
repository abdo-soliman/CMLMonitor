import os
import time
import logging
from models import Config
from extensions import app
from workload_manager import WorkloadManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - [%(process)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Fetch polling interval from environment variables, default to 60 seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 60))

def main():
    logging.info(f"Starting CML Background Poller. Update interval set to {POLL_INTERVAL} seconds.")

    with app.app_context():
        # 1. Wait for the main Gunicorn application to finish DB migrations and Day-0 Setup
        setup_complete = False
        while not setup_complete:
            try:
                init_config = Config.query.filter_by(attr='init').first()
                if init_config and init_config.value == '1':
                    setup_complete = True
                    break
            except Exception:
                pass

            logging.info("Waiting for database migrations and initial setup to complete...")
            time.sleep(5)

    # Initialize the manager (which connects to Valkey)
    manager = WorkloadManager()

    # Infinite polling loop
    while True:
        manager.fetch_and_cache()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
