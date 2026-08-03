import re
import ast
import time
import cmlapi
import urllib3
import logging
import argparse
import pandas as pd
from pathlib import Path
from pprint import pprint
from utils import SearchFilters
from smtp_utils import send_email
from kubernetes import client, config
from cmlmonitor_db import get_configs
from ldap_utils import get_user_full_name
from kubernetes.client.rest import ApiException
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timezone, timedelta
from croniter import croniter, CroniterBadCronError
from utils import split_age, age_toseconds, seconds_to_age, age_dict_tostring, keep_only_arabic, validate_none_or_empty


WORKSPACE_DOMAIN = None
API_KEY = None
NAMESPACE_PREFIX = None
KUBECONFIG_PATH = None
ECS_WEBUI_BASE_URL = None
smtp_enabled = None
smtp_use_tls = None
smtp_server = None
smtp_port = None
smtp_user = None
smtp_password = None
smtp_subject = None
smtp_alert_subject = None
smtp_report_subject = None
sender_email = None
alert_recipient_emails = None
report_recipient_emails = None
OUTPUT = None
LDAP_ENABLED = None
LDAP_SERVER = None
LDAP_PORT = None
BIND_USER_DN = None
BIND_USER_PASSWORD = None
BASE_DN = None
MODE = None

alert_cron_string = None
report_cron_string = None
alert_cron_changed = False
report_cron_changed = False


EMAIL_TEMPLATES_PATH = "mail_templates"


def check_cml_connection(workspace_domain: str, api_key: str):
    """
    Attempts to list workload types via CML API, if successful
    then provided workspace_domain, api_key are valid

    Params: workspace_domain -> str, URL for CML
            api_key -> str, API_KEY for user on CML
    Returns: cml_connected -> bool, True if connection is established successfully.
             message -> str or None, None if successsful otherwise error message.
    """
    try:
        client = cmlapi.default_client(workspace_domain, api_key)
        api_response = client.list_workload_types_with_http_info()
        if api_response[1] == 200:
            return True, None

        return False, f"Connection failed with the following status {api_response[1]} and the following HTTP Header: {api_response[2]}"
    except Exception as e:
        return False, str(e)


def is_cml_apikey_admin(workspace_domain: str, api_key: str) -> bool:
    """
    Checks if a CML API key belongs to an administrator.
    Relies on intentionally triggering a 400 Bad Request on an admin-only
    endpoint to verify authorization without actually creating resources.

    Params: workspace_domain -> str, URL for CML
            api_key -> str, API_KEY for admin user on CML
    Returns: is_cml_admin -> bool, True if provided api_key is for an admin account on CML
    """
    try:
        client = cmlapi.default_client(workspace_domain, api_key)
        # empty payload so we don't actually create a runtime repo but simply test privileges
        body = cmlapi.CreateRuntimeRepoRequest()
        client.create_runtime_repo_with_http_info(body)

        # If it somehow succeeds, the user definitely has admin privileges
        return True
    except cmlapi.rest.ApiException as e:
        if e.status == 400:
            # Server accepted the authorization but rejected the empty payload, therefore, the user is an Admin.
            return True
        return False
    except Exception as e:
        return False


def test_kube_config(kube_config_file_path):
    """
    Checks connection to kubernetes cluster can be established via rke2.yaml config file.
    Attempts to list namespaces using provided rke2.yaml if successful the file is valid

    Params: kube_config_file_path -> str URL for CML
    Returns: kube_config_valid -> bool, True if provided config_file is a valid rke2.yaml
             message -> str, test connection result message
    """
    try:
        # Load the configuration from the temporary file
        config.load_kube_config(config_file=kube_config_file_path)

        # Initialize the CoreV1Api client
        v1 = client.CoreV1Api()

        # Attempt a simple, lightweight API call to verify connection and auth
        # A 5-second timeout prevents the request from hanging if the IP is unreachable
        v1.list_namespace(_request_timeout=5)

        return True, "Kubernetes connection successful."

    except config.config_exception.ConfigException as e:
        return False, f"Invalid kubeconfig file format: {str(e)}"
    except ApiException as e:
        return False, f"Kubernetes API error: {e.reason} (HTTP {e.status})"
    except urllib3.exceptions.MaxRetryError:
        return False, "Could not reach the Kubernetes cluster (Connection timed out or refused)."
    except Exception as e:
        return False, f"Unexpected error connecting to Kubernetes: {str(e)}"


