import os
import re
import math
import cmlapi
import urllib3
import logging
import posixpath
import pandas as pd
from extensions import app
from urllib.parse import quote
from models import Runtime, Config
from collections import defaultdict
from kubernetes import client, config
from ldap_utils import get_user_full_name
from kubernetes.utils import parse_quantity
from kubernetes.client.rest import ApiException
from datetime import datetime, timezone, timedelta
from utils import SearchFilters, WorkloadStatus, seconds_to_age, age_dict_tostring, keep_only_arabic


class CMLAPIManager:
    def  __init__(self):
        self.POD_CLUSTERING_WINDOW_SIZE = int(os.getenv("POD_CLUSTERING_WINDOW_SIZE", 120))
        with app.app_context():
            cml_configs = Config.get_configs("cml")
            self.WORKSPACE_DOMAIN = cml_configs["WORKSPACE_DOMAIN"]
            self.API_KEY = cml_configs["API_KEY"]
            self.NAMESPACE_PREFIX = cml_configs["NAMESPACE_PREFIX"]
            self.KUBECONFIG_PATH = cml_configs["KUBECONFIG_PATH"]
            self.ECS_WEBUI_BASE_URL = cml_configs["ECS_WEBUI_BASE_URL"]
            self.LDAP_ENABLED = Config.get_configs("ldap")["LDAP_ENABLED"]

        config.load_kube_config(config_file=self.KUBECONFIG_PATH)
        self.v1 = client.CoreV1Api()
        self.cml_client = cmlapi.default_client(self.WORKSPACE_DOMAIN, self.API_KEY)

    def clean_projectname(self, project_name):
        result = project_name.replace("\u202f", ' ')
        result = re.sub(r'[^\x00-\x7f]', r'', result) 
        result = result.lower().strip()
        result = re.sub(r'\s*-\s*', '-', result) 
        result = re.sub(r'\s+', '-', result) 
        result = re.sub(r'-+', '-', result)  
        result = result.replace('&', 'and')
        result = result.replace('|', 'or')

        if result == "":
            return "404"
        return result

    def get_project(self, project_id):
        try:
            response = self.cml_client.get_project(project_id)
            project = response.to_dict()
            username = project["owner"]["username"].lower().replace(' ', '')
            project_name = self.clean_projectname(project["name"])
            parts = [self.WORKSPACE_DOMAIN, username, project_name]
            if project_name == "404":
                parts = [self.WORKSPACE_DOMAIN, "404"]

            project["url"] = posixpath.join(*parts)
            return project
        except Exception as e:
            logging.error(f"Failed to capture project using ID: {project_id} with the following error: {e}")
        return None

    def get_image_editor(self, image_url):
        if not image_url:
            return None, None
            
        with app.app_context():
            runtime = Runtime.query.filter_by(image=image_url).first()
            if runtime:
                return runtime.editor_name.strip(), runtime.editor_version.strip()

            return None, None

    def get_engine_cpu_and_ram(self, engine):
        if engine and engine.resources and engine.resources.requests:
            requests = engine.resources.requests

            raw_cpu = requests.get("cpu")
            raw_memory = requests.get("memory")

            cpu = float(parse_quantity(raw_cpu)) if raw_cpu is not None else 1.0
            ram = 2.0
            if raw_memory:
                memory_bytes = float(parse_quantity(raw_memory))
                ram = memory_bytes / (1024 * 1024 * 1024)

            return math.ceil(cpu), math.ceil(ram)

        return 1, 2 # Default fallback

    def cluster_pods_by_time_window(self, pods):
        clustered_windows = defaultdict(list)
        window_seconds = self.POD_CLUSTERING_WINDOW_SIZE * 60

        for pod in pods:
            creation_time = pod.get("creation_time")
            if not creation_time:
                continue

            ts = creation_time.timestamp()
            floored_ts = math.floor(ts / window_seconds) * window_seconds

            window_start = datetime.fromtimestamp(floored_ts, tz=timezone.utc)
            window_end = window_start + timedelta(minutes=self.POD_CLUSTERING_WINDOW_SIZE)

            start_str = window_start.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            end_str = window_end.strftime('%Y-%m-%dT%H:%M:%S.000Z')

            window_key = (start_str, end_str)
            clustered_windows[window_key].append(pod)

        return clustered_windows

    def get_user_from_namespace(self, namespace):
        try:
            user_id = int(namespace.split('-')[-1])
            response = self.cml_client.get_short_user_by_id(user_id)
            return response.to_dict()["username"]
        except Exception as e:
            logging.error(f"Exception when fetching username from namespace: {e}")
            return None

    def check_cml_connection(self):
        try:
            api_response = self.cml_client.list_workload_types_with_http_info()
            if api_response[1] == 200:
                return True, None
            return False, f"Connection failed with the following status {api_response[1]} and the following HTTP Header: {api_response[2]}"
        except Exception as e:
            return False, str(e)

    def is_cml_apikey_admin(self) -> bool:
        try:
            body = cmlapi.CreateRuntimeRepoRequest()
            self.cml_client.create_runtime_repo_with_http_info(body)
            return True
        except cmlapi.rest.ApiException as e:
            if e.status == 400:
                return True
            return False
        except Exception as e:
            return False

    def test_kube_config(self, kube_config_file_path):
        try:
            config.load_kube_config(config_file=kube_config_file_path)
            v1 = client.CoreV1Api()
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

    def get_running_pods(self, cutoff_age_seconds):
        config.load_kube_config(config_file=self.KUBECONFIG_PATH)

        now = datetime.now(timezone.utc)
        pods = []
        raw = []

        try:
            response = self.v1.list_pod_for_all_namespaces(watch=False)
            for pod in response.items:
                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace
                phase = pod.status.phase 
                status = "unknown"
                reason = None
                start_time = pod.status.start_time
                creation_time = pod.metadata.creation_timestamp

                age = int((now - start_time).total_seconds()) if start_time else 0
                namespace_pattern = re.compile(rf"^{re.escape(self.NAMESPACE_PREFIX)}.*$")
                
                if re.fullmatch(namespace_pattern, namespace) and age >= cutoff_age_seconds:
                    raw.append(pod)

                    # Safeguard container extraction
                    engine_container = next((c for c in (pod.spec.containers or []) if c.name == "engine"), None)
                    username, project_id, engine_image = None, None, None
                    cpu, ram = 0, 0
                    
                    if engine_container:
                        username = next((c.value for c in (engine_container.env or []) if c.name == "HADOOP_USER_NAME"), None)
                        project_id = next((c.value for c in (engine_container.env or []) if c.name == "CDSW_PROJECT_ID"), None)
                        cpu, ram = self.get_engine_cpu_and_ram(engine_container)
                        engine_image = engine_container.image

                    # Safely fetch labels in case they are missing
                    labels = pod.metadata.labels or {}
                    role = labels.get("ds-role", "unknown")
                    role = "session or application" if role == "session" else role
                    role = "job" if role == "job-run" else role
                    
                    parent = pod.metadata.owner_references[0].name if pod.metadata.owner_references else None

                    if phase != "Running":
                        status = phase
                        reason = pod.status.reason if pod.status.reason else None
                    else:
                        engine = next((c for c in (pod.status.container_statuses or []) if c.name == "engine"), None)
                        state_dict = {
                            k: v
                            for k, v in (engine.state.to_dict() if engine and engine.state else {}).items()
                            if v is not None
                        }

                        status = next(iter(state_dict), "unknown")
                        reason = (state_dict.get(status) or {}).get("reason")

                    editor_name, editor_version = self.get_image_editor(engine_image)
                    pods.append({
                        "namespace": namespace,
                        "namespace_url": f"{self.ECS_WEBUI_BASE_URL}#/pod?namespace={namespace}#:~:text={quote(pod_name).replace('-', '%2D')}",
                        "username": username,
                        "project_id": project_id,
                        "name": pod_name,
                        "role": role,
                        "parent": parent,
                        "status": WorkloadStatus(status.lower()),
                        "reason": reason,
                        "editor_name": editor_name,
                        "editor_version": editor_version,
                        "age": age,
                        "cpu": cpu,
                        "memory": ram,
                        "start_time": start_time,
                        "creation_time": creation_time,
                    })

            return pods
        except ApiException as e:
            logging.error(f"Exception when calling CoreV1Api->list_pod_for_all_namespaces:{e}\n")

    def get_running_sessions(self, start, end, zombies_only=False):
        logging.info("Connecting to CML API...")

        sort = 'created_at'
        page_size = 100000
        time_range_search_filter = "{\"created_time\":{\"min\":\"" + start + "\",\"max\":\"" + end + "\"}}"
        try:
            logging.info(f"Getting Usage Stats for all running Sessions between: {start} and {end}")
            if zombies_only:
                search_filter = "{\"workload_type\":\"session\",\"status\":\"running\"}"
                api_response = self.cml_client.list_usage(search_filter=search_filter, sort=sort, page_size=page_size, time_range_search_filter=time_range_search_filter)
            else:
                api_response = self.cml_client.list_usage(sort=sort, page_size=page_size, time_range_search_filter=time_range_search_filter)

            response = api_response.to_dict()
            return response["usage_response"]
        except cmlapi.rest.ApiException as e:
            logging.error(f"Exception when calling CMLServiceApi->list_usage: {e}")

    def match_pods_with_cml_workload(self, pods, cml_workloads):
        unified_workloads = []
        for pod in pods:
            workload = next((w for w in cml_workloads if pod["name"] == w["id"]), None)
            printable_age = age_dict_tostring(seconds_to_age(pod['age']))
            
            unified_workload = {
                "namespace": pod["namespace"],
                "namespace_url": pod["namespace_url"],
                "id": pod["name"],
                "role": pod["role"],
                "parent": pod["parent"],
                "status": pod["status"],
                "reason": pod["reason"],
                "age": printable_age,
                "age_seconds": pod['age'],
                "editor_name": pod["editor_name"],
                "editor_version": pod["editor_version"],
                "start_time": pod["start_time"],
                "creation_time": pod["creation_time"]
            }

            if workload is None:
                username = pod["username"] if pod["username"] is not None else self.get_user_from_namespace(pod["namespace"])
                project = self.get_project(pod["project_id"]) if pod["project_id"] else {"name": "Unknown", "url": self.WORKSPACE_DOMAIN}
                
                project_url = project["url"]
                parts = [project_url, "engines", pod["name"]]
                workload_url = posixpath.join(*parts)
                
                unified_workload.update({
                    "workload_type": "orphan",
                    "user": username,
                    "project": project["name"],
                    "name": None,
                    "workload_url": workload_url,
                    "cpu": pod["cpu"],
                    "ram": int(pod['memory']) if pod['memory'] else 0,
                    "Resource Profile": f"{pod['cpu']} vCPU / {int(pod['memory']) if pod['memory'] else 0} GiB Memory"
                })
            else:
                workload["cpu"] = int(workload["cpu"]) if workload["cpu"] > 1 else workload["cpu"]
                project_url = workload["project_info"]["url"]
                parts = [project_url, "applications"]
                applications_url = posixpath.join(*parts)
                workload_url = applications_url if workload["workload_type"] == "application" else workload["workload_url"]
                
                unified_workload.update({
                    "workload_type": workload["workload_type"],
                    "user": workload["creator"],
                    "project": workload["project_name"],
                    "name": workload["name"],
                    "workload_url": workload_url,
                    "cpu": workload["cpu"],
                    "ram": int(workload['memory']) if workload.get('memory') else 0,
                    "Resource Profile": f"{workload['cpu']} vCPU / {int(workload['memory']) if workload.get('memory') else 0} GiB Memory"
                })

            if self.LDAP_ENABLED:
                display_name = get_user_full_name(unified_workload["user"])
                display_name, _ = keep_only_arabic(display_name)
                unified_workload["full_name"] = display_name
                unified_workload["show_full_name"] = display_name is not None
            else:
                unified_workload["full_name"] = None
                unified_workload["show_full_name"] = False

            unified_workloads.append(unified_workload)

        return unified_workloads

    def workload_report(self, cutoff_seconds=1, zombies_only=False):
        pods = self.get_running_pods(cutoff_seconds)
        pod_clusters = self.cluster_pods_by_time_window(pods)

        all_cml_usage_data = []
        for (start_str, end_str), pods_in_window in pod_clusters.items():
            cml_data = self.get_running_sessions(start_str, end_str, zombies_only=zombies_only)

            if cml_data:
                all_cml_usage_data.extend(cml_data)

        workloads = self.match_pods_with_cml_workload(pods, all_cml_usage_data)

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
            if workload.get("user"): search_data[SearchFilters.USERNAME.value].add(workload["user"])
            if workload.get("full_name"): search_data[SearchFilters.USER_FULLNAME.value].add(workload["full_name"])
            if workload.get("project"): search_data[SearchFilters.PROJECT.value].add(workload["project"])
            if workload.get("name"): search_data[SearchFilters.SESSION_NAME.value].add(workload["name"])
            if workload.get("namespace"): search_data[SearchFilters.NAMESPACE.value].add(workload["namespace"])
            if workload.get("id"): search_data[SearchFilters.SESSION_ID.value].add(workload["id"])
            if workload.get("status"): search_data[SearchFilters.STATUS.value].add(workload["status"])
            if workload.get("age"): search_data[SearchFilters.AGE.value].add(workload["age"])
            if workload.get("Resource Profile"): search_data[SearchFilters.RESOURCES.value].add(workload["Resource Profile"])

        search_data = {k: list(v) for k, v in search_data.items()}
        return workloads, search_data

if __name__ == "__main__":
    cmlapi_manager = CMLAPIManager()
    workloads, _ = cmlapi_manager.workload_report()

    df = pd.DataFrame(workloads)
    df["start_time"] = pd.to_datetime(df["start_time"])
    df["creation_time"] = pd.to_datetime(df["creation_time"])
    df["start_time"] = df["start_time"].dt.tz_convert("Asia/Riyadh").dt.tz_localize(None)
    df["creation_time"] = df["creation_time"].dt.tz_convert("Asia/Riyadh").dt.tz_localize(None)
    df.to_excel("pods_workloads.xlsx", index=False)
