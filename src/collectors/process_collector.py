import psutil
from typing import List, Dict, Any

class ProcessCollector:
    @staticmethod
    def get_top_processes(limit: int = 5) -> List[Dict[str, Any]]:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'memory_info']):
            try:
                info = p.info
                info['cpu_percent'] = info.get('cpu_percent') or 0.0
                info['memory_percent'] = info.get('memory_percent') or 0.0
                if info['status'] == psutil.STATUS_ZOMBIE:
                    info["issue"] = "zombie"
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        procs.sort(key=lambda x: x.get('cpu_percent', 0.0), reverse=True)
        return procs[:limit]

    @staticmethod
    def get_memory_hogs(limit: int = 5) -> List[Dict[str, Any]]:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'memory_info']):
            try:
                info = p.info
                info['memory_percent'] = info.get('memory_percent') or 0.0
                mem_info = info.get('memory_info')
                info['memory_rss'] = mem_info.rss if mem_info else 0
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        procs.sort(key=lambda x: x.get('memory_rss', 0), reverse=True)
        return procs[:limit]

    @staticmethod
    def get_zombie_processes() -> List[Dict[str, Any]]:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'status', 'ppid']):
            try:
                if p.info.get('status') == psutil.STATUS_ZOMBIE:
                    procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return procs