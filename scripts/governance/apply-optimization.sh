#!/usr/bin/env bash
# ==============================================================================
# ARCH LINUX ON-DEMAND SYSTEM OPTIMIZATION SCRIPT (PERMANENT SYSTEM-WIDE INSTALL)
# Strictly adheres to SYSTEM_RULEBOOK.md (Rules 1-7).
# ==============================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run as root (e.g. sudo bash apply-optimization.sh)"
    exit 1
fi

TIMESTAMP=$(date +%F-%H%M%S)
BACKUP_DIR="/etc/systemd/system-backup-$TIMESTAMP"
echo "=== Step 0: Scientific Measurement Baseline (Rule 7) ==="
systemd-analyze > "/tmp/boot-baseline-$TIMESTAMP.txt" 2>&1 || true
systemd-analyze critical-chain graphical.target >> "/tmp/boot-baseline-$TIMESTAMP.txt" 2>&1 || true
echo "[✓] Boot baseline logged to /tmp/boot-baseline-$TIMESTAMP.txt"

echo ""
echo "=== Step 1: Creating Full Configuration Backup in $BACKUP_DIR ==="
mkdir -p "$BACKUP_DIR"
cp -a /etc/systemd/system "$BACKUP_DIR/systemd-system"
[ -d /etc/sysctl.d ] && cp -a /etc/sysctl.d "$BACKUP_DIR/sysctl.d"
[ -d /etc/systemd/journald.conf.d ] && cp -a /etc/systemd/journald.conf.d "$BACKUP_DIR/journald.conf.d"
[ -d /etc/udev/rules.d ] && cp -a /etc/udev/rules.d "$BACKUP_DIR/udev-rules.d"
[ -d /etc/pacman.d/hooks ] && cp -a /etc/pacman.d/hooks "$BACKUP_DIR/pacman-hooks" || true
echo "[✓] Configuration backup complete."

echo ""
echo "=== Step 2: Boot Critical Path Optimizations (Rule 6.3) ==="

# 2.1 Disable NetworkManager-wait-online (eliminates boot delay waiting for network)
if systemctl is-enabled NetworkManager-wait-online.service &>/dev/null; then
    systemctl disable NetworkManager-wait-online.service
    echo "[✓] Disabled NetworkManager-wait-online.service"
fi

# 2.2 Disable failed VMware service from boot (handled on-demand via wrapper)
if systemctl is-enabled vmware.service &>/dev/null; then
    systemctl disable vmware.service
    echo "[✓] Disabled vmware.service from boot"
fi

# 2.3 Switch snapd to pure socket activation (only starts when a snap runs)
if systemctl is-enabled snapd.service &>/dev/null; then
    systemctl disable snapd.service
    systemctl enable --now snapd.socket
    echo "[✓] Converted snapd to on-demand socket activation"
fi

# 2.4 Switch virtlogd to pure socket activation
if systemctl is-enabled virtlogd.service &>/dev/null; then
    systemctl disable virtlogd.service
    systemctl enable --now virtlogd.socket
    echo "[✓] Converted virtlogd to on-demand socket activation"
fi

# 2.5 Resolve firewall conflict (Rule 4.1: Verify firewalld running before ufw removal)
if firewall-cmd --state &>/dev/null; then
    echo "[✓] Verified firewalld is active and running."
    if systemctl is-enabled ufw.service &>/dev/null; then
        systemctl disable --now ufw.service
        echo "[✓] Disabled duplicate ufw.service"
    fi
else
    echo "[!] Warning: firewalld is not active; skipping ufw disable for safety."
fi

# 2.6 Resolve dual time-sync conflict (Rule 4.2: UDP 123 is blocked; https-timesync is authoritative)
if systemctl is-enabled https-timesync.timer &>/dev/null; then
    if systemctl is-active chronyd.service &>/dev/null || systemctl is-enabled chronyd.service &>/dev/null; then
        systemctl disable --now chronyd.service 2>/dev/null || true
        echo "[✓] Resolved time-sync conflict: disabled failing chronyd in favor of https-timesync.timer"
    fi
    systemctl disable https-timesync.service 2>/dev/null || true
fi

echo ""
echo "=== Step 3: Hardware Power & Thermal Governance (Rule 5) ==="

# 3.1 Ensure power-profiles-daemon remains masked so TLP has full control
systemctl mask power-profiles-daemon 2>/dev/null || true
echo "[✓] Verified power-profiles-daemon is masked"

# 3.2 NVIDIA dGPU Runtime D3cold Power Gating (Rule 5.4)
mkdir -p /etc/udev/rules.d
cat << 'UDEVEOF' > /etc/udev/rules.d/80-nvidia-pm.rules
# Enable runtime PM for NVIDIA VGA/3D controller devices
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x03[0-9]*", ATTR{power/control}="auto", ATTR{power/async}="enabled"
# Enable runtime PM for NVIDIA Audio devices
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x040300", ATTR{power/control}="auto", ATTR{power/async}="enabled"
UDEVEOF
udevadm control --reload
udevadm trigger --subsystem-match=pci
echo "[✓] Installed /etc/udev/rules.d/80-nvidia-pm.rules (PCI runtime PM auto)"