def update_configs_or_exit():
    set_configs()

    if not smtp_enabled:
        exit()

    if MODE == "alert" and alert_cron_string == "":
        exit()

    if MODE == "report" and report_cron_string == "":
        exit()


def get_running_pods(cutoff_age_seconds):
    config.load_kube_config(config_file=KUBECONFIG_PATH)

    # --- Create API client ---
    v1 = client.CoreV1Api()
    now = datetime.now(timezone.utc)
    pods = []

    try:
        # List all pods in all namespaces
        response = v1.list_pod_for_all_namespaces(watch=False)
        for pod in response.items:
            pod_name = pod.metadata.name
            namespace = pod.metadata.namespace
            status = pod.status.phase  # Running, Pending, etc.
            start_time = pod.status.start_time

            if status == "Running":
                delta = now - pod.status.start_time
                age = int(delta.total_seconds())

                namespace_pattern = re.compile(rf"^{re.escape(NAMESPACE_PREFIX)}.*$")
                if re.fullmatch(namespace_pattern, namespace) and age >= cutoff_age_seconds:
                    pods.append({
                        "namespace": namespace,
                        "name": pod_name,
                        "status": status,
                        "age": age,
                        "start_time": start_time
                    })

        sorted_pods = sorted(pods, key=lambda x: x["age"], reverse=True)
        start = (sorted_pods[0]["start_time"]).strftime('%Y-%m-%d')
        end = (sorted_pods[-1]["start_time"] + timedelta(days=1)).strftime('%Y-%m-%d')
        return sorted_pods, start, end

    except ApiException as e:
        logging.error(f"Exception when calling CoreV1Api->list_pod_for_all_namespaces:{e}\n")


def get_running_sessions(start, end, session_only=True):
    logging.info("Connecting to CML API...")
    client = cmlapi.default_client(WORKSPACE_DOMAIN, API_KEY)

    search_filter = "{\"workload_type\":\"session\",\"status\":\"running\"}" if session_only else "{\"status\":\"running\"}"
    sort = 'created_at'
    page_size = 100000
    time_range_search_filter = "{\"created_time\":{\"min\":\"" + start + "\",\"max\":\"" + end + "\"}}"

    try:
        logging.info(f"Getting Usage Stats for all running Sessions between: {start} and {end}")
        api_response = client.list_usage(search_filter=search_filter, sort=sort, page_size=page_size, time_range_search_filter=time_range_search_filter)

        response = api_response.to_dict()
        return response["usage_response"]
    except cmlapi.rest.ApiException as e:
        logging.error(f"Exception when calling CMLServiceApi->list_usage: {e}")


def match_pods_with_sessions(running_pods, zombie_sessions):
    zombies = []
    for session in zombie_sessions:
        pod = next((pod for pod in running_pods if pod["name"] == session["id"]), None)

        # remove sessions that don't have a running pod yet
        if pod is None:
            continue

        session["cpu"] = int(session["cpu"]) if session["cpu"] > 1 else session["cpu"]
        printable_age = age_dict_tostring(seconds_to_age(pod['age']))

        zombie = {
            "workload_type": session["workload_type"],
            "user": session["creator"],
            "full_name": None,
            "show_full_name": False,
            "project": session["project_name"],
            "name": session["name"],
            "namespace": pod["namespace"],
            "id": session["id"],
            "status": pod["status"],
            "age": printable_age,
            "age_seconds": pod['age'],
            "cpu": session["cpu"],
            "ram": int(session['memory']),
            "Resource Profile": f"{session['cpu']} vCPU / {int(session['memory'])} GiB Memory"
        }

        if LDAP_ENABLED:
            display_name = get_user_full_name(session["creator"])
            display_name, _ = keep_only_arabic(display_name)
            zombie["full_name"] = display_name
            zombie["show_full_name"] = display_name is not None

        zombies.append(zombie)

    return zombies


