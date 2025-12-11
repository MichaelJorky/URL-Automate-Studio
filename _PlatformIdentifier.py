import json
import requests
import socket
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import defaultdict

# ================= KONFIGURASI =================
MAX_INTERNAL_LINKS_PER_DOMAIN = 1
MAX_WORKERS = 10

BLACKLIST_DOMAINS = {
    '4chan.org', 'accuweather.com', 'adobe.com', 'alibaba.com', 'aliexpress.com',
    'amazon.co.jp', 'amazon.co.uk', 'amazon.com', 'amazon.de', 'amazon.fr',
    'amazon.in', 'amazon.it', 'app.link', 'archiveofourown.org', 'ask.com',
    'aol.com', 'aws.amazon.com', 'baidu.com', 'bbc.co.uk', 'bbc.com',
    'bilibili.com', 'bing.com', 'bit.ly', 'blackhatworld.com', 'blibli.com', 'bloomberg.com',
    'blogger.com', 'blogspot.com', 'bp.blogspot.com', 'bukalapak.com',
    'canva.com', 'cangkok.com', 'chatgpt.com', 'cloudflare.com', 'cnn.com', 'codeproject.com',
    'daum.net', 'dailymail.co.uk', 'dailymotion.com', 'detik.com', 'discord.com',
    'disneyplus.com', 'docs.google.com', 'dogpile.com', 'doubleclick.net',
    'drive.google.com', 'dropbox.com', 'duckduckgo.com', 'dzen.ru',
    'ebay.com', 'ecosia.org', 'en.wikipedia.org', 'etsy.com', 'excite.com',
    'fanfiction.net', 'fandom.com', 'facebook.com', 'fb.com', 'fb.watch',
    'flickr.com', 'fmoviesz.to', 'forbes.com', 'foxnews.com', 'gibiru.com',
    'gigablast.org', 'github.com', 'github.io', 'githubusercontent.com',
    'gitlab.com', 'globo.com', 'google-analytics.com', 'google.com',
    'google.co.id', 'googleapis.com', 'googleusercontent.com', 'googlesyndication.com',
    'gstatic.com', 'hanime.tv', 'ibm.com', 'icloud.com', 'idntimes.com',
    'ikea.com', 'ilovepdf.com', 'imgur.com', 'instructure.com', 'info.com',
    'instagram.com', 'jd.id', 'kapanlagi.com', 'kaskus.co.id', 'kompas.com',
    'kumparan.com', 'lazada.co.id', 'line.me', 'linkedin.com', 'liputan6.com',
    'live.com', 'marca.com', 'max.com', 'mediafire.com', 'mediawiki.org', 'medium.com',
    'merdeka.com', 'microsoft.com', 'microsoftonline.com', 'myshopify.com', 'mojoportal.com',
    'naver.com', 'netflix.com', 'noodlemagazine.com', 'nytimes.com', 'o-seznam.cz',
    'oath.com', 'okezone.com', 'openai.com', 'oracle.com', 'outlook.com', 'ozon.ru',
    'page.link', 'pastebin.com', 'paypal.com', 'pixiv.net', 'pinterest.com', 'plipeo.com', 'plus.com',
    'primevideo.com', 'qwant.com', 'quora.com', 'rakuten.co.jp', 'reddit.com',
    'roblox.com', 'rutube.ru', 'scribd.com', 'seznam.cz', 'sharepoint.com', 'shopify.com',
    'shopee.co.id', 'shopee.com', 'skype.com', 'slideshare.net', 'snapchat.com', 'sociolla.com',
    'spotify.com', 'startpage.com', 'stackoverflow.com', 'steampowered.com', 'suara.com',
    'swisscows.com', 'target.com', 'telegram.org', 'temu.com', 'theguardian.com',
    't.co', 'tiktok.com', 'tokopedia.com', 'tribunnews.com', 'tumblr.com',
    'twitch.tv', 'uol.com.br', 'uservoice.com', 'vimeo.com', 'wechat.com', 'weather.com',
    'whatsapp.com', 'walmart.com', 'wikimedia.org', 'wikipedia.org', 'wikimediafoundation.org', 'wildberries.ru', 'wix.com',
    'wixsite.com', 'wordpress.com', 'wordpress.org', 'wp.com', 'x.com',
    'yahoo.com', 'yahoo.co.jp', 'yandex.ru', 'ya.ru', 'yimg.com', 'you.com',
    'youtube.com', 'youtu.be', 'zalora.co.id', 'zoom.us'
}

