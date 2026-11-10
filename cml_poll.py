import os
import time
from logger import logger
from models import Config
from extensions import app
from workload_manager import WorkloadManager


# Fetch polling interval from environment variables, default to 60 seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 60))

def main():
    logger.info(f"Starting CML Background Poller. Update interval set to {POLL_INTERVAL} seconds.")

    # 1. Wait for the main Gunicorn application to finish DB migrations and Day-0 Setup
    setup_complete = False
    while not setup_complete:
        try:
            with app.app_context():
                init_config = Config.query.filter_by(attr='init').first()
                if init_config and init_config.value == '1':
                    setup_complete = True
                    break
        except Exception as e:
            pass

        logger.info("Waiting for database migrations and initial setup to complete...")
        time.sleep(5)

    # Initialize the manager (which connects to Valkey)
    manager = WorkloadManager()

    # Infinite polling loop
    while True:
        manager.fetch_and_cache()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
