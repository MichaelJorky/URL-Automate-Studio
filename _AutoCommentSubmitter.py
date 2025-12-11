import asyncio
import re
import json
import random
import os
import socket
import base64
import requests 
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from fake_useragent import UserAgent

# --- KONFIGURASI ---
MAX_THREADS = 10
TIMEOUT = 20000 # UBAH JADI 20000 (20 Detik) agar tidak menunggu kelamaan
MAX_RETRIES_PER_URL = 1
QUEUE_BUFFER_SIZE = 500 # Hanya menampung 500 URL di RAM, sisanya antri di Harddisk

# --- KONFIGURASI CAPTCHA SOLVER (GSA / CAPTCHA SNIPER) ---
CAPTCHA_ENABLED = True
#CAPTCHA_API_URL = "http://127.0.0.1:80/in.php" 
CAPTCHA_API_URL = "http://127.0.0.1:80/gsa_test.gsa"
CAPTCHA_API_KEY = "random" 

# --- KONFIGURASI FILTER ---
MAX_URLS_PER_DOMAIN = 1  # Batas maksimal URL per domain

# Daftar situs populer yang HARUS DIABAIKAN (Blacklist)
# Cukup tambah kata kuncinya saja disini, otomatis mencocokkan .google. / google.com / dll
IGNORED_KEYWORDS = [
    "4chan.org", "accuweather.com", "adobe.com", "alibaba.com", "aliexpress.com",
    "amazon.co.jp", "amazon.co.uk", "amazon.com", "amazon.de", "amazon.fr",
    "amazon.in", "amazon.it", "app.link", "archiveofourown.org", "ask.com",
    "aol.com", "aws.amazon.com", "baidu.com", "bbc.co.uk", "bbc.com",
    "bilibili.com", "bing.com", "bit.ly", "blackhatworld.com", "blibli.com", "bloomberg.com",
    "blogger.com", "blogspot.com", "bp.blogspot.com", "bukalapak.com",
    "canva.com", "cangkok.com", "chatgpt.com", "cloudflare.com", "cnn.com", "codeproject.com",
    "daum.net", "dailymail.co.uk", "dailymotion.com", "detik.com", "discord.com",
    "disneyplus.com", "docs.google.com", "dogpile.com", "doubleclick.net",
    "drive.google.com", "dropbox.com", "duckduckgo.com", "dzen.ru",
    "ebay.com", "ecosia.org", "en.wikipedia.org", "etsy.com", "excite.com",
    "fanfiction.net", "fandom.com", "facebook.com", "fb.com", "fb.watch",
    "flickr.com", "fmoviesz.to", "forbes.com", "foxnews.com", "gibiru.com",
    "gigablast.org", "github.com", "github.io", "githubusercontent.com",
    "gitlab.com", "globo.com", "google-analytics.com", "google.com",
    "google.co.id", "googleapis.com", "googleusercontent.com", "googlesyndication.com",
    "gstatic.com", "hanime.tv", "ibm.com", "icloud.com", "idntimes.com",
    "ikea.com", "ilovepdf.com", "imgur.com", "instructure.com", "info.com",
    "instagram.com", "jd.id", "kapanlagi.com", "kaskus.co.id", "kompas.com",
    "kumparan.com", "lazada.co.id", "line.me", "linkedin.com", "liputan6.com",
    "live.com", "marca.com", "max.com", "mediafire.com", "mediawiki.org", "medium.com",
    "merdeka.com", "microsoft.com", "microsoftonline.com", "myshopify.com", "mojoportal.com",
    "naver.com", "netflix.com", "noodlemagazine.com", "nytimes.com", "o-seznam.cz",
    "oath.com", "okezone.com", "openai.com", "oracle.com", "outlook.com", "ozon.ru",
    "page.link", "pastebin.com", "paypal.com", "pixiv.net", "pinterest.com", "plipeo.com", "plus.com",
    "primevideo.com", "qwant.com", "quora.com", "rakuten.co.jp", "reddit.com",
    "roblox.com", "rutube.ru", "scribd.com", "seznam.cz", "sharepoint.com", "shopify.com",
    "shopee.co.id", "shopee.com", "skype.com", "slideshare.net", "snapchat.com", "sociolla.com",
    "spotify.com", "startpage.com", "stackoverflow.com", "steampowered.com", "suara.com",
    "swisscows.com", "target.com", "telegram.org", "temu.com", "theguardian.com",
    "t.co", "tiktok.com", "tokopedia.com", "tribunnews.com", "tumblr.com",
    "twitch.tv", "uol.com.br", "uservoice.com", "vimeo.com", "wechat.com", "weather.com",
    "whatsapp.com", "walmart.com", "wikimedia.org", "wikipedia.org", "wikimediafoundation.org", "wildberries.ru", "wix.com",
    "wixsite.com", "wordpress.com", "wordpress.org", "wp.com", "x.com",
    "yahoo.com", "yahoo.co.jp", "yandex.ru", "ya.ru", "yimg.com", "you.com",
    "youtube.com", "youtu.be", "zalora.co.id", "zoom.us"
]