IGNORE_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico',
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm',
    '.mp3', '.wav', '.ogg', '.m4a',
    '.zip', '.rar', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.css', '.js', '.json', '.xml', '.txt', '.exe', '.apk'
)

# ================= GLOBAL VARS =================
CURRENT_PROXY_DICT = None 
IS_PROXY_CHECKED = False
DOMAIN_LINK_COUNTER = defaultdict(int)

# ================= HELPER UTAMA: CEK DOMAIN & PATH =================
def is_url_blacklisted(full_url):
    """
    Mengecek apakah URL (termasuk path apapun) berasal dari domain blacklist.
    Logika: Cek apakah host URL berakhiran dengan domain di blacklist.
    """
    try:
        # 1. Ambil domain utamanya saja (netloc)
        parsed = urlparse(full_url)
        domain = parsed.netloc.lower()
        
        # Hapus port jika ada (contoh: localhost:8080 -> localhost)
        if ":" in domain:
            domain = domain.split(":")[0]
            
        # Jika domain kosong (link relative error), return False dulu biar diproses validator
        if not domain:
            return False

        # 2. Loop cek blacklist
        for blocked in BLACKLIST_DOMAINS:
            # Cek Persis ATAU Subdomain (Ends With)
            # Contoh blocked: 'google.com'
            # domain: 'google.com' -> MATCH
            # domain: 'drive.google.com' -> MATCH (.endswith)
            if domain == blocked or domain.endswith("." + blocked):
                return True
                
        return False
    except:
        return True # Jika URL error parsing, anggap blacklist untuk keamanan

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/121.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/122.0.0.0"
]

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Referer': 'https://www.google.com/'
    }
    
# ================= HELPER FUNCTION: CHECK BLACKLIST =================
def is_domain_blacklisted(url):
    """Cek apakah domain ada di blacklist"""
    try:
        domain = urlparse(url).netloc.lower()
        # Hapus www.
        if domain.startswith('www.'): 
            domain = domain[4:]
        
        # Cek exact match
        if domain in BLACKLIST_DOMAINS:
            return True
            
        # Cek subdomains (misal: accounts.google.com matches google.com)
        for bl in BLACKLIST_DOMAINS:
            if domain.endswith("." + bl):
                return True
        return False
    except:
        return True # Jika URL error, anggap blacklist agar aman    

# ================= SERVER DETECTION =================
def detect_server_name(response):
    try:
        headers = response.headers
        server_raw = headers.get('Server', '').strip()
        via_header = headers.get('Via', '').strip()
        
        if 'cf-ray' in headers: return "Cloudflare"
        if 'x-github-request-id' in headers: return "GitHub Pages"
        if 'x-netlify' in headers: return "Netlify"
        if 'x-vercel-id' in headers: return "Vercel"
        
        if server_raw:
            low_srv = server_raw.lower()
            if 'gws' in low_srv: return "Google GWS"
            if 'akamai' in low_srv: return "Akamai"
            if 'nginx' in low_srv: return "Nginx"
            if 'apache' in low_srv: return "Apache"
            if 'microsoft-iis' in low_srv: return "IIS"
            if 'litespeed' in low_srv: return "LiteSpeed"
            if 'openresty' in low_srv: return "OpenResty"
            return server_raw[:25]

        if 'google' in via_header.lower(): return "Google (Via)"
        return "Unknown"
    except: return "Unknown"

