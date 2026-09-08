import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.collectors.hardware import HardwareCollector
from src.collectors.os_collector import OSCollector
from src.collectors.process_collector import ProcessCollector
from src.collectors.network_collector import NetworkCollector

def test_hardware_collector_cpu():
    cpu = HardwareCollector.collect_cpu()
    assert "overall_utilization" in cpu
    assert isinstance(cpu["overall_utilization"], float)
    assert "per_core" in cpu
    assert isinstance(cpu["per_core"], list)
    assert len(cpu["per_core"]) > 0

def test_hardware_collector_ram():
    ram = HardwareCollector.collect_ram()
    assert "total" in ram
    assert "used" in ram
    assert "available" in ram
    assert "percent" in ram
    assert ram["total"] > 0

def test_hardware_collector_gpu():
    gpu = HardwareCollector.collect_gpu()
    assert "present" in gpu
    if gpu["present"]:
        assert "temperature" in gpu
        assert "utilization" in gpu
        assert "vram_total" in gpu

def test_hardware_collector_storage():
    disks = HardwareCollector.collect_storage()
    assert "/" in disks or "/home" in disks or any(disks.keys())

def test_hardware_collector_battery():
    bat = HardwareCollector.collect_battery()
    assert "present" in bat

def test_hardware_collector_temps():
    temps = HardwareCollector.collect_temperatures()
    assert isinstance(temps, dict)

def test_hardware_collector_fans():
    fans = HardwareCollector.collect_fans()
    assert isinstance(fans, dict)

def test_os_collector_failed_services():
    failed = OSCollector.get_failed_services()
    assert isinstance(failed, list)

def test_process_collector_top():
    procs = ProcessCollector.get_top_processes(3)
    assert isinstance(procs, list)
    assert len(procs) <= 3

def test_process_collector_memory_hogs():
    procs = ProcessCollector.get_memory_hogs(3)
    assert isinstance(procs, list)
    assert len(procs) <= 3

def test_network_collector():
    net = NetworkCollector.check_connectivity()
    assert "bytes_sent" in net
    assert "bytes_recv" in net
    assert "connected" in net