# Regex Pattern (Lengkap)
PATTERNS = {
    'open_form_text': re.compile(r'\b(add\s*(new|entry|comment|reply|review|message|to\s*guestbook)|new\s*(entry|comment|message|post)|write\s*(entry|comment|review|a\s*review)?|sign(\s*guestbook)?|leave\s*(a\s*)?(comment|reply|message|comments)|post\s*(comment|reply)|create\s*(post|entry)|reply|continue|next|open\s*form|show\s*(form|comment|reply)|submit\s*comment|compose|start\s*(writing|reply)|gwolle-gb-write|eintragen|schreiben|neuen\s*eintrag|ins gästebuch|laisser\s*un\s*commentaire|poster\s*un\s*commentaire|deja\s*un\s*comentario|isi\s*buku\s*tamu|tinggalkan\s*pesan)\b', re.IGNORECASE),
    'open_form_attr': re.compile(r'(open|toggle|show|add|write|reply|comment|guestbook|entry|compose|create|new[-_]?(post|entry)|form[-_]?(toggle|show)|apeboard|gwolle|gbook|zenfolio)', re.IGNORECASE),
    'email': re.compile(r'((account|sys(tem)?|login|user|contact|prim(ary)?|work|pers(onal)?|bus(iness)?|rec(overy)?|alt|notif(ication)?|gebruiker|benutzer|pengguna|alamat|indirizzo|endereco|adresse)?[-_.]?e?[-_]?mail([-_.](add?res(s|se)|dizhi|kontak|juso|utilisateur))?|surel|courriel|correo|youxiang|dianzi|imeil|mēru|posta(\s|_)?elettronica|cf6)', re.IGNORECASE),
    'website': re.compile(r'((social|github|insta|face|linked|you|tik|shop|blog|port|prof|comp|pers|land|targ|call|end|api|canon|ext)[a-z]*[-_]?(url|link|site|page)|web(site|seite|saito|usaito|_?link|_?url)?|u~ebu|situs|sito|sitio|wang(zhi|zhan|luo)|tautan|halaman|lien|enlace|lianjie|rinku|sāto|indirizzo|direccion|endereco|homepage|url|link|site|icq|betreff|subject)', re.IGNORECASE),
    'location': re.compile(r'((geo|map|google|pin|current|lokasi|tempat)?[-_.]?(location|place|point|pos|loca(tie|lizacao|lisation)|ubicacion|posizione|didian|basho|jisang)|(full|street)?[-_.]?(add?res(s|se)?|alamat|dizhi|juso|j[uū]sho|indirizzo|direccion|endereco)|(city|town|machi|chengshi|dosi|kota|kabupaten|cidade|ciudad|ville|citta|stad(t)?|state|provin[a-z]*|regio[a-z]*|bundesland|wilayah|quyu|shengfen|chiiki|guojia|gugga|kuni|land|pais|pays|paese|negara)|(street|rua|rue|calle|via|strasse|straat|jalan)|(zip|postal|code|cep|plz|cap|youbian|kode_pos|coord|lat|long|lintang|bujur)|cf15|from)', re.IGNORECASE),
    'message': re.compile(r'((chat|support|ticket|bug|issue|dm|reply|user|your|votre|tuo|isi|kirim)?_?mess(age|aggio|eeji|iji)|mensaj(e|es)|mensagem|nachricht|bericht|pesan(_?kamu)?|xinxi|liuyan|comm?ent(s|aire|o|ario)?|komenta?r|komento|not(e|es|iz)|feedback|sugg?est(ion)?|masukan|saran|tanggapan|descri(p(tion|cion)|zione)|deskripsi|beschr(eibung|ijving)|setsumei|seolmyeong|miaoshu|keterangan|solicitud|demande|pedido|request|inquir(y|ies)|report|meldung|avis|geomjeung|gwolle|tribute|kide|cf12|cmt|body|inh(alt|oud)|conten(t|u|ido|udo)|neirong|naeyong|naiyou|(input|reply)?_?text)', re.IGNORECASE),
    'submit': re.compile(r'((cta|action|primary|call_to|form|tombol)?[-_]?(submit|send(en)?|save|post|go|apply|add|upload|unggah|publish|kirim|simpan|lanjut|selesai|konfirmasi|env(iar|oyer)|guardar|continu(e|ar|er|a)|finaliz(e|ar)|valid(er|ate)|invia|salv(a|ar)|conferma|speichern|weiter|bestätigen|verzenden|opslaan|doorgaan|bevestigen|sōshin|okuru|kakunin|jeon(song|송)|hwagin|tijiao|fasong|queren|complete|proceed|finish|next|sbmtb|eintragen)([-_]?(btn|button|now|form|to_next))?)', re.IGNORECASE),
    'phone': re.compile(r'((user|contact|emer(gency)?|alt(ernate)?|sec(ondary)?|office|work|home|pers(onal)?|prim(ary)?|call)[-_.]?(phone|num(ber)?|no)|(cell|hand|tele)?phone([-_. ]?(no|num(ber)?))?|mobile([-_. ]?(no|num(ber)?))?|tel(ephone)?([-_. ]?(no|num(ber)?))?|(nomor|no)[-_.]?(hp|telp|telepon)|(wa|whatsapp)([-_. ]?(no|num(ber)?))?|\bhp\b)', re.IGNORECASE),
    'password': re.compile(r'((user|login|acc(ount)?|sec(ure|ret|urity)?|new|curr(ent)?|old|confirm|repeat|retype|verify|auth|access)?[-_.]?(pass(word|wd|code)?|pwd)|(access|auth)[-_.]?(code|key)|\bpin\b)', re.IGNORECASE),
    'captcha_input': re.compile(r'(captcha([-_. ]?(code|val(ue)?|text|ans(wer)?|resp(onse)?|token(_?input)?|sol(ution)?|verif(ication)?|entry|(user_?)?input))?|verif(y|ication)([-_. ]?code)?|robot|secnum|phrase|math|security|kode)', re.IGNORECASE),
    'captcha_img': re.compile(r'(captcha([-_. ]?(img|image|pic|pho(to)?|render|svg|canvas|media|chal(lenge)?|url(_img)?|prev(iew)?|sprite|audio|video))?|sec|random|verify|image)', re.IGNORECASE),
    'success': re.compile(r'(thank you|thanks|success|saved|added|submitted|posted|in moderation|awaiting moderation|message sent|comment submitted|your comment has been posted|terima kasih|sukses|berhasil|tersimpan|ditambahkan|komentar terkirim|komentar menunggu moderasi|gracias|éxito|guardado|enviado|publicado|comentario enviado|obrigado|sucesso|salvo|merci|succès|enregistré|ajouté|envoyé|danke|erfolg|gespeichert|gesendet|hinzugefügt|grazie|successo|salvato|inviato|pubblicato|bedankt|succes|opgeslagen|verzonden|спасибо|успех|сохранено|отправлено|добавлено|شكرا|تم بنجاح|تم الحفظ|تم الإرسال|谢谢|成功|已保存|已发送|已提交|謝謝|已儲存|已送出|ありがとうございます|成功しました|保存しました|送信されました|감사합니다|성공|저장되었습니다|전송되었습니다|धन्यवाद|सफल|सहेजा गया|भेजा गया|teşekkürler|başarılı|kaydedildi|gönderildi|cám ơn|thành công|đã lưu|đã gửi|salamat|tagumpay|na-save|naipadala|ขอบคุณ|สำเร็จ|บันทึกแล้ว|ส่งแล้ว)', re.IGNORECASE),
    'error': re.compile(r'(captcha (incorrect|mismatch|failed|salah|incorrecto|incorreto|falsch|errato|bị chặn)|(incorrect|wrong|invalid) (captcha|code)|(verification|security check) failed|robot detected|are you a robot|spam|banned|blocked|blacklisted|denied|failure|gagal verifikasi|kode (salah|tidak sesuai)|tidak valid|dilarang|bloqueado|denegado|falha|erro|refusé|ungültiger|gesperrt|blockiert|non valido|mislukt|geblokkeerd|ошибка|заблокировано|отклонено|خطأ|فشل|مرفوض|错误|失败|被封锁|封鎖|エラー|禁止|오류|차단됨|त्रुटि|विफल|अवरुद्ध|hatalı|başarısız|engellendi|không đúng|thất bại|ไม่ถูกต้อง|ล้มเหลว|error|failed|invalid)', re.IGNORECASE),
    'cookie_accept': re.compile(r'(accept(\s*all)?|allow(\s*all)?|agree|consent|cookie|ok|got it|i understand|alle(\s*akzeptieren)?|akzeptieren|zustimmen|verstanden|accepter|tout accepter|autoriser|setuju|izinkan|terima|save(\s*settings)?|speichern)', re.IGNORECASE),
    'negative_content': re.compile(r'(casino|poker|porn||viagra|slot|gacor|togel)', re.IGNORECASE)
}