# ================= CMS/WAF DETECTION =================
def detect_cms_and_tech(html_content, soup, headers):
    """Deteksi CMS, Framework, dan teknologi website dengan database lengkap"""
    detections = []
    html_lower = html_content.lower()
    headers_str = str(headers).lower()
    
    # === DATABASE CMS LENGKAP ===
    cms_patterns = {
        # --- Major CMS ---
        'WordPress': [r'wp-content', r'wp-includes', r'/wp-admin/', r'generator.*wordpress', r'wp-json'],
        'Joomla': [r'joomla', r'com_joomla', r'/media/com_', r'/components/com_', r'index.php\?option=com_'],
        'Drupal': [r'drupal', r'/sites/all/', r'Drupal.settings', r'/sites/default/files'],
        'Magento': [r'magento', r'/skin/frontend/', r'Mage\.Cookies', r'static/version'],
        'Shopify': [r'shopify', r'cdn\.shopify\.com', r'Shopify\.theme'],
        'Wix': [r'wix\.com', r'wix-dns', r'X-Wix-Request-Id'],
        'Squarespace': [r'squarespace', r'static\.squarespace\.com'],
        'Blogger': [r'blogger', r'blogspot\.com', r'm=1'],
        'Ghost': [r'ghost', r'ghost-sdk', r'generator.*ghost'],
        'Bitrix24': [r'bitrix', r'/bitrix/'],
        'PrestaShop': [r'prestashop', r'PrestaShop'],
        'OpenCart': [r'opencart', r'route=common/home', r'catalog/view/theme'],
        'WooCommerce': [r'woocommerce', r'wc-ajax='],
        
        # --- Python/JS/Headless ---
        'Django CMS': [r'django-cms', r'csrfmiddlewaretoken'],
        'Wagtail': [r'wagtail'],
        'Strapi': [r'strapi', r'/uploads/'],
        'Sanity': [r'sanity\.io', r'cdn\.sanity\.io'],
        'Contentful': [r'contentful', r'images\.ctfassets\.net'],
        'Webflow': [r'webflow', r'w-mod-'],
        'HubSpot': [r'hs-script-loader', r'hubspot\.com'],
        'React': [r'react', r'react-dom', r'_next', r'data-reactroot'],
        'Vue.js': [r'vue', r'vue\.js', r'data-v-'],
        'Angular': [r'angular', r'ng-version', r'app-root'],
        'Svelte': [r'svelte'],
        'Gatsby': [r'gatsby', r'___loader'],
        'Next.js': [r'next\.js', r'__NEXT_DATA__'],
        'Nuxt.js': [r'nuxt', r'__NUXT__'],
        
        # --- Static Site Generators ---
        'Jekyll': [r'jekyll', r'generator.*jekyll'],
        'Hugo': [r'hugo', r'generator.*hugo'],
        'Hexo': [r'hexo', r'generator.*hexo'],
        'Pelican': [r'pelican'],
        'Eleventy': [r'11ty', r'eleventy'],

        # --- Forum/Wiki ---
        'vBulletin': [r'vbulletin'],
        'XenForo': [r'xenforo'],
        'phpBB': [r'phpbb'],
        'MediaWiki': [r'mediawiki', r'wgPageName'],
        'DokuWiki': [r'dokuwiki'],

        # --- INDONESIA SPECIFIC & GOVERNMENT CMS ---
        'CMS Balitbang': [r'balitbang', r'cmsbalitbang', r'theme/balitbang', r'member/login_balitbang'],
        'OpenSID': [r'opensid', r'donjo-app', r'desa 2.0', r'tema://', r'sid surat'],
        'Siskeudes': [r'siskeudes', r'simda desa'],
        'SiPintar': [r'sipintar', r'kawah edukasi'],
        'LokalCMS': [r'lokalcms', r'lokomedia'],
        'Lokomedia': [r'lokomedia', r'bukulokomedia'],
        'AuraCMS': [r'auracms'],
        'PopojiCMS': [r'popojicms'],
        'SchoolCMS': [r'schoolcms', r'school-cms'],
        'E-Office Gov': [r'e-office', r'siola', r'simpeg', r'e-kinerja'],
        'SPSE (LPSE)': [r'lpse', r'spse', r'eproc'],
        'JDIH CMS': [r'jdih'],
        'PPID CMS': [r'ppid'],
        'Siakba': [r'siakba'],
        'Dapodik': [r'dapodik'],
        'InfoDesa': [r'infodesa', r'prodeskel'],
        'SmartVillage': [r'smartvillage', r'smart village'],
        'KampusMerdeka': [r'kampus merdeka'],
        
        # --- OTHER CMS FROM LIST (Generic Matching) ---
        # Pola umum: Mencari nama CMS di meta generator, footer "powered by", atau path khas
        'Typo3': [r'typo3'],
        'Concrete5': [r'concrete5'],
        'Backdrop CMS': [r'backdrop'],
        'Grav': [r'grav', r'gravcms'],
        'MODX': [r'modx'],
        'SilverStripe': [r'silverstripe'],
        'Umbraco': [r'umbraco'],
        'DotNetNuke': [r'dnn', r'dotnetnuke'],
        'Weebly': [r'weebly'],
        'Sitecore': [r'sitecore'],
        'Kentico': [r'kentico'],
        'Craft CMS': [r'craft cms'],
        'ExpressionEngine': [r'expressionengine'],
        'Adobe Experience Manager': [r'cq5', r'clientlibs'],
        'BigCommerce': [r'bigcommerce'],
        'Volusion': [r'volusion'],
        '3dcart': [r'3dcart'],
        'Lightspeed': [r'lightspeed'],
        'Textpattern': [r'textpattern'],
        'Contao': [r'contao'],
        'Liferay': [r'liferay'],
        'Alfresco': [r'alfresco'],
        'ProcessWire': [r'processwire'],
        'Bolt CMS': [r'bolt'],
        'GetSimple': [r'getsimple'],
        'Moodle': [r'moodle', r'/lib/javascript.php'],
        'OJS': [r'ojs', r'open journal systems', r'/index.php/index/login'],
        'CodeIgniter': [r'codeigniter', r'ci_session'],
        'Laravel': [r'laravel', r'csrf-token'],
        'Yii': [r'yii'],
        'Symfony': [r'symfony'],
        
        # --- List Tambahan (Name Matching) ---
        'Bagisto': [r'bagisto'], 'Spree': [r'spree'], 'Sylius': [r'sylius'],
        'Ecwid': [r'ecwid'], 'KeystoneJS': [r'keystone'], 'Directus': [r'directus'],
        'Prismic': [r'prismic'], 'Storyblok': [r'storyblok'], 'DatoCMS': [r'datocms'],
        'Kirby': [r'kirby'], 'Statamic': [r'statamic'], 'Jimdo': [r'jimdo'],
        'Strikingly': [r'strikingly'], 'Tilda': [r'tilda'], 'Carrd': [r'carrd'],
        'OctoberCMS': [r'octobercms'], 'PyroCMS': [r'pyrocms'], 'Mezzanine': [r'mezzanine'],
        'Plone': [r'plone'], 'Zope': [r'zope'], 'eZ Publish': [r'ez publish'],
        'XOOPS': [r'xoops'], 'Tiki Wiki': [r'tiki'], 'OpenCms': [r'opencms'],
        'Mura': [r'mura'], 'PHP-Fusion': [r'php-fusion'], 'e107': [r'e107'],
        'phpNuke': [r'phpnuke'], 'Subrion': [r'subrion'], 'Silex': [r'silex'],
        'Mahara': [r'mahara'], 'Jamroom': [r'jamroom'], 'CuteNews': [r'cutenews'],
        'Automad': [r'automad'], 'WonderCMS': [r'wondercms'], 'Serendipity': [r'serendipity'],
        'CloudCannon': [r'cloudcannon'], 'Agility CMS': [r'agility'], 'Squidex': [r'squidex'],
        'Kontent.ai': [r'kontent.ai'], 'Builder.io': [r'builder.io'], 'TinaCMS': [r'tina'],
        'Enonic': [r'enonic'], 'Flotiq': [r'flotiq'], 'Saleor': [r'saleor'],
        'Shopware': [r'shopware'], 'CubeCart': [r'cubecart'], 'VirtueMart': [r'virtuemart'],
        'X-Cart': [r'x-cart'], 'AbanteCart': [r'abantecart'], 'Thirty Bees': [r'thirty bees'],
        'Broadleaf': [r'broadleaf'], 'AmeriCommerce': [r'americommerce'], 'Selz': [r'selz'],
        'Vendure': [r'vendure'], 'Arc XP': [r'arc xp'], 'Quintype': [r'quintype'],
        'Movable Type': [r'movable type'], 'Typepad': [r'typepad'], 'Medium': [r'medium'],
        'Issuu': [r'issuu'], 'Newspaper': [r'newspaper'], 'Blox': [r'blox'],
        'Nanoc': [r'nanoc'], 'Metalsmith': [r'metalsmith'], 'Publii': [r'publii'],
        'Dorik': [r'dorik'], 'Zyro': [r'zyro'], 'Unbounce': [r'unbounce'],
        'Leadpages': [r'leadpages'], 'Duda': [r'duda'], 'Site123': [r'site123'],
        'Tumblr': [r'tumblr'], 'Postach.io': [r'postach.io'], 'Write.as': [r'write.as'],
        'Jahia': [r'jahia'], 'Crownpeak': [r'crownpeak'], 'Hippo': [r'hippo'],
        'Bloomreach': [r'bloomreach'], 'Squiz': [r'squiz'], 'Ingeniux': [r'ingeniux'],
        'Vignette': [r'vignette'], 'FatWire': [r'fatwire'], 'Mozello': [r'mozello'],
        'Voog': [r'voog'],
        
        # --- E-Commerce & Toko Online Indonesia ---
        'TokoTalk': [r'tokotalk'], 'Sirclo': [r'sirclo'], 'Jejualan': [r'jejualan'],
        'NiagaCMS': [r'niagacms'], 'Jarvis Store': [r'jarvis'], 'TokoDaring': [r'tokodaring'],
        'Zahir Shop': [r'zahir'], 'EasyStore': [r'easystore'],
        
        # --- Niche Indonesia & Portal Berita ---
        'CMS Rumah Belajar': [r'rumah belajar'], 'Limas CMS': [r'limas'], 
        'Kotak-Merah': [r'kotak-merah'], 'KataCMS': [r'katacms'], 'Mora CMS': [r'mora cms'],
        'X-One': [r'x-one'], 'Udinus CMS': [r'udinus'], 'Prodesk': [r'prodesk'],
        'Simdes': [r'simdes'], 'Simpeg': [r'simpeg'], 'SekolahKu': [r'sekolahku'],
        'CMS BSE': [r'bse'], 'Madrasah Digital': [r'madrasah digital'], 
        'RuangKelas': [r'ruangkelas'], 'Blood CMS': [r'blood'], 'KabarCMS': [r'kabarcms'],
        'ID-Journal': [r'id-journal'], 'RevolusiNews': [r'revolusinews'], 'AMedia': [r'amedia'],
        'AnekaCMS': [r'anekacms'], 'RajaCMS': [r'rajacms'], 'BeritaKita': [r'beritakita'],
        'XCMS': [r'xcms']
    }
    
    # 1. Cek WAF (Web Application Firewall)
    waf_detected = []
    if 'x-waf-eventinfo' in headers_str: waf_detected.append("Imperva WAF")
    if 'x-sucuri-id' in headers_str: waf_detected.append("Sucuri WAF")
    if 'cf-ray' in headers_str: waf_detected.append("Cloudflare WAF")
    if 'x-protected-by' in headers_str and 'squarespace' in headers_str: waf_detected.append("Squarespace WAF")
    
    if waf_detected:
        detections.extend(waf_detected)
    
    # 2. Cek Meta Generator
    meta_generator = soup.find('meta', {'name': 'generator'})
    if meta_generator and meta_generator.get('content'):
        content = meta_generator['content'].lower()
        detections.append(f"Meta: {content}") # Debug hint
        for cms, patterns in cms_patterns.items():
            if cms.lower() in content:
                detections.append(cms)

    # 3. Cek Patterns di HTML dan Header
    # (Optimasi: Hanya loop patterns jika belum terdeteksi lewat meta)
    for cms, patterns in cms_patterns.items():
        if cms in detections: continue
        
        for pattern in patterns:
            # Cek di HTML Body
            if re.search(pattern, html_content, re.IGNORECASE):
                detections.append(cms)
                break
            # Cek di Headers (misal cookie atau x-powered-by)
            if re.search(pattern, headers_str, re.IGNORECASE):
                detections.append(cms)
                break

    # 4. Filter Hasil Unik
    unique_detections = []
    seen = set()
    for d in detections:
        # Bersihkan string "Meta: ..."
        clean_d = d.replace("Meta: ", "").strip()
        # Perbaiki format nama jika perlu
        if clean_d.lower() == 'wp-content': clean_d = 'WordPress'
        
        if clean_d not in seen and len(clean_d) > 2:
            seen.add(clean_d)
            unique_detections.append(clean_d)
            
    # 5. Fallback Heuristics (Jika tidak ada match pasti)
    if not unique_detections:
        if 'wp-json' in html_lower: return "CMS: WordPress (API)"
        if '/node/' in html_lower: return "CMS: Drupal?"
        if '/index.php?option=' in html_lower: return "CMS: Joomla?"
        if 'cdn.shopify.com' in html_lower: return "CMS: Shopify"
        return "Unknown"
        
    # Format Output
    return " | ".join(unique_detections[:4]) # Ambil max 4 deteksi teratas

