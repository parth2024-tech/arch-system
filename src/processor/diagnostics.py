from typing import List, Dict, Any
from datetime import datetime

class DiagnosticEngine:
    def __init__(self, thresholds: Dict[str, Any]):
        self.t = thresholds

    def analyze(self, cpu: dict, ram: dict, gpu: dict, storage: dict, battery: dict, 
                temps: dict, fans: dict, os_data: dict, processes: dict, network: dict, 
                nvme: dict) -> List[Dict[str, Any]]:
        issues = []
        timestamp = datetime.now().isoformat()

        # RAM check
        ram_pct = ram.get("percent", 0)
        if ram_pct > self.t.get("ram_critical_pct", 95):
            issues.append({
                "component": "RAM",
                "severity": "CRITICAL",
                "title": "Severe Memory Pressure",
                "description": f"RAM utilization is at {ram_pct}%. Available memory dangerously low.",
                "evidence": f"Used: {ram['used'] / (1024**3):.2f}GB / Total: {ram['total'] / (1024**3):.2f}GB, Swap: {ram.get('swap_percent', 0)}%",
                "recommendation": "Investigate top memory-consuming processes and close unneeded applications immediately."
            })
        elif ram_pct > self.t.get("ram_warning_pct", 85):
            issues.append({
                "component": "RAM",
                "severity": "HIGH",
                "title": "High RAM Utilization",
                "description": f"RAM utilization is at {ram_pct}%.",
                "evidence": f"Used: {ram['used'] / (1024**3):.2f}GB / Available: {ram['available'] / (1024**3):.2f}GB",
                "recommendation": "Monitor memory growth for potential leaks. Consider closing unused applications."
            })

        # CPU temperature check
        cpu_temp = temps.get("coretemp_Package id 0", 0) or temps.get("coretemp_", 0)
        if cpu_temp > self.t.get("cpu_temp_critical", 95):
            issues.append({
                "component": "CPU",
                "severity": "CRITICAL",
                "title": "CPU Overheating",
                "description": f"CPU package temperature reached {cpu_temp}°C (critical threshold: {self.t.get('cpu_temp_critical', 95)}°C).",
                "evidence": f"Package temp: {cpu_temp}°C, CPU utilization: {cpu.get('overall_utilization', 0)}%",
                "recommendation": "Reduce CPU workload immediately. Check fan operation and thermal paste."
            })
        elif cpu_temp > self.t.get("cpu_temp_warning", 80):
            issues.append({
                "component": "CPU",
                "severity": "WARNING",
                "title": "Elevated CPU Temperature",
                "description": f"CPU package temperature is {cpu_temp}°C (warning threshold: {self.t.get('cpu_temp_warning', 80)}°C).",
                "evidence": f"Package temp: {cpu_temp}°C, CPU utilization: {cpu.get('overall_utilization', 0)}%",
                "recommendation": "Monitor temperature trend. Ensure adequate ventilation."
            })

        # GPU temperature check
        if gpu.get("present"):
            gpu_temp = gpu.get("temperature", 0)
            if gpu_temp > self.t.get("gpu_temp_critical", 90):
                issues.append({
                    "component": "GPU",
                    "severity": "CRITICAL",
                    "title": "GPU Overheating",
                    "description": f"NVIDIA RTX 3050 temperature reached {gpu_temp}°C.",
                    "evidence": f"GPU Temp: {gpu_temp}°C, Utilization: {gpu.get('utilization', 0)}%, Power: {gpu.get('power_draw', 0)}W",
                    "recommendation": "Reduce GPU workload immediately to prevent thermal shutdown."
                })
            elif gpu_temp > self.t.get("gpu_temp_warning", 80):
                issues.append({
                    "component": "GPU",
                    "severity": "WARNING",
                    "title": "Elevated GPU Temperature",
                    "description": f"GPU temperature is {gpu_temp}°C.",
                    "evidence": f"GPU Temp: {gpu_temp}°C, Utilization: {gpu.get('utilization', 0)}%",
                    "recommendation": "Monitor GPU workload. Check if fan is spinning adequately."
                })

        # Storage check
        for mount, disk in storage.items():
            disk_pct = disk.get("percent", 0)
            if disk_pct > self.t.get("disk_critical_pct", 95):
                issues.append({
                    "component": "STORAGE",
                    "severity": "CRITICAL",
                    "title": f"Critical Disk Space on {mount}",
                    "description": f"Disk usage at {disk_pct}% on {mount}.",
                    "evidence": f"Free: {disk['free'] / (1024**3):.2f}GB / Total: {disk['total'] / (1024**3):.2f}GB",
                    "recommendation": "Free up disk space immediately. Remove unnecessary files or expand storage."
                })
            elif disk_pct > self.t.get("disk_warning_pct", 85):
                issues.append({
                    "component": "STORAGE",
                    "severity": "WARNING",
                    "title": f"Low Disk Space on {mount}",
                    "description": f"Disk usage at {disk_pct}% on {mount}.",
                    "evidence": f"Free: {disk['free'] / (1024**3):.2f}GB",
                    "recommendation": "Plan disk cleanup. Monitor growth rate."
                })

        # NVMe health check
        if nvme:
            nvme_temp = nvme.get("temperature", 0)
            if nvme_temp > self.t.get("nvme_temp_critical", 75):
                issues.append({
                    "component": "STORAGE",
                    "severity": "CRITICAL",
                    "title": "NVMe Overheating",
                    "description": f"NVMe temperature reached {nvme_temp}°C.",
                    "evidence": f"NVMe Temp: {nvme_temp}°C, Percentage Used: {nvme.get('percentage_used', 0)}%",
                    "recommendation": "Improve case airflow. Consider adding thermal pad to NVMe."
                })
            elif nvme_temp > self.t.get("nvme_temp_warning", 65):
                issues.append({
                    "component": "STORAGE",
                    "severity": "WARNING",
                    "title": "Elevated NVMe Temperature",
                    "description": f"NVMe temperature is {nvme_temp}°C.",
                    "evidence": f"NVMe Temp: {nvme_temp}°C",
                    "recommendation": "Monitor NVMe temperature trend."
                })
            
            if nvme.get("critical_warning", 0) != 0:
                issues.append({
                    "component": "STORAGE",
                    "severity": "HIGH",
                    "title": "NVMe Critical Warning",
                    "description": f"NVMe SMART critical warning flags set: {nvme.get('critical_warning', 0)}",
                    "evidence": f"Critical warning: {nvme.get('critical_warning', 0)}, Media errors: {nvme.get('media_errors', 0)}",
                    "recommendation": "Backup data immediately. Consider drive replacement."
                })

        # Battery check
        if battery.get("present"):
            bat_pct = battery.get("percent", 100)
            if not battery.get("power_plugged", True):
                if bat_pct <= self.t.get("battery_critical_pct", 10):
                    issues.append({
                        "component": "BATTERY",
                        "severity": "CRITICAL",
                        "title": "Battery Critically Low",
                        "description": f"Battery at {bat_pct}% and not charging.",
                        "evidence": f"Battery: {bat_pct}%, Status: Discharging",
                        "recommendation": "Connect AC adapter immediately to prevent data loss."
                    })
                elif bat_pct <= self.t.get("battery_low_pct", 20):
                    issues.append({
                        "component": "BATTERY",
                        "severity": "WARNING",
                        "title": "Battery Low",
                        "description": f"Battery at {bat_pct}% and not charging.",
                        "evidence": f"Battery: {bat_pct}%, Status: Discharging",
                        "recommendation": "Connect AC adapter soon."
                    })

        # Failed services check
        failed = os_data.get("failed_services", [])
        if failed:
            issues.append({
                "component": "SERVICES",
                "severity": "WARNING",
                "title": "Failed systemd Services Detected",
                "description": f"The following services have failed: {', '.join(failed)}",
                "evidence": f"Failed units: {failed}",
                "recommendation": f"Check logs using 'systemctl status {failed[0]}' and restart if safe."
            })

        # Kernel errors
        kernel_errors = os_data.get("kernel_errors", [])
        if kernel_errors:
            issues.append({
                "component": "KERNEL",
                "severity": "WARNING",
                "title": "Recent Kernel Errors Detected",
                "description": f"Found {len(kernel_errors)} kernel error(s) in current boot.",
                "evidence": "; ".join(kernel_errors[:3]),
                "recommendation": "Review full kernel logs with 'journalctl -p err -b'. May indicate hardware or driver issues."
            })

        # Network connectivity
        if not network.get("connected", True):
            issues.append({
                "component": "NETWORK",
                "severity": "WARNING",
                "title": "Network Connectivity Issue",
                "description": "No network connectivity detected.",
                "evidence": f"WiFi Signal: {network.get('wifi_signal', 0)}%, Connected: {network.get('connected', False)}",
                "recommendation": "Check WiFi connection, router status, or network manager."
            })
        elif network.get("wifi_signal", 100) < 30 and network.get("wifi_signal", 0) > 0:
            issues.append({
                "component": "NETWORK",
                "severity": "INFO",
                "title": "Weak WiFi Signal",
                "description": f"WiFi signal strength is {network.get('wifi_signal')}%.",
                "evidence": f"SSID: {network.get('wifi_ssid', 'unknown')}, Signal: {network.get('wifi_signal')}%",
                "recommendation": "Consider moving closer to access point or checking for interference."
            })

        # Process issues
        zombies = processes.get("zombies", [])
        if zombies:
            issues.append({
                "component": "PROCESSES",
                "severity": "INFO",
                "title": f"Zombie Processes Detected ({len(zombies)})",
                "description": "Defunct processes waiting for parent to reap.",
                "evidence": f"Zombie PIDs: {[z.get('pid') for z in zombies[:5]]}",
                "recommendation": "Usually harmless. Parent process should reap them. If persistent, investigate parent process."
            })

        return issues