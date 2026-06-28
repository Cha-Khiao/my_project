import streamlit as st
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlparse
import re

def is_valid_news_title(title: str, search_query: str = "") -> bool:
    if not title or len(title) < 15: return False
    if not re.search(r'[ก-๙]', title): return False
    trash_keywords = ['หน้าแรก', 'เข้าสู่ระบบ', 'สมัครสมาชิก', 'หมวดหมู่', 'tag', 'archive', 'ค้นหา', 'ติดต่อเรา', 'เกี่ยวกับเรา', 'นโยบายความเป็นส่วนตัว']
    if any(trash in title.lower() for trash in trash_keywords): return False
    if search_query:
        query_words = [w.strip() for w in search_query.split() if len(w.strip()) > 1]
        if query_words:
            match_count = sum(1 for w in query_words if w.lower() in title.lower())
            if len(query_words) >= 3 and match_count < 2: return False
            elif len(query_words) < 3 and match_count < 1: return False
    return True

@st.cache_data(ttl=3600, show_spinner=False)
def search_news_references(query: str, num_results: int = 5) -> list:
    """ระบบรวมพลัง 3 เครื่องยนต์ พร้อมระบบ Caching จดจำผลลัพธ์"""
    if not query.strip(): return []
    results = []
    urls_seen = set()
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

    # 1: Google News RSS
    try:
        rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=th&gl=TH&ceid=TH:th"
        res_rss = requests.get(rss_url, headers=headers, timeout=10)
        if res_rss.status_code == 200:
            root = ET.fromstring(res_rss.content)
            for item in root.findall('.//item'):
                title = item.find('title').text if item.find('title') is not None else ""
                link = item.find('link').text if item.find('link') is not None else ""
                if is_valid_news_title(title, query) and link not in urls_seen:
                    results.append({'title': title, 'href': link, 'body': "Google News"})
                    urls_seen.add(link)
                    if len(results) >= num_results: return results
    except Exception: pass

    # 2: DuckDuckGo HTML
    if len(results) < num_results:
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
                    if not link or link in urls_seen or not title: continue
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if any(wd in domain for wd in whitelist) and is_valid_news_title(title, query):
                        results.append({'title': title, 'href': link, 'body': "DuckDuckGo"})
                        urls_seen.add(link)
                        if len(results) >= num_results: return results
        except Exception: pass

    # 3: Bing Web Search
    if len(results) < num_results:
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
                    if not link or link in urls_seen: continue
                    domain = urlparse(link.lower()).netloc.replace('www.', '')
                    if any(wd in domain for wd in whitelist) and is_valid_news_title(title, query):
                        results.append({'title': title, 'href': link, 'body': "Bing Search"})
                        urls_seen.add(link)
                        if len(results) >= num_results: return results
        except Exception: pass

    return results