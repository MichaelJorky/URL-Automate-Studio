import requests
import socket
import json
import os
import random
import time
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIGURATION =================
MAX_THREADS = 15 
TIMEOUT_VAL = 10

# LOCK UNTUK FILE OPERATION (PENTING AGAR TIDAK BENTROK ANTAR THREAD)
FILE_LOCK = threading.Lock()
PROXY_FILE_PATH = os.path.join("locales", "_proxies.txt")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

def log_to_delphi(status_type, msg, url, proxy_info, http_code=0, is_raw=False):
    data = {
        "type": status_type,
        "timestamp": time.strftime("%H:%M:%S"),
        "url": url,
        "msg": msg,
        "proxy": proxy_info,
        "http_code": http_code,
        "raw_log": is_raw
    }
    print(json.dumps(data), flush=True)

# ================= FILE MANAGEMENT LOGIC (NEW) =================

def ensure_unique_proxies():
    """Membersihkan duplikat saat start"""
    with FILE_LOCK:
        if not os.path.exists(PROXY_FILE_PATH): return
        try:
            with open(PROXY_FILE_PATH, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Gunakan set untuk menghapus duplikat
            unique_lines = list(set(lines))
            
            # Tulis ulang hanya jika ada perubahan jumlah baris
            if len(unique_lines) != len(lines):
                with open(PROXY_FILE_PATH, "w") as f:
                    f.write("\n".join(unique_lines))
        except: pass

def add_proxy_to_file(proxy_str):
    """Menambahkan proxy valid (dari API) ke file lokal"""
    with FILE_LOCK:
        try:
            # Baca dulu agar tidak duplikat
            current_proxies = []
            if os.path.exists(PROXY_FILE_PATH):
                with open(PROXY_FILE_PATH, "r") as f:
                    current_proxies = [line.strip() for line in f if line.strip()]
            
            if proxy_str not in current_proxies:
                with open(PROXY_FILE_PATH, "a") as f:
                    f.write(f"\n{proxy_str}")
        except: pass

def remove_proxy_from_file(proxy_str):
    """Menghapus proxy mati dari file lokal"""
    with FILE_LOCK:
        try:
            if not os.path.exists(PROXY_FILE_PATH): return
            
            with open(PROXY_FILE_PATH, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
            
            if proxy_str in lines:
                lines.remove(proxy_str)
                # Tulis ulang file tanpa proxy yg mati
                with open(PROXY_FILE_PATH, "w") as f:
                    f.write("\n".join(lines))
        except: pass

# ================= PROXY LOGIC =================
def validate_proxy(proxy_str):
    """Cek koneksi ke ipify.org"""
    try:
        p_dict = {"http": f"http://{proxy_str}", "https": f"http://{proxy_str}"} if "://" not in proxy_str else {"http": proxy_str, "https": proxy_str}
        
        start_t = time.time()
        # Timeout validasi 4 detik
        r = requests.get("https://api.ipify.org", headers=get_headers(), proxies=p_dict, timeout=4)
        
        if r.status_code == 200:
            return p_dict, f"Active ({r.text.strip()}) - {round(time.time()-start_t, 2)}s"
    except:
        pass
    return None, None

def get_best_topology_proxy():
    logs = []
    
    # 1. Cek Local Tools (Prioritas Utama - Tidak dihapus file, krn ini apps lain)
    ports = [(8080, "http://127.0.0.1:8080"), (1080, "socks5://127.0.0.1:1080")]
    for port, url in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                p_dict, status = validate_proxy(url)
                if p_dict: return p_dict, f"Local Tool (Port {port})", logs
            sock.close()
        except: pass

    # 2. Cek File Proxy (locales/_proxies.txt)
    # Loop proxy acak, jika mati -> Hapus dari file
    try:
        if os.path.exists(PROXY_FILE_PATH):
            with open(PROXY_FILE_PATH, "r") as f:
                proxies = [line.strip() for line in f if line.strip()]
            
            if proxies:
                logs.append(f"Checking File Proxy ({len(proxies)} available)...")
                attempts = 0
                max_attempts = 15 # Jangan terlalu lama looping
                
                # Kita copy list agar aman saat remove dari list utama di memori
                candidates = random.sample(proxies, min(len(proxies), max_attempts))
                
                for px in candidates:
                    p_dict, status = validate_proxy(px)
                    if p_dict:
                        return p_dict, "Local File", logs
                    else:
                        # === LOGIC HAPUS PROXY MATI ===
                        # logs.append(f"Removing dead proxy: {px}") 
                        remove_proxy_from_file(px)
    except: pass

    # 3. Cek Free API (Proxyscrape)
    # Jika hidup -> Tambah ke file
    try:
        logs.append("Checking Free API...")
        url = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=2000&country=all&ssl=all&anonymity=all"
        r = requests.get(url, headers=get_headers(), timeout=5)
        if r.status_code == 200:
            proxies = r.text.splitlines()
            logs.append(f"API returned {len(proxies)} proxies. Validating...")
            
            valid_candidates = [p for p in proxies if ":" in p]
            if valid_candidates:
                random.shuffle(valid_candidates)
                # Coba 20 biji dari API
                for px in valid_candidates[:30]: 
                    p_dict, status = validate_proxy(px)
                    if p_dict:
                        # === LOGIC SIMPAN PROXY HIDUP ===
                        # logs.append(f"Harvested new proxy: {px}")
                        add_proxy_to_file(px) 
                        return p_dict, "Free API (Harvested)", logs
    except Exception as e: logs.append(f"API Error: {str(e)}")
    
    logs.append("All proxies failed. Fallback to DIRECT.")
    return None, "DIRECT CONNECTION", logs

# ================= CORE PROCESS =================
def simple_ping(url):
    try:
        domain = url.split("//")[-1].split("/")[0]
        requests.get(f"http://{domain}", timeout=3, headers=get_headers())
        return "Ping OK"
    except: return "Ping Failed"

def process_check(redirect_template, target_url):
    final_url = redirect_template.replace("[URL]", target_url)
    
    # Ambil proxy (dengan fitur auto-clean/auto-add)
    proxy_dict, proxy_source, proxy_logs = get_best_topology_proxy()
    
    # Log Checking
    log_msg = f"Checking: {final_url} using {proxy_source}"
    log_to_delphi("log", log_msg, final_url, proxy_source, 0, True)

    status_msg = "Unknown"
    http_code = 0
    ping_result = "-"

    try:
        response = requests.get(final_url, headers=get_headers(), proxies=proxy_dict, timeout=TIMEOUT_VAL)
        http_code = response.status_code
        if http_code == 200:
            status_msg = "OK / Found"
            ping_result = simple_ping(final_url)
        else:
            status_msg = f"HTTP {http_code}"
    except Exception as e:
        status_msg = f"Error: {type(e).__name__}"

    full_msg = f"{status_msg} | {ping_result}"
    log_to_delphi("result", full_msg, final_url, proxy_source, http_code, False)

def main():
    # 0. Bersihkan duplikat di file proxy saat awal jalan
    ensure_unique_proxies()
    
    # 1. Ambil Argumen
    input_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    target_urls = []
    
    if input_arg.strip() != "":
        target_urls = [input_arg.strip()]
    else:
        log_to_delphi("log", "Reading assets/_website.txt...", "System", "None", 0, True)
        website_file = os.path.join("assets", "_website.txt")
        if os.path.exists(website_file):
            with open(website_file, "r") as f:
                target_urls = [line.strip() for line in f if line.strip()]
        
        if not target_urls:
             log_to_delphi("error", "No URL source found!", "", "None", 0, True)
             return

    redirect_file = os.path.join("assets", "_urlredirect.txt")
    if not os.path.exists(redirect_file):
        log_to_delphi("error", "Redirect file missing!", "", "None", 0, True)
        return
        
    with open(redirect_file, "r") as f:
        redirect_templates = [line.strip() for line in f if line.strip()]

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        for target in target_urls:
            log_to_delphi("log", f"=== TARGET: {target} ===", target, "System", 0, True)
            futures = [executor.submit(process_check, tmpl, target) for tmpl in redirect_templates]
            for future in futures: future.result()

if __name__ == "__main__":
    main()