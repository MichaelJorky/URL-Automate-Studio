import sys
import json
import time
import random
import urllib.parse
import os
import requests
import re
import asyncio
import base64

# ============================================
# 1. SETUP & DEPENDENCIES
# ============================================
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Menginstall library yang kurang...", flush=True)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "beautifulsoup4", "requests"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright

from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ============================================
# 2. KONFIGURASI
# ============================================
CAPTCHA_SOLVER_URL = "http://127.0.0.1:80/gsa_test.gsa" 
#CAPTCHA_API_URL = "http://127.0.0.1:80/in.php" 

# ============================================
# 3. UTILITY TEXT CLEANER
# ============================================
def clean_text(text):
    if not text: return text
    try: text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    except: pass
    try: text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    except: pass
    try: text = ' '.join(text.split())
    except: pass
    return text.strip()

builtin_print = __builtins__.print if isinstance(__builtins__, dict) else __builtins__.print
def safe_print(*args, **kwargs):
    kwargs['flush'] = True 
    try:
        cleaned = [clean_text(arg) if isinstance(arg, str) else arg for arg in args]
        return builtin_print(*cleaned, **kwargs)
    except:
        try: return builtin_print(*args, **kwargs)
        except: pass
sys.modules[__name__].print = safe_print
__builtins__.print = safe_print

# ============================================
# 4. DOMAIN MANAGEMENT
# ============================================
def normalize_url(url):
    if not url: return ""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip('/')
    if netloc.startswith('www.'): netloc = netloc[4:]
    return f"{scheme}://{netloc}{path}"

def get_domain_key(url):
    if not url: return ""
    parsed = urlparse(url.strip().lower())
    netloc = parsed.netloc
    if ':' in netloc: netloc = netloc.split(':')[0]
    if netloc.startswith('www.'): netloc = netloc[4:]
    return netloc

def is_search_engine_url(url):
    if not url: return False
    search_engine_keywords = [
        'google', 'bing', 'yahoo', 'duckduckgo', 'yandex',
        'brave', 'startpage', 'ecosia', 'you.com', 'baidu',
        'naver', 'qwant', 'wikipedia', 'swisscows', 'cangkok',
        'seznam', 'ask', 'dogpile', 'aol', 'gibiru', 'excite',
        'info.com', 'metacrawler', 'webcrawler', 'daum',
        'search.ch', 'plipeo', 'gigablast'
    ]
    domain_key = get_domain_key(url)
    for keyword in search_engine_keywords:
        if keyword in domain_key:
            url_lower = url.lower()
            if not any(param in url_lower for param in ['url=', 'redirect=', 'link=']):
                serp_patterns = ['/search', '?q=', '&q=', 'query=', 'search?', 'serp', 'results']
                if any(pattern in url_lower for pattern in serp_patterns):
                    return True
    return False

class DomainTracker:
    def __init__(self, max_per_domain=2):
        self.max_per_domain = max_per_domain
        self.domain_counter = {}
        self.processed_urls = set()
    
    def can_add_url(self, url):
        if not url: return False
        norm_url = normalize_url(url)
        if norm_url in self.processed_urls: return False
        if is_search_engine_url(url) and 'url=' not in url.lower(): return False
        domain_key = get_domain_key(url)
        current_count = self.domain_counter.get(domain_key, 0)
        if current_count >= self.max_per_domain: return False
        return True
    
    def add_url(self, url):
        if not url: return False
        norm_url = normalize_url(url)
        if norm_url in self.processed_urls: return False
        domain_key = get_domain_key(url)
        self.domain_counter[domain_key] = self.domain_counter.get(domain_key, 0) + 1
        self.processed_urls.add(norm_url)
        return True
    
    def get_domain_count(self, url):
        domain_key = get_domain_key(url)
        return self.domain_counter.get(domain_key, 0)

def filter_results_by_domain(results, max_per_domain=2):
    if not results: return []
    domain_groups = {}
    for result in results:
        url = result.get('url', '')
        if not url: continue
        domain_key = get_domain_key(url)
        if domain_key not in domain_groups: domain_groups[domain_key] = []
        domain_groups[domain_key].append(result)
    
    filtered_results = []
    for domain, domain_results in domain_groups.items():
        root_results = []
        path_results = []
        for result in domain_results:
            url = result.get('url', '')
            parsed = urlparse(url)
            if not parsed.path or parsed.path in ('', '/'): root_results.append(result)
            else: path_results.append(result)
        
        selected = []
        for result in path_results[:max_per_domain]: selected.append(result)
        remaining = max_per_domain - len(selected)
        if remaining > 0 and root_results:
            root_results.sort(key=lambda x: 0 if x.get('url', '').startswith('https') else 1)
            selected.append(root_results[0])
        filtered_results.extend(selected)
    return filtered_results

