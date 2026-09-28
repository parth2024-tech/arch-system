# ARCH LINUX SYSTEM GOVERNANCE & PROCESS RULEBOOK
**System: HP Victus 15-fa1xxx | OS: Arch Linux (Kernel LTS) | Architecture: On-Demand Event-Driven**

---

## PREAMBLE

The computing resources of this system—CPU cycles, RAM, battery energy, NVMe I/O, and thermal headroom—belong strictly to the user. 

Software installed on this machine is an invited guest. No application, daemon, helper, updater, database, or background service has the right to consume resources without explicit, real-time user intent.

> ### THE SUPREME LAW OF THE SYSTEM
> **DO NOT RUN A SERVICE JUST BECAUSE IT EXISTS. RUN IT ONLY WHEN IT IS ACTUALLY NEEDED.**  
> **IF THE USER OPENS IT, IT OPENS. IF THE USER CLOSES IT, ALL ASSOCIATED PROCESSES MUST TERMINATE COMPLETELY.**

---

## PART I: THE 7 CONSTITUTIONAL PROCESS RULES

### RULE 1: The Principle of Explicit Intent (Zero Unsolicited Boot)
1. **No Spontaneous Startup**: No process shall be added to boot targets (`multi-user.target`, `default.target`, or user autostart) without explicit justification and classification.
2. **Existence $\neq$ Execution**: Having a package installed on the NVMe drive confers zero permission for that package to place a running process in memory.
3. **Ban on Idle Pollers**: Applications must not install background check daemons, update polling trays, or telemetry collectors that run 24/7. Updates are performed deliberately via `pacman` / `yay`.
4. **User-Authorized Continuous Background Services (Exceptions)**:
   Any continuous 24/7 background daemon running on this machine requires explicit user designation in this Rulebook. Currently, the following exception is authorized:
   - **`obsidian-telegram-bot.service`**: Continuous headless automation bot managing vault ingestion via Telegram API. Exempted from idle auto-termination.

### RULE 2: The Strict On-Demand Lifecycle Protocol
Every non-core application must adhere to the three-stage lifecycle:
$$\text{User Launch} \longrightarrow \text{Execution (Foreground Only)} \longrightarrow \text{Complete Termination}$$

1. **Invocation**: The application and its required dependencies start *only* upon user action (launcher click or terminal command).
2. **Scope Isolation**: Heavy child processes (renderers, socket helpers, utility workers) must remain bound to the primary application's lifecycle.
3. **Hard Exit**: When the main window is closed by the user, **all** helper, background, and orphaned processes belonging to that application must terminate immediately. No lingering processes are permitted in RAM.

### RULE 3: D-Bus & IPC Backdoor Neutralization
1. **No Auto-Spawning via IPC**: Applications and desktop widgets must not use D-Bus activation to silently resurrect heavy suites (e.g., KDE calendar widgets waking Akonadi and MySQL).
2. **Stubbing Prohibited Activations**: Any D-Bus service that attempts unsolicited background resurrection must be neutralized in `~/.local/share/dbus-1/services/` by pointing its `Exec=` to `/bin/false`.
3. **Clean Fallbacks**: The system must gracefully reject auto-activation requests without crashing the desktop compositor.

### RULE 4: Single-Responsibility Subsystems (No Redundancy)
1. **One Firewall Only**: The system runs `firewalld`. Duplicate firewalls (`ufw`) are strictly prohibited from enabling at boot to prevent rule collisions and boot latency. Before disabling `ufw`, verify `firewall-cmd --state` reports `running`.
2. **One Timekeeper Only**: The local network and ISP block UDP port 123 (NTP), rendering `chronyd` completely non-functional (`Reach: 0`, `Stratum: 0`). Therefore, `https-timesync.timer` (running asynchronously over HTTPS port 443 20s after boot and every 1h) is the single authoritative timekeeper. `chronyd` is prohibited from running concurrently.
3. **One Bluetooth Manager Only**: KDE Plasma native Bluetooth (`bluedevil`) handles all Bluetooth operations. GTK applets (`blueman`) must never autostart.
4. **One Volume Subsystem Only**: PipeWire + WirePlumber managed directly through Plasma shell handles audio. Standalone volume daemons (`kmix`) are prohibited from background execution.
5. **One Power Manager Only**: `tlp` has sole authority over CPU frequency, platform profiles, and PCIe power gating. `power-profiles-daemon` must remain masked permanently.
6. **Co-Dependent Server Daemons**: Inbound `sshd` is strictly on-demand. When `sshd` is stopped, `fail2ban` has no active server log to protect and must remain stopped and disabled.

