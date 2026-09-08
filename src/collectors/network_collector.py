import psutil
import subprocess
from typing import Dict, Any

class NetworkCollector:
    @staticmethod
    def check_connectivity() -> Dict[str, Any]:
        net_io = psutil.net_io_counters()
        wifi_signal = 0
        ssid = ""
        try:
            # Use nmcli with better parsing
            out = subprocess.check_output(
                ["nmcli", "-t", "-f", "IN-USE,SIGNAL,SSID", "dev", "wifi", "list"], 
                timeout=2
            ).decode("utf-8")
            for line in out.splitlines():
                parts = line.split(":")
                if len(parts) >= 3:
                    # First field is IN-USE marker (* or empty)
                    if parts[0] == "*":
                        wifi_signal = int(parts[1]) if parts[1].isdigit() else 0
                        ssid = parts[2]
                        break
        except Exception:
            pass

        return {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "errin": net_io.errin,
            "errout": net_io.errout,
            "dropin": net_io.dropin,
            "dropout": net_io.dropout,
            "wifi_signal": wifi_signal,
            "wifi_ssid": ssid,
            "connected": wifi_signal > 0 or net_io.bytes_recv > 0
        }

    @staticmethod
    def get_interfaces() -> Dict[str, Any]:
        interfaces = {}
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, addr_list in addrs.items():
            interfaces[name] = {
                "is_up": stats[name].isup if name in stats else False,
                "speed": stats[name].speed if name in stats else 0,
                "mtu": stats[name].mtu if name in stats else 0,
                "addresses": [{"family": str(a.family), "address": a.address} for a in addr_list]
            }
        return interfaces