# ================= PROXY LOGIC =================
def validate_proxy(proxy_str):
    try:
        p_dict = {"http": f"http://{proxy_str}", "https": f"http://{proxy_str}"} if "://" not in proxy_str else {"http": proxy_str, "https": proxy_str}
        r = requests.get("https://api.ipify.org", headers=get_headers(), proxies=p_dict, timeout=5)
        if r.status_code == 200: return r.text.strip()
    except: pass
    return None

def get_best_topology_proxy():
    # Cek Local Proxy Apps
    ports = [(8080, "http://127.0.0.1:8080"), (1080, "socks5://127.0.0.1:1080")]
    for port, url in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result == 0:
                if validate_proxy(url): return url, f"Local Tool (Port {port})"
        except: pass

    # Cek Proxy File
    try:
        with open("locales/_proxies.txt", "r") as f:
            proxies = [line.strip() for line in f if line.strip()]
        for px in random.sample(proxies, min(len(proxies), 5)):
            if validate_proxy(px): return px, "Local File"
    except: pass

    # Cek Free API
    try:
        url = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=2000&country=all&ssl=all&anonymity=all"
        r = requests.get(url, headers=get_headers(), timeout=10)
        if r.status_code == 200:
            proxies = r.text.splitlines()
            for px in random.sample(proxies, min(len(proxies), 3)):
                if ":" in px and validate_proxy(px): return px, "Free API"
    except: pass
    
    return None, None