### RULE 5: Memory, Thermal & Hardware Boundaries
1. **ZRAM-First Memory Policy**: Fast compressed `zram` (`/dev/zram0`, Priority 100) handles all working memory paging with `vm.swappiness = 100`. NVMe disk swapfile (Priority 10) is reserved strictly for emergency exhaustion fallback.
2. **No Memory-Leaking Helpers**: Desktop helper portals (e.g., `xdg-desktop-portal-kde`) must not exceed 100 MB RAM. Any portal that leaks memory must be restarted.
3. **Hardware-First Power Governors**:
   - On AC Power: `powersave` governor + Intel HWP `balance_performance` allows the CPU to boost up to 4.8 GHz *only when load is detected*, resting at 400 MHz when idle.
   - On Battery: `powersave` governor + EPP `power` + Turbo Disabled (`no_turbo=1`) guarantees cool, quiet, long battery life.
4. **NVIDIA dGPU Runtime Dynamic Power Management (RTD3)**:
   - The discrete NVIDIA GeForce RTX 3050 Laptop GPU (Ada AD106M) must enter Runtime D3cold (`suspended`, 0W consumption) when no 3D application or CUDA workload is active.
   - PCI runtime power control must be configured to `auto` via `/etc/udev/rules.d/80-nvidia-pm.rules`.
   - `nvidia-persistenced` is superseded by modern kernel runtime PM and must remain disabled to allow complete GPU suspension.

### RULE 6: System Logging & Maintenance Discipline
1. **Journal Cap**: System logs in `/etc/systemd/journald.conf.d/size.conf` must never exceed `200M` on disk.
2. **Weekly Trimming & Caching**: Automated timers handle maintenance:
   - `fstrim.timer`: Trims NVMe SSD weekly.
   - `paccache.timer`: Cleans redundant pacman pkg cache weekly.
3. **Boot Chain Streamlining**: `NetworkManager-wait-online.service` delays graphical login and must remain disabled unless headless network mounts require it.

### RULE 7: The Scientific Measurement & Verification Protocol
No optimization or service modification shall be claimed as effective based on projections alone. Every system change must follow:
$$\text{Baseline Measurement} \longrightarrow \text{Targeted Intervention} \longrightarrow \text{Empirical Verification}$$

1. **Boot Performance**: Verified before and after with `systemd-analyze` and `systemd-analyze critical-chain graphical.target`.
2. **Memory Footprint**: Verified before and after with `free -h` and `ps_mem` (available RAM, swap composition).
3. **Compliance Audit**: Verified immediately using `~/.local/bin/audit-rules`.

---

## PART II: PROCESS CLASSIFICATION & GOVERNANCE MATRIX