# --- DEFINISI REGEX NAMA (DIPECAH 3 AGAR AKURAT) ---
# 1. KHUSUS FIRST NAME (Nama Depan)
PATTERNS_FIRSTNAME = re.compile(r'((first|given|fore|depan|vor|voor|prenom|mingzi|namae)[-_.]?name|nama[-_.]?depan|vorname|voornaam|prenom)', re.IGNORECASE)

# 2. KHUSUS LAST NAME (Nama Belakang/Keluarga)
PATTERNS_LASTNAME = re.compile(r'((last|sur|family|belakang|nach|achter|cognom|apellid|sobrenome|xing)[-_.]?name|nama[-_.]?(belakang|keluarga)|nachname|achternaam|familiem?naam)', re.IGNORECASE)

# 3. NAMA UMUM / FULL NAME (Sapu Jagat)
PATTERNS_FULLNAME = re.compile(r'((full|display|nick|user|pen|real|legal|preferred|profile|contact|voll|benutzer|nom(bre|e)?|nama(_?lengkap)?|shimei|seimei|ireum|seongham|xingming)?[-_.]?name|nama|nom(_?(completo|t))?|author|writer|penulis|pengguna|auteur|autore|persona|alias|pilmyeong|biaoqianming|gwolle_gb_|cf1\b)', re.IGNORECASE)

