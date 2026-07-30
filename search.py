from curl_cffi import requests 
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlparse
import re
import concurrent.futures

# ================= โค้ดส่วนจัดการเงื่อนไข =================
def is_valid_news_title(title: str) -> bool:
    if not title or len(title) < 5: return False
    if not re.search(r'[ก-๙]', title): return False
    
    # 💡 ถอดคำขยะที่อาจบังเอิญไปตรงกับชื่อข่าวจริงๆ ออกไป (เช่น tag, 18+)
    hard_trash = [
        'บทความและข่าว', 'รวมข่าว', 'ข่าวล่าสุด', 'หน้าหลัก', 'ประเด็นร้อน', 'อัปเดตล่าสุด',
        'แท็ก', 'เรื่องที่เกี่ยวข้อง', 'หน้าแรก', 'เข้าสู่ระบบ', 'สมัครสมาชิก', 'หมวดหมู่',
        'แคปชั่น', 'คำคม', 'คลิปหลุด', 'หวย', 'เลขเด็ด', 'สลากกินแบ่ง'
    ]
    if any(trash in title.lower() for trash in hard_trash): 
        return False
        
    # 💡 ยกเลิกการกรองคำค้นหาที่ตึงเกินไป (Soft-Match) เพื่อปล่อยให้ข่าวทุกบริบทรอดเข้าไปให้ AI อ่านได้
                
    return True

def is_blacklisted_domain(domain: str) -> bool:
    # แบนโซเชียลมีเดียและเว็บบอร์ดขยะไม่ให้เข้ามาเป็นอ้างอิงเด็ดขาด
    blacklist = ['tiktok.com', 'facebook.com', 'instagram.com', 'x.com', 'twitter.com', 'pantip.com', 'youtube.com']
    return any(b in domain.lower() for b in blacklist)

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
                        snippet = snippet_soup.get_text(strip=True)
                    
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if not is_blacklisted_domain(domain) and is_valid_news_title(title):
                        res.append({'title': title, 'href': link, 'pub_date': pub_date, 'snippet': snippet if snippet else "Google News", 'domain': domain})
        except Exception as e: 
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
                        snippet = desc.text.strip()
                        
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if not is_blacklisted_domain(domain) and is_valid_news_title(title):
                        res.append({'title': title, 'href': link, 'pub_date': pub_date, 'snippet': snippet if snippet else "Bing News", 'domain': domain})
        except Exception as e: 
            pass
        return res
        
    def fetch_ddg_html():
        res = []
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote(query + ' ข่าว')}"
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
                    if not is_blacklisted_domain(domain) and is_valid_news_title(title):
                        res.append({'title': title, 'href': link, 'pub_date': 'ไม่ระบุ', 'snippet': snippet, 'domain': domain})
        except Exception as e: 
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
                    
    # 💡 อุดรอยรั่ว! ให้ความสำคัญกับ news.google.com เป็นอันดับ 1 เพื่อไม่ให้ข่าวจริงกระเด็นหลุดไป
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