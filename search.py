from curl_cffi import requests 
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlparse
import re
import concurrent.futures

def is_blacklisted_domain(domain: str) -> bool:
    blacklist = ['tiktok.com', 'facebook.com', 'instagram.com', 'x.com', 'twitter.com', 'pantip.com', 'youtube.com']
    return any(b in domain.lower() for b in blacklist)

# 💡 เพิ่มพารามิเตอร์ snippet เข้ามา เพื่อให้อ่านเนื้อหาข่าวย่อด้วย
def calculate_relevance_and_filter(title: str, snippet: str, query: str = "") -> bool:
    if not title or len(title) < 5: return False
    if not re.search(r'[ก-๙]', title): return False
    
    hard_trash = [
        'บทความและข่าว', 'รวมข่าว', 'ข่าวล่าสุด', 'หน้าหลัก', 'ประเด็นร้อน', 'อัปเดตล่าสุด',
        'แท็ก', 'tags', 'tag', 'เรื่องที่เกี่ยวข้อง', 'archive', 'หน้าแรก', 'เข้าสู่ระบบ', 'สมัครสมาชิก', 'หมวดหมู่',
        'แคปชั่น', 'คำคม', 'ความรัก', 'วาเลนไทน์', 'สวัสดีวัน', 'คอร์ดเพลง', 'แจกวอลเปเปอร์', 
        'โปรโมชั่น', 'โค้ดส่วนลด', 'คลิปหลุด', '18+', 'หวย', 'เลขเด็ด', 'ดูดวง', 'ผลบอล', 'สลากกินแบ่ง', 'pantip'
    ]
    if any(trash in title.lower() for trash in hard_trash): 
        return False
        
    # 💡 กฎเหล็ก Strict Keyword Matching (คุณภาพ > ปริมาณ)
    if query and query != "SKIP_SEARCH":
        clean_query = re.sub(r'[^\w\sก-๙]', ' ', query)
        query_words = [w.lower() for w in clean_query.split() if len(w) > 2]
        
        # เอาพาดหัวและรายละเอียดมารวมกัน เพื่อหาบริบท
        text_to_check = (title + " " + snippet).replace(" ", "").lower()
        
        if query_words:
            matched_words = [w for w in query_words if w in text_to_check]
            
            # บังคับว่าต้องเจอคีย์เวิร์ดกี่คำ ถึงจะยอมรับว่าเป็น "ข่าวที่เกี่ยวข้อง"
            if len(query_words) == 1 and len(matched_words) < 1:
                return False
            elif len(query_words) == 2 and len(matched_words) < 2:
                # ค้นหา 2 คำ ต้องเจอทั้ง 2 คำ! (เช่น ชื่อคน + บริบท)
                return False
            elif len(query_words) >= 3 and len(matched_words) < len(query_words) - 1:
                # ค้นหา 3 คำขึ้นไป อนุโลมให้พลาดได้แค่ 1 คำเท่านั้น
                return False
                
    return True

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
    
    session = requests.Session(impersonate="chrome")

    def fetch_google_rss():
        res = []
        try:
            rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=th&gl=TH&ceid=TH:th"
            res_rss = session.get(rss_url, timeout=5)
            if res_rss.status_code == 200:
                root = ET.fromstring(res_rss.content)
                for item in root.findall('.//item'):
                    title = item.find('title').text if item.find('title') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    
                    pub_date_tag = item.find('pubDate')
                    pub_date = pub_date_tag.text if pub_date_tag is not None else "ไม่ระบุ"
                    
                    snippet = ""
                    desc = item.find('description')
                    if desc is not None and desc.text:
                        snippet_soup = BeautifulSoup(desc.text, "html.parser")
                        snippet = snippet_soup.get_text(separator=" ", strip=True)
                    
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    # 💡 ตรวจความเป๊ะของเนื้อหาก่อนดึงเข้าสู่ระบบ
                    if not is_blacklisted_domain(domain) and calculate_relevance_and_filter(title, snippet, query):
                        res.append({'title': title, 'href': link, 'pub_date': pub_date, 'snippet': snippet if snippet else "Google News", 'domain': domain})
        except Exception: 
            pass
        return res

    def fetch_bing_rss():
        res = []
        try:
            rss_url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss&cc=th"
            res_rss = session.get(rss_url, timeout=5)
            if res_rss.status_code == 200:
                root = ET.fromstring(res_rss.content)
                for item in root.findall('.//item'):
                    title = item.find('title').text if item.find('title') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    
                    pub_date_tag = item.find('pubDate')
                    pub_date = pub_date_tag.text if pub_date_tag is not None else "ไม่ระบุ"
                    
                    snippet = ""
                    desc = item.find('description')
                    if desc is not None and desc.text:
                        snippet_soup = BeautifulSoup(desc.text, "html.parser")
                        snippet = snippet_soup.get_text(separator=" ", strip=True)
                        
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    # 💡 ตรวจความเป๊ะของเนื้อหาก่อนดึงเข้าสู่ระบบ
                    if not is_blacklisted_domain(domain) and calculate_relevance_and_filter(title, snippet, query):
                        res.append({'title': title, 'href': link, 'pub_date': pub_date, 'snippet': snippet if snippet else "Bing News", 'domain': domain})
        except Exception: 
            pass
        return res
        
    def fetch_ddg_html():
        res = []
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
            res_ddg = session.get(ddg_url, timeout=5)
            if res_ddg.status_code == 200:
                soup = BeautifulSoup(res_ddg.text, 'html.parser')
                for div in soup.find_all('div', class_='result__body'):
                    title_tag = div.find('h2', class_='result__title')
                    if not title_tag: continue
                    a_tag = title_tag.find('a')
                    if not a_tag: continue
                    title = a_tag.text.strip()
                    link = a_tag.get('href', '')
                    
                    snippet_tag = div.find('a', class_='result__snippet')
                    snippet = snippet_tag.text.strip() if snippet_tag else "DuckDuckGo"
                    
                    if "uddg=" in link:
                        link = unquote(link.split("uddg=")[1].split("&")[0])
                    if not link or not title: continue
                    
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    # 💡 ตรวจความเป๊ะของเนื้อหาก่อนดึงเข้าสู่ระบบ
                    if not is_blacklisted_domain(domain) and calculate_relevance_and_filter(title, snippet, query):
                        res.append({'title': title, 'href': link, 'pub_date': 'ไม่ระบุ', 'snippet': snippet, 'domain': domain})
        except Exception: 
            pass
        return res

    results = []
    urls_seen = set()

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
                    
    def get_priority(item):
        domain = item.get('domain', '')
        if 'antifakenewscenter.com' in domain or 'sure.factcheckthailand.org' in domain or 'cofact.org' in domain:
            return 0 
        elif any(wd in domain for wd in whitelist) or 'news.google.com' in domain:
            return 1
        return 2

    results.sort(key=get_priority)
    
    for r in results:
        r.pop('domain', None)
                    
    return results[:num_results]