# --- HELPER FUNCTIONS ---
def log_to_delphi(status, url, message, data=None):
    output = {"status": status, "url": url, "msg": message, "data": data or {}}
    print(json.dumps(output), flush=True)

def load_list(path_to_file):
    """Fungsi load asset (kecil) ke memori"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, path_to_file)
    if not os.path.exists(full_path): return []
    try:
        # errors='ignore' mencegah crash jika ada karakter aneh di file asset
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def count_file_lines(path_to_file):
    """Menghitung total baris file target valid (mengabaikan baris kosong)"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, path_to_file)
    if not os.path.exists(full_path): return 0
    count = 0
    try:
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # PERBAIKAN: Hanya hitung jika baris tidak kosong
                if line.strip(): 
                    count += 1
    except: pass
    return count

# Load Assets (Kecuali Target URLs)
firstnames    = load_list('assets/_firstname.txt')
lastnames     = load_list('assets/_lastname.txt')
emails        = load_list('assets/_email.txt')
messages      = load_list('assets/_message.txt')
websites      = load_list('assets/_website.txt')
locations     = load_list('assets/_location.txt')
local_proxies = load_list('locales/_proxies.txt')
phone         = load_list('assets/_phone.txt')
password      = load_list('assets/_password.txt')
# Target URL tidak di-load disini lagi agar hemat RAM

# --- FUNGSI SOLVE CAPTCHA (GSA/CS) ---
async def solve_captcha_local(image_buffer):
    try:
        img_str = base64.b64encode(image_buffer).decode('utf-8')
        payload = {
            'method': 'base64',
            'key': CAPTCHA_API_KEY,
            'body': img_str,
            'json': 1
        }
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.post(CAPTCHA_API_URL, data=payload, timeout=5))
        
        if resp.status_code == 200:
            res_text = resp.text
            if res_text.startswith('{'):
                js = resp.json()
                if 'request' in js: return js['request']
            if '|' in res_text:
                return res_text.split('|')[1]
            return res_text
    except Exception as e:
        return None
    return None

