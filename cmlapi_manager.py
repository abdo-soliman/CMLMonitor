import os
import re
import math
import redis
import cmlapi
import urllib3
import logging
import posixpath
import concurrent.futures
from urllib.parse import quote
from collections import defaultdict
from kubernetes import client, config
from kubernetes.utils import parse_quantity
from kubernetes.client.rest import ApiException
from datetime import datetime, timezone, timedelta

from extensions import db, app
from ldap_utils import get_user_full_name
from models import Runtime, Config, User, Job
from utils import SearchFilters, WorkloadStatus, seconds_to_age, age_dict_tostring, keep_only_arabic, parse_quantity, sqlite_fix_timezone

class CMLAPIManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def  __init__(self):
        if self._initialized:
            return
            
        valkey_host = os.getenv("VALKEY_HOST", "localhost")
        valkey_port = int(os.getenv("VALKEY_PORT", 6379))
        self.valkey = redis.Redis(host=valkey_host, port=valkey_port, db=0, decode_responses=True)

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
        self._initialized = True

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
                    engine_container = next((c for c in (pod.spec.containers or []) if c.name == "engine"), None)
                    username, project_id, engine_image = None, None, None
                    cpu, ram = 0, 0
                    
                    if engine_container:
                        username = next((c.value for c in (engine_container.env or []) if c.name == "HADOOP_USER_NAME"), None)
                        project_id = next((c.value for c in (engine_container.env or []) if c.name == "CDSW_PROJECT_ID"), None)
                        cpu, ram = self.get_engine_cpu_and_ram(engine_container)
                        engine_image = engine_container.image

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

    def get_running_sessions(self, start, end):
        sort = 'created_at'
        page_size = 100000
        time_range_search_filter = "{\"created_time\":{\"min\":\"" + start + "\",\"max\":\"" + end + "\"}}"
        try:
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
            cml_data = self.get_running_sessions(start_str, end_str)

            if cml_data:
                all_cml_usage_data.extend(cml_data)

        workloads = self.match_pods_with_cml_workload(pods, all_cml_usage_data)
        if zombies_only:
            workloads = [workload for workload in workloads if workload["workload_type"] == "session" or workload["workload_type"] == "orphan"]

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

    def sync_runtimes(self):
        """Fetches runtimes from CML API and updates the local database in a tight transaction."""
        # Use Valkey as a distributed lock with a 60-second expiration
        if not self.valkey.set("runtimes_sync_lock", "locked", nx=True, ex=60):
            return False

        logging.info("Starting runtimes sync from CML API...")
        try:
            response = self.cml_client.list_runtimes(page_size=1000)
            data = response.to_dict().get("runtimes", [])
            
            users_map = {0: "system"}
            for rt_data in data:
                user_id = rt_data.get("register_user_id")
                if user_id and user_id not in users_map:
                    try:
                        u_resp = self.cml_client.get_short_user_by_id(user_id)
                        users_map[user_id] = u_resp.to_dict().get("username", "unknown")
                    except Exception:
                        users_map[user_id] = "unknown"
            
            with app.app_context():
                valid_db_usernames = {u.username for u in User.query.all()}
                existing_runtimes = {r.image: r for r in Runtime.query.all()}
                active_images = set()

                for rt_data in data:
                    image = rt_data.get("image_identifier")
                    active_images.add(image)
                    
                    user_id = rt_data.get("register_user_id")
                    cml_username = users_map.get(user_id, "unknown")
                    added_by = cml_username if cml_username in valid_db_usernames else None
                    
                    editor_name = rt_data.get("editor")
                    editor_version = rt_data.get("edition")
                    status = str(rt_data.get("status", "ENABLED")).upper()
                    if status not in ["ENABLED", "DISABLED"]:
                        status = "ENABLED"
                    
                    db_runtime = existing_runtimes.get(image)
                    if db_runtime:
                        db_runtime.editor_name = editor_name
                        db_runtime.editor_version = editor_version
                        db_runtime.status = status
                        db_runtime.added_by = added_by
                    else:
                        new_runtime = Runtime(
                            image=image,
                            editor_name=editor_name,
                            editor_version=editor_version,
                            status=status,
                            added_by=added_by
                        )
                        db.session.add(new_runtime)

                for image, db_runtime in existing_runtimes.items():
                    if image not in active_images:
                        db.session.delete(db_runtime)
                        
                db.session.commit()
            logging.info("Successfully synced runtimes from CML API.")
            return True
        except Exception as e:
            logging.error(f"Failed to sync runtimes: {e}")
            return False
        finally:
            self.valkey.delete("runtimes_sync_lock")

    def _process_project_jobs(self, project):
        """Worker function for threading. Fetches all jobs and runs for a single project."""
        project_id = project["id"]
        project_username = project["owner"]["username"].lower().replace(' ', '')
        project_clean_name = self.clean_projectname(project["name"])

        parts = [self.WORKSPACE_DOMAIN, project_username, project_clean_name]
        if project_clean_name == "404":
            parts = [self.WORKSPACE_DOMAIN, "404"]
        project_url = posixpath.join(*parts)

        local_jobs_payload = []
        local_db_updates = []

        try:
            jobs_response = self.cml_client.list_jobs(project_id, page_size=1000)
            cml_jobs = jobs_response.to_dict().get("jobs", [])
        except Exception:
            return local_jobs_payload, local_db_updates

        for cml_job in cml_jobs:
            job_id = cml_job["id"]
            job_type = cml_job.get("type", "manual")

            last_run_starting_time = None
            last_run_finished_time = None
            last_run_status = "Unknown"

            try:
                runs_response = self.cml_client.list_job_runs(project_id, job_id, sort="-created_at", page_size=1)
                runs = runs_response.to_dict().get("job_runs", [])
                if runs:
                    last_run = runs[0]
                    last_run_starting_time = last_run.get("starting_at")
                    last_run_finished_time = last_run.get("finished_at")

                    raw_status = last_run.get("status", "Unknown")
                    if isinstance(raw_status, str):
                        status_parts = raw_status.split("_")
                        last_run_status = status_parts[1].capitalize() if len(status_parts) == 2 else raw_status.capitalize()
            except Exception:
                pass

            parent_job_id = cml_job.get("parent_id") if job_type == "dependent" else None
            cron_schedule = cml_job.get("schedule", "") if job_type == "cron" else ""

            editor_name, editor_version = self.get_image_editor(cml_job.get("runtime_identifier"))
            cpu = float(cml_job.get("cpu", 0.0))
            ram = float(cml_job.get("memory", 0.0))

            job_tz_str = cml_job.get("timezone") or "UTC"
            created_at = sqlite_fix_timezone(cml_job.get("created_at"), job_tz_str)
            updated_at = sqlite_fix_timezone(cml_job.get("updated_at"), job_tz_str)

            creator_user = cml_job.get("creator", {}).get("username", "")
            fullname = get_user_full_name(creator_user) if self.LDAP_ENABLED else creator_user
            fullname, _ = keep_only_arabic(fullname) if self.LDAP_ENABLED else (fullname, False)

            local_jobs_payload.append({
                "id": job_id,
                "name": cml_job["name"],
                "username": creator_user,
                "fullname": fullname,
                "project_name": project["name"],
                "project_url": project_url,
                "editor_name": editor_name,
                "editor_version": editor_version,
                "script": cml_job.get("script", ""),
                "job_type": job_type,
                "schedule": cron_schedule,
                "parent_job_id": parent_job_id,
                "paused": bool(cml_job.get("paused", False)),
                "cpu": cpu,
                "ram": ram,
                "last_run_starting_time": last_run_starting_time,
                "last_run_finished_time": last_run_finished_time,
                "last_run_status": last_run_status
            })

            local_db_updates.append({
                "id": job_id,
                "project_id": project_id,
                "username": creator_user,
                "name": cml_job["name"],
                "type": job_type,
                "parent_job_id": parent_job_id,
                "paused": bool(cml_job.get("paused", False)),
                "script": cml_job.get("script", ""),
                "schedule": cron_schedule,
                "runtime_id": cml_job.get("runtime_identifier"),
                "cpu": cpu,
                "ram": ram,
                "created_at": created_at,
                "updated_at": updated_at
            })

        return local_jobs_payload, local_db_updates

    def sync_jobs(self):
        """FULL SYNC: Fetches projects, jobs, and runs. Updates DB and Valkey."""
        if not self.cml_client:
            return False, [], "CML Client not initialized."

        # Distributed Redis lock prevents UI timeouts if already syncing (Auto-expires in 5 mins)
        if not self.valkey.set("cml_jobs_sync_lock", "locked", nx=True, ex=300):
            return False, [], "A job sync is already in progress. Please wait."

        try:
            logging.info("Starting threaded FULL jobs sync from CML API...")
            projects_response = self.cml_client.list_projects(page_size=1000, include_all_projects=True)
            projects = projects_response.to_dict().get("projects", [])

            jobs_payload = []
            db_updates = []

            # 10 threads to rapidly query the jobs for each project
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(self._process_project_jobs, p) for p in projects]
                for future in concurrent.futures.as_completed(futures):
                    p_payload, p_db_updates = future.result()
                    jobs_payload.extend(p_payload)
                    db_updates.extend(p_db_updates)

            # Post-process parent job names for the UI schedule column
            for job in jobs_payload:
                if job["parent_job_id"]:
                    parent_name = next((j["name"] for j in jobs_payload if j["id"] == job["parent_job_id"]), job["parent_job_id"])
                    job["schedule"] = parent_name

            with app.app_context():
                existing_jobs = {j.id: j for j in Job.query.all()}
                active_job_ids = set()

                for data in db_updates:
                    job_id = data["id"]
                    active_job_ids.add(job_id)

                    db_job = existing_jobs.get(job_id)
                    if db_job:
                        db_job.name = data["name"]
                        db_job.type = data["type"]
                        db_job.parent_job_id = data["parent_job_id"]
                        db_job.paused = data["paused"]
                        db_job.script = data["script"]
                        db_job.schedule = data["schedule"]
                        db_job.runtime_id = data["runtime_id"]
                        db_job.cpu = data["cpu"]
                        db_job.ram = data["ram"]
                        db_job.updated_at = data["updated_at"]
                    else:
                        new_job = Job(**data)
                        db.session.add(new_job)

                for job_id, db_job in existing_jobs.items():
                    if job_id not in active_job_ids:
                        db.session.delete(db_job)

                db.session.commit()
            return True, jobs_payload, "Jobs fully synced."
        except Exception as e:
            logging.error(f"Failed to run FULL sync jobs: {e}")
            return False, [], f"Sync failed: {e}"
        finally:
            self.valkey.delete("cml_jobs_sync_lock")

    def _fetch_single_job_run(self, job_id, project_id):
        """Worker function for lightweight sync."""
        try:
            runs_response = self.cml_client.list_job_runs(project_id, job_id, sort="-created_at", page_size=1)
            runs = runs_response.to_dict().get("job_runs", [])
            if runs:
                last_run = runs[0]

                raw_status = last_run.get("status", "Unknown")
                status = str(raw_status).capitalize()
                if isinstance(raw_status, str) and len(raw_status.split("_")) == 2:
                    status = raw_status.split("_")[1].capitalize()

                return job_id, {
                    "starting_at": last_run.get("starting_at"),
                    "finished_at": last_run.get("finished_at"),
                    "status": status
                }
        except:
            pass
        return job_id, None

    def sync_jobs_lightweight(self):
        """LIGHTWEIGHT SYNC: Rapidly updates runs for known jobs."""
        if not self.cml_client:
            return False, {}, "CML Client not initialized."

        # Share the exact same Redis lock with the heavy sync
        if not self.valkey.set("cml_jobs_sync_lock", "locked", nx=True, ex=300):
            return False, {}, "A job sync is already in progress. Please wait."

        try:
            logging.info("Starting threaded LIGHTWEIGHT jobs sync...")
            with app.app_context():
                # Query all known jobs from DB
                jobs = Job.query.all()
                tasks = [(j.id, j.project_id) for j in jobs]

            updates = {}

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(self._fetch_single_job_run, jid, pid) for jid, pid in tasks]
                for future in concurrent.futures.as_completed(futures):
                    jid, run_data = future.result()
                    if run_data:
                        updates[jid] = run_data

            return True, updates, "Lightweight sync complete."
        except Exception as e:
            logging.error(f"Failed to run LIGHTWEIGHT sync jobs: {e}")
            return False, {}, f"Sync failed: {e}"
        finally:
            self.valkey.delete("cml_jobs_sync_lock")

    def get_worker_node_utilization(self):
        try:
            config.load_kube_config(config_file=self.KUBECONFIG_PATH)
            nodes = self.v1.list_node().items
            node_data = {}

            for node in nodes:
                labels = node.metadata.labels or {}
                is_master = any(
                    key in labels 
                    for key in ["node-role.kubernetes.io/master", "node-role.kubernetes.io/control-plane", "node-role.kubernetes.io/etcd"]
                )
                if is_master:
                    continue

                name = node.metadata.name
                cpu_cap = parse_quantity(node.status.capacity.get("cpu", 0))
                mem_cap = parse_quantity(node.status.capacity.get("memory", 0))

                node_data[name] = {
                    "cpu_cap": cpu_cap,
                    "mem_cap": mem_cap,
                    "cpu_req": 0.0,
                    "mem_req": 0.0
                }

            pods = self.v1.list_pod_for_all_namespaces().items
            for pod in pods:
                node_name = pod.spec.node_name
                if not node_name or node_name not in node_data:
                    continue
                if pod.status.phase in ["Succeeded", "Failed"]:
                    continue

                for container in pod.spec.containers:
                    requests = container.resources.requests or {}
                    if "cpu" in requests:
                        node_data[node_name]["cpu_req"] += parse_quantity(requests["cpu"])
                    if "memory" in requests:
                        node_data[node_name]["mem_req"] += parse_quantity(requests["memory"])

            result = []
            for node_name, data in node_data.items():
                cpu_req = data["cpu_req"]
                cpu_cap = data["cpu_cap"]
                cpu_pct = (cpu_req / cpu_cap * 100) if cpu_cap > 0 else 0.0

                mem_req_gi = data["mem_req"] / (1024 ** 3)
                mem_cap_gi = data["mem_cap"] / (1024 ** 3)
                mem_pct = (mem_req_gi / mem_cap_gi * 100) if mem_cap_gi > 0 else 0.0

                def resolve_color(pct):
                    if pct < 75.0:
                        return "#007bff"
                    elif pct <= 90.0:
                        return "#ffc107"
                    else:
                        return "#dc3545"

                result.append({
                    "node_name": node_name,
                    "cpu": {
                        "req": round(cpu_req, 2),
                        "cap": round(cpu_cap, 2),
                        "pct": round(cpu_pct, 2),
                        "formatted": f"{cpu_req:.2f}/{cpu_cap:.2f}",
                        "color": resolve_color(cpu_pct)
                    },
                    "ram": {
                        "req_gi": round(mem_req_gi, 2),
                        "cap_gi": round(mem_cap_gi, 2),
                        "pct": round(mem_pct, 2),
                        "formatted": f"{mem_req_gi:.2f}/{mem_cap_gi:.2f}",
                        "color": resolve_color(mem_pct)
                    }
                })

            return sorted(result, key=lambda x: x["node_name"])
        except Exception as e:
            logging.error(f"Error calculating node utilization: {e}")
            return []
