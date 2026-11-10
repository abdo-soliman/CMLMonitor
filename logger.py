import logging

# ---------------------------------------------------------
# UNIFIED CUSTOM LOGGER CONFIGURATION
# ---------------------------------------------------------

# Grab the exact logger instance that Gunicorn explicitly controls
logger = logging.getLogger("gunicorn.error")

# Fallback block purely for non-Gunicorn isolated processes (like cml_poll.py)
if not logger.hasHandlers():
    logger.setLevel(logging.INFO)
    log_handler = logging.FileHandler("/home/cdsw/app.log", mode='a', encoding='utf-8')
    formatter = logging.Formatter("[%(levelname)s] %(asctime)s [%(process)d:%(threadName)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    logger.propagate = False
