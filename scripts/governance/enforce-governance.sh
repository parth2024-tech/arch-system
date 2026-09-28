#!/usr/bin/env bash
# ==============================================================================
# PERMANENT SYSTEM GOVERNANCE ENFORCER
# Invoked at boot and automatically after every pacman transaction.
# Guarantees that updates and reboots NEVER compromise the On-Demand Rulebook.
# ==============================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run as root."
    exit 1
fi

# 1. Ensure prohibited boot services remain disabled
PROHIBITED_SERVICES=(
    "chronyd.service"
    "ufw.service"
    "vmware.service"
    "fail2ban.service"
    "sshd.service"
    "NetworkManager-wait-online.service"
    "nvidia-persistenced.service"
)

for svc in "${PROHIBITED_SERVICES[@]}"; do
    if systemctl is-enabled "$svc" &>/dev/null; then
        systemctl disable "$svc" 2>/dev/null || true
    fi
    if systemctl is-active "$svc" &>/dev/null; then
        systemctl stop "$svc" 2>/dev/null || true
    fi
done

# 2. Ensure pure socket activation for on-demand services
if systemctl is-enabled snapd.service &>/dev/null; then
    systemctl disable snapd.service 2>/dev/null || true
    systemctl enable snapd.socket 2>/dev/null || true
fi

if systemctl is-enabled virtlogd.service &>/dev/null; then
    systemctl disable virtlogd.service 2>/dev/null || true
    systemctl enable virtlogd.socket 2>/dev/null || true
fi

# 3. Ensure power-profiles-daemon remains masked
systemctl mask power-profiles-daemon 2>/dev/null || true

# 4. Enforce Autostart Shields in /etc/xdg/autostart and user directories
SHIELD_APPS=(
    "kalarm.autostart.desktop"
    "blueman.desktop"
    "kmix_autostart.desktop"
    "org.kde.discover.notifier.desktop"
    "org.kde.kdeconnect.daemon.desktop"
    "baloo_file.desktop"
    "snap-userd-autostart.desktop"
    "org.kde.kclockd-autostart.desktop"
)

# Apply to all human users in /home
for user_home in /home/*; do
    if [ -d "$user_home/.config" ]; then
        user_autostart="$user_home/.config/autostart"
        mkdir -p "$user_autostart"
        u_owner=$(stat -c '%u:%g' "$user_home")
        for app in "${SHIELD_APPS[@]}"; do
            target="$user_autostart/$app"
            if [ ! -f "$target" ] || ! grep -q "Hidden=true" "$target" 2>/dev/null; then
                cat << DEOF > "$target"
[Desktop Entry]
Type=Application
Name=Shielded by System Rulebook
Hidden=true
X-KDE-autostart-condition=false
DEOF
                chown "$u_owner" "$target"
            fi
        done
        
        # Enforce D-Bus circuit breaker for Akonadi
        user_dbus="$user_home/.local/share/dbus-1/services"
        mkdir -p "$user_dbus"
        dbus_target="$user_dbus/org.freedesktop.Akonadi.Control.service"
        if [ ! -f "$dbus_target" ] || ! grep -q "/bin/false" "$dbus_target" 2>/dev/null; then
            cat << DBOUT > "$dbus_target"
[D-BUS Service]
Name=org.freedesktop.Akonadi.Control
Exec=/bin/false
DBOUT
            chown "$u_owner" "$dbus_target"
        fi
    fi
done

# 5. Enforce NVIDIA Runtime PM Power Gating
mkdir -p /etc/udev/rules.d
if [ ! -f /etc/udev/rules.d/80-nvidia-pm.rules ]; then
    cat << 'UDEVEOF' > /etc/udev/rules.d/80-nvidia-pm.rules
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x03[0-9]*", ATTR{power/control}="auto", ATTR{power/async}="enabled"
ACTION=="add", SUBSYSTEM=="pci", ATTR{vendor}=="0x10de", ATTR{class}=="0x040300", ATTR{power/control}="auto", ATTR{power/async}="enabled"
UDEVEOF
    udevadm control --reload 2>/dev/null || true
    udevadm trigger --subsystem-match=pci 2>/dev/null || true
fi

# Dynamically set power control to auto if device exists
if [ -f /sys/bus/pci/devices/0000:01:00.0/power/control ]; then
    echo auto > /sys/bus/pci/devices/0000:01:00.0/power/control 2>/dev/null || true
fi

# 6. Ensure sysctl zram policy is active
if [ -f /etc/sysctl.d/99-vm-zram.conf ]; then
    sysctl -p /etc/sysctl.d/99-vm-zram.conf 2>/dev/null || true
fi

echo "[✓] System Governance Rules re-enforced successfully."