| Process / Service | Category | Classification | Policy & Enforcement |
| :--- | :--- | :--- | :--- |
| **`kwin_wayland` / `plasmashell`** | Desktop Core | **CRITICAL** | Allowed 24/7. Manages desktop display, Wayland, and user interface. |
| **`pipewire` / `wireplumber`** | Audio Subsystem | **CRITICAL** | Allowed 24/7. Low-latency, low-overhead native audio server. |
| **`NetworkManager` / `wpa_supplicant`**| Connectivity | **CRITICAL** | Allowed 24/7. Essential for local network and Wi-Fi. |
| **`systemd-journald` / `logind` / `udevd`** | Kernel / Init | **CRITICAL** | Allowed 24/7. Core operating system stability. Capped to 200MB. |
| **`firewalld`** | Security | **CRITICAL** | Allowed 24/7. Primary dynamic host firewall. |
| **`tlp`** | Power Management | **CRITICAL** | Allowed 24/7. Dynamic CPU and hardware power manager. |
| **`obsidian-telegram-bot`** | Automation | **CONTINUOUS EXCEPTION** | User-authorized 24/7 background ingestion bot. Monitored for memory leaks. |
| **`https-timesync.timer`** | Timekeeping | **TIMER** | Authoritative timekeeper. Runs asynchronously 20s after boot and every 1h over HTTPS. |
| **`snapd`** | Package Runtime | **SOCKET** | `snapd.service` disabled from boot. Starts *only* via `snapd.socket` if a snap app runs. |
| **`virtlogd` / `libvirtd`** | Virtualization | **SOCKET** | Disabled from boot. Starts *only* via `libvirtd.socket` if a VM is opened. |
| **`vmware`** | Hypervisor | **ON-DEMAND** | Disabled from boot. Managed strictly via `~/.local/bin/vmware`. |
| **`Akonadi / MySQL Suite`** | PIM Suite | **ON-DEMAND** | Autostart blocked. Muzzled in D-Bus. Starts/stops strictly with KMail/KAlarm. |
| **`kdeconnect`** | Mobile Sync | **ON-DEMAND** | Autostart blocked. Runs only when `kdeconnect-app` wrapper launches; dies on exit. |
| **`laptop-monitor-dashboard`** | Telemetry | **ON-DEMAND** | Disabled from boot. Started on-demand via `~/.local/bin/laptop-monitor`. |
| **`Zen / Brave Browsers`** | Web Browsers | **ON-DEMAND** | Managed via lifecycle wrappers. All renderers killed when window closes. |
| **`Ollama / Hermes / LiteLLM`** | AI / LLM Runtimes | **ON-DEMAND** | Disabled from boot. Starts only when Hermes agent runs; terminates on exit. |
| **`SSHD`** | Remote Server | **ON-DEMAND** | Disabled from boot. Started manually via `sudo systemctl start sshd`. |
| **`proton.VPN`** | VPN Service | **ON-DEMAND** | Disabled from boot. Starts only when user explicitly connects to VPN. |
| **`chronyd`** | Timekeeping | **PROHIBITED** | Redundant and non-functional (UDP 123 blocked). Disabled permanently. |
| **`nvidia-persistenced`** | Graphics Daemon | **DISABLED** | Superseded by kernel RTD3 power management (`power/control=auto`). |
| **`NetworkManager-wait-online`** | Network Wait | **DISABLED** | Unnecessary blocker for mobile desktops. Adds 1-3s to boot. |
| **`Blueman`** | Bluetooth Applet | **PROHIBITED** | Redundant. Native KDE Bluetooth used. Autostart blocked. |
| **`KMix`** | Audio Mixer | **PROHIBITED** | Redundant. Native Plasma volume used. Autostart blocked. |
| **`DiscoverNotifier`** | Update Checker | **PROHIBITED** | Pointless polling on Arch. Autostart blocked. |
| **`UFW`** | Duplicate Firewall| **PROHIBITED** | Conflicts with Firewalld and adds 2.2s boot delay. Disabled permanently. |
| **`fail2ban`** | Security Monitor | **PROHIBITED AT BOOT** | Co-dependent on SSH. Disabled at boot; runs only when `sshd` is active. |
| **`baloo_file`** | File Indexer | **PROHIBITED** | High CPU and NVMe wear indexing. Autostart blocked. |
| **`kclockd`** | Alarm Daemon | **PROHIBITED** | Redundant with system timers. Autostart blocked. |
| **`snap-userd-autostart`** | Snap User Daemon | **PROHIBITED** | Redundant user-session poller. Autostart blocked. |
| **`speech-dispatcher`** | Screen Reader | **PROHIBITED** | Unsolicited audio daemon. Starts only if text-to-speech is requested. |

---

## PART III: ENFORCEMENT & COMPLIANCE TOOLS

The system enforces this Rulebook through four automated defensive barriers:

1. **The Autostart Shield** (`~/.config/autostart/*.desktop`):
   Overrides any package-installed desktop autostarts in `/etc/xdg/autostart/` with `Hidden=true`.
2. **The D-Bus Circuit Breaker** (`~/.local/share/dbus-1/services/`):
   Nullifies unsolicited background service activations with `Exec=/bin/false`.
3. **The Wrapper Dispatcher** (`~/.local/bin/`):
   Takes precedence over `/usr/bin/` in `$PATH`. Controls execution, tracks PID trees, and executes cleanup on exit.
4. **The System Health Verifier** (`~/.local/bin/audit-rules`):
   An executable audit tool that inspects all running processes, timer configurations, hardware power states, and user exceptions against this Rulebook.

---

*Adopted for system governance. Any new software installed must comply with these directives.*
