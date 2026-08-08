import os
import requests
import re
import concurrent.futures
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def fetch_serper(endpoint, payload, api_key, timeout=15):
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(f"https://google.serper.dev/{endpoint}", headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        results = []
        items = data.get("organic", []) if endpoint == "search" else data.get("news", [])
        
        for item in items:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "date": item.get("date", "ไม่ระบุ")
            })
        return results
    except Exception as e:
        print(f"❌ Serper API Error ({endpoint}): {e}")
        return []

def search_news_references(query: str, num_results: int = 10, must_have_keywords: list = None, source_url: str = "") -> list:
    if not query.strip() or query == "SKIP_SEARCH": 
        return []
    
    serper_api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not serper_api_key:
        try:
            import streamlit as st
            serper_api_key = st.secrets.get("SERPER_API_KEY", "").strip()
        except: pass
        
    if not serper_api_key:
        print("❌ System Error: ไม่พบ SERPER_API_KEY ในไฟล์ .env")
        return []

    # ปล่อยเครื่องหมาย " " ไว้ เพื่อใช้ล็อก Google
    clean_query = query.replace("'", "")
    clean_source_url = source_url.split('?')[0].rstrip('/').lower() if source_url else ""

    blacklisted_domains = [
        'tiktok.com', 'facebook.com', 'instagram.com', 'x.com', 'twitter.com', 'pantip.com', 'youtube.com', 'blockdit.com',
        'wikipedia.org', 'wiktionary.org', 'longdo.com', 'thai-language.com', 'sanook.com/dictionary', 'dict.'
    ]

    trusted_media = [
        'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'news.ch7.com', 'ch3plus.com', '3plusnews.com', 
        'one31.net', 'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 'springnews.co.th', 
        'mcot.net', 'tna.mcot.net', 'workpointtoday.com', 'thaich8.com',
        'thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 
        'thaipost.net', 'komchadluek.net', 'naewna.com', 'siamrath.co.th', 
        'bangkokbiznews.com', 'prachachat.net', 'thansettakij.com', 'posttoday.com', 
        'mgronline.com', 'prachatai.com', 'isranews.org', 'thestandard.co', 'thematter.co', 'the101.world', 
        'thaipublica.org', 'voicetv.co.th', 'moneyandbanking.co.th', 'efinancethai.com', 
        'bbc.com', 'reuters.com', 'apnews.com', 'sanook.com', 'kapook.com', 'today.line.me'
    ]

    payload_general = {"q": clean_query, "gl": "th", "hl": "th", "num": 15}
    payload_news = {"q": clean_query, "gl": "th", "hl": "th", "num": 10}
    payload_gov = {"q": f"{clean_query} site:go.th", "gl": "th", "hl": "th", "num": 10}

    raw_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_gov = executor.submit(fetch_serper, "search", payload_gov, serper_api_key)
        future_news = executor.submit(fetch_serper, "news", payload_news, serper_api_key)
        future_general = executor.submit(fetch_serper, "search", payload_general, serper_api_key)
        
        raw_results.extend(future_gov.result())
        raw_results.extend(future_news.result())
        raw_results.extend(future_general.result())

    urls_seen = set()
    processed_results = []
    
    for item in raw_results:
        title = item.get("title", "").strip()
        link = item.get("link", "")
        content = item.get("snippet", "")[:1200]
        pub_date = item.get("date", "ไม่ระบุ")
        
        title_lower = title.lower()
        link_lower = link.lower()
        
        # บล็อกไฟล์ PDF
        if '[pdf]' in title_lower or 'pdf' in title_lower:
            continue
        if re.search(r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx)($|\?)', link_lower):
            continue
            
        if not title or title_lower == 'untitled' or len(title) < 5:
            continue

        parsed_url = urlparse(link_lower)
        domain = parsed_url.netloc.replace('www.', '')
        link_clean = link_lower.split('?')[0].rstrip('/')
        
        # บล็อก Generic Homepages อย่าง "Ministry of Interior - กระทรวงมหาดไทย"
        if not parsed_url.path or parsed_url.path == '/' or parsed_url.path.lower() in ['/home', '/th', '/index']:
            continue
        if re.search(r'/(category|topic|tag|tags|author|page)/|\.xml|sitemap', link_lower):
            continue
            
        if clean_source_url and (clean_source_url == link_clean):
            continue
            
        if link in urls_seen or any(b in domain for b in blacklisted_domains):
            continue
        if not re.search(r'[ก-๙]', title + content):
            continue
            
        # 💡 Soft-Filter: อย่างน้อยชื่อเรื่องหรือเนื้อหาต้องมีคำบังคับโผล่มาบ้าง กันข่าวหลงทาง
        text_content = (title + " " + content).lower()
        if must_have_keywords:
            has_relevant_word = False
            for w in must_have_keywords:
                if w.lower() in text_content:
                    has_relevant_word = True
                    break
            # ถ้าไม่มีคำว่า "สายไฟ" หรือ "สุรินทร์" ในชื่อเรื่องเลย ให้เตะทิ้ง (เช่น โซลาร์เซลล์)
            if not has_relevant_word:
                continue 
        
        tier = 2
        if domain.endswith('.go.th') or domain.endswith('.gov') or domain.endswith('.ac.th') or domain.endswith('.or.th'):
            tier = 0
        elif 'antifakenewscenter.com' in domain or 'sure.factcheckthailand.org' in domain or 'cofact.org' in domain:
            tier = 0
        elif any(wd in domain for wd in trusted_media) or 'news.google.com' in domain:
            tier = 1

        urls_seen.add(link)
        processed_results.append({
            'title': title,
            'href': link,
            'pub_date': pub_date,
            'snippet': content, 
            'tier': tier 
        })
        
    processed_results.sort(key=lambda x: x['tier'])
    
    for r in processed_results:
        r.pop('tier', None)
        
    return processed_results[:num_results]