def workload_report():
    set_configs()

    running_pods, start, end = get_running_pods(1)
    running_sessions = get_running_sessions(start, end, session_only=False)

    if len(running_sessions) <= 0:
        return []

    workloads = match_pods_with_sessions(running_pods, running_sessions)

    search_data = {
        SearchFilters.ALL.value: set(),
        SearchFilters.USERNAME.value: set(),
        SearchFilters.USER_FULLNAME.value: set(),
        SearchFilters.PROJECT.value: set(),
        SearchFilters.SESSION_NAME.value: set(),
        SearchFilters.NAMESPACE.value: set(),
        SearchFilters.SESSION_ID.value: set(),
        SearchFilters.STATUS.value: set(),
        SearchFilters.AGE.value: set(),
        SearchFilters.RESOURCES.value: set()
    }

    for workload in workloads:
        search_data[SearchFilters.USERNAME.value].add(workload["user"])
        search_data[SearchFilters.USER_FULLNAME.value].add(workload["full_name"])
        search_data[SearchFilters.PROJECT.value].add(workload["project"])
        search_data[SearchFilters.SESSION_NAME.value].add(workload["name"])
        search_data[SearchFilters.NAMESPACE.value].add(workload["namespace"])
        search_data[SearchFilters.SESSION_ID.value].add(workload["id"])
        search_data[SearchFilters.STATUS.value].add(workload["status"])
        search_data[SearchFilters.AGE.value].add(workload["age"])
        search_data[SearchFilters.RESOURCES.value].add(workload["Resource Profile"])

    search_data = {k: list(v) for k, v in search_data.items()}

    return workloads, search_data


def report_email_content(df, file_name):
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

    return template.render(
        sessions=sessions,
        apps=apps,
        jobs=jobs,
        file_name=file_name,
        datetime=datetime.now().strftime("%Y-%m-%d %I:%M %p")
    )


def alert_email_content(zombies):
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


def alert_main(cutoff_age_seconds):
    logging.info(f"Running Monitoring Script for pods older than {cutoff_age_seconds}s ...")
    running_pods, start, end = get_running_pods(cutoff_age_seconds)
    logging.info("Fetching coresponding sessions from CML API")
    zombie_sessions = get_running_sessions(start, end)

    if len(zombie_sessions) <= 0:
        logging.info(f"No Zombie sessions detected")
        return

    zombies = match_pods_with_sessions(running_pods, zombie_sessions)

    if len(zombies) > 0:
        logging.info(f"Zombie Sessions detected, Sending Alert Email ...")
        if OUTPUT == "smtp":
            html_content = alert_email_content(zombies)
            send_email(
                smtp_server, \
                smtp_port, \
                smtp_use_tls, \
                smtp_user, \
                smtp_password, \
                sender_email, \
                subject=smtp_alert_subject, \
                content=html_content, \
                recipient_emails=alert_recipient_emails)
        elif OUTPUT == "json":
            pprint(zombies)
    else:
        logging.info(f"No Zombie Sessions detected")