domain_tracker = DomainTracker(max_per_domain=2)

# ============================================
# 5. SISTEM PROXY
# ============================================
used_proxies = []
current_proxy_index = 0

def validate_proxy(proxy, source_name):
    print(f"[Info Proxy] Mengecek {source_name}: {proxy}...")
    try:
        r = requests.get("https://api.ipify.org", proxies={"http": f"http://{proxy}", "https": f"http://{proxy}"}, timeout=8)
        if r.status_code == 200:
            ip = clean_text(r.text.strip())
            print(f"[Info Proxy] SUKSES! IP Terbaca: {ip}")
            return ip
    except Exception as e:
        print(f"[Info Proxy] GAGAL ({source_name}): {e}")
        return None
    return None

def fetch_psiphon_proxy():
    for port in [8080, 1080]:
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                sock.close()
                return f"127.0.0.1:{port}"
        except: continue
    return None

def load_local_proxies():
    try:
        base_path = os.getcwd()
        file_path = os.path.join(base_path, "locales", "_proxies.txt")
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return [l.strip() for l in f if ":" in l]
        return []
    except: return []

def get_working_proxy(engine_name=None):
    print("--- MULAI PENGECEKAN PROXY ---")
    proxy = fetch_psiphon_proxy()
    if proxy:
        if validate_proxy(proxy, "Local Tool"): return proxy, f"{proxy} (Local Tool)"
    else:
        print("[Info Proxy] Local Tool tidak aktif.")

    locals_p = load_local_proxies()
    if locals_p:
        global current_proxy_index, used_proxies
        if not used_proxies: current_proxy_index = 0
        proxy = locals_p[current_proxy_index % len(locals_p)]
        current_proxy_index += 1
        used_proxies.append(proxy)
        
        if validate_proxy(proxy, "File Local"):
            return proxy, f"{proxy} (File Local)"
    else:
        print("[Info Proxy] File locales/_proxies.txt kosong/tidak ada.")

    try:
        print("[Info Proxy] Mencoba Free API ProxyScrape...")
        url = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&format=text&anonymity=Elite&timeout=20"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            lines = r.text.splitlines()
            for line in lines[:3]:
                p = line.replace("http://", "").strip()
                if validate_proxy(p, "Free API"): return p, f"{p} (Free API)"
    except Exception as e: 
        print(f"[Info Proxy] API Error: {e}")

    print("[Info Proxy] Menggunakan koneksi DIRECT (Tanpa Proxy).")
    return None, "Direct (No Proxy)"

# ============================================
# 6. PLAYWRIGHT & HUMAN ACTIONS (UPDATED)
# ============================================
async def apply_stealth(page):
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    await page.add_init_script("window.chrome = {runtime: {}}")
    await page.add_init_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]})")
    await page.add_init_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")

async def human_actions(page):
    print("[Human Act] Menggerakkan mouse dan scrolling...", flush=True)
    try:
        viewport = page.viewport_size
        if not viewport:
            w, h = 1920, 1080
        else:
            w, h = viewport['width'], viewport['height']

        await page.mouse.move(w / 2, h / 2, steps=10)
        
        for i in range(random.randint(5, 7)):
            rand_x = random.randint(100, w - 100)
            rand_y = random.randint(100, h - 100)
            
            await page.mouse.move(rand_x, rand_y, steps=random.randint(15, 30))
            scroll_amount = random.randint(300, 700)
            await page.mouse.wheel(0, scroll_amount)
            
            await asyncio.sleep(random.uniform(0.8, 2.0))
            
        print("[Human Act] Selesai scrolling.", flush=True)
            
    except Exception as e: 
        print(f"[Human Act] Error: {e}", flush=True)

