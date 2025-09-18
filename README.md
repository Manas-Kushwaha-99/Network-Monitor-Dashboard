---

# Network Monitor Dashboard

A modern, single-file network monitoring dashboard built with Flet.

This tool provides a clean, dark-mode-only UI for monitoring your system’s network details, running ping/traceroute tests, and performing Ookla-powered speed tests.

Everything runs from one file. No external scripts. No clutter.

---

## ✨ Features

* **Modern, responsive UI** (Dark mode only)
* **Single file execution**: just run `Network Monitor.exe` (or `Network Monitor.py`)
* **Network overview**: interfaces, IP addresses, subnet, gateway, MAC, DNS, and status
* **Public network info**: public IP and current DNS servers
* **Built-in tools**:

  * Ping any host/IP
  * Traceroute (`pathping` on Windows)
  * Ookla Speedtest CLI (auto-download on Windows, JSON parsed for clean output)
* **Auto-refresh** (toggleable)
* **Console log** with timestamped results
* **Error handling**: irrelevant internal errors are fully silenced
* **Windows only**

---

## 📸 Screenshot

![WhatsApp Image 2025-09-19 at 01 32 52_7c156f75](https://github.com/user-attachments/assets/4feb293c-2489-4730-8cb8-79fec9a5809f) 
![WhatsApp Image 2025-09-19 at 01 32 52_2f3ada05](https://github.com/user-attachments/assets/6c868890-51cc-41bc-b87a-3a9e98d9c850) 
![WhatsApp Image 2025-09-19 at 01 32 52_4d25e9a0](https://github.com/user-attachments/assets/7cb809e0-4fdd-481c-8e87-625ca4e5bb52)

---

## 🔧 Requirements

* Python **3.9+**
* flet
* psutil
* netifaces
* requests

Install them all with:

```bash
pip install flet psutil netifaces requests
```

---

## 🚀 Usage

1. Clone this repository:

   ```bash
   git clone https://github.com/Manas-Kushwaha-99/Network-Monitor-Dashboard.git
   cd network-monitor-dashboard
   ```
2. Run the script:

   ```bash
   python "Network Monitor.py"
   ```

   or launch the packaged version:

   ```bash
   Network Monitor.exe
   ```
3. The app opens in a desktop window with all tools available.

> **Note (Windows users):**
> The first time you run a speed test, the app will try to automatically download the official **Ookla Speedtest CLI**.
> If this fails (due to firewall, proxy, or permissions), manually [download it](https://www.speedtest.net/apps/cli) and place `speedtest.exe` in the same folder as:
>
> * `Network Monitor.py`, or
> * `Network Monitor.exe` (if using the packaged version).

Without `speedtest.exe`, all other features work fine, but speed tests will show an error.

---

## 🖥️ Features in Action

* **Network Overview**
  See active interfaces with status, IPv4/IPv6, MAC, subnet, and gateway.

* **Public Network Info**
  View your current public IP and DNS servers in use.

* **Tools Panel**

  * Enter a host/IP and click **Ping** to check connectivity.
  * Use **Traceroute** to diagnose route issues.
  * Run **Speed Test** for bandwidth, latency, and server details.
  * Use **Refresh Now** for an instant network info update.

* **Console Output**
  Results and logs are displayed with timestamps for quick inspection.

---

## ⚠️ Notes

* Windows users get PowerShell-based DNS detection.
* Internal debug logs are suppressed; only relevant user-facing messages appear.

---
