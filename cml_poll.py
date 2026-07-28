import time
import logging
import os
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
    
    # Initialize the manager (which connects to Valkey)
    manager = WorkloadManager()

    # Infinite polling loop
    while True:
        manager.fetch_and_cache()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