def report_main(cutoff_age_seconds):
    logging.info(f"Running Report Script for pods older than {cutoff_age_seconds}s ...")
    running_pods, start, end = get_running_pods(cutoff_age_seconds)
    logging.info("Fetching coresponding sessions from CML API")
    running_sessions = get_running_sessions(start, end, session_only=False)

    if len(running_sessions) <= 0:
        logging.info(f"No Running sessions detected")
        return

    sessions = match_pods_with_sessions(running_pods, running_sessions)

    if len(sessions) > 0:
        logging.info(f"Running Sessions detected, Sending Report Email ...")
        df = pd.DataFrame(sessions)
        df = df.drop('show_full_name', axis=1)

        report_file_path = Path(f"cml_report_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
        df.to_excel(report_file_path, index=False)

        logging.info(f"Creating Report Email ...")
        html_content = report_email_content(df, report_file_path)

        logging.info(f"Sending Report Email with Report file Attached ...")

        send_email(
            smtp_server, \
            smtp_port, \
            smtp_use_tls, \
            smtp_user, \
            smtp_password, \
            sender_email, \
            subject=smtp_report_subject, \
            content=html_content, \
            recipient_emails=report_recipient_emails, \
            attachments=[report_file_path])

        # remove file after sending email
        report_file_path.unlink(missing_ok=True)
    else:
        logging.info(f"No Running Sessions detected")


def alert_daemon(cutoff_age_seconds):
    global alert_cron_changed
    try:
        update_configs_or_exit()
        iterator = croniter(alert_cron_string, datetime.now())
        next_time = iterator.get_next(datetime)
        while True:
            update_configs_or_exit()
            if alert_cron_changed:
                alert_cron_changed = False
                iterator = croniter(alert_cron_string, datetime.now())
                next_time = iterator.get_next(datetime)
            now = datetime.now()

            logging.info(f"Checking current epoch ...")
            if now >= next_time:
                iterator = croniter(alert_cron_string, now)
                next_time = iterator.get_next(datetime)
                logging.info(f"Current time: {now} is later than scheduled runtime {next_time}")
                alert_main(cutoff_age_seconds)
            else:
                logging.info(f"Current time: {now} is ealier than scheduled runtime {next_time}")

            logging.info("Sleeping for 10 Minutes ...")
            time.sleep(600)
    except CroniterBadCronError as e:
        logging.error(f"Invalid Cron tab string provided: {e}")
    except Exception as e:
        logging.error(f"Application Failed due to the following exception: {e}")


def report_daemon(cutoff_age_seconds):
    global report_cron_changed

    try:
        update_configs_or_exit()
        iterator = croniter(report_cron_string, datetime.now())
        next_time = iterator.get_next(datetime)
        while True:
            update_configs_or_exit()
            if report_cron_changed:
                report_cron_changed = False
                iterator = croniter(report_cron_string, datetime.now())
                next_time = iterator.get_next(datetime)

            now = datetime.now()

            logging.info(f"Checking current epoch ...")
            if now >= next_time:
                iterator = croniter(report_cron_string, now)
                next_time = iterator.get_next(datetime)
                logging.info(f"Current time: {now} is later than scheduled runtime {next_time}")
                report_main(cutoff_age_seconds)
            else:
                logging.info(f"Current time: {now} is ealier than scheduled runtime {next_time}")

            logging.info("Sleeping for 10 Minutes ...")
            time.sleep(600)
    except CroniterBadCronError as e:
        logging.error(f"Invalid Cron tab string provided: {e}")
    except Exception as e:
        logging.error(f"Application Failed due to the following exception: {e}")


def set_configs():
    global smtp_enabled, smtp_use_tls, smtp_port, smtp_server, smtp_user, smtp_password, smtp_alert_subject, smtp_report_subject, sender_email, alert_recipient_emails, report_recipient_emails, WORKSPACE_DOMAIN, API_KEY, NAMESPACE_PREFIX, KUBECONFIG_PATH, ECS_WEBUI_BASE_URL, LDAP_ENABLED, LDAP_SERVER, LDAP_PORT, BIND_USER_DN, BIND_USER_PASSWORD, BASE_DN, alert_cron_string, report_cron_string, alert_cron_changed, report_cron_changed

    configs = get_configs()

    smtp_config = configs["smtp"]
    cmlapi_config = configs["cmlapi"]
    ldap_config = configs["ldap"]
    runtime_config = configs["runtime"]

    smtp_enabled = validate_none_or_empty(smtp_config.get("smtp_enabled"))
    if smtp_enabled:
        smtp_use_tls = validate_none_or_empty(smtp_config.get("smtp_use_tls"))
        smtp_port = validate_none_or_empty(smtp_config.get("smtp_port"))
        smtp_server = validate_none_or_empty(smtp_config.get("smtp_server")).replace('"', '')
        smtp_user = validate_none_or_empty(smtp_config.get("smtp_user")).replace('"', '')
        smtp_password = validate_none_or_empty(smtp_config.get("smtp_password")).replace('"', '')
        smtp_alert_subject = validate_none_or_empty(smtp_config.get("smtp_alert_subject")).replace('"', '')
        smtp_report_subject = validate_none_or_empty(smtp_config.get("smtp_report_subject")).replace('"', '')
        sender_email = validate_none_or_empty(smtp_config.get("sender_email")).replace('"', '')
        alert_recipient_emails = ast.literal_eval(validate_none_or_empty(smtp_config.get("alert_recipient_emails")))
        report_recipient_emails = ast.literal_eval(validate_none_or_empty(smtp_config.get("report_recipient_emails")))

        if not isinstance(alert_recipient_emails, list):
            raise TypeError("alert_recipient_emails must be a list of emails")
    
        if not isinstance(report_recipient_emails, list):
            raise TypeError("report_recipient_emails must be a list of emails")

    WORKSPACE_DOMAIN = validate_none_or_empty(cmlapi_config.get("WORKSPACE_DOMAIN")).replace('"', '')
    API_KEY = validate_none_or_empty(cmlapi_config.get("API_KEY")).replace('"', '')
    NAMESPACE_PREFIX = validate_none_or_empty(cmlapi_config.get("NAMESPACE_PREFIX")).replace('"', '')
    KUBECONFIG_PATH = validate_none_or_empty(cmlapi_config.get("KUBECONFIG_PATH")).replace('"', '')
    ECS_WEBUI_BASE_URL = validate_none_or_empty(cmlapi_config.get("ECS_WEBUI_BASE_URL")).replace('"', '')

    LDAP_ENABLED = validate_none_or_empty(ldap_config.get("LDAP_ENABLED"))
    if LDAP_ENABLED:
        LDAP_SERVER = validate_none_or_empty(ldap_config.get("LDAP_SERVER"))
        LDAP_PORT = validate_none_or_empty(ldap_config.get("LDAP_PORT"))
        BASE_DN = validate_none_or_empty(ldap_config.get("BASE_DN"))
        BIND_USER_DN = validate_none_or_empty(ldap_config.get("BIND_USER_DN"))
        BIND_USER_PASSWORD = validate_none_or_empty(ldap_config.get("BIND_USER_PASSWORD"))

    new_alert_cron_string = runtime_config.get("alert_daemon").replace('"', '')
    new_report_cron_string = runtime_config.get("report_daemon").replace('"', '')

    alert_cron_changed = new_alert_cron_string != alert_cron_string
    report_cron_changed = new_report_cron_string != report_cron_string

    alert_cron_string = new_alert_cron_string
    report_cron_string = new_report_cron_string


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="CML Monitor",
        description="A Program to monitor workload running on CML"
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

    try:
        cutoff_age_seconds = age_toseconds(split_age(args.cutoff))
        MODE = args.mode
        OUTPUT = args.output
        if args.dry_run:
            # exit if smtp is disabled by admin
            set_configs()
            if not smtp_enabled:
                exit()

            logging.info("Starting Dry Run ...")
            if MODE == "alert":
                alert_main(cutoff_age_seconds)
            elif MODE == "report":
                report_main(cutoff_age_seconds)
            else:
                raise RuntimeError("Invalid Running Mode")
        else:
            logging.info("Application Starting ...")
            if MODE == "alert":
                alert_daemon(cutoff_age_seconds)
            elif MODE == "report":
                report_daemon(cutoff_age_seconds)
            else:
                raise RuntimeError("Invalid Running Mode")
    except Exception as e:
        logging.error(f"Application Failed due to the following exception: {e}")
