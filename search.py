# ไม่ใช้ requests ธรรมดาแล้ว เปลี่ยนมาใช้ curl_cffi เพื่อปลอมตัวเป็นเบราว์เซอร์
from curl_cffi import requests 
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlparse
import re
import concurrent.futures

# ================= โค้ดส่วนจัดการเงื่อนไข (คงเดิม) =================
def is_valid_news_title(title: str, query: str = "") -> bool:
    if not title or len(title) < 10: return False
    if not re.search(r'[ก-๙]', title): return False
    
    hard_trash = ['หน้าแรก', 'เข้าสู่ระบบ', 'สมัครสมาชิก', 'หมวดหมู่', 'tag', 'archive', 'คลิปหลุด', '18+']
    if any(trash in title.lower() for trash in hard_trash): return False
    
    dynamic_spam = ['หวย', 'เลขเด็ด', 'ดูดวง', 'ผลบอล', 'สลากกินแบ่ง']
    if any(spam in title.lower() for spam in dynamic_spam):
        if not query or not any(spam in query.lower() for spam in dynamic_spam):
            return False 
            
    if query:
        query_words = query.split()
        core_words = [w for w in query_words if len(w) > 2]
        if core_words:
            match = any(word.lower() in title.lower() for word in core_words)
            if not match and len(core_words) > 1: 
                return False
                
    return True

# ================= ฟังก์ชันค้นหาหลัก =================
def search_news_references(query: str, num_results: int = 5) -> list:
    if not query.strip() or query == "SKIP_SEARCH": return []
    
    whitelist = [
        'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'ch3plus.com', 'one31.net', 
        'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 'springnews.co.th', 
        'mcot.net', 'workpointtoday.com', 'gmm25.com', 'jkn18.com', 'thairathtv',
        'thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 
        'thaipost.net', 'komchadluek.net', 'naewna.com', 'siamrath.co.th', 
        'banmuang.co.th', 'innnews.co.th', 'lokmatichon.com',
        'bangkokbiznews.com', 'prachachat.net', 'thansettakij.com', 'posttoday.com', 
        'moneyandbanking.co.th', 'efinancethai.com', 'longtunman.com',
        'isranews.org', 'hfocus.org', 'ilaw.or.th', 'thaipublica.org', 
        'factcheckthailand', 'cofact.org', 'sure.factcheckthailand.org',
        'thestandard.co', 'thematter.co', 'sanook.com', 'kapook.com', 
        'spacebar.th', 'waymagazine.org', 'themomentum.co', 'feedforfuture.co',
        'today.line.me', 'bbc.com', 'voicetv.co.th', 'dw.com'
    ]
    
    # Session ของ curl_cffi จะช่วยปลอมตัวเป็น Chrome ทำให้ไม่โดนบล็อก
    # เราระบุ impersonate="chrome" ตั้งแต่ตอนสร้าง Session เลย
    session = requests.Session(impersonate="chrome")

    def fetch_google_rss():
        res = []
        try:
            rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=th&gl=TH&ceid=TH:th"
            res_rss = session.get(rss_url, timeout=8)
            if res_rss.status_code == 200:
                root = ET.fromstring(res_rss.content)
                for item in root.findall('.//item'):
                    title = item.find('title').text if item.find('title') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    
                    # พยายามดึง snippet จาก description ถ้ามี
                    snippet = ""
                    desc = item.find('description')
                    if desc is not None and desc.text:
                        # ลบแท็ก HTML ทิ้ง
                        snippet_soup = BeautifulSoup(desc.text, "html.parser")
                        snippet = snippet_soup.get_text(strip=True)
                    
                    if is_valid_news_title(title, query):
                        res.append({'title': title, 'href': link, 'snippet': snippet if snippet else "Google News"})
        except Exception as e: 
            print(f"Google RSS Error: {e}")
        return res

    def fetch_bing_rss():
        res = []
        try:
            rss_url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss&cc=th"
            res_rss = session.get(rss_url, timeout=8)
            if res_rss.status_code == 200:
                root = ET.fromstring(res_rss.content)
                for item in root.findall('.//item'):
                    title = item.find('title').text if item.find('title') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    
                    snippet = ""
                    desc = item.find('description')
                    if desc is not None and desc.text:
                        snippet = desc.text.strip()
                        
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if any(wd in domain for wd in whitelist) and is_valid_news_title(title, query):
                        res.append({'title': title, 'href': link, 'snippet': snippet if snippet else "Bing News"})
        except Exception as e: 
            print(f"Bing RSS Error: {e}")
        return res
        
    def fetch_ddg_html():
        """ 🛡️ DDG HTML คราวนี้รอดชัวร์ เพราะใช้ curl_cffi ปลอมตัวเป็น Chrome """
        res = []
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote(query + ' ข่าว')}"
            res_ddg = session.get(ddg_url, timeout=10)
            if res_ddg.status_code == 200:
                soup = BeautifulSoup(res_ddg.text, 'html.parser')
                for div in soup.find_all('div', class_='result__body'):
                    title_tag = div.find('h2', class_='result__title')
                    if not title_tag: continue
                    a_tag = title_tag.find('a')
                    if not a_tag: continue
                    title = a_tag.text.strip()
                    link = a_tag.get('href', '')
                    
                    # ดึง Snippet ของ DuckDuckGo
                    snippet_tag = div.find('a', class_='result__snippet')
                    snippet = snippet_tag.text.strip() if snippet_tag else "DuckDuckGo"
                    
                    if "uddg=" in link:
                        link = unquote(link.split("uddg=")[1].split("&")[0])
                    if not link or not title: continue
                    
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if any(wd in domain for wd in whitelist) and is_valid_news_title(title, query):
                        res.append({'title': title, 'href': link, 'snippet': snippet})
        except Exception as e: 
            print(f"DDG Error: {e}")
        return res

    results = []
    urls_seen = set()

    # รัน 3 ช่องทางพร้อมกัน (Concurrency)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(fetch_google_rss), 
            executor.submit(fetch_bing_rss), 
            executor.submit(fetch_ddg_html)
        ]
        
        for future in concurrent.futures.as_completed(futures):
            engine_results = future.result()
            for item in engine_results:
                if item['href'] not in urls_seen:
                    urls_seen.add(item['href'])
                    results.append(item)
                    
    # ถ้ามีผลลัพธ์มากกว่า num_results ให้ตัดแค่ที่ต้องการ
    return results[:num_results]