# --- CLASS PROXY MANAGER ---
class ProxyManager:
    def __init__(self):
        self.api_proxies = []
        self.local_pool = local_proxies.copy()
        random.shuffle(self.local_pool)

    def check_port(self, ip, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            result = s.connect_ex((ip, port))
            s.close()
            return result == 0
        except: return False

    def fetch_api_proxies(self):
        try:
            url = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=2000&country=all&ssl=all&anonymity=all"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                self.api_proxies = [x.strip() for x in r.text.splitlines() if ':' in x]
                log_to_delphi("INFO", "SYSTEM", f"Fetched {len(self.api_proxies)} proxies from API")
        except: pass

    def get_proxy(self, attempt_number):
        if self.check_port('127.0.0.1', 8080): return {"server": "http://127.0.0.1:8080"}, "Local Tool (HTTP)"
        if self.check_port('127.0.0.1', 1080): return {"server": "socks5://127.0.0.1:1080"}, "Local Tool (SOCKS)"
        if self.local_pool:
            px = self.local_pool.pop(0)
            self.local_pool.append(px)
            return {"server": f"http://{px}"}, f"Local ({px})"
        if not self.api_proxies: self.fetch_api_proxies()
        if self.api_proxies:
            px = self.api_proxies.pop(0)
            return {"server": f"http://{px}"}, f"API ({px})"
        return None, "Direct"

proxy_manager = ProxyManager()

# --- WORKER UTAMA ---
class GuestbookWorker:
    def __init__(self, url):
        self.url = url

    async def run(self):
        ua = UserAgent()
        
        for attempt in range(1, MAX_RETRIES_PER_URL + 1):
            proxy_conf, proxy_name = proxy_manager.get_proxy(attempt)
            log_to_delphi("RETRY" if attempt > 1 else "INFO", self.url, f"Processing ({proxy_name})...")

            async with async_playwright() as p:
                # ============================================================
                # TAMBAHAN: Konfigurasi browser args
                # ============================================================
                args = [
                    "--headless=new",  # Mode headless terbaru (lebih stabil)
                    "--disable-blink-features=AutomationControlled", 
                    "--no-sandbox", 
                    "--disable-extensions", 
                    "--window-size=1366,768",
                    "--window-position=0,0"
                ]
                
                browser = None
                try:
                    browser = await p.chromium.launch(
                        headless=True,  
                        args=args,      
                        proxy=proxy_conf
                        # : ignore_https_errors=True
                    )
                    
                    context = await browser.new_context(
                        user_agent=ua.random,
                        viewport={'width': 1920, 'height': 1080},
                        ignore_https_errors=True
                    )
                    
                    # Script anti-detection
                    await context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    """)
                    
                    page = await context.new_page()
                    
                    try:
                        await page.goto(self.url, timeout=TIMEOUT, wait_until='domcontentloaded')
                        await page.wait_for_timeout(2000) # Tunggu loading awal
                    except:
                        raise Exception("Timeout/Connection Error")
                        
                    # ============================================================
                    # A. PENANGANAN COOKIE BANNER
                    # ============================================================
                    # Kita cari tombol "Accept", "Allow", "Save" yang menutupi layar
                    try:
                        # Cari tombol yang mengandung kata-kata setuju/cookie
                        cookie_btns = await page.query_selector_all('button, a, div[role="button"], span[role="button"], input[type="button"], input[type="submit"]')
                        
                        for btn in cookie_btns:
                            if await btn.is_visible():
                                txt = await btn.inner_text() or ""
                                val = await btn.get_attribute('value') or ""
                                check_str = f"{txt} {val}"
                                
                                # Jika tombol cocok dengan pola "Terima Cookie"
                                if PATTERNS['cookie_accept'].search(check_str):
                                    # Pastikan bukan tombol submit form (cek konteks)
                                    if not PATTERNS['submit'].search(check_str): 
                                        try:
                                            # Highlight sebentar (opsional, visual debug)
                                            # await btn.scroll_into_view_if_needed()
                                            await btn.click(timeout=1000)
                                            log_to_delphi("INFO", self.url, "Cookie banner dismissed.")
                                            await page.wait_for_timeout(1000) # Tunggu banner hilang
                                            break # Cukup klik satu tombol utama
                                        except: pass
                    except: pass    

                    # ============================================================
                    # 1. SMART FORM DETECTION
                    # ============================================================
                    async def count_visible_inputs():
                        inputs = await page.query_selector_all('input[type="text"], input[type="email"], textarea')
                        count = 0
                        for i in inputs:
                            if await i.is_visible(): count += 1
                        return count

                    # Cek jumlah input visible awal
                    initial_visible_count = await count_visible_inputs()
                    
                    # Jika input visible < 2, kita asumsikan form tersembunyi/belum ada
                    if initial_visible_count < 2:
                        log_to_delphi("INFO", self.url, "Form inputs hidden. Searching for 'Open Form' triggers...")
                        
                        candidates = await page.query_selector_all('a, button, input[type="button"], input[type="submit"], [role="button"], span, div[onclick], b, font')
                        potential_triggers = []

                        for el in candidates:
                            try:
                                if not await el.is_visible(): continue
                                
                                txt = await el.inner_text() or ""
                                txt = txt.strip()[:100]

                                attr_vals = []
                                for attr in ['id', 'class', 'onclick', 'href', 'data-toggle', 'data-target', 'aria-label', 'title', 'name']:
                                    val = await el.get_attribute(attr)
                                    if val: attr_vals.append(val)
                                attr_str = " ".join(attr_vals)

                                is_match_text = PATTERNS['open_form_text'].search(txt)
                                is_match_attr = PATTERNS['open_form_attr'].search(attr_str)
                                is_js_link = 'javascript:' in attr_str or attr_str == '#' or 'void(0)' in attr_str

                                if is_match_text or is_match_attr or (is_js_link and is_match_attr):
                                    potential_triggers.append(el)
                            except: pass

                        form_opened = False
                        
                        # Simpan URL awal untuk deteksi navigasi (Pindah Halaman)
                        original_url = page.url

                        for btn in potential_triggers:
                            try:
                                # Snapshot kondisi sebelum klik
                                before_count = await count_visible_inputs()
                                
                                await btn.scroll_into_view_if_needed()
                                try: await btn.hover()
                                except: pass
                                
                                # --- AKSI KLIK ---
                                try: 
                                    # Coba klik normal
                                    await btn.click(timeout=2000)
                                except:
                                    # Fallback JS Click (Sangat ampuh untuk <a href="javascript:...">)
                                    await page.evaluate("(el) => el.click()", btn)
                                
                                # --- DETEKSI HASIL KLIK ---
                                
                                # KASUS A: Navigasi Halaman (URL Berubah)
                                # Contoh: Klik 'guestbook_eintrag.php'
                                if page.url != original_url:
                                    log_to_delphi("INFO", self.url, "Navigation detected. Waiting for load...")
                                    try:
                                        await page.wait_for_load_state('domcontentloaded', timeout=10000)
                                        await page.wait_for_timeout(1000) # Buffer extra
                                    except: pass
                                    
                                    # Cek di halaman baru ada input gak?
                                    if await count_visible_inputs() > 0:
                                        log_to_delphi("INFO", self.url, "Form found on new page!")
                                        form_opened = True
                                        break
                                
                                # KASUS B: Javascript Toggle (Halaman Tetap, DOM Berubah)
                                # Contoh: onclick="gb_toggleAddEntry()"
                                else:
                                    await page.wait_for_timeout(1500) # Tunggu animasi JS
                                    
                                    # Cek Onclick Eval (Jurus Terakhir jika klik JS gagal trigger)
                                    if await count_visible_inputs() <= before_count:
                                        onclick_val = await btn.get_attribute('onclick')
                                        if onclick_val:
                                            try:
                                                await page.evaluate(onclick_val)
                                                await page.wait_for_timeout(1500)
                                            except: pass

                                    # Final Check
                                    if await count_visible_inputs() > before_count:
                                        log_to_delphi("INFO", self.url, "Form opened successfully (AJAX/JS)!")
                                        form_opened = True
                                        break 

                            except Exception: continue
                            
                            if form_opened: break
                            
                    # ============================================================
                    # 2. GENERATE DATA
                    # ============================================================
                    val_firstname = random.choice(firstnames) if firstnames else "Guest"
                    val_lastname = random.choice(lastnames) if lastnames else "User"
                    
                    if val_firstname == val_lastname: val_lastname += "son"
                    val_fullname = f"{val_firstname} {val_lastname}" # "Zara Weber"
                    
                    val_message = random.choice(messages) if messages else "Great site!"
                    # Pesan unik untuk verifikasi (hindari kesalahan deteksi nama)
                    verify_msg_snippet = val_message[:15]         

                    # ============================================================
                    # 3. PENGISIAN FORM (LOGIKA ANTI-DUPLIKAT)
                    # ============================================================
                    
                    elements = await page.query_selector_all('input:not([type="hidden"]), textarea, select')
                    filled_count = 0
                    
                    # FLAG PENTING: Untuk mendeteksi apakah firstname sudah diisi
                    has_filled_firstname = False 
                    
                    for el in elements:
                        if not await el.is_visible(): continue

                        tag = await el.evaluate("el => el.tagName.toLowerCase()")
                        eid = await el.get_attribute('id') or ""
                        ename = await el.get_attribute('name') or ""
                        etype = await el.get_attribute('type') or ""
                        comb = f"{eid} {ename}".lower()

                        # --- LOGIKA PENGISIAN ---

                        # 1. Cek FIRST NAME dulu
                        if PATTERNS_FIRSTNAME.search(comb):
                            await el.fill(val_firstname) # Isi "Zara"
                            has_filled_firstname = True  # Tandai sudah isi depan
                            filled_count += 1
                        
                        # 2. Cek LAST NAME
                        elif PATTERNS_LASTNAME.search(comb):
                            await el.fill(val_lastname) # Isi "Weber"
                            filled_count += 1
                        
                        # 3. Cek FULL NAME / GENERIC NAME (Logika Cerdas)
                        elif PATTERNS_FULLNAME.search(comb):
                            if has_filled_firstname:
                                # JIKA Firstname TADI SUDAH DIISI, maka kolom "Name" ini 
                                # pasti maksudnya adalah LAST NAME (agar tidak kembar "Zara Zara Weber")
                                await el.fill(val_lastname) # Isi "Weber"
                            else:
                                # Jika belum ada firstname, berarti ini kolom nama lengkap biasa
                                await el.fill(val_fullname) # Isi "Zara Weber"
                            filled_count += 1

                        # A. PASSWORD
                        if etype == 'password' or PATTERNS['password'].search(comb):
                            await el.fill("P@ssWord123!") # Static pass
                            filled_count += 1

                        # B. MESSAGE
                        elif tag == 'textarea' or PATTERNS['message'].search(comb):
                            await el.fill(val_message)
                            filled_count += 1
                            
                        # C. PHONE
                        elif PATTERNS['phone'].search(comb):
                            await el.fill(random.choice(phone) if phone else "081234567891")
                            filled_count += 1   
                        
                        # D. EMAIL
                        elif PATTERNS['email'].search(comb):
                            await el.fill(random.choice(emails) if emails else "test@mail.com")
                            filled_count += 1
                        
                        # E. WEBSITE
                        elif PATTERNS['website'].search(comb):
                            await el.fill(random.choice(websites) if websites else "http://google.com")
                            filled_count += 1
                                               
                        # F. LOCATION
                        elif PATTERNS['location'].search(comb):
                            await el.fill(random.choice(locations) if locations else "New York")
                            filled_count += 1

                        # G. CAPTCHA
                        elif CAPTCHA_ENABLED and PATTERNS['captcha_input'].search(comb):
                            captcha_answer = None
                            imgs = await page.query_selector_all('img')
                            target_img = None
                            for img in imgs:
                                isrc = await img.get_attribute('src') or ""
                                ialt = await img.get_attribute('alt') or ""
                                iid = await img.get_attribute('id') or ""
                                if PATTERNS['captcha_img'].search(f"{isrc} {ialt} {iid}"):
                                    if await img.is_visible():
                                        target_img = img
                                        break
                            
                            if target_img:
                                try:
                                    img_buffer = await target_img.screenshot()
                                    captcha_answer = await solve_captcha_local(img_buffer)
                                except: pass
                            
                            if captcha_answer:
                                await el.fill(captcha_answer)
                                filled_count += 1
                        
                        # H. CHECKBOX
                        elif etype == 'checkbox':
                             if not await el.is_checked(): 
                                try: await el.check()
                                except: 
                                    # Fallback JS click untuk checkbox bandel
                                    try: await page.evaluate("(el) => el.click()", el)
                                    except: pass

                        # I. RADIO BUTTON
                        elif etype == 'radio':
                            is_group_checked = await page.evaluate("""(name) => {
                                let radios = document.getElementsByName(name);
                                for (let i = 0; i < radios.length; i++) {
                                    if (radios[i].checked) return true;
                                }
                                return false;
                            }""", ename)
                            
                            if not is_group_checked:
                                try: await el.check()
                                except: pass

                    # ============================================================
                    # 4. SUBMIT & VALIDASI (Updated: DELAY 3 DETIK)
                    # ============================================================
                    if filled_count > 0:
                        
                        # --- FITUR BARU: JEDA SEBELUM KLIK SUBMIT ---
                        log_to_delphi("INFO", self.url, "Form filled. Waiting 3s before submit...")
                        await page.wait_for_timeout(3000) # Jeda 3 detik agar terlihat natural
                        # ---------------------------------------------

                        submits = await page.query_selector_all('input[type="submit"], button')
                        submitted = False
                        for btn in submits:
                            val = await btn.get_attribute('value') or ""
                            txt = await btn.inner_text()
                            if PATTERNS['submit'].search(f"{val} {txt}"):
                                await btn.scroll_into_view_if_needed()
                                try: await btn.click()
                                except: await page.evaluate("(el) => el.click()", btn)
                                submitted = True; log_to_delphi("INFO", self.url, "Submit clicked.")
                                break
                        
                        if submitted:
                            # Gunakan timeout global atau fallback
                            try: await page.wait_for_load_state('networkidle', timeout=15000)
                            except: await page.wait_for_timeout(5000)

                            final_content = await page.content()
                            if PATTERNS['success'].search(final_content):
                                log_to_delphi("SUCCESS", self.url, "Verified: Success message.", {"proxy": proxy_name})
                                return

                            # RELOAD VALIDATION
                            log_to_delphi("INFO", self.url, "Reloading page to verify...")
                            try:
                                await page.goto(self.url, timeout=TIMEOUT, wait_until='domcontentloaded')
                                await page.wait_for_timeout(3000)
                                recheck_content = await page.content()
                                
                                if verify_msg_snippet in recheck_content:
                                    log_to_delphi("SUCCESS", self.url, "Verified: Message found!", {"proxy": proxy_name}); return
                                elif val_fullname in recheck_content:
                                    log_to_delphi("SUCCESS", self.url, f"Verified: Name '{val_fullname}' found!", {"proxy": proxy_name}); return
                                elif val_firstname in recheck_content:
                                     log_to_delphi("SUCCESS", self.url, f"Verified: Firstname found!", {"proxy": proxy_name}); return
                                elif not PATTERNS['error'].search(recheck_content):
                                     log_to_delphi("SUCCESS", self.url, "Submitted (No error found)", {"proxy": proxy_name}); return

                            except Exception:
                                log_to_delphi("SUCCESS", self.url, "Submitted (Validation skipped)", {"proxy": proxy_name})

                    else:
                        raise Exception("No input forms filled")

                except Exception as e:
                    err_msg = str(e).split('\n')[0]
                    log_to_delphi("ERROR", self.url, f"Attempt {attempt} failed: {err_msg}")
                finally:
                    await asyncio.sleep(10)
                    if browser: 
                        try:
                            await browser.close()
                        except:
                            pass
        
        log_to_delphi("FAILED_FINAL", self.url, "All attempts failed.")

# --- PRODUCER & CONSUMER (STREAMING) ---

async def url_producer(queue, path_to_file):
    """
    Membaca file, memfilter URL sampah, root domain, blacklist, 
    dan membatasi jumlah URL per domain sebelum masuk antrian.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, path_to_file)
    
    if not os.path.exists(full_path):
        log_to_delphi("ERROR", "SYSTEM", f"File not found: {path_to_file}")
        for _ in range(MAX_THREADS): await queue.put(None)
        return

    # --- MEMORY UNTUK FILTERING ---
    seen_urls = set()       # Untuk membuang duplikat URL persis
    domain_counts = {}      # Untuk menghitung jatah per domain
    
    filtered_count = 0      # Statistik yang dibuang
    accepted_count = 0      # Statistik yang diterima

    try:
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                raw_url = line.strip()
                if not raw_url: continue
                
                # Normalisasi URL (tambah http jika belum ada)
                if not raw_url.startswith('http'): 
                    url = 'http://' + raw_url
                else:
                    url = raw_url

                # 1. FILTER DUPLIKAT URL (Exact Match)
                if url in seen_urls:
                    filtered_count += 1
                    continue
                seen_urls.add(url)

                # Parsing URL untuk analisa lebih dalam
                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower() # contoh: www.google.com
                    path = parsed.path             # contoh: /guestbook/index.php
                    query = parsed.query           # contoh: ?id=123
                except:
                    filtered_count += 1
                    continue

                # 2. FILTER BLACKLIST (Situs Populer)
                # Cek jika ada kata kunci blacklist di dalam domain
                # Contoh: "google" ada di "www.google.co.id" -> True -> Skip
                found_keyword = None
                for kw in IGNORED_KEYWORDS:
                    if kw in domain:
                        found_keyword = kw
                        break
                
                if found_keyword:
                    filtered_count += 1
                    # KIRIM LOG KE DELPHI:
                    # Status "WARNING" dipilih agar:
                    # 1. Muncul di ListView sebagai "SKIP"
                    # 2. Progress Bar Delphi menghitungnya sebagai "Selesai" (Maju langkah)
                    # 3. Muncul di Memo Log [RAW]
                    log_to_delphi("WARNING", url, f"Ignored/Blacklist: Domain contains '{found_keyword}'")
                    continue

                # 3. FILTER ROOT DOMAIN
                # Kita tidak mau submit ke Homepage (biasanya tidak ada form guestbook disitu)
                # Logika: Jika path kosong ATAU path cuma "/" DAN tidak ada query string
                is_root = (path == '' or path == '/') and (not query)
                if is_root:
                    # print(f"[FILTER] Root Domain Ignored: {url}") # Debugging
                    filtered_count += 1
                    continue

                # 4. FILTER LIMIT PER DOMAIN
                # Pastikan domain bersih (hapus www. agar www.contoh.com dan contoh.com dianggap sama)
                clean_domain = domain.replace('www.', '')
                
                current_count = domain_counts.get(clean_domain, 0)
                if current_count >= MAX_URLS_PER_DOMAIN:
                    # print(f"[FILTER] Limit Reached for {clean_domain}") # Debugging
                    filtered_count += 1
                    continue
                
                # JIKA LOLOS SEMUA FILTER:
                domain_counts[clean_domain] = current_count + 1
                accepted_count += 1
                
                # Masukkan ke antrian worker
                await queue.put(url)

        # Lapor ke Delphi/Console hasil filter
        log_to_delphi("INFO", "SYSTEM", f"Filter Done. Accepted: {accepted_count}, Filtered/Ignored: {filtered_count}")

    except Exception as e:
        log_to_delphi("ERROR", "SYSTEM", f"Error reading file stream: {e}")

    # Sinyal Stop
    for _ in range(MAX_THREADS):
        await queue.put(None)

