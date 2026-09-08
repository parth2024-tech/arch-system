import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.processor.diagnostics import DiagnosticEngine

@pytest.fixture
def thresholds():
    return {
        "cpu_temp_warning": 80.0,
        "cpu_temp_critical": 95.0,
        "gpu_temp_warning": 80.0,
        "gpu_temp_critical": 90.0,
        "nvme_temp_warning": 65.0,
        "nvme_temp_critical": 75.0,
        "ram_warning_pct": 85.0,
        "ram_critical_pct": 95.0,
        "disk_warning_pct": 85.0,
        "disk_critical_pct": 95.0,
        "battery_low_pct": 20.0,
        "battery_critical_pct": 10.0,
    }

@pytest.fixture
def engine(thresholds):
    return DiagnosticEngine(thresholds)

@pytest.fixture
def base_cpu():
    return {"overall_utilization": 25.0, "per_core": [20.0]*16, "load_avg": [0.5]*3, "freq_current": 2000.0}

@pytest.fixture
def base_ram():
    return {"total": 16*1024**3, "used": 8*1024**3, "available": 8*1024**3, "percent": 50.0, 
            "swap_total": 0, "swap_used": 0, "swap_percent": 0}

@pytest.fixture
def base_gpu():
    return {"present": True, "temperature": 45.0, "utilization": 10.0, 
            "vram_total": 4*1024**3, "vram_used": 1*1024**3, "power_draw": 15.0, "sm_clock": 500.0}

@pytest.fixture
def base_storage():
    return {"/": {"total": 500*1024**3, "used": 200*1024**3, "free": 300*1024**3, "percent": 40.0}}

@pytest.fixture
def base_battery():
    return {"present": True, "percent": 90, "secsleft": 3600, "power_plugged": True}

@pytest.fixture
def base_temps():
    return {"coretemp_Package id 0": 55.0}

@pytest.fixture
def base_fans():
    return {"hp_fan1": 2600, "hp_fan2": 2400}

@pytest.fixture
def base_os_data():
    return {"failed_services": [], "kernel_errors": []}

@pytest.fixture
def base_processes():
    return {"zombies": []}

@pytest.fixture
def base_network():
    return {"connected": True, "wifi_signal": 80, "wifi_ssid": "test"}

@pytest.fixture
def base_nvme():
    return {"temperature": 40, "percentage_used": 14, "critical_warning": 0, "media_errors": 0}

def test_healthy_system(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    assert len(issues) == 0

def test_ram_critical(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_ram["percent"] = 97.0
    base_ram["used"] = 15.5 * 1024**3
    base_ram["available"] = 0.5 * 1024**3
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    ram_issues = [i for i in issues if i["component"] == "RAM"]
    assert len(ram_issues) == 1
    assert ram_issues[0]["severity"] == "CRITICAL"

def test_ram_warning(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_ram["percent"] = 90.0
    base_ram["used"] = 14.4 * 1024**3
    base_ram["available"] = 1.6 * 1024**3
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    ram_issues = [i for i in issues if i["component"] == "RAM"]
    assert len(ram_issues) == 1
    assert ram_issues[0]["severity"] == "HIGH"

def test_cpu_temp_critical(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_temps["coretemp_Package id 0"] = 97.0
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    cpu_issues = [i for i in issues if i["component"] == "CPU"]
    assert len(cpu_issues) == 1
    assert cpu_issues[0]["severity"] == "CRITICAL"

def test_cpu_temp_warning(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_temps["coretemp_Package id 0"] = 85.0
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    cpu_issues = [i for i in issues if i["component"] == "CPU"]
    assert len(cpu_issues) == 1
    assert cpu_issues[0]["severity"] == "WARNING"

def test_gpu_temp_critical(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_gpu["temperature"] = 92.0
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    gpu_issues = [i for i in issues if i["component"] == "GPU"]
    assert len(gpu_issues) == 1
    assert gpu_issues[0]["severity"] == "CRITICAL"

def test_storage_critical(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_storage["/"]["percent"] = 97.0
    base_storage["/"]["used"] = 485*1024**3
    base_storage["/"]["free"] = 15*1024**3
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    storage_issues = [i for i in issues if i["component"] == "STORAGE"]
    assert len(storage_issues) == 1
    assert storage_issues[0]["severity"] == "CRITICAL"

def test_battery_critical(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_battery["percent"] = 5
    base_battery["power_plugged"] = False
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    bat_issues = [i for i in issues if i["component"] == "BATTERY"]
    assert len(bat_issues) == 1
    assert bat_issues[0]["severity"] == "CRITICAL"

def test_failed_services(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_os_data["failed_services"] = ["vmware.service", "bluetooth.service"]
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    svc_issues = [i for i in issues if i["component"] == "SERVICES"]
    assert len(svc_issues) == 1
    assert svc_issues[0]["severity"] == "WARNING"

def test_kernel_errors(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_os_data["kernel_errors"] = ["error 1", "error 2"]
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    kernel_issues = [i for i in issues if i["component"] == "KERNEL"]
    assert len(kernel_issues) == 1
    assert kernel_issues[0]["severity"] == "WARNING"

def test_zombie_processes(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_processes["zombies"] = [{"pid": 123, "name": "defunct"}, {"pid": 456, "name": "defunct"}]
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    proc_issues = [i for i in issues if i["component"] == "PROCESSES"]
    assert len(proc_issues) == 1
    assert proc_issues[0]["severity"] == "INFO"

def test_nvme_critical_warning(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_nvme["critical_warning"] = 1
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    nvme_issues = [i for i in issues if i["component"] == "STORAGE" and "NVMe Critical Warning" in i["title"]]
    assert len(nvme_issues) == 1
    assert nvme_issues[0]["severity"] == "HIGH"

def test_weak_wifi(engine, base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme):
    base_network["wifi_signal"] = 25
    issues = engine.analyze(base_cpu, base_ram, base_gpu, base_storage, base_battery, base_temps, base_fans, base_os_data, base_processes, base_network, base_nvme)
    net_issues = [i for i in issues if i["component"] == "NETWORK" and "Weak" in i["title"]]
    assert len(net_issues) == 1
    assert net_issues[0]["severity"] == "INFO"