import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlparse
import re
import concurrent.futures

def is_valid_news_title(title: str, query: str = "") -> bool:
    """ตัวกรองอัจฉริยะ: ดักขยะ SEO Spam แบบยืดหยุ่น"""
    if not title or len(title) < 10: return False
    if not re.search(r'[ก-๙]', title): return False
    
    # 🛑 1. ขยะที่แบนถาวร (ไม่มีประโยชน์ในแง่ข่าวสารแน่นอน)
    hard_trash = ['หน้าแรก', 'เข้าสู่ระบบ', 'สมัครสมาชิก', 'หมวดหมู่', 'tag', 'archive', 'คลิปหลุด', '18+']
    if any(trash in title.lower() for trash in hard_trash): return False
    
    # 🧠 2. Dynamic Spam Filter (บล็อกหวย/ดูดวง เฉพาะตอนที่เนื้อหาหลักไม่ได้เกี่ยวกับเรื่องพวกนี้)
    dynamic_spam = ['หวย', 'เลขเด็ด', 'ดูดวง', 'ผลบอล', 'สลากกินแบ่ง']
    
    if any(spam in title.lower() for spam in dynamic_spam):
        if not query or not any(spam in query.lower() for spam in dynamic_spam):
            return False 
            
    # 🎯 3. Soft-Relevance Check (ต้องมีคำหลักตรงกันบ้าง)
    if query:
        query_words = query.split()
        core_words = [w for w in query_words if len(w) > 2]
        if core_words:
            match = any(word.lower() in title.lower() for word in core_words)
            if not match: return False
            
    return True

def search_news_references(query: str, num_results: int = 5) -> list:
    """ระบบรวมพลัง 3 เครื่องยนต์ทำงานพร้อมกัน (Concurrent Execution) พร้อมด่านตรวจสกัดอัจฉริยะ"""
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
        'factcheckthailand', 'cofact.org',
        'thestandard.co', 'thematter.co', 'sanook.com', 'kapook.com', 
        'spacebar.th', 'waymagazine.org', 'themomentum.co', 'feedforfuture.co',
        'today.line.me', 'bbc.com/thai', 'voicetv.co.th', 'dw.com/th'
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    results = []
    urls_seen = set()

    # Worker 1: Google News
    def fetch_google():
        res = []
        try:
            rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=th&gl=TH&ceid=TH:th"
            res_rss = requests.get(rss_url, headers=headers, timeout=10)
            if res_rss.status_code == 200:
                root = ET.fromstring(res_rss.content)
                for item in root.findall('.//item'):
                    title = item.find('title').text if item.find('title') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    if is_valid_news_title(title, query):
                        res.append({'title': title, 'href': link, 'body': "Google News"})
        except Exception: pass
        return res

    # Worker 2: DuckDuckGo
    def fetch_ddg():
        res = []
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote(query + ' ข่าว')}"
            res_ddg = requests.get(ddg_url, headers=headers, timeout=12)
            if res_ddg.status_code == 200:
                soup = BeautifulSoup(res_ddg.text, 'html.parser')
                for div in soup.find_all('div', class_='result__body'):
                    title_tag = div.find('h2', class_='result__title')
                    if not title_tag: continue
                    a_tag = title_tag.find('a')
                    if not a_tag: continue
                    title = a_tag.text.strip()
                    link = a_tag.get('href', '')
                    if "uddg=" in link:
                        link = unquote(link.split("uddg=")[1].split("&")[0])
                    if not link or not title: continue
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if any(wd in domain for wd in whitelist) and is_valid_news_title(title, query):
                        res.append({'title': title, 'href': link, 'body': "DuckDuckGo"})
        except Exception: pass
        return res

    # Worker 3: Bing Search
    def fetch_bing():
        res = []
        try:
            web_url = f"https://www.bing.com/search?q={quote(query + ' ข่าว')}"
            res_web = requests.get(web_url, headers=headers, timeout=12)
            if res_web.status_code == 200:
                soup = BeautifulSoup(res_web.text, 'html.parser')
                for li in soup.find_all('li', class_='b_algo'):
                    a_tag = li.find('a')
                    if not a_tag: continue
                    link = a_tag.get('href', '')
                    title = a_tag.text
                    if not link: continue
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if any(wd in domain for wd in whitelist) and is_valid_news_title(title, query):
                        res.append({'title': title, 'href': link, 'body': "Bing Search"})
        except Exception: pass
        return res

    # ปล่อย Worker ทั้ง 3 ตัวทำงานพร้อมกันแบบขนาน
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(fetch_google),
            executor.submit(fetch_ddg),
            executor.submit(fetch_bing)
        ]
        
        for future in concurrent.futures.as_completed(futures):
            engine_results = future.result()
            for item in engine_results:
                if item['href'] not in urls_seen:
                    urls_seen.add(item['href'])
                    results.append(item)
                    if len(results) >= num_results:
                        return results
                        
    return results