async def worker_wrapper(sem, queue):
    """Worker mengambil job dari antrian"""
    while True:
        url = await queue.get()
        
        # Sinyal berhenti diterima
        if url is None:
            queue.task_done()
            break
            
        async with sem:
            # Jalankan bot
            bot = GuestbookWorker(url)
            await bot.run()
        
        queue.task_done()

async def main():
    target_file = 'logs/_AutoCommentSubmitter.txt'
    
    # 1. Hitung total data dulu (Cepat) untuk progress bar Delphi
    total_data = count_file_lines(target_file)
    if total_data == 0:
        log_to_delphi("ERROR", "SYSTEM", "Target URL file empty or not found.")
        return

    # Kirim Init Signal
    print(json.dumps({"status": "INIT", "total": total_data, "msg": f"Streaming {total_data} URLs"}), flush=True)

    # 2. Buat Queue dengan buffer terbatas (Hemat RAM)
    queue = asyncio.Queue(maxsize=QUEUE_BUFFER_SIZE)

    # 3. Jalankan Producer dan Consumer
    sem = asyncio.Semaphore(MAX_THREADS)
    
    # Task Producer (Pembaca File)
    producer_task = asyncio.create_task(url_producer(queue, target_file))
    
    # Task Consumers (Para Worker)
    consumers = [asyncio.create_task(worker_wrapper(sem, queue)) for _ in range(MAX_THREADS)]
    
    # Tunggu Producer selesai membaca file
    await producer_task
    
    # Tunggu antrian habis diproses
    await queue.join()
    
    # Tunggu worker shutdown proper
    await asyncio.gather(*consumers)

    log_to_delphi("INFO", "SYSTEM", "All tasks finished.")

if __name__ == "__main__":
    # --- CRITICAL FIX FOR WINDOWS ---
    # Menggunakan ProactorEventLoopPolicy agar Playwright Subprocess bisa jalan di Windows
    if os.name == 'nt': 
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())