import subprocess
from typing import Dict, Any, List

class OSCollector:
    @staticmethod
    def get_failed_services() -> List[str]:
        try:
            out = subprocess.check_output(
                ["systemctl", "--failed", "--no-legend", "--no-pager"],
                timeout=3
            ).decode("utf-8").strip()
            services = []
            for line in out.splitlines():
                parts = line.split()
                if parts and len(parts) >= 1:
                    # First column is the unit name
                    unit = parts[0]
                    if unit.endswith('.service') or unit.endswith('.socket') or unit.endswith('.timer'):
                        services.append(unit)
            return services
        except Exception:
            return []

    @staticmethod
    def get_recent_kernel_errors(lines: int = 20, window_minutes: int = 10) -> List[str]:
        try:
            cmd = ["journalctl", "-k", "-p", "err", "-b", "--no-pager", "-n", str(lines)]
            if window_minutes > 0:
                cmd.extend(["--since", f"-{window_minutes}m"])
            out = subprocess.check_output(cmd, timeout=3).decode("utf-8").strip()
            if not out or out == "-- No entries --":
                return []
            return [line for line in out.splitlines() if line.strip() and not line.startswith("--")]
        except Exception:
            return []

    @staticmethod
    def get_recent_kernel_warnings(lines: int = 20) -> List[str]:
        try:
            out = subprocess.check_output(
                ["journalctl", "-p", "warning", "-b", "--no-pager", "-n", str(lines)],
                timeout=3
            ).decode("utf-8").strip()
            return out.splitlines()
        except Exception:
            return []

    @staticmethod
    def get_boot_time() -> float:
        try:
            import time
            with open("/proc/uptime", "r") as f:
                uptime = float(f.read().split()[0])
            return time.time() - uptime
        except Exception:
            return 0.0

    @staticmethod
    def get_last_reboots(limit: int = 5) -> List[str]:
        try:
            out = subprocess.check_output(
                ["last", "-x", "reboot", "--time-format", "iso", "-n", str(limit)],
                timeout=3
            ).decode("utf-8").strip()
            return out.splitlines()
        except Exception:
            return []

    @staticmethod
    def get_crashed_processes(limit: int = 20) -> List[str]:
        try:
            out = subprocess.check_output(
                ["coredumpctl", "list", "--no-pager", "-n", str(limit)],
                timeout=3
            ).decode("utf-8").strip()
            return out.splitlines()
        except Exception:
            return []