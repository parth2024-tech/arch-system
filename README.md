# HERMES Laptop Health & Performance Monitor

A lightweight, 24/7 hardware, OS, and performance diagnostics system with intelligent anomaly detection, predictive forecasting, alerting, and an interactive HTMX web dashboard tailored for **Arch Linux** (optimized for hybrid hardware such as Intel Core i7-12650H + NVIDIA GeForce RTX 3050).

---

## Features

- **Hardware & OS Collectors**:
  - **CPU**: Per-core loads, overall utilization, frequencies, load averages.
  - **RAM**: Memory utilization, buffers, cache, swap activity.
  - **GPU**: NVIDIA GPU tracking via `nvidia-smi` (zero dGPU wake-up overhead when inactive).
  - **Thermals & Fans**: Real-time sensor temperatures across CPU cores, GPU, NVMe, and fan RPMs.
  - **Storage & NVMe**: Disk space monitoring and NVMe SMART health attributes (wear level, critical warnings, media errors).
  - **Battery**: Charge state, drain rates, AC plug status, estimated time remaining.
  - **OS & Services**: Failed systemd units, kernel errors via `journalctl`, and core dumps via `coredumpctl`.
  - **Processes**: Top CPU and memory consumers, zombie PID detection.
  - **Network**: Connectivity status, gateway latency, Wi-Fi SSID, and link quality.

- **Intelligent Diagnostics & Anomaly Engine**:
  - **Rule-based Diagnostics**: 5 severity tiers (`INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) with automatic health scoring (0–100).
  - **Univariate Anomaly Detection**: Z-score spike detection and Exponentially Weighted Moving Average (EWMA) trend tracking.
  - **Multivariate Anomaly Detection**: Local `IsolationForest` (scikit-learn) trained on historical system metrics.
  - **Predictive Health Forecasting**: Linear regression over rolling 24-hour windows estimating dynamic risk scores and time-to-critical thresholds.

- **Zero-Cloud, Low Footprint**:
  - Requires **< 50MB RAM** and **< 1% CPU overhead**.
  - Embedded **SQLite in WAL (Write-Ahead Logging)** mode with rolling 7-day automatic data retention.
  - Zero external API costs or cloud agents required.

- **Interactive Web Dashboard**:
  - Built with **FastAPI**, **Jinja2**, and **HTMX** for smooth real-time polling without heavy JavaScript framework bloat.
  - Auto-refreshing status panels, active issue cards, anomaly history, and forecasting charts.

- **Telegram Alerts**:
  - Async notifications via `httpx` with rate limiting, deduplication, retry backoff, and Telegram `MarkdownV2` formatting.

- **24/7 systemd Automation**:
  - Run as background systemd user services (`laptop-monitor-collector.timer` & `laptop-monitor-dashboard.service`).

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                      Data Ingestion                    │
│   HardwareCollector   OSCollector   ProcessCollector   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   Storage Layer                        │
│            SQLite WAL (data/monitor.db)                │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│             Diagnostic & Analytics Engines             │
│   Deterministic Rules   Anomaly Engine   Predictive    │
└───────────────────────────┬────────────────────────────┘
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
┌─────────────────────────┐   ┌──────────────────────────┐
│   Telegram Dispatcher   │   │  FastAPI + HTMX Web UI   │
│   (HIGH/CRITICAL Alerts)│   │  (http://127.0.0.1:8000) │
└─────────────────────────┘   └──────────────────────────┘
```

---

## Getting Started

### Prerequisites

- **OS**: Arch Linux (or any modern Linux distribution with systemd)
- **Python**: 3.11+
- Recommended packages: `lm_sensors`, `smartmontools`, `nvme-cli`, `nvidia-utils` (if NVIDIA GPU present)

### Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/parth2024-tech/arch-system.git
   cd arch-system
   ```

2. **Run setup & start dashboard**:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```
   The dashboard will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

3. **Run tests**:
   ```bash
   source venv/bin/activate
   pytest tests/ -v
   ```

---

## 24/7 Background Service Setup (systemd)

To run the collector every 30 seconds and keep the web dashboard active automatically on login:

```bash
# 1. Copy user unit files
mkdir -p ~/.config/systemd/user
cp systemd/laptop-monitor-collector.service ~/.config/systemd/user/
cp systemd/laptop-monitor-collector.timer ~/.config/systemd/user/
cp systemd/laptop-monitor-dashboard.service ~/.config/systemd/user/

# 2. Reload systemd daemon
systemctl --user daemon-reload

# 3. Enable and start units
systemctl --user enable --now laptop-monitor-collector.timer
systemctl --user enable --now laptop-monitor-dashboard.service

# 4. Check service status
systemctl --user status laptop-monitor-collector.timer laptop-monitor-dashboard.service
```

---

## Configuration

Edit [`config/monitor.toml`](config/monitor.toml) to adjust thresholds, poll frequencies, and alert rules:

```toml
[monitor]
interval_seconds = 30
retention_days = 7
db_path = "data/monitor.db"

[thresholds]
cpu_temp_warning = 80.0
cpu_temp_critical = 95.0
gpu_temp_warning = 80.0
gpu_temp_critical = 90.0
ram_warning_pct = 85.0
ram_critical_pct = 95.0
disk_warning_pct = 85.0
disk_critical_pct = 95.0
battery_low_pct = 20.0
battery_critical_pct = 10.0

[anomaly]
enabled = true
model_retrain_interval_hours = 6
contamination = 0.05
zscore_threshold = 3.0

[predictive]
enabled = true
forecast_horizon_hours = 4
trend_window_hours = 24
```

### Telegram Alerts (Optional)

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Set your credentials:
   ```ini
   TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
   TELEGRAM_CHAT_ID="your_telegram_chat_id"
   ```

---

## REST API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | HTML dashboard overview |
| `/api/status` | `GET` | Current hardware metrics and health scores |
| `/api/issues` | `GET` | Active issues and severity rankings |
| `/api/history` | `GET` | Historical time-series metrics |
| `/api/anomalies`| `GET` | Detected anomalies and baseline ranges |
| `/api/predictions` | `GET` | Linear forecasts and time-to-critical estimates |
| `/api/telegram/health` | `GET` | Telegram bot connectivity status |
| `/api/telegram/test` | `POST` | Dispatches a test alert to Telegram |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