async def solve_captcha_gsa(page):
    print("[CAPTCHA] Mendeteksi captcha...")
    try:
        captcha_img = None
        selectors = ["img[src*='captcha']", "img[alt='captcha']", "#captcha_image", ".captcha-img", "#recaptcha_image"]
        
        for sel in selectors:
            if await page.locator(sel).count() > 0 and await page.locator(sel).is_visible():
                captcha_img = page.locator(sel).first
                break
        
        if not captcha_img:
            if await page.locator("iframe[src*='recaptcha']").count() > 0:
                print("[CAPTCHA] Terdeteksi reCAPTCHA Google.")
            return False

        img_bytes = await captcha_img.screenshot()
        print(f"[CAPTCHA] Mengirim ke GSA ({CAPTCHA_SOLVER_URL})...")
        files = {'file': ('captcha.png', img_bytes, 'image/png')}
        data = {'action': 'decaptcher'}
        
        try:
            res = requests.post(CAPTCHA_SOLVER_URL, files=files, data=data, timeout=10)
            answer = res.text.strip()
            
            if res.status_code == 200 and answer and "ERROR" not in answer.upper():
                print(f"[CAPTCHA] Jawaban GSA: {answer}")
                input_selectors = ["input[name*='captcha']", "input[name*='code']", "input[type='text']"]
                for inp in input_selectors:
                    if await page.locator(inp).count() > 0:
                        await page.locator(inp).first.fill(answer)
                        await page.keyboard.press('Enter')
                        await asyncio.sleep(3)
                        return True
        except:
            print("[CAPTCHA] Gagal koneksi ke GSA Webserver.")

    except Exception as e:
        print(f"[CAPTCHA] Error: {e}")
    return False

# ============================================
# 7. URL GENERATOR
# ============================================
def get_search_url(engine, query, enc_query, num):
    urls = {
        'Google': f"https://www.google.com/search?q={enc_query}&num={num}&hl=en&gl=us",
        'Bing': f"https://www.bing.com/search?q={enc_query}&count={num}",
        'DuckDuckGo': f"https://duckduckgo.com/html/?q={enc_query}",
        'Brave Search': f"https://search.brave.com/search?q={enc_query}",
        'Startpage': f"https://www.startpage.com/do/dsearch?query={enc_query}",
        'Yahoo!': f"https://search.yahoo.com/search?p={enc_query}",
        'Yandex': f"https://yandex.com/search/?text={enc_query}",
        'Baidu': f"https://www.baidu.com/s?wd={enc_query}",
        'Wikipedia': f"https://en.wikipedia.org/w/index.php?search={enc_query}",
        'Ask.com': f"https://www.ask.com/web?q={enc_query}",
        'Seznam': f"https://search.seznam.cz/?q={enc_query}",
        'AOL Search': f"https://search.aol.com/aol/search?q={enc_query}",
        'Ecosia': f"https://www.ecosia.org/search?method=index&q={enc_query}",
        'You.com': f"https://you.com/search?q={enc_query}&tbm=youchat",
        'Naver': f"https://search.naver.com/search.naver?where=nexearch&sm=top_hty&ie=utf8&query={enc_query}",
        'Qwant': f"https://www.qwant.com/?q={enc_query}&t=web",
        'Swisscows': f"https://swisscows.com/en/web?query={enc_query}",
        'Cangkok': f"https://cangkok.com/id/search.php?no1=2&kk=0&rc=rinci&mcl=&milih={enc_query}&ok=&ok1=0&ok2=0&td=web&urut=&ab=&u2=&rk=&jml=50",
        'Dogpile': f"https://www.dogpile.com/serp?q={enc_query}",
        'Gibiru': f"https://gibiru.com/results.html?q={enc_query}",
        'Excite': f"https://results.excite.com/serp?q={enc_query}",
        'Info.com': f"https://www.info.com/serp?q={enc_query}",
        'MetaCrawler': f"https://www.metacrawler.com/serp?q={enc_query}",
        'WebCrawler': f"https://www.webcrawler.com/serp?q={enc_query}",
        'Daum Search': f"https://search.daum.net/search?w=tot&q={enc_query}",
        'search.ch': f"https://search.ch/tel/?all={enc_query}",
        'Plipeo': f"https://search.plipeo.com/search?q={enc_query}",
        'GigaBlast': f"https://gigablast.org/search/?q={enc_query}"
    }
    return urls.get(engine)

# ============================================
# 8. ADD RESULT
# ============================================
def add_result(res_list, title, url, engine, limit, proxy, max_per_domain=2):
    if len(res_list) >= limit or not url or not title: return
    if len(title) < 3: return
    if not domain_tracker.can_add_url(url): return
    
    norm_url = normalize_url(url)
    existing_urls = [normalize_url(item['url']) for item in res_list]
    if norm_url in existing_urls: return
    
    domain_key = get_domain_key(url)
    domain_count = domain_tracker.get_domain_count(url)
    parsed = urlparse(url)
    is_root_url = not parsed.path or parsed.path in ('', '/')
    
    if is_root_url:
        existing_root_urls = [
            item['url'] for item in res_list 
            if get_domain_key(item['url']) == domain_key and 
            (not urlparse(item['url']).path or urlparse(item['url']).path in ('', '/'))
        ]
        if existing_root_urls: return
    
    domain_tracker.add_url(url)
    clean_u = url.split('?')[0] if '?' in url and 'url=' not in url else url
    
    res_list.append({
        "judul": clean_text(title), 
        "url": clean_u, 
        "sumber": engine, 
        "proxy": proxy
    })
    print(f"  [{engine}] [{domain_count+1}/{max_per_domain}] {clean_text(title)[:50]}...")

