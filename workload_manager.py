import os
import json
import redis
import logging
from datetime import datetime
from cmlapi_manager import CMLAPIManager
from utils import WorkloadType, SearchFilters, OrderByFilters

# --- Custom JSON Encoder and Decoder for Datetime ---
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def datetime_decoder(dct):
    """Intercepts dictionaries during JSON loading to parse datetime strings."""
    for key in ["start_time", "creation_time"]:
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
        return cls._instance

    def __init__(self):
        self.cmlapi_manager = CMLAPIManager()
        # Initialize Valkey (Redis) Connection
        valkey_host = os.getenv("VALKEY_HOST", "localhost")
        valkey_port = int(os.getenv("VALKEY_PORT", 6379))
        self.valkey = redis.Redis(host=valkey_host, port=valkey_port, db=0, decode_responses=True)

    def fetch_and_cache(self):
        """Fetches data from CML API, processes it, and caches it in Valkey."""
        logging.info("Fetching workload data from CML API...")
        try:
            raw_workloads, search_data = self.cmlapi_manager.workload_report()
            grouped_workloads = self.group_workload_by_id(raw_workloads)

            self.valkey.set("cml_workloads", json.dumps(grouped_workloads, cls=DateTimeEncoder))
            self.valkey.set("cml_search_data", json.dumps(search_data, cls=DateTimeEncoder))
            logging.info("Successfully updated Valkey cache.")
        except Exception as e:
            logging.error(f"Error fetching/caching data: {e}")

    def get(self, user, filter=None, search_filter=None, search_value=None, order_by=None, desc=None):
        # Read the single source of truth from Valkey
        cached_data = self.valkey.get("cml_workloads")
        workloads = json.loads(cached_data, object_hook=datetime_decoder) if cached_data else []

        # filter for user workload if user is not admin
        if not user.is_admin:
            workloads = [workload for workload in workloads if workload["user"] == user.username]

        to_be_search_filter = SearchFilters.ALL
        if search_filter is not None and search_filter.value in SearchFilters._value2member_map_:
            to_be_search_filter = search_filter

        to_be_search_value = ""
        if search_value is not None:
            to_be_search_value = search_value.lower()

        if to_be_search_filter != WorkloadType.ALL and len(to_be_search_value) > 0:
            if to_be_search_filter == SearchFilters.USERNAME:
                workloads = [workload for workload in workloads if to_be_search_value in workload["user"].lower()]
            elif to_be_search_filter == SearchFilters.SESSION_ID:
                workloads = [workload for workload in workloads if to_be_search_value in workload["id"].lower()]
            elif to_be_search_filter == SearchFilters.USER_FULLNAME:
                workloads = [workload for workload in workloads if to_be_search_value in workload["full_name"].lower()]
            elif to_be_search_filter == SearchFilters.PROJECT:
                workloads = [workload for workload in workloads if to_be_search_value in workload["project"].lower()]
            elif to_be_search_filter == SearchFilters.SESSION_NAME:
                workloads = [workload for workload in workloads if to_be_search_value in workload["name"].lower()]
            elif to_be_search_filter == SearchFilters.NAMESPACE:
                workloads = [workload for workload in workloads if to_be_search_value in workload["namespace"].lower()]
            elif to_be_search_filter == SearchFilters.STATUS:
                workloads = [workload for workload in workloads if to_be_search_value in workload["status"].lower()]
            elif to_be_search_filter == SearchFilters.AGE:
                workloads = [workload for workload in workloads if to_be_search_value in workload["age"].lower()]
            elif to_be_search_filter == SearchFilters.RESOURCES:
                workloads = [workload for workload in workloads if to_be_search_value in workload["resources"].lower()]

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

        # order by
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
            "search_filter": to_be_search_filter,
            "search_value": to_be_search_value,
            "order_by_filter": to_be_order_by,
            "desc": to_be_desc
        }

        return workloads, counts, filters

    def get_search_data(self):
        cached_data = self.valkey.get("cml_search_data")
        return json.loads(cached_data) if cached_data else {}

    def refresh(self):
        """Forces an immediate update to Valkey (e.g., UI 'Refresh Data' button)"""
        self.fetch_and_cache()

    def group_workload_by_id(self, workloads):
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
            for workload in sub_workload:
                if parent:
                    workload["workload_type"] = parent["workload_type"]
                items.append(workload)
                cpu += workload.get("cpu", 0)
                ram += workload.get("ram", 0)

            parent = sub_workload[0] if parent is None else parent
            cpu = int(cpu) if cpu >= 1 else cpu
            parent["cpu"] = cpu
            parent["ram"] = ram
            parent["Resource Profile"] = f"{cpu} vCPU / {ram} GiB Memory"
            grouped_workloads.append({
                **parent,
                "has_sub_workload": True,
                "sub_workload": items
            })

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