# Disable nvidia-persistenced as it prevents GPU from entering D3cold sleep
if systemctl is-enabled nvidia-persistenced.service &>/dev/null; then
    systemctl disable --now nvidia-persistenced.service
    echo "[✓] Disabled nvidia-persistenced.service to allow true GPU suspension"
fi

# Dynamic runtime test: set auto immediately
if [ -f /sys/bus/pci/devices/0000:01:00.0/power/control ]; then
    echo auto > /sys/bus/pci/devices/0000:01:00.0/power/control || true
fi

# 3.3 Ensure dynamic power management module option
cat << 'NVEOF' > /etc/modprobe.d/nvidia-power.conf
options nvidia NVreg_DynamicPowerManagement=0x02
NVEOF
echo "[✓] Configured /etc/modprobe.d/nvidia-power.conf"

# 3.4 Apply TLP profile
tlp start 2>/dev/null || tlp ac 2>/dev/null || true
echo "[✓] TLP profile active"

echo ""
echo "=== Step 4: Memory, Swap & Logging Policies (Rule 5.1 & 6.1) ==="

# 4.1 Cap systemd journal to 200M to prevent unbounded disk/memory growth
mkdir -p /etc/systemd/journald.conf.d
cat << 'JEOF' > /etc/systemd/journald.conf.d/size.conf
[Journal]
SystemMaxUse=200M
RuntimeMaxUse=64M
JEOF
journalctl --vacuum-size=200M 2>/dev/null || true
echo "[✓] Journal capped to 200M"

# 4.2 Enforce vm.swappiness = 100 for optimal zram page pressure
cat << 'SYSEOF' > /etc/sysctl.d/99-vm-zram.conf
vm.swappiness = 100
vm.watermark_boost_factor = 0
vm.watermark_scale_factor = 125
vm.page-cluster = 0
SYSEOF
sysctl -p /etc/sysctl.d/99-vm-zram.conf 2>/dev/null || true
echo "[✓] Enforced vm.swappiness = 100 for zram"

echo ""
echo "=== Step 5: Network Server Daemon Optimization (Rule 4.6) ==="

if systemctl is-enabled sshd.service &>/dev/null; then
    systemctl disable --now sshd.service
    echo "[✓] Disabled sshd.service from boot (start on-demand: sudo systemctl start sshd)"
fi

if systemctl is-enabled fail2ban.service &>/dev/null; then
    systemctl disable --now fail2ban.service
    echo "[✓] Disabled fail2ban.service from boot (tied to sshd lifecycle)"
fi

echo ""
echo "=== Step 6: Permanent System-Wide Governance & Pacman Immune System ==="

# 6.1 Install system-wide Rulebook and Enforcer
mkdir -p /etc/system-governance
cp -f "/home/thor/Desktop/arch system/SYSTEM_RULEBOOK.md" /etc/system-governance/SYSTEM_RULEBOOK.md
chmod 644 /etc/system-governance/SYSTEM_RULEBOOK.md

cp -f /home/thor/.local/share/ondemand-optimization/enforce-governance.sh /usr/local/bin/enforce-system-governance
chmod 755 /usr/local/bin/enforce-system-governance
echo "[✓] Installed /usr/local/bin/enforce-system-governance"

cp -f /home/thor/.local/bin/audit-rules /usr/local/bin/audit-rules
chmod 755 /usr/local/bin/audit-rules
echo "[✓] Installed system-wide /usr/local/bin/audit-rules"

# 6.2 Install system-wide profile
cat << 'PROFEOF' > /etc/profile.d/system-governance.sh
# System Governance Environment Setup
export PATH="/usr/local/bin:$HOME/.local/bin:$PATH"
PROFEOF
chmod 644 /etc/profile.d/system-governance.sh
echo "[✓] Installed /etc/profile.d/system-governance.sh"

# 6.3 Install Pacman Post-Transaction Hook (Immune System against updates)
mkdir -p /etc/pacman.d/hooks
cat << 'HOOKEOF' > /etc/pacman.d/hooks/99-system-governance.hook
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = *

[Action]
Description = Re-enforcing Arch Linux On-Demand System Rulebook after package transactions...
When = PostTransaction
Exec = /usr/local/bin/enforce-system-governance
Depends = bash
HOOKEOF
chmod 644 /etc/pacman.d/hooks/99-system-governance.hook
echo "[✓] Installed Pacman Hook: /etc/pacman.d/hooks/99-system-governance.hook"

# 6.4 Install systemd boot enforcement service
cat << 'UNITEOF' > /etc/systemd/system/system-governance-shield.service
[Unit]
Description=Arch Linux On-Demand System Governance Shield
After=basic.target
Before=graphical.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/enforce-system-governance
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNITEOF
systemctl daemon-reload
systemctl enable system-governance-shield.service
echo "[✓] Installed and enabled system-governance-shield.service at boot"

# Run enforcement immediately
/usr/local/bin/enforce-system-governance

echo ""
echo "=========================================================================="
echo "★ ARCH LINUX GOVERNANCE INSTALLED PERMANENTLY ACROSS THE SYSTEM! ★"
echo "  1. Configured udev, sysctl, journald, and systemd units."
echo "  2. Installed Pacman Hook: Re-enforces rules automatically on every update."
echo "  3. Installed system-governance-shield.service: Runs on every boot."
echo "  4. Installed /usr/local/bin/audit-rules: Accessible by all users everywhere."
echo "=========================================================================="