# ============================================
# 9. IMPROVED PARSING FUNCTIONS
# ============================================
def parse_bing_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain):
    """Parse Bing results with multiple selectors"""
    # Method 1: Main Bing result structure
    for item in soup.select('li.b_algo'):
        h2 = item.select_one('h2 a')
        if h2:
            title = h2.text.strip()
            url = h2.get('href', '')
            if url and 'bing.com' not in url:
                add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)
    
    # Method 2: Alternative Bing structure
    for item in soup.select('a[target="_blank"]'):
        if item.get('href', '').startswith('http') and not item.get('href', '').startswith('https://www.bing.com'):
            parent = item.find_parent('li')
            if parent and 'b_algo' in parent.get('class', []):
                title = item.text.strip()
                url = item.get('href', '')
                if title and url:
                    add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)
    
    # Method 3: Direct anchor tags with specific attributes
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and 'bing.com' not in href:
            # Check if it's a search result (not navigation)
            parent_classes = a.find_parent().get('class', [])
            if any(cls in ['b_algo', 'b_title', 'b_caption'] for cls in parent_classes):
                title = a.text.strip()
                if len(title) > 10:
                    add_result(hasil, title, href, engine_name, jumlah, proxy_info, max_per_domain)

def parse_duckduckgo_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain):
    """Parse DuckDuckGo results with multiple selectors"""
    # Method 1: Main DuckDuckGo result structure
    for item in soup.select('a[data-testid="result-title-a"]'):
        title = item.text.strip()
        url = item.get('href', '')
        if url:
            add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)
    
    # Method 2: Span with specific class
    for span in soup.select('span.EKtkFWMYpwzMKOYr0GYm'):
        a_tag = span.find_parent('a')
        if a_tag and a_tag.get('href'):
            title = span.text.strip()
            url = a_tag['href']
            if url.startswith('http'):
                add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)

def parse_dogpile_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain):
    """Parse Dogpile results"""
    # Method 1: Anchor tags with specific class
    for a in soup.select('a.web-google__title'):
        title = a.text.strip()
        url = a.get('href', '')
        if url:
            add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)
    
    # Method 2: Generic fallback for Dogpile
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and 'dogpile.com' not in href:
            title = a.text.strip()
            if len(title) > 15:
                add_result(hasil, title, href, engine_name, jumlah, proxy_info, max_per_domain)

def parse_search_ch_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain):
    """Parse search.ch results"""
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Filter out internal links and only get external ones
        if href.startswith('http') and 'search.ch' not in href:
            title = a.text.strip()
            # For search.ch, the title might be in parent elements
            if len(title) < 5:
                parent = a.find_parent(['div', 'li'])
                if parent:
                    title = parent.get_text(strip=True)[:100]
            
            if len(title) > 10:
                add_result(hasil, title, href, engine_name, jumlah, proxy_info, max_per_domain)

def parse_baidu_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain):
    """Parse Baidu results"""
    for span in soup.select('span.tts-b-hl'):
        title = span.get_text(strip=True)
        # Find the link nearby
        parent = span.find_parent('a')
        if parent and parent.get('href'):
            url = parent['href']
            if url.startswith('http'):
                add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)
    
    # Alternative method for Baidu
    for a in soup.select('a[data-click]'):
        title = a.get_text(strip=True)
        url = a.get('href', '')
        if url.startswith('http') and len(title) > 10:
            add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)

def parse_brave_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain):
    """Parse Brave search results"""
    # Method 1: Div with title attribute
    for div in soup.find_all('div', attrs={'title': True}):
        if 'wikipedia' in div.get('title', '').lower():
            title = div['title']
            # Find the link
            a_tag = div.find('a')
            if a_tag and a_tag.get('href'):
                url = a_tag['href']
                add_result(hasil, title, url, engine_name, jumlah, proxy_info, max_per_domain)
    
    # Method 2: Citation with URL
    for cite in soup.select('cite.snippet-url'):
        url_text = cite.get_text(strip=True)
        if url_text.startswith('http'):
            # Find the title in previous sibling
            prev = cite.find_previous_sibling(['h3', 'div', 'a'])
            if prev:
                title = prev.get_text(strip=True)
                add_result(hasil, title, url_text, engine_name, jumlah, proxy_info, max_per_domain)

