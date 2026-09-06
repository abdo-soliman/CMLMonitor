import ast
import time
import logging
import argparse
import pandas as pd
from pathlib import Path
from pprint import pprint
from models import Config
from extensions import app
from datetime import datetime
from smtp_utils import send_email
from utils import split_age, age_toseconds
from workload_manager import WorkloadManager
from jinja2 import Environment, FileSystemLoader
from croniter import croniter, CroniterBadCronError

workload_manager = None
OUTPUT = None
MODE = None
EMAIL_TEMPLATES_PATH = "mail_templates"

class AlertsManager:
    def __init__(self):
        self.alerts_enabled = None
        self.smtp_use_tls = None
        self.smtp_server = None
        self.smtp_port = None
        self.smtp_user = None
        self.smtp_password = None
        self.smtp_alert_subject = None
        self.smtp_report_subject = None
        self.sender_email = None
        self.alert_recipient_emails = None
        self.report_recipient_emails = None

        self.alert_cron_string = None
        self.report_cron_string = None
        self.alert_cron_changed = False
        self.report_cron_changed = False
        self.set_configs()

    def set_configs(self):
        with app.app_context():
            alert_configs = Config.get_configs("alert")
            runtime_configs = Config.get_configs("runtime")

            self.alerts_enabled = alert_configs.get("alert_enabled")
            self.smtp_use_tls = alert_configs.get("smtp_use_tls")
            self.smtp_port = alert_configs.get("smtp_port")
            self.smtp_server = alert_configs.get("smtp_server")
            self.smtp_user = alert_configs.get("smtp_user")
            self.smtp_password = alert_configs.get("smtp_password")
            self.smtp_alert_subject = alert_configs.get("smtp_alert_subject")
            self.smtp_report_subject = alert_configs.get("smtp_report_subject")
            self.sender_email = alert_configs.get("sender_email")
            self.alert_recipient_emails = ast.literal_eval(alert_configs.get("alert_recipient_emails"))
            self.report_recipient_emails = ast.literal_eval(alert_configs.get("report_recipient_emails"))
    
            if not isinstance(self.alert_recipient_emails, list):
                raise TypeError("alert_recipient_emails must be a list of emails")
    
            if not isinstance(self.report_recipient_emails, list):
                raise TypeError("report_recipient_emails must be a list of emails")
    
            new_alert_cron_string = runtime_configs.get("alert_daemon")
            new_report_cron_string = runtime_configs.get("report_daemon")
    
            self.alert_cron_changed = new_alert_cron_string != self.alert_cron_string
            self.report_cron_changed = new_report_cron_string != self.report_cron_string
    
            self.alert_cron_string = new_alert_cron_string
            self.report_cron_string = new_report_cron_string

    def update_configs_or_exit(self):
        self.set_configs()

        if not self.alerts_enabled:
            exit()

        if MODE == "alert" and self.alert_cron_string == "":
            exit()

        if MODE == "report" and self.report_cron_string == "":
            exit()

    def report_email_content(self, df, file_name):
        file_loader = FileSystemLoader(EMAIL_TEMPLATES_PATH)
        env = Environment(loader=file_loader)
        template = env.get_template('report.html.jinja')

        summary_df = df.groupby('workload_type').agg(
            count=('workload_type', 'count'),
            total_cpu=('cpu', 'sum'),
            total_ram=('ram', 'sum')
        ).reset_index()

        workload_data = summary_df.set_index('workload_type').to_dict('index')
        # Now you can extract them into separate variables:
        sessions = workload_data.get('session', {'count': 0, 'total_cpu': 0, 'total_ram': 0})
        jobs = workload_data.get('job', {'count': 0, 'total_cpu': 0, 'total_ram': 0})
        apps = workload_data.get('application', {'count': 0, 'total_cpu': 0, 'total_ram': 0})
        orphans = workload_data.get('orphan', {'count': 0, 'total_cpu': 0, 'total_ram': 0})

        return template.render(
            sessions=sessions,
            apps=apps,
            jobs=jobs,
            orphans=orphans,
            file_name=file_name,
            datetime=datetime.now().strftime("%Y-%m-%d %I:%M %p")
        )

    def alert_email_content(self, zombies):
        file_loader = FileSystemLoader(EMAIL_TEMPLATES_PATH)
        env = Environment(loader=file_loader)
        template = env.get_template('alert.html.jinja')

        total_cpu = 0
        total_ram = 0
        for zombie in zombies:
            total_cpu = total_cpu + zombie["cpu"]
            total_ram = total_ram + zombie["ram"]

        return template.render(
            zombies=zombies,
            total_zombies=len(zombies),
            total_cpu=total_cpu,
            total_ram=total_ram,
            datetime=datetime.now().strftime("%Y-%m-%d %I:%M %p")
        )

    def alert_main(self, cutoff_age_seconds):
        logging.info(f"Running Monitoring Script for pods older than {cutoff_age_seconds}s ...")
        zombies, _ = workload_manager.cmlapi_manager.workload_report(cutoff_age_seconds, zombies_only=True)
        zombies = workload_manager.group_workload_by_id(zombies)

        if len(zombies) > 0:
            logging.info(f"Zombie Sessions detected, Sending Alert Email ...")
            if OUTPUT == "smtp":
                html_content = self.alert_email_content(zombies)
                send_email(
                    self.smtp_server, \
                    self.smtp_port, \
                    self.smtp_use_tls, \
                    self.smtp_user, \
                    self.smtp_password, \
                    self.sender_email, \
                    subject=self.smtp_alert_subject, \
                    content=html_content, \
                    recipient_emails=self.alert_recipient_emails)
            elif OUTPUT == "json":
                pprint(zombies)
        else:
            logging.info(f"No Zombie Sessions detected")

    def report_main(self, cutoff_age_seconds):
        logging.info(f"Running Report Script for pods older than {cutoff_age_seconds}s ...")
        workloads, _ = workload_manager.cmlapi_manager.workload_report(cutoff_age_seconds)
        workloads = workload_manager.group_workload_by_id(workloads)

        if len(workloads) > 0:
            logging.info(f"Running Sessions detected, Sending Report Email ...")
            df = pd.DataFrame(workloads)

            report_file_path = Path(f"cml_report_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
            logging.info(f"Creating Report Email ...")
            html_content = self.report_email_content(df, report_file_path)

            df = df.drop('show_full_name', axis=1)
            df = df.drop('role', axis=1)
            df = df.drop('parent', axis=1)
            df = df.drop('has_sub_workload', axis=1)
            df = df.drop('sub_workload', axis=1)
            df = df.drop('namespace_url', axis=1)
            df = df.drop('workload_url', axis=1)
            df = df.drop('age_seconds', axis=1)
            df = df.drop('cpu', axis=1)
            df = df.drop('ram', axis=1)

            df = df[["id", "namespace", "project", "workload_type", "name", "status", "reason", "editor_name", "editor_version", "Resource Profile", "user", "full_name", "age", "start_time", "creation_time"]]

            if df["reason"].isna().all():
                df = df.drop(columns=["reason"])

            df["start_time"] = pd.to_datetime(df["start_time"])
            df["creation_time"] = pd.to_datetime(df["creation_time"])
            df["start_time"] = df["start_time"].dt.tz_convert("Asia/Riyadh").dt.tz_localize(None)
            df["creation_time"] = df["creation_time"].dt.tz_convert("Asia/Riyadh").dt.tz_localize(None)

            df.to_excel(report_file_path, index=False)

            logging.info(f"Sending Report Email with Report file Attached ...")

            send_email(
                self.smtp_server, \
                self.smtp_port, \
                self.smtp_use_tls, \
                self.smtp_user, \
                self.smtp_password, \
                self.sender_email, \
                subject=self.smtp_report_subject, \
                content=html_content, \
                recipient_emails=self.report_recipient_emails, \
                attachments=[report_file_path])

            # remove file after sending email
            report_file_path.unlink(missing_ok=True)
        else:
            logging.info(f"No Running Sessions detected")

    def alert_daemon(self, cutoff_age_seconds):
        try:
            self.update_configs_or_exit()
            iterator = croniter(self.alert_cron_string, datetime.now())
            next_time = iterator.get_next(datetime)
            while True:
                self.update_configs_or_exit()
                if self.alert_cron_changed:
                    self.alert_cron_changed = False
                    iterator = croniter(self.alert_cron_string, datetime.now())
                    next_time = iterator.get_next(datetime)
                now = datetime.now()

                logging.info(f"Checking current epoch ...")
                if now >= next_time:
                    iterator = croniter(self.alert_cron_string, now)
                    next_time = iterator.get_next(datetime)
                    logging.info(f"Current time: {now} is later than scheduled runtime {next_time}")
                    self.alert_main(cutoff_age_seconds)
                else:
                    logging.info(f"Current time: {now} is ealier than scheduled runtime {next_time}")

                logging.info("Sleeping for 10 Minutes ...")
                time.sleep(600)
        except CroniterBadCronError as e:
            logging.error(f"Invalid Cron tab string provided: {e}")
        except Exception as e:
            logging.error(f"Application Failed due to the following exception: {e}")

    def report_daemon(self, cutoff_age_seconds):
        try:
            self.update_configs_or_exit()
            iterator = croniter(self.report_cron_string, datetime.now())
            next_time = iterator.get_next(datetime)
            while True:
                self.update_configs_or_exit()
                if self.report_cron_changed:
                    self.report_cron_changed = False
                    iterator = croniter(self.report_cron_string, datetime.now())
                    next_time = iterator.get_next(datetime)

                now = datetime.now()

                logging.info(f"Checking current epoch ...")
                if now >= next_time:
                    iterator = croniter(self.report_cron_string, now)
                    next_time = iterator.get_next(datetime)
                    logging.info(f"Current time: {now} is later than scheduled runtime {next_time}")
                    self.report_main(cutoff_age_seconds)
                else:
                    logging.info(f"Current time: {now} is ealier than scheduled runtime {next_time}")

                logging.info("Sleeping for 10 Minutes ...")
                time.sleep(600)
        except CroniterBadCronError as e:
            logging.error(f"Invalid Cron tab string provided: {e}")
        except Exception as e:
            logging.error(f"Application Failed due to the following exception: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="CML Monitor",
        description="A Program to monitor Zombie sessions running on Kubernetes"
    )

    parser.add_argument("-m", "--mode", type=str, choices=["alert", "report"], default="alert", help="--mode <alert,report>")
    parser.add_argument("--dry-run", action="store_true", help="--dry-run <Run for a single run>")
    parser.add_argument("-c", "--cutoff", type=str, required=True, help="-c|--cutoff <CUT_OFF_AGE>")
    parser.add_argument("-l", "--log", type=str, default="cmlmonitor.log", help="-l|--log <log file path")
    parser.add_argument("-o", "--output", type=str, choices=["smtp", "json"], default="smtp", help="--output <smtp,json>")
    args = parser.parse_args()

    if args.dry_run:
        logging.basicConfig(
            level=logging.INFO,
            format="[%(levelname)s] %(asctime)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    else:
        logging.basicConfig(
            filename=args.log,
            filemode="a",
            level=logging.INFO,
            format="[%(levelname)s] %(asctime)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    workload_manager = WorkloadManager()
    alerts_manager = AlertsManager()

    try:
        cutoff_age_seconds = age_toseconds(split_age(args.cutoff))
        MODE = args.mode
        OUTPUT = args.output
        if args.dry_run:
            # exit if smtp is disabled by admin
            if not alerts_manager.alerts_enabled:
                exit()

            logging.info("Starting Dry Run ...")
            if MODE == "alert":
                alerts_manager.alert_main(cutoff_age_seconds)
            elif MODE == "report":
                alerts_manager.report_main(cutoff_age_seconds)
            else:
                raise RuntimeError("Invalid Running Mode")
        else:
            logging.info("Application Starting ...")
            if MODE == "alert":
                alerts_manager.alert_daemon(cutoff_age_seconds)
            elif MODE == "report":
                alerts_manager.report_daemon(cutoff_age_seconds)
            else:
                raise RuntimeError("Invalid Running Mode")
    except Exception as e:
        logging.error(f"Application Failed due to the following exception: {e}")
