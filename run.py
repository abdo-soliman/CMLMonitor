import os

os.chdir(os.environ["WORK_DIR"])

from gunicorn.app.base import BaseApplication
from app import app

class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.options = options
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value for key, value in self.options.items() \
            if key in self.cfg.settings and value is not None
        }

        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application

if __name__ == "__main__":
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
