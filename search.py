import os
import requests
import re
import concurrent.futures
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def fetch_exa_api(payload, api_key, timeout=25):
    url = "https://api.exa.ai/search"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-api-key": api_key
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except Exception as e:
        print(f"❌ Exa API Error: {e}")
        return []

def is_actual_article(url, title):
    parsed = urlparse(url.lower())
    path = parsed.path
    path_parts = [p for p in path.split('/') if p]
    title_lower = title.lower()

    if re.search(r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx)($|\?)', url.lower()): return False
    if '[pdf]' in title_lower or 'pdf' in title_lower: return False
    if not path_parts: return False
    if path in ['/', '/th', '/en', '/th/', '/en/', '/index.html', '/index.php', '/default.aspx', '/home']: return False

    aggregator_keywords = ['category', 'topic', 'tag', 'tags', 'author', 'page', 'search', 'archive', 'archives', 'gallery', 'calendar', 'sitemap']
    if any(keyword in path_parts for keyword in aggregator_keywords): return False

    if len(path_parts) == 1:
        single_path = path_parts[0]
        if single_path in ['news', 'latest', 'pr', 'article', 'articles', 'update', 'ข่าวด่วน', 'ข่าว']: return False
        if len(single_path) < 10 and not re.search(r'\.(html|htm|php|aspx)', single_path): return False

    generic_titles = ['หน้าแรก', 'หน้าหลัก', 'รวมข่าว', 'ข่าวล่าสุด', 'ข่าวด่วน', 'home', 'official website', 'เว็บไซต์ทางการ']
    if any(g_title in title_lower for g_title in generic_titles):
        if len(title_lower) < 30: return False
    
    if len(title.strip().split()) <= 2 and len(title) < 20: return False
    return True

# 💡 Python ทำการเปรียบเทียบด่านแรก (Pre-Comparison) ตัดขยะทิ้งก่อนส่งถึง AI
def search_news_references(query: str, locations: list, core_keywords: list, target_year: str, num_results: int = 10, source_url: str = "") -> list:
    if not query.strip() or query == "SKIP_SEARCH": return []
    
    exa_api_key = os.getenv("EXA_API_KEY", "").strip()
    if not exa_api_key:
        try:
            import streamlit as st
            exa_api_key = st.secrets.get("EXA_API_KEY", "").strip()
        except: pass
        
    if not exa_api_key:
        print("❌ System Error: ไม่พบ EXA_API_KEY ในไฟล์ .env")
        return []

    clean_query = query.replace('"', '').replace("'", "")
    clean_source_url = source_url.split('?')[0].rstrip('/').lower() if source_url else ""

    blacklisted_domains = [
        'youtube.com', 'youtu.be', 'tiktok.com', 'facebook.com', 'instagram.com', 'x.com', 'twitter.com', 
        'vimeo.com', 'dailymotion.com', 'line.me', 'blockdit.com', 'pantip.com',
        'wikipedia.org', 'wiktionary.org', 'longdo.com', 'thai-language.com'
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

    payload_gov = {
        "query": clean_query,
        "type": "auto", 
        "useAutoprompt": False,
        "numResults": 15,
        "includeDomains": ["go.th", "antifakenewscenter.com", "sure.factcheckthailand.org", "cofact.org"],
        "contents": { "text": { "maxCharacters": 1500 } }
    }

    payload_media = {
        "query": clean_query,
        "type": "auto",
        "useAutoprompt": False,
        "numResults": 20,
        "includeDomains": trusted_media,
        "contents": { "text": { "maxCharacters": 1500 } }
    }

    raw_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_gov = executor.submit(fetch_exa_api, payload_gov, exa_api_key)
        future_media = executor.submit(fetch_exa_api, payload_media, exa_api_key)
        raw_results.extend(future_gov.result())
        raw_results.extend(future_media.result())

    urls_seen = set()
    processed_results = []
    
    for item in raw_results:
        title = item.get("title", "").strip() if item.get("title") else "ข่าวที่เกี่ยวข้อง"
        link = item.get("url", "")
        content = item.get("text", "")[:1500] 
        pub_date = item.get("publishedDate", "ไม่ระบุ")
        
        parsed_url = urlparse(link.lower())
        domain = parsed_url.netloc.replace('www.', '')
        link_clean = link.lower().split('?')[0].rstrip('/')

        if re.search(r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx)($|\?)', link.lower()): continue
        if '[pdf]' in title.lower() or 'pdf' in title.lower(): continue
        if clean_source_url and (clean_source_url == link_clean): continue
        if link in urls_seen or any(b in domain for b in blacklisted_domains): continue

        text_content = (title + " " + content).lower()
        
        # ⚠️ 1. เปรียบเทียบสถานที่ (Hard Gate): ไม่ตรง = เตะทิ้ง
        if locations:
            if not any(loc.lower() in text_content for loc in locations):
                continue 

        # ⚠️ 2. เปรียบเทียบปี พ.ศ. (Strict Regex Time Gate): 
        # ถ้าเนื้อหามีการระบุปีเก่าๆ แต่ไม่มีปีเป้าหมายเลย = เตะทิ้งแน่นอน 100%
        if target_year:
            try:
                ty_th = str(target_year).strip()
                ty_en = str(int(ty_th) - 543)
                
                has_target_year = ty_th in text_content or ty_en in text_content
                
                # ใช้ Regex กวาดหาตัวเลขปีทั้งหมดในเนื้อหาข่าว
                years_in_text = re.findall(r'\b(25\d{2}|20\d{2})\b', text_content)
                
                if years_in_text:
                    # ถ้ามีการระบุปีในข่าว แต่ในนั้นไม่มีปีเป้าหมาย (เช่น มีแต่ 2561 แต่หา 2569 ไม่เจอ) = ข่าวเก่าล้านเปอร์เซ็นต์
                    if not has_target_year:
                        continue # เตะทิ้ง!
            except Exception:
                pass

        # ⚠️ 3. เปรียบเทียบแก่นเรื่อง (Hard Gate)
        if core_keywords:
            has_core = any(kw.lower() in text_content for kw in core_keywords)
            if not has_core:
                continue

        is_gov_or_factcheck = domain.endswith('.go.th') or domain.endswith('.gov') or domain.endswith('.ac.th') or domain.endswith('.or.th') or 'antifakenewscenter.com' in domain or 'sure.factcheckthailand.org' in domain or 'cofact.org' in domain

        if not is_gov_or_factcheck:
            if not is_actual_article(link, title): 
                continue

        tier = 2
        if is_gov_or_factcheck:
            tier = 0
        elif any(wd in domain for wd in trusted_media):
            tier = 1

        urls_seen.add(link)
        processed_results.append({
            'title': title,
            'href': link,
            'pub_date': pub_date[:10] if pub_date != "ไม่ระบุ" else pub_date, 
            'snippet': content,
            'tier': tier
        })
        
    # จัดอันดับตามความน่าเชื่อถือของสื่อ (ข่าวทุกชิ้นที่รอดมาคือข่าวที่ตรงบริบท 100% แล้ว)
    processed_results.sort(key=lambda x: x['tier'])
    for r in processed_results: r.pop('tier', None)
        
    # ส่ง 10 ลิงก์ที่เจ๋งที่สุดให้ AI เปรียบเทียบเนื้อหาลึกๆ
    return processed_results[:num_results]