import flet as ft
import platform
import subprocess
import socket
import threading
import time
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import concurrent.futures
try:
    import psutil
    import netifaces
    import requests
except ImportError as e:
    print(f"Missing required library: {e}")
    print("Install with: pip install flet psutil netifaces requests")
    exit(1)


class NetworkMonitor:
    """Embedded backend: Network information gathering and testing tools."""

    def __init__(self):
        self.system_platform = platform.system().lower()
        self._cache = {}
        self._cache_timeout = {}

    def get_network_info(self, use_cache: bool = True) -> Dict[str, Any]:
        cache_key = "network_info"
        if use_cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        interfaces_info = {}
        IGNORE_KEYWORDS = [
            'loopback', 'isatap', 'teredo', 'tunnel',
            'vmware', 'vbox', 'docker', 'virtualbox', 'vmnet',
            'npcap', 'npcap loopback',
            'wan miniport', 'pseudo', 'software',
            'bluetooth', 'airpods', 'iphone'
        ]

        try:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()

            for iface_name, addresses in addrs.items():
                if any(keyword in iface_name.lower() for keyword in IGNORE_KEYWORDS):
                    continue

                iface_stat = stats.get(iface_name)
                iface_info = {
                    "name": iface_name,
                    "is_up": iface_stat.isup if iface_stat else False,
                    "speed": iface_stat.speed if iface_stat and iface_stat.speed > 0 else None,
                    "mac": None, "ipv4": None, "ipv6": None, "subnet_mask": None,
                    "status": "Connected" if (iface_stat and iface_stat.isup) else "Disconnected"
                }

                for addr in addresses:
                    if addr.family == psutil.AF_LINK:
                        iface_info["mac"] = addr.address
                    elif addr.family == socket.AF_INET:
                        if addr.address == "127.0.0.1":
                            continue
                        elif iface_info["is_up"]:
                            iface_info["ipv4"] = addr.address
                            iface_info["subnet_mask"] = addr.netmask
                    elif addr.family == socket.AF_INET6:
                        ipv6_addr = addr.address.split('%')[0]
                        if iface_info["is_up"]:
                            if not ipv6_addr.startswith('fe80') or not iface_info["ipv6"]:
                                iface_info["ipv6"] = ipv6_addr

                interfaces_info[iface_name] = iface_info

        except Exception as e:
            return {"error": f"Failed to get network info: {str(e)}"}

        self._cache[cache_key] = interfaces_info
        self._cache_timeout[cache_key] = time.time() + 5
        return interfaces_info

    def get_default_gateway(self) -> Dict[str, Any]:
        try:
            gateways = netifaces.gateways()
            default_gw = {"ipv4": None, "ipv6": None}
            default_info = gateways.get('default', {})
            if netifaces.AF_INET in default_info:
                default_gw["ipv4"] = default_info[netifaces.AF_INET]
            if netifaces.AF_INET6 in default_info:
                default_gw["ipv6"] = default_info[netifaces.AF_INET6]
            return default_gw
        except Exception as e:
            return {"ipv4": None, "ipv6": None, "error": str(e)}

    def get_dns_servers(self) -> List[str]:
        dns_servers = []
        try:
            if self.system_platform == "windows":
                cmd = "Get-DnsClientServerAddress -AddressFamily IPv4 | Select-Object -ExpandProperty ServerAddresses"
                ok, out, err = self._run_powershell(cmd)
                if not ok:
                    raise RuntimeError(err or "Failed to read DNS via PowerShell")
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                for ip in lines:
                    if self._is_valid_ipv4(ip):
                        dns_servers.append(ip)
                seen = set()
                unique_dns = []
                for ip in dns_servers:
                    if ip not in seen:
                        seen.add(ip)
                        unique_dns.append(ip)
                    if len(unique_dns) >= 2:
                        break
                return unique_dns
            else:
                try:
                    with open("/etc/resolv.conf", "r") as f:
                        for line in f:
                            stripped = line.strip()
                            if stripped.startswith("nameserver"):
                                parts = stripped.split()
                                if len(parts) >= 2:
                                    candidate = parts[1]
                                    if self._is_valid_ipv4(candidate):
                                        dns_servers.append(candidate)
                except FileNotFoundError:
                    pass
        except Exception as e:
            print(f"[DEBUG] DNS lookup failed: {e}")
            dns_servers = ["8.8.8.8", "1.1.1.1"]

        seen = set()
        unique_dns = []
        for ip in dns_servers:
            if ip not in seen:
                seen.add(ip)
                unique_dns.append(ip)
            if len(unique_dns) >= 2:
                break
        return unique_dns

    def _run_powershell(self, command: str) -> tuple[bool, str, str]:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def get_public_ip(self) -> Optional[str]:
        cache_key = "public_ip"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        apis = [
            "https://api.ipify.org?format=text",
            "https://httpbin.org/ip",
            "https://checkip.amazonaws.com"
        ]

        for api in apis:
            try:
                response = requests.get(api, timeout=3)
                if response.status_code == 200:
                    if "ipify" in api or "amazonaws" in api:
                        ip = response.text.strip()
                    elif "httpbin" in api:
                        data = response.json()
                        ip = data.get("origin", "").split(",")[0].strip()
                    else:
                        ip = response.text.strip()

                    self._cache[cache_key] = ip
                    self._cache_timeout[cache_key] = time.time() + 30
                    return ip
            except Exception:
                continue

        return None

    def ping_host(self, host: str, count: int = 4, timeout: int = 5) -> str:
        try:
            if self.system_platform == "windows":
                cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            else:
                cmd = ["ping", "-c", str(count), "-W", str(timeout), host]
                startupinfo = None

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + count + 5,
                startupinfo=startupinfo
            )

            output = result.stdout.strip() if result.stdout else ""
            error = result.stderr.strip() if result.stderr else ""

            if result.returncode == 0:
                return output
            else:
                return error or f"Ping failed (exit code: {result.returncode})"

        except subprocess.TimeoutExpired:
            return f"Ping command timed out"
        except Exception as e:
            return f"Ping error: {str(e)}"

    def traceroute_host(self, host: str) -> str:
        try:
            if self.system_platform == "windows":
                cmd = ["pathping", "-n", "-q", "2", "-p", "500", "-h", "30", host]
                timeout = 90
            else:
                for cmd_name in ["mtr", "traceroute", "tracepath"]:
                    try:
                        subprocess.run([cmd_name, "--version"],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       timeout=2)
                        if cmd_name == "mtr":
                            cmd = [cmd_name, "-n", "-c", "10", "-r", host]
                        elif cmd_name == "traceroute":
                            cmd = [cmd_name, "-n", "-w", "3", "-q", "2", "-m", "30", host]
                        else:
                            cmd = [cmd_name, "-n", "-l", host]
                        timeout = 60
                        break
                    except FileNotFoundError:
                        continue
                else:
                    return "No traceroute tool found (install mtr, traceroute, or tracepath)"

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if self.system_platform == "windows" else 0
            )

            stdout, _ = process.communicate(timeout=timeout)

            if process.returncode == 0:
                return stdout.strip() or "No output received"
            else:
                return f"Traceroute failed with exit code {process.returncode}:\n{stdout}"

        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=5)
            except:
                pass
            return "Traceroute timed out after 90 seconds (network may be blocking ICMP/TCP probes)"
        except Exception as e:
            return f"Traceroute error: {str(e)}"

    def _download_speedtest_cli(self):
        """Download Ookla Speedtest CLI for Windows if not already present."""
        import os
        exe_path = "speedtest.exe"

        if os.path.exists(exe_path):
            return exe_path

        try:
            print("Downloading Ookla Speedtest CLI...")
            url = "https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-win64.zip"
            import urllib.request
            import zipfile
            import io

            with urllib.request.urlopen(url) as response:
                zip_data = io.BytesIO(response.read())

            with zipfile.ZipFile(zip_data) as zf:
                for file in zf.namelist():
                    if file.endswith("speedtest.exe"):
                        with open(exe_path, "wb") as f:
                            f.write(zf.read(file))
                        break
            print(f"Downloaded {exe_path}")
            return exe_path

        except Exception as e:
            raise RuntimeError(f"Failed to download Speedtest CLI: {str(e)}")

    def _run_speedtest_cli(self) -> Dict[str, Any]:
        """Run Ookla Speedtest CLI and parse JSON output."""
        try:
            exe_path = self._download_speedtest_cli()

            result = subprocess.run(
                [exe_path, "--format=json", "--accept-license", "--accept-gdpr"],
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode != 0:
                return {"error": f"Speedtest CLI failed with exit code {result.returncode}: {result.stderr.strip()}"}

            output = result.stdout.strip()
            data = json.loads(output)

            return {
                "download_mbps": round(data["download"]["bandwidth"] / 125000, 2),
                "upload_mbps": round(data["upload"]["bandwidth"] / 125000, 2),
                "ping_ms": round(data["ping"]["latency"], 2),
                "server": data["server"]["name"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except json.JSONDecodeError:
            return {"error": "Invalid JSON output from Speedtest CLI"}
        except subprocess.TimeoutExpired:
            return {"error": "Speedtest CLI timed out after 60 seconds"}
        except FileNotFoundError:
            return {"error": "speedtest.exe not found"}
        except Exception as e:
            return {"error": f"Speedtest CLI error: {str(e)}"}

    def run_speedtest(self) -> Dict[str, Any]:
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            result = self._run_speedtest_cli()
            if "error" not in result:
                return result
            else:
                last_error = result["error"]
                time.sleep(3)

        return {"error": last_error or "Speed test failed after 3 attempts"}

    def _is_valid_ipv4(self, ip: str) -> bool:
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False

    def _is_cache_valid(self, key: str) -> bool:
        return (key in self._cache and
                key in self._cache_timeout and
                time.time() < self._cache_timeout[key])


class NetworkDashboard:

    def __init__(self):
        self.monitor = NetworkMonitor()
        self.auto_refresh = True
        self.refresh_interval = 10
        self.page = None

    def main(self, page: ft.Page):
        self.page = page
        self.setup_page()
        self.create_ui_elements()
        self.setup_layout()
        self.start_auto_refresh()
        self.refresh_network_info()

    def setup_page(self):
        self.page.title = "Network Monitor Dashboard"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.maximizable = False
        self.page.window.resizable = False
        self.page.padding = 15
        self.page.window.width = 695
        self.page.window.height = 1000
        
        self.page.scroll = ft.ScrollMode.AUTO
        self.page.on_close = self.on_page_close

    def create_ui_elements(self):
        self.header_icon = ft.Icon(ft.Icons.LAN, size=32, color="#61dafb")
        self.header_title = ft.Text(
            "Network Monitor Dashboard",
            size=28,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE
        )

        self.auto_refresh_switch = ft.Switch(
            label="Auto Refresh",
            value=True,
            on_change=self.toggle_auto_refresh
        )

        self.public_ip_card = self.create_info_card("Public Network", [])
        self.interface_cards = []

        self.target_host_field = ft.TextField(
            label="Target Host/IP",
            value="8.8.8.8",
            width=200,
            border_radius=8
        )

        self.ping_btn = ft.ElevatedButton(
            "Ping",
            icon=ft.Icons.NETWORK_CHECK,
            on_click=self.on_ping_click,
            style=self.get_button_style()
        )

        self.traceroute_btn = ft.ElevatedButton(
            "Traceroute",
            icon=ft.Icons.ROUTE,
            on_click=self.on_traceroute_click,
            style=self.get_button_style()
        )

        self.speedtest_btn = ft.ElevatedButton(
            "Speed Test",
            icon=ft.Icons.SPEED,
            on_click=self.on_speedtest_click,
            style=self.get_button_style()
        )

        self.refresh_btn = ft.ElevatedButton(
            "Refresh Now",
            icon=ft.Icons.REFRESH,
            on_click=self.on_refresh_click,
            style=self.get_button_style()
        )

        self.output_console = ft.TextField(
            label="Output / Logs",
            multiline=True,
            min_lines=15,
            max_lines=15,
            read_only=True,
            value="Network Monitor Dashboard initialized...\nWelcome! Use the buttons above to run network tests.",
            bgcolor="#000000",
            color="#43b581",
            border_color="#7289da",
            border_radius=8,
            text_style=ft.TextStyle(
                font_family="Consolas, 'Courier New', monospace",
                size=12
            )
        )

        self.last_update_text = ft.Text(
            "Last updated: Never",
            size=12,
            color=ft.Colors.GREY_400
        )

    def create_info_card(self, title: str, content: list, width: int = None):
        return ft.Container(
            content=ft.Column(
                [ft.Text(title, weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.WHITE)] + content,
                spacing=8
            ),
            padding=16,
            margin=8,
            border_radius=10,
            bgcolor="#2c2f33",
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=8,
                color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
                offset=ft.Offset(0, 2)
            ),
            width=width
        )

    def get_button_style(self):
        return ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            elevation=2
        )

    def setup_layout(self):
        header = ft.Row([
            self.header_icon,
            self.header_title,
            ft.Container(expand=True),
            self.auto_refresh_switch
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        self.network_overview = ft.Row(
            [self.public_ip_card],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
            wrap=True
        )

        tools_panel = ft.Container(
            content=ft.Row([
                self.target_host_field,
                self.ping_btn,
                self.traceroute_btn,
                self.speedtest_btn,
                self.refresh_btn
            ], spacing=12, wrap=True),
            padding=16,
            margin=ft.margin.symmetric(vertical=10),
            border_radius=10,
            bgcolor="#2c2f33",
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=4,
                color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
                offset=ft.Offset(0, 1)
            )
        )

        console_container = ft.Container(
            content=ft.Column([
                self.output_console,
                ft.Row([
                    self.last_update_text,
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Clear Console",
                        on_click=self.clear_console,
                        icon=ft.Icons.CLEAR
                    )
                ])
            ]),
            margin=ft.margin.symmetric(vertical=10)
        )

        self.page.add(
            ft.Column([
                header,
                ft.Divider(height=1, color="#99aab5"),
                ft.Text("Network Overview", size=18, weight=ft.FontWeight.BOLD),
                self.network_overview,
                ft.Text("Network Tools", size=18, weight=ft.FontWeight.BOLD),
                tools_panel,
                ft.Text("Console Output", size=18, weight=ft.FontWeight.BOLD),
                console_container
            ], spacing=15)
        )

    def refresh_network_info(self):
        try:
            network_info = self.monitor.get_network_info()
            gateway_info = self.monitor.get_default_gateway()
            dns_servers = self.monitor.get_dns_servers()
            public_ip = self.monitor.get_public_ip()

            gateway_ip = "N/A"
            if isinstance(gateway_info.get("ipv4"), tuple):
                gateway_ip = gateway_info["ipv4"][0]

            public_content = [
                ft.Row([
                    ft.Icon(ft.Icons.PUBLIC, size=16, color="#43b581"),
                    ft.Text(f"Public IP: {public_ip or 'Unavailable'}", size=14, color=ft.Colors.WHITE)
                ]),
                ft.Row([
                    ft.Icon(ft.Icons.DNS, size=16, color="#f39c12"),
                    ft.Text(f"DNS: {', '.join(dns_servers[:2]) if dns_servers else 'N/A'}", size=14, color=ft.Colors.WHITE)
                ])
            ]

            self.public_ip_card.content = ft.Column(
                [ft.Text("Public Network Info", weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.WHITE)] + public_content,
                spacing=8
            )

            self.interface_cards.clear()
            if isinstance(network_info, dict) and "error" not in network_info:
                for iface_name, iface_info in network_info.items():
                    current_gateway_ip = None
                    if isinstance(gateway_info.get("ipv4"), tuple) and gateway_info["ipv4"][1] == iface_name:
                        current_gateway_ip = gateway_info["ipv4"][0]

                    self.create_interface_card(iface_name, iface_info, gateway=current_gateway_ip)

            all_cards = [self.public_ip_card] + self.interface_cards
            self.network_overview.controls = all_cards

            current_time = time.strftime("%H:%M:%S")
            self.last_update_text.value = f"Last updated: {current_time}"

            self.page.update()

        except Exception as e:
            self.add_console_output(f"Error refreshing network info: {str(e)}")

    def create_interface_card(self, name: str, info: dict, gateway: str = None):
        status_color = "#43b581" if info.get("is_up") else "#f04747"
        is_wifi = any(keyword in name.lower() for keyword in ["wi-fi", "wireless", "wlan"])
        status_icon = ft.Icons.WIFI if is_wifi else ft.Icons.CABLE

        content = [
            ft.Row([
                ft.Icon(status_icon, size=16, color=status_color),
                ft.Text(f"Status: {info.get('status', 'Unknown')}",
                        color=status_color,
                        weight=ft.FontWeight.W_500)
            ]),
            ft.Divider(height=5, color="#99aab5"),
        ]

        if info.get("ipv4") and info.get("is_up"):
            content.append(ft.Text(f"IPv4: {info.get('ipv4')}", size=12, color=ft.Colors.WHITE))
            if info.get("subnet_mask"):
                content.append(ft.Text(f"Subnet: {info.get('subnet_mask')}", size=12, color=ft.Colors.WHITE))

        if info.get("ipv6") and info.get("is_up"):
            content.append(ft.Text(f"IPv6: {info.get('ipv6')}", size=12, color=ft.Colors.WHITE))

        if info.get("mac"):
            content.append(ft.Text(f"MAC: {info.get('mac')}", size=12, color=ft.Colors.WHITE))

        if gateway and info.get("is_up"):
            content.append(ft.Text(f"Gateway: {gateway}", size=12, color=ft.Colors.WHITE))

        card = self.create_info_card(name, content, width=300)
        self.interface_cards.append(card)

    def add_console_output(self, message: str):
        # Filter out internal noise — silence it completely
        if "Auto-refresh task error" in message or "Event loop is closed" in message:
            return

        timestamp = time.strftime("%H:%M:%S")
        self.output_console.value += f"\n[{timestamp}] {message}"
        self.page.update()

    def clear_console(self, e):
        self.output_console.value = "Console cleared."
        self.page.update()

    def toggle_auto_refresh(self, e):
        self.auto_refresh = e.control.value
        status = "enabled" if self.auto_refresh else "disabled"
        self.add_console_output(f"Auto refresh {status}")

    def start_auto_refresh(self):
        def refresh_loop():
            while True:
                if self.auto_refresh:
                    try:
                        self.page.run_task(self.refresh_network_info)
                    except Exception as e:
                        pass  # Ignore — handled by UI thread safety
                time.sleep(self.refresh_interval)

        refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        refresh_thread.start()

    def on_ping_click(self, e):
        host = self.target_host_field.value or "8.8.8.8"
        self.add_console_output(f"Starting ping to {host}...")

        def run_ping():
            try:
                result = self.monitor.ping_host(host, count=4)
                self.add_console_output(f"Ping Results:\n{result}")
            except Exception as error:
                self.add_console_output(f"Ping failed: {str(error)}")

        threading.Thread(target=run_ping, daemon=True).start()

    def on_traceroute_click(self, e):
        host = self.target_host_field.value or "8.8.8.8"
        self.add_console_output(f"Starting traceroute to {host}...")

        def run_traceroute():
            try:
                result = self.monitor.traceroute_host(host)
                self.add_console_output(f"Traceroute Results:\n{result}")
            except Exception as error:
                self.add_console_output(f"Traceroute failed: {str(error)}")

        threading.Thread(target=run_traceroute, daemon=True).start()

    def on_speedtest_click(self, e):
        self.add_console_output("Starting speed test... (this may take a moment)")

        def run_speedtest():
            try:
                result = self.monitor.run_speedtest()
                if "error" in result:
                    self.add_console_output(f"Speed test failed: {result['error']}")
                else:
                    output = f"""Speed Test Results:
Download: {result['download_mbps']} Mbps
Upload: {result['upload_mbps']} Mbps
Ping: {result['ping_ms']} ms
Server: {result['server']}
Time: {result['timestamp']}"""
                    self.add_console_output(output)
            except Exception as error:
                self.add_console_output(f"Speed test failed: {str(error)}")

        threading.Thread(target=run_speedtest, daemon=True).start()

    def on_refresh_click(self, e):
        self.add_console_output("Manually refreshing network information...")
        self.refresh_network_info()

    def on_page_close(self, e):
        self.add_console_output("Shutting down network monitor...")
        self.auto_refresh = False


def main(page: ft.Page):
    dashboard = NetworkDashboard()
    dashboard.main(page)


if __name__ == "__main__":
    ft.app(target=main)
