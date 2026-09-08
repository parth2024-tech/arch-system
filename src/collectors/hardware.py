import psutil
import subprocess
import shutil
import json
import os
from typing import Dict, Any

class HardwareCollector:
    @staticmethod
    def collect_cpu() -> Dict[str, Any]:
        freq = psutil.cpu_freq()
        return {
            "overall_utilization": psutil.cpu_percent(interval=0.1),
            "per_core": psutil.cpu_percent(interval=0.1, percpu=True),
            "load_avg": [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()],
            "freq_current": freq.current if freq else 0.0,
            "freq_min": freq.min if freq else 0.0,
            "freq_max": freq.max if freq else 0.0,
        }

    @staticmethod
    def collect_ram() -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "total": mem.total,
            "used": mem.used,
            "available": mem.available,
            "percent": mem.percent,
            "cached": getattr(mem, 'cached', 0),
            "buffers": getattr(mem, 'buffers', 0),
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
        }

    @staticmethod
    def collect_gpu() -> Dict[str, Any]:
        res = {"present": False}
        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.total,memory.used,power.draw,clocks.current.sm", "--format=csv,noheader,nounits"],
                    timeout=2
                ).decode("utf-8").strip()
                parts = [p.strip() for p in out.split(",")]
                if len(parts) >= 7:
                    res = {
                        "present": True,
                        "name": parts[0],
                        "temperature": float(parts[1]) if parts[1] != 'N/A' else 0.0,
                        "utilization": float(parts[2]) if parts[2] != 'N/A' else 0.0,
                        "vram_total": float(parts[3]) * 1024 * 1024,
                        "vram_used": float(parts[4]) * 1024 * 1024,
                        "power_draw": float(parts[5]) if parts[5] != 'N/A' else 0.0,
                        "sm_clock": float(parts[6]) if parts[6] != 'N/A' else 0.0,
                    }
            except Exception:
                pass
        return res

    @staticmethod
    def collect_storage() -> Dict[str, Any]:
        disks = {}
        for part in psutil.disk_partitions(all=False):
            # Skip snap mounts (read-only, always 100% full)
            if '/var/lib/snapd/snap/' in part.mountpoint:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks[part.mountpoint] = {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent
                }
            except PermissionError:
                continue
        return disks

    @staticmethod
    def collect_battery() -> Dict[str, Any]:
        if hasattr(psutil, "sensors_battery"):
            bat = psutil.sensors_battery()
            if bat:
                return {
                    "present": True,
                    "percent": bat.percent,
                    "secsleft": bat.secsleft,
                    "power_plugged": bat.power_plugged
                }
        return {"present": False}

    @staticmethod
    def collect_temperatures() -> Dict[str, Any]:
        temps = {}
        if hasattr(psutil, "sensors_temperatures"):
            try:
                data = psutil.sensors_temperatures()
                for name, entries in data.items():
                    for entry in entries:
                        key = f"{name}_{entry.label}" if entry.label else name
                        temps[key] = entry.current
            except Exception:
                pass
        return temps

    @staticmethod
    def collect_fans() -> Dict[str, Any]:
        fans = {}
        if hasattr(psutil, "sensors_fans"):
            try:
                data = psutil.sensors_fans()
                for name, entries in data.items():
                    for entry in entries:
                        key = f"{name}_{entry.label}" if entry.label else name
                        fans[key] = entry.current
            except Exception:
                pass
        return fans

    @staticmethod
    def collect_nvme_health() -> Dict[str, Any]:
        res = {}
        if shutil.which("nvme"):
            try:
                out = subprocess.check_output(
                    ["nvme", "smart-log", "/dev/nvme0n1", "-o", "json"],
                    timeout=3,
                    stderr=subprocess.DEVNULL
                ).decode("utf-8")
                import json
                data = json.loads(out)
                res = {
                    "temperature": data.get("temperature", 0),
                    "percentage_used": data.get("percentage_used", 0),
                    "data_units_read": data.get("data_units_read", 0),
                    "data_units_written": data.get("data_units_written", 0),
                    "critical_warning": data.get("critical_warning", 0),
                    "media_errors": data.get("media_errors", 0),
                    "power_on_hours": data.get("power_on_hours", 0),
                    "power_cycles": data.get("power_cycles", 0),
                    "unsafe_shutdowns": data.get("unsafe_shutdowns", 0),
                }
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                # Permission denied - nvme smart-log needs root, or timeout
                pass
            except Exception:
                pass
        
        # Fallback: try to get NVMe temperature from sensors
        if not res.get("temperature"):
            try:
                if hasattr(psutil, "sensors_temperatures"):
                    data = psutil.sensors_temperatures()
                    for name, entries in data.items():
                        if "nvme" in name.lower():
                            for entry in entries:
                                if "composite" in entry.label.lower() or not entry.label:
                                    res["temperature"] = entry.current
                                    break
            except Exception:
                pass
        
        return res