import os
import time
import json
import redis
import logging
from datetime import datetime, timezone
from cmlapi_manager import CMLAPIManager
from utils import WorkloadType, SearchFilters, OrderByFilters, WorkloadStatus

# --- Custom JSON Encoder and Decoder for Datetime ---
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def datetime_decoder(dct):
    """Intercepts dictionaries during JSON loading to parse datetime strings."""
    for key in ["start_time", "creation_time", "last_run_starting_time", "last_run_finished_time"]:
        if key in dct and dct[key] is not None:
            try:
                dct[key] = datetime.fromisoformat(dct[key])
            except (ValueError, TypeError):
                pass
    return dct

class WorkloadManager():
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.cmlapi_manager = CMLAPIManager()
        self.cmlapi_manager.initialize()
        valkey_host = os.getenv("VALKEY_HOST", "localhost")
        valkey_port = int(os.getenv("VALKEY_PORT", 6379))
        self.valkey = redis.Redis(host=valkey_host, port=valkey_port, db=0, decode_responses=True)
        self._initialized = True

    def fetch_and_cache(self):
        """Fetches data from CML API, processes it, and caches it in Valkey."""
        if not self.valkey.set("cml_workload_sync_lock", "locked", nx=True, ex=300):
            return False, "A workload sync is already in progress."

        try:
            self.valkey.set("cml_workload_sync_status", "running")
            logging.info("Fetching workload data from CML API...")
            
            raw_workloads, search_data = self.cmlapi_manager.workload_report()
            grouped_workloads = self.group_workload_by_id(raw_workloads)

            self.valkey.set("cml_workloads", json.dumps(grouped_workloads, cls=DateTimeEncoder))
            self.valkey.set("cml_search_data", json.dumps(search_data, cls=DateTimeEncoder))
            
            logging.info("Successfully updated Valkey cache.")
            self.valkey.set("cml_workload_sync_status", "success")
            return True, "Workload cache updated."
        except Exception as e:
            logging.error(f"Error fetching/caching data: {e}")
            self.valkey.set("cml_workload_sync_status", "failed")
            return False, str(e)
        finally:
            self.valkey.delete("cml_workload_sync_lock")

    def get(self, user, filter=None, search_filters=None, order_by=None, desc=None):
        cached_data = self.valkey.get("cml_workloads")
        workloads = json.loads(cached_data, object_hook=datetime_decoder) if cached_data else []

        if not user.is_admin:
            workloads = [workload for workload in workloads if workload["user"] == user.username]

        if search_filters:
            for sf in search_filters:
                param = sf.get("param")
                val = sf.get("value", "").lower()
                if not val:
                    continue
                
                if param == SearchFilters.USERNAME.value:
                    workloads = [w for w in workloads if w.get("user") and val in str(w["user"]).lower()]
                elif param == SearchFilters.SESSION_ID.value:
                    workloads = [w for w in workloads if w.get("id") and val in str(w["id"]).lower()]
                elif param == SearchFilters.USER_FULLNAME.value:
                    workloads = [w for w in workloads if w.get("full_name") and val in str(w["full_name"]).lower()]
                elif param == SearchFilters.PROJECT.value:
                    workloads = [w for w in workloads if w.get("project") and val in str(w["project"]).lower()]
                elif param == SearchFilters.SESSION_NAME.value:
                    workloads = [w for w in workloads if w.get("name") and val in str(w["name"]).lower()]
                elif param == SearchFilters.NAMESPACE.value:
                    workloads = [w for w in workloads if w.get("namespace") and val in str(w["namespace"]).lower()]
                elif param == SearchFilters.STATUS.value:
                    workloads = [w for w in workloads if w.get("status") and val in str(w["status"]).lower()]
                elif param == SearchFilters.AGE.value:
                    workloads = [w for w in workloads if w.get("age") and val in str(w["age"]).lower()]
                elif param == SearchFilters.RESOURCES.value:
                    workloads = [w for w in workloads if w.get("Resource Profile") and val in str(w["Resource Profile"]).lower()]

        counts = {item.value: 0 for item in WorkloadType if item != WorkloadType.ALL}
        for workload in workloads:
            workload_type = workload["workload_type"]
            if workload_type in counts:
                counts[workload_type] += 1

        counts[WorkloadType.ALL.value] = len(workloads)

        to_be_filter = WorkloadType.ALL
        if filter is not None and filter.value in WorkloadType._value2member_map_:
            to_be_filter = filter

        if to_be_filter != WorkloadType.ALL:
            workloads = [workload for workload in workloads if workload["workload_type"] == to_be_filter.value]

        to_be_order_by = OrderByFilters.ALL
        if order_by is not None:
            to_be_order_by = order_by.lower()

        to_be_desc = False
        if desc is not None:
            to_be_desc = desc

        if to_be_order_by == OrderByFilters.AGE:
            workloads = sorted(workloads, key=lambda x: x['age_seconds'], reverse=to_be_desc)
        elif to_be_order_by == OrderByFilters.RESOURCES:
            if to_be_desc:
                workloads = sorted(workloads, key=lambda x: (-x['ram'], -x['cpu']))
            else:
                workloads = sorted(workloads, key=lambda x: (x['ram'], x['cpu']))

        filters = {
            "filter": to_be_filter,
            "order_by_filter": to_be_order_by,
            "desc": to_be_desc
        }

        return workloads, counts, filters

    def get_search_data(self):
        cached_data = self.valkey.get("cml_search_data")
        return json.loads(cached_data) if cached_data else {}

    def refresh(self):
        self.fetch_and_cache()

    def cache_jobs(self):
        try:
            self.valkey.set("cml_heavy_sync_status", "running")
            success, jobs_payload, msg = False, [], ""

            for _ in range(10):
                success, jobs_payload, msg = self.cmlapi_manager.sync_jobs()
                if success or "already in progress" not in msg:
                    break
                time.sleep(3)

            if success:
                self.valkey.set("cml_jobs", json.dumps(jobs_payload, cls=DateTimeEncoder))
                logging.info(msg)
                self.valkey.set("cml_heavy_sync_status", "success")
            else:
                self.valkey.set("cml_heavy_sync_status", "failed")

            return success, msg
        except Exception as e:
            logging.error(f"Error executing Full Jobs cache: {e}")
            self.valkey.set("cml_heavy_sync_status", "failed")
            return False, str(e)

    def cache_jobs_lightweight(self):
        """Lightweight sync: Modifies the existing payload cache."""
        try:
            cached_data = self.valkey.get("cml_jobs")
            if not cached_data:
                return self.cache_jobs()

            success, updates, msg = self.cmlapi_manager.sync_jobs_lightweight()
            
            if success:
                jobs_payload = json.loads(cached_data, object_hook=datetime_decoder)
                for job in jobs_payload:
                    if job["id"] in updates:
                        run_data = updates[job["id"]]
                        job["last_run_starting_time"] = run_data["starting_at"]
                        job["last_run_finished_time"] = run_data["finished_at"]
                        job["last_run_status"] = run_data["status"]

                self.valkey.set("cml_jobs", json.dumps(jobs_payload, cls=DateTimeEncoder))
                logging.info(msg)
            return success, msg
        except Exception as e:
            logging.error(f"Error executing Lightweight Jobs cache: {e}")
            return False, str(e)

    def get_jobs(self, user, search_filters):
        cached_data = self.valkey.get("cml_jobs")
        jobs = json.loads(cached_data, object_hook=datetime_decoder) if cached_data else []

        if not user.is_admin:
            jobs = [job for job in jobs if job["username"] == user.username]

        jobs_search_data = {
            "name": list(set(str(j.get("name", "")) for j in jobs if j.get("name"))),
            "username": list(set(str(j.get("username", "")) for j in jobs if j.get("username"))),
            "project": list(set(str(j.get("project_name", "")) for j in jobs if j.get("project_name"))),
            "script": list(set(str(j.get("script", "")) for j in jobs if j.get("script"))),
            "job_type": list(set(str(j.get("job_type", "")) for j in jobs if j.get("job_type"))),
            "status": list(set(str(j.get("last_run_status", "")) for j in jobs if j.get("last_run_status")))
        }

        for sf in search_filters:
            param = sf.get("param")
            val = sf.get("value", "").lower()
            if not val:
                continue

            if param == "name":
                jobs = [j for j in jobs if j.get("name") and val in str(j["name"]).lower()]
            elif param == "username":
                jobs = [j for j in jobs if j.get("username") and val in str(j["username"]).lower()]
            elif param == "project":
                jobs = [j for j in jobs if j.get("project_name") and val in str(j["project_name"]).lower()]
            elif param == "script":
                jobs = [j for j in jobs if j.get("script") and val in str(j["script"]).lower()]
            elif param == "job_type":
                jobs = [j for j in jobs if j.get("job_type") and val in str(j["job_type"]).lower()]
            elif param == "status":
                jobs = [j for j in jobs if j.get("last_run_status") and val in str(j["last_run_status"]).lower()]

        jobs = sorted(jobs, key=lambda x: str(x.get("last_run_starting_time") or ""), reverse=True)

        return jobs, jobs_search_data

    def group_workload_by_id(self, workloads):
        cached_jobs_str = self.valkey.get("cml_jobs")
        jobs_dict = {}
        if cached_jobs_str:
            try:
                parsed_jobs = json.loads(cached_jobs_str, object_hook=datetime_decoder)
                jobs_dict = {",".join([job["project_name"], job["name"]]): job for job in parsed_jobs}
            except Exception:
                pass

        for workload in workloads:
            if workload["parent"]:
                continue
            if workload["role"] == "spark-executor":
                workload["parent"] = workload["id"].split("-")[1]

        unique_ids = list({w['parent'] if w["role"] == "spark-executor" else w['id'] for w in workloads})
        grouped_workloads = []
        for id in unique_ids:
            sub_workload = [workload for workload in workloads if workload["id"] == id or workload["parent"] == id]
            if len(sub_workload) == 1:
                grouped_workloads.append({**sub_workload[0], "has_sub_workload": False, "sub_workload": []})
                continue

            cpu = 0
            ram = 0
            items = []
            parent = next((w for w in sub_workload if w["role"] != "spark-executor"), None)
            if parent is not None:
                cpu = parent["cpu"]
                ram = parent["ram"]
                items.append(parent.copy())
                sub_workload.remove(parent)

            has_no_running_sub_workloads = True
            for workload in sub_workload:
                if parent:
                    workload["workload_type"] = parent["workload_type"]

                if workload["status"] == WorkloadStatus.RUNNING:
                    has_no_running_sub_workloads = False

                items.append(workload)
                cpu += workload.get("cpu", 0)
                ram += workload.get("ram", 0)

            parent = sub_workload[0] if parent is None else parent
            cpu = int(cpu) if cpu >= 1 else cpu
            parent["cpu"] = cpu
            parent["ram"] = ram
            parent["Resource Profile"] = f"{cpu} vCPU / {ram} GiB Memory"

            if has_no_running_sub_workloads and parent["status"] == WorkloadStatus.RUNNING:
                parent["status"] = WorkloadStatus.STUCK
                parent["reason"] = "No Running Executors"

            grouped_workloads.append({
                **parent,
                "has_sub_workload": True,
                "sub_workload": items
            })

        for workload in grouped_workloads:
            if workload.get("workload_type") == "job" and workload.get("status") == WorkloadStatus.RUNNING:
                job_id = ",".join([workload["project"], workload["name"]])
                job = jobs_dict.get(job_id)
                if job:
                    if job["job_type"] == "cron":
                        last_run_start_time = job["last_run_starting_time"]
                        if last_run_start_time and getattr(last_run_start_time, 'year', None) == 1:
                            workload["status"] = WorkloadStatus.STUCK
                            workload["reason"] = "Passed New Run Schedule"

                    elif job["job_type"] == "dependent" and job.get("parent_job_id"):
                        parent_job = jobs_dict.get(job["parent_job_id"])
                        if parent_job:
                            finished_at = parent_job.get("last_run_finished_time")
                            parent_status = parent_job.get("last_run_status", "").lower()
                            start_time = workload.get("start_time")

                            if finished_at and start_time and parent_status == "succeeded":
                                try:
                                    if finished_at.tzinfo is None:
                                        finished_at = finished_at.replace(tzinfo=timezone.utc)
                                    if start_time.tzinfo is None:
                                        start_time = start_time.replace(tzinfo=timezone.utc)

                                    if finished_at > start_time:
                                        workload["status"] = WorkloadStatus.STUCK
                                        workload["reason"] = "Parent Job has a more recent run"
                                except Exception as e:
                                    logging.error(f"Failed to compare finished_at for parent job {parent_job['id']}: {e}")

        return grouped_workloads

    def expand_sub_workloads(self):
        cached_data = self.valkey.get("cml_workloads")
        workloads = json.loads(cached_data, object_hook=datetime_decoder) if cached_data else []

        expanded_workloads = []
        for workload in workloads:
            sub_workload = workload.get("sub_workload", [])
            workload.pop("has_sub_workload", None)
            workload.pop("sub_workload", None)

            expanded_workloads = expanded_workloads + [workload] + sub_workload

        expanded_workloads = sorted(expanded_workloads, key=lambda x: (-x['age_seconds'], x['id'], -x['ram']))
        return expanded_workloads

    def cache_node_utilization(self):
        """Queries worker node metrics and saves them into Valkey."""
        try:
            node_stats = self.cmlapi_manager.get_worker_node_utilization()
            self.valkey.set("cml_node_utilization", json.dumps(node_stats))
        except Exception as e:
            logging.error(f"Error caching node utilization: {e}")

    def get_node_utilization(self):
        """Reads worker node metrics from Valkey."""
        cached_data = self.valkey.get("cml_node_utilization")
        return json.loads(cached_data) if cached_data else []
    