# ================= VALIDATE LINK (Thread-safe) =================
def validate_link_thread_safe(link_info):
    link_url, parent_domain, is_internal = link_info
    
    # [PENTING] FILTER GANDA: Cek lagi di dalam thread
    if is_url_blacklisted(link_url):
        return None

    if is_internal and DOMAIN_LINK_COUNTER[urlparse(link_url).netloc] >= MAX_INTERNAL_LINKS_PER_DOMAIN:
        return None
    
    try:
        resp = requests.get(link_url, headers=get_headers(), proxies=CURRENT_PROXY_DICT, 
                            timeout=10, verify=False, allow_redirects=True)
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            cms_info = detect_cms_and_tech(resp.text, soup, resp.headers)
            
            return {
                'url': link_url,
                'cms': cms_info,
                'server': detect_server_name(resp),
                'status': resp.status_code,
                'is_internal': is_internal,
                'domain': urlparse(link_url).netloc
            }
        return None
    except: return None

# ================= BATCH VALIDATION =================
def validate_links_in_parallel(links_to_validate, parent_domain):
    validated_links = []
    link_data = [(link, parent_domain, is_int) for link, is_int in links_to_validate]
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_link = {executor.submit(validate_link_thread_safe, data): data for data in link_data}
        
        for future in as_completed(future_to_link):
            try:
                result = future.result()
                if result:
                    if result['is_internal']:
                        DOMAIN_LINK_COUNTER[result['domain']] += 1
                    validated_links.append(result)
                    
                    internal_count = sum(1 for link in validated_links if link['is_internal'])
                    if internal_count >= MAX_INTERNAL_LINKS_PER_DOMAIN:
                        for f in future_to_link.keys():
                            if not f.done(): f.cancel()
            except: pass
    
    return validated_links

# ================= SMART CRAWL FUNCTION =================
def crawl_urls(source_urls):
    global CURRENT_PROXY_DICT, IS_PROXY_CHECKED, DOMAIN_LINK_COUNTER
    results = []
    DOMAIN_LINK_COUNTER.clear()
    
    for url in source_urls:
        if not url.startswith('http'): url = 'http://' + url
        
        # 1. CEK BLACKLIST LEVEL UTAMA
        # Ini akan memblokir: https://facebook.com/profile.php?id=123
        if is_url_blacklisted(url):
            results.append({"type": "log", "msg": f"[SKIP] Blacklisted Domain: {url}"})
            continue

        # Setup Proxy (Singkat)
        if not IS_PROXY_CHECKED:
            px, name = get_best_topology_proxy()
            if px: CURRENT_PROXY_DICT = {"http": px, "https": px}
            else: CURRENT_PROXY_DICT = {}
            IS_PROXY_CHECKED = True
            
        try:
            results.append({"type": "log", "msg": f"[SCAN] Crawling Parent: {url}"})
            resp = requests.get(url, headers=get_headers(), proxies=CURRENT_PROXY_DICT, timeout=15, verify=False)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, 'html.parser')
                cms_info = detect_cms_and_tech(resp.text, soup, resp.headers)
                
                results.append({
                    "type": "data", "found_url": url, 
                    "cms_info": cms_info, "status": "200", 
                    "server": f"Parent ({detect_server_name(resp)})"
                })
                
                # EKSTRAKSI LINK
                links = soup.find_all('a', href=True)
                seen = set()
                links_to_validate = []
                parent_domain = urlparse(url).netloc
                
                for link in links:
                    full_url = urljoin(url, link['href'])
                    
                    # 2. CEK BLACKLIST LEVEL ANAK (CHILD LINKS)
                    # Jika ada link <a href="https://twitter.com/share"> -> SKIP
                    # Jika ada link <a href="https://google.com/search?q=xyz"> -> SKIP
                    if is_url_blacklisted(full_url): 
                        continue

                    # Filter ekstensi file sampah
                    path = urlparse(full_url).path.lower()
                    if path.endswith(IGNORE_EXTENSIONS): continue
                    
                    if full_url not in seen and full_url != url:
                        seen.add(full_url)
                        is_internal = (urlparse(full_url).netloc == parent_domain)
                        links_to_validate.append((full_url, is_internal))
                
                # Proses Validasi (Paralel)
                target_links = links_to_validate[:15] # Ambil 15 sampel
                if target_links:
                    results.append({"type": "log", "msg": f"   -> Validating {len(target_links)} CLEAN links (Blacklist filtered)..."})
                    
                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exc:
                        futures = {exc.submit(validate_link_thread_safe, (l, parent_domain, i)): (l, i) for l, i in target_links}
                        for future in as_completed(futures):
                            try:
                                res = future.result()
                                if res:
                                    if res['is_internal']: DOMAIN_LINK_COUNTER[res['domain']] += 1
                                    sType = "Int" if res['is_internal'] else "Ext"
                                    results.append({
                                        "type": "data", "found_url": res['url'], 
                                        "cms_info": res['cms'], "status": str(res['status']), 
                                        "server": f"{sType} ({res['server']})"
                                    })
                            except: pass
            else:
                 results.append({"type": "log", "msg": f"[X] HTTP {resp.status_code}"})
                 
        except Exception as e:
            results.append({"type": "log", "msg": f"[X] Error: {str(e)[:50]}"})

    return json.dumps(results, default=str)