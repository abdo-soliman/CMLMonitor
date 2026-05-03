import logging
import threading
from cmlmonitor import workload_report
from utils import WorkloadType, SearchFilters, OrderByFilters


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class WorkloadManager():
    def __init__(self, periodic_update_interval_sec):
        self.workload = None
        self.search_data = None
        self.interval = periodic_update_interval_sec
        self.thread = None

    def start_caching(self):
        """The main async loop. Runs periodically or when triggered."""
        logging.info("Updating Workload")
        self.workload, self.search_data = workload_report()
        self.group_workload_by_id() # some sub tasks are listed as seperate tasks we group all tasks with the same id
        logging.info("Workload updated")
        self.thread = threading.Timer(self.interval, self.start_caching)
        self.thread.start()

    def stop_caching(self):
        """Gracefully stops the background loop."""
        if self.thread:
            self.thread.cancel()

    def get(self, user, filter=None, search_filter=None, search_value=None, order_by=None, desc=None):
        workloads = self.workload

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
        # order by

        filters = {
            "filter": to_be_filter,
            "search_filter": to_be_search_filter,
            "search_value": to_be_search_value,
            "order_by_filter": to_be_order_by,
            "desc": to_be_desc
        }

        return workloads, counts, filters

    def get_search_data(self):
        return self.search_data

    def refresh(self):
        if self.thread:
            self.thread.cancel()

        self.workload, self.search_data = workload_report()
        self.group_workload_by_id() # some sub tasks are listed as seperate tasks we group all tasks with the same id
        self.thread = threading.Timer(self.interval, self.start_caching)
        self.thread.start()

    def group_workload_by_id(self):
        workloads = self.workload
        unique_ids = list({w['id'] for w in workloads})
        grouped_workloads = []
        for id in unique_ids:
            sub_workload = [workload for workload in workloads if workload["id"] == id]
            if len(sub_workload) == 1:
                grouped_workloads.append({**sub_workload[0], "has_sub_workload": False, "sub_workload": []})
                continue

            name = sub_workload[0]["name"]
            workload_type = sub_workload[0]["workload_type"]
            user = sub_workload[0]["user"]
            full_name = sub_workload[0]["full_name"]
            show_full_name = sub_workload[0]["show_full_name"]
            project = sub_workload[0]["project"]
            namespace = sub_workload[0]["namespace"]
            status = sub_workload[0]["status"]
            age = sub_workload[0]["age"]
            age_seconds = sub_workload[0]["age_seconds"]
            cpu = 0
            ram = 0
            items = []
            for workload in sub_workload:
                if not workload["name"].endswith("_spark executor"):
                    name = workload["name"]
                    workload_type = workload["workload_type"]
                    user = workload["user"]
                    full_name = workload["full_name"]
                    show_full_name = workload["show_full_name"]
                    project = workload["project"]
                    namespace = workload["namespace"]
                    status = workload["status"]
                    age = workload["age"]
                    age_seconds = workload["age_seconds"]

                items.append(workload)
                cpu = cpu + workload["cpu"]
                ram = ram + workload["ram"]

            grouped_workloads.append({
                "workload_type": workload_type,
                "user": user,
                "full_name": full_name,
                "show_full_name": show_full_name,
                "project": project,
                "name": name,
                "namespace": namespace,
                "id": id,
                "status": status,
                "age": age,
                "age_seconds": age_seconds, 
                "cpu": cpu,
                "ram": ram,
                "Resource Profile": f"{cpu} vCPU / {ram} GiB Memory",
                "has_sub_workload": True,
                "sub_workload": items
            })

        self.workload = grouped_workloads

    def expand_sub_workloads(self):
        workloads = self.workload

        expanded_workloads = []
        for workload in workloads:
            sub_workload = workload["sub_workload"]
            workload.pop("has_sub_workload", None)
            workload.pop("sub_workload", None)

            expanded_workloads = expanded_workloads + [workload] + sub_workload

        expanded_workloads = sorted(expanded_workloads, key=lambda x: (-x['age_seconds'], x['id'], -x['ram']))
        return expanded_workloads