# ============================================
# 10. CORE SCRAPING
# ============================================
async def scrape_async(kata_kunci, jumlah, engine_name, max_per_domain=2):
    print(f"\n{'='*60}")
    print(f"SCRAPING: {engine_name} | KEYWORD: {kata_kunci}")
    print(f"{'='*60}")
    
    global domain_tracker
    domain_tracker = DomainTracker(max_per_domain=max_per_domain)
    hasil = []
    
    raw_proxy, proxy_info = get_working_proxy(engine_name)
    print(f"STATUS PROXY FINAL: {proxy_info}")
    
    p_config = None
    if raw_proxy:
        if '@' in raw_proxy:
            u_p, i_p = raw_proxy.split('@')
            p_config = {"server": f"http://{i_p}", "username": u_p.split(':')[0], "password": u_p.split(':')[1]}
        else:
            p_config = {"server": f"http://{raw_proxy}"}

    async with async_playwright() as p:
        args = [
            "--headless=new",
            "--disable-blink-features=AutomationControlled", 
            "--no-sandbox", 
            "--disable-extensions", 
            "--window-size=1366,768",
            "--window-position=0,0"
        ]
        
        print("Membuka browser (Playwright)...")
        try:
            browser = await p.chromium.launch(headless=True, args=args, proxy=p_config)
            
            await asyncio.sleep(2)

            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            context = await browser.new_context(user_agent=ua, viewport={'width':1920,'height':1080})
            page = await context.new_page()
            await apply_stealth(page)

            enc_q = urllib.parse.quote_plus(kata_kunci)
            url = get_search_url(engine_name, kata_kunci, enc_q, jumlah + 5)
            
            if not url: 
                print(f"Engine {engine_name} tidak valid.")
            else:
                print(f"Mengakses: {url}")
                for attempt in range(3):
                    try:
                        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
                        
                        title = await page.title()
                        content = await page.content()
                        if "captcha" in title.lower() or "bot" in title.lower() or "traffic" in content.lower():
                            print("!!! DETEKSI CAPTCHA !!!")
                            if await solve_captcha_gsa(page):
                                continue
                            else:
                                print("Gagal solve captcha.")
                        
                        print("Halaman berhasil dimuat.")
                        break
                    except Exception as e:
                        print(f"Retry {attempt+1}: {e}")
                        await asyncio.sleep(2)

                await human_actions(page)

                html = await page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                print("Memulai parsing data...")
                
                # Dispatch to specific parser based on engine
                if engine_name == 'Google':
                    for item in soup.select('div.g, div.tF2Cxc'):
                        h3 = item.select_one('h3')
                        a = item.select_one('a')
                        if h3 and a: 
                            add_result(hasil, h3.text, a['href'], engine_name, jumlah, proxy_info, max_per_domain)
                
                elif engine_name == 'Bing':
                    parse_bing_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain)
                
                elif engine_name == 'DuckDuckGo':
                    parse_duckduckgo_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain)
                
                elif engine_name == 'Dogpile':
                    parse_dogpile_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain)
                
                elif engine_name == 'search.ch':
                    parse_search_ch_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain)
                
                elif engine_name == 'Baidu':
                    parse_baidu_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain)
                
                elif engine_name == 'Brave Search':
                    parse_brave_results(soup, engine_name, jumlah, proxy_info, hasil, max_per_domain)
                
                # Fallback for other engines
                else:
                    print(f"Menggunakan Fallback Parser untuk {engine_name}...")
                    for a in soup.find_all('a', href=True):
                        if len(hasil) >= jumlah: break
                        href = a['href']
                        title = a.get_text(strip=True)
                        if href.startswith('http') and len(title) > 10:
                            # Skip search engine internal links
                            if not any(engine in href.lower() for engine in ['google', 'bing', 'duckduckgo', 'yandex']):
                                add_result(hasil, title, href, engine_name, jumlah, proxy_info, max_per_domain)

                # Apply domain filtering
                hasil = filter_results_by_domain(hasil, max_per_domain)
                print(f"Parsing selesai. Total: {len(hasil)}")

        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
        finally:
            print("Menutup browser dalam 10 detik...")
            await asyncio.sleep(10) 
            try: 
                await browser.close()
            except: 
                pass
            
    return json.dumps(hasil, indent=2, ensure_ascii=False)

def mulai_scrape(kata_kunci, jumlah, engine_name, max_per_domain=2):
    return asyncio.run(scrape_async(kata_kunci, jumlah, engine_name, max_per_domain))