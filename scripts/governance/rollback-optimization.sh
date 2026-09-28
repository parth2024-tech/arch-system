#!/usr/bin/env bash
# ==============================================================================
# ROLLBACK SCRIPT FOR ON-DEMAND SYSTEM OPTIMIZATION
# Restores previous system configurations and services.
# ==============================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run as root (e.g. sudo bash rollback-optimization.sh)"
    exit 1
fi

echo "=== Rolling Back System Configurations ==="

# 1. Remove journald cap
rm -f /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald
echo "[✓] Removed journald size cap"

# 2. Re-enable standard services
systemctl enable NetworkManager-wait-online.service 2>/dev/null || true
systemctl enable chronyd.service 2>/dev/null || true
systemctl start chronyd.service 2>/dev/null || true
systemctl enable ufw.service 2>/dev/null || true
systemctl enable snapd.service 2>/dev/null || true
systemctl enable virtlogd.service 2>/dev/null || true
systemctl enable nvidia-persistenced.service 2>/dev/null || true
echo "[✓] Re-enabled systemd services"

# 3. Clean up custom udev rules
rm -f /etc/udev/rules.d/80-nvidia-pm.rules
udevadm control --reload
udevadm trigger --subsystem-match=pci
echo "[✓] Removed custom NVIDIA udev rule"

echo "Rollback completed. Please reboot to verify standard defaults."
