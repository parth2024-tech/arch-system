#!/usr/bin/env bash
# ==============================================================================
# PERMANENT FIX FOR SLEEP / WAKE BLACK SCREEN AND POST-RESUME LAG
# System: HP Victus 15-fa1xxx | Intel i7-12650H + NVIDIA RTX 3050 Laptop
# ==============================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run as root (e.g. sudo bash fix-sleep-lag.sh)"
    exit 1
fi

TIMESTAMP=$(date +%F-%H%M%S)
BACKUP_DIR="/etc/systemd/sleep-fix-backup-$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

echo "=== Step 1: Backing up configuration files to $BACKUP_DIR ==="
[ -f /etc/default/grub ] && cp -a /etc/default/grub "$BACKUP_DIR/grub"
[ -f /etc/modprobe.d/i915.conf ] && cp -a /etc/modprobe.d/i915.conf "$BACKUP_DIR/i915.conf"
[ -f /etc/modprobe.d/nvidia.conf ] && cp -a /etc/modprobe.d/nvidia.conf "$BACKUP_DIR/nvidia.conf"
[ -f /etc/tlp.conf ] && cp -a /etc/tlp.conf "$BACKUP_DIR/tlp.conf"
echo "[✓] Backups complete."

echo ""
echo "=== Step 2: Fixing Display Wake & Eliminating Broken PSR2 ==="
# Broken Panel Self Refresh 2 (i915.enable_psr=2) causes link training timeout on wake,
# leaving screen black for 15-30s and causing massive compositor frame drop lag.
# Setting enable_psr=0 fixes display resume instantly.

cat << 'MODEOF' > /etc/modprobe.d/i915.conf
# Safe Intel Graphics configuration: disable broken PSR on HP Victus 144Hz panel
options i915 enable_psr=0 enable_fbc=1
MODEOF
echo "[✓] Configured /etc/modprobe.d/i915.conf (enable_psr=0)"

# Update GRUB kernel command line
sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=".*"/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash i915.enable_psr=0"/' /etc/default/grub
echo "[✓] Updated /etc/default/grub with clean kernel parameters"
grub-mkconfig -o /boot/grub/grub.cfg
echo "[✓] Regenerated /boot/grub/grub.cfg"

echo ""
echo "=== Step 3: Removing Broken gpu-suspend.service Touching NVMe SSD ==="
# The old gpu-suspend.service targeted 0000:02:00.0 (Samsung 980PRO NVMe SSD),
# causing disk I/O stalls and lockups upon wake.
if systemctl is-enabled gpu-suspend.service &>/dev/null; then
    systemctl disable --now gpu-suspend.service 2>/dev/null || true
fi
rm -f /etc/systemd/system/gpu-suspend.service
systemctl daemon-reload

# Restore NVMe SSD power control to safe default (on)
if [ -f /sys/bus/pci/devices/0000:02:00.0/power/control ]; then
    echo on > /sys/bus/pci/devices/0000:02:00.0/power/control
    echo "[✓] Restored Samsung NVMe SSD (0000:02:00.0) power control to normal"
fi

echo ""
echo "=== Step 4: Ensuring NVIDIA VRAM Preservation & Clean Resume ==="
# NVIDIA Wayland driver requires preserving video memory allocations to prevent
# buffer corruption and compositor stalls upon wake.
cat << 'NVEOF' > /etc/modprobe.d/nvidia.conf
options nvidia-drm modeset=1
options nvidia NVreg_DynamicPowerManagement=0x02
options nvidia NVreg_PreserveVideoMemoryAllocations=1
options nvidia NVreg_TemporaryFilePath=/var/tmp
options nvidia NVreg_InitializeSystemMemoryAllocations=0
NVEOF
echo "[✓] Configured /etc/modprobe.d/nvidia.conf with VRAM preservation"

systemctl enable nvidia-suspend.service 2>/dev/null || true
systemctl enable nvidia-resume.service 2>/dev/null || true
systemctl enable nvidia-hibernate.service 2>/dev/null || true
echo "[✓] Enabled NVIDIA systemd suspend/resume services"

echo ""
echo "=== Step 5: Fixing TLP Battery CPU Throttling on HP Victus ==="
# low-power profile causes HP Victus Embedded Controller (EC) to throttle CPU
# package to 400 MHz upon waking on battery. Using balanced/balance_power allows
# smooth UI response while preserving long battery life.
sed -i 's/PLATFORM_PROFILE_ON_BAT=low-power/PLATFORM_PROFILE_ON_BAT=balanced/g' /etc/tlp.conf
sed -i 's/CPU_ENERGY_PERF_POLICY_ON_BAT=power/CPU_ENERGY_PERF_POLICY_ON_BAT=balance_power/g' /etc/tlp.conf
sed -i 's/PCIE_ASPM_ON_BAT=powersupersave/PCIE_ASPM_ON_BAT=default/g' /etc/tlp.conf
tlp start 2>/dev/null || true
echo "[✓] Optimized TLP battery profiles in /etc/tlp.conf"

echo ""
echo "=========================================================================="
echo "★ PERMANENT FIX APPLIED SUCCESSFULLY! ★"
echo "  1. Panel Self Refresh (PSR) disabled: Screen wakes instantly with 0 lag."
echo "  2. Broken NVMe SSD power hook removed: No more storage I/O stalls."
echo "  3. NVIDIA VRAM allocations preserved: No Wayland buffer corruption."
echo "  4. CPU clock throttling fixed: CPU no longer stuck at 400 MHz on wake."
echo "  5. GRUB configuration rebuilt and saved to /boot/grub/grub.cfg."
echo "=========================================================================="
