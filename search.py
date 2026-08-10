import os
import requests
import re
import concurrent.futures
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# 🏛️ WHITELIST แหล่งข้อมูลที่น่าเชื่อถือ (ตามคำแนะนำอาจารย์)
# =========================================================
OFFICIAL_SOURCES = [
    "antifakenewscenter.com",
    "sure.factcheckthailand.org",
    "cofact.org",
    "go.th",  # เว็บไซต์รัฐบาลไทยทั้งหมด
    "gov.th",
    "ddc.moph.go.th",  # กรมควบคุมโรค
    "thaigov.go.th",  # ทำเนียบรัฐบาล
    "prachasampai.go.th",  # สำนักข่าวกรมประชาสัมพันธ์
]

TRUSTED_MEDIA = [
    # สื่อสาธารณะ
    "thaipbs.or.th",
    "tpbs.or.th",
    # สื่อหนังสือพิมพ์ใหญ่
    "thairath.co.th",
    "khaosod.co.th",
    "matichon.co.th",
    "dailynews.co.th",
    "thaipost.net",
    "komchadluek.net",
    "naewna.com",
    "siamrath.co.th",
    "bangkokbiznews.com",
    "prachachat.net",
    "thansettakij.com",
    "posttoday.com",
    "mgronline.com",
    "prachatai.com",
    # สื่อออนไลน์คุณภาพ
    "thestandard.co",
    "thematter.co",
    "the101.world",
    "thaipublica.org",
    "voicetv.co.th",
    "nationtv.tv",
    "springnews.co.th",
    "mcot.net",
    "workpointtoday.com",
    # สื่อโทรทัศน์
    "pptvhd36.com",
    "ch7.com",
    "news.ch7.com",
    "ch3plus.com",
    "3plusnews.com",
    "one31.net",
    "amarintv.com",
    # สำนักข่าวต่างประเทศที่รายงานภาษาไทย
    "bbc.com/thai",
    "reuters.com",
    "apnews.com",
    "cnn.com",
    # พอร์ทัลข่าวทั่วไป (แต่มีมาตรฐาน)
    "sanook.com",
    "kapook.com",
]

EDUCATIONAL_SOURCES = [
    "ac.th",  # มหาวิทยาลัยทั้งหมดในไทย
    "chula.ac.th",
    "mahidol.ac.th",
    "tu.ac.th",
    "ku.ac.th",
    "cmu.ac.th",
]

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

def get_source_tier(domain: str) -> int:
    """กำหนดลำดับความน่าเชื่อถือของแหล่งข้อมูล"""
    domain = domain.lower()
    
    # Tier 0: หน่วยงานราชการและองค์กรตรวจสอบข้อเท็จจริง
    for src in OFFICIAL_SOURCES:
        if src in domain:
            return 0
    
    # Tier 1: สื่อมวลชนที่น่าเชื่อถือ
    for src in TRUSTED_MEDIA:
        if src in domain:
            return 1
    
    # Tier 2: สถาบันการศึกษา
    for src in EDUCATIONAL_SOURCES:
        if src in domain:
            return 2
    
    # Tier 3: ทั่วไป (ยังไม่ระบุชัดเจน)
    return 3

# 💡 ด่านเปรียบเทียบแรก: Python สกัดเนื้อหาที่ไม่ใช่อย่างเด็ดขาด
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

    # สร้าง Payload สำหรับค้นหาแบบแบ่งชั้นความน่าเชื่อถือ
    payload_official = {
        "query": clean_query,
        "type": "auto", 
        "useAutoprompt": False,
        "numResults": 20,  # เพิ่มจำนวนผลลัพธ์เพื่อให้ครอบคลุมมากขึ้น
        "includeDomains": OFFICIAL_SOURCES,
        "contents": { "text": { "maxCharacters": 2000 } }  # เพิ่มข้อความเพื่อวิเคราะห์ได้ละเอียดขึ้น
    }

    payload_media = {
        "query": clean_query,
        "type": "auto",
        "useAutoprompt": False,
        "numResults": 30,  # เพิ่มจำนวนผลลัพธ์
        "includeDomains": TRUSTED_MEDIA,
        "contents": { "text": { "maxCharacters": 2000 } }
    }

    payload_general = {
        "query": clean_query,
        "type": "auto",
        "useAutoprompt": False,
        "numResults": 20,
        "excludeDomains": blacklisted_domains,
        "contents": { "text": { "maxCharacters": 2000 } }
    }

    raw_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_official = executor.submit(fetch_exa_api, payload_official, exa_api_key)
        future_media = executor.submit(fetch_exa_api, payload_media, exa_api_key)
        future_general = executor.submit(fetch_exa_api, payload_general, exa_api_key)
        
        raw_results.extend(future_official.result())
        raw_results.extend(future_media.result())
        raw_results.extend(future_general.result())

    urls_seen = set()
    processed_results = []
    
    for item in raw_results:
        title = item.get("title", "").strip() if item.get("title") else "ข่าวที่เกี่ยวข้อง"
        link = item.get("url", "")
        content = item.get("text", "")[:2000] 
        pub_date = item.get("publishedDate", "ไม่ระบุ")
        
        parsed_url = urlparse(link.lower())
        domain = parsed_url.netloc.replace('www.', '')
        link_clean = link.lower().split('?')[0].rstrip('/')

        # กรองไฟล์ขยะและเว็บซ้ำ
        if re.search(r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx)($|\?)', link.lower()): continue
        if '[pdf]' in title.lower() or 'pdf' in title.lower(): continue
        if clean_source_url and (clean_source_url == link_clean): continue
        if link in urls_seen or any(b in domain for b in blacklisted_domains): continue

        text_content = (title + " " + content).lower()
        
        # ⚠️ 1. เปรียบเทียบสถานที่: ใช้ Fuzzy Matching แบบยืดหยุ่น
        if locations:
            location_match = False
            for loc in locations:
                # ตรวจสอบทั้งชื่อเต็มและชื่อย่อ
                if loc.lower() in text_content:
                    location_match = True
                    break
                # ตรวจสอบคำที่เกี่ยวข้อง (เช่น "กทม" กับ "กรุงเทพมหานคร")
                if loc.lower() == "กรุงเทพ" and ("กทม" in text_content or "กรุงเทพฯ" in text_content):
                    location_match = True
                    break
            if not location_match:
                # ถ้าไม่มีสถานที่เลย แต่ยังพอมีความเกี่ยวข้องอยู่ ให้เก็บไว้แต่ลดคะแนน
                # ไม่ตัดทิ้งทันทีเพื่อไม่ให้พลาดข้อมูลสำคัญ
                pass

        # ⚠️ 2. เปรียบเทียบปี พ.ศ.: ยืดหยุ่นมากขึ้น
        if target_year:
            try:
                ty_th = str(target_year).strip()
                ty_en = str(int(ty_th) - 543)
                has_target_year = ty_th in text_content or ty_en in text_content
                
                # ค้นหาตัวเลขปีทั้งหมดที่ปรากฏในข่าว
                years_in_text = re.findall(r'\b(25\d{2}|20\d{2})\b', text_content)
                if years_in_text and not has_target_year:
                    # อนุญาตให้มีปีอื่นปนได้บ้าง แต่ต้องมีอย่างน้อย 1 ปีที่ใกล้เคียง (±2 ปี)
                    current_year_int = int(ty_th)
                    acceptable_years = [current_year_int, current_year_int-1, current_year_int+1, current_year_int-2, current_year_int+2]
                    has_acceptable_year = any(str(y) in years_in_text for y in acceptable_years)
                    if not has_acceptable_year:
                        continue 
            except Exception:
                pass

        # ⚠️ 3. เปรียบเทียบแก่นเรื่อง: ยืดหยุ่นมากขึ้น
        match_score = 0
        if core_keywords:
            keyword_matches = 0
            for kw in core_keywords:
                if kw.lower() in text_content:
                    keyword_matches += 1
                    match_score += 3
                if kw.lower() in title.lower():
                    match_score += 8
            
            # ถ้ามี keyword ตรงอย่างน้อย 1 ใน 3 ก็ถือว่าเกี่ยวข้อง
            if keyword_matches >= 1:
                pass  # เก็บไว้
            else:
                continue  # ไม่เกี่ยวข้องจริงๆ ค่อยตัดทิ้ง

        # ประเมินความน่าเชื่อถือของแหล่งที่มา
        tier = get_source_tier(domain)
        
        # เพิ่มคะแนนให้กับแหล่งที่น่าเชื่อถือ
        if tier == 0:  # ราชการ/Fact-checker
            match_score += 15
        elif tier == 1:  # สื่อหลัก
            match_score += 10
        elif tier == 2:  # การศึกษา
            match_score += 8
        
        # ตรวจสอบว่าเป็นบทความจริงหรือไม่ (เฉพาะแหล่งทั่วไป)
        if tier >= 3:
            if not is_actual_article(link, title): 
                continue

        urls_seen.add(link)
        processed_results.append({
            'title': title,
            'href': link,
            'pub_date': pub_date[:10] if pub_date != "ไม่ระบุ" else pub_date, 
            'snippet': content,
            'tier': tier,
            'match_score': match_score,
            'domain': domain
        })
        
    # จัดอันดับด้วยความเกี่ยวข้องและความน่าเชื่อถือ
    processed_results.sort(key=lambda x: (-x['match_score'], x['tier']))
    
    # ตัด tier และ match_score ออกก่อนส่งให้ AI
    for r in processed_results: 
        r.pop('tier', None)
        r.pop('match_score', None)
        r.pop('domain', None)
        
    return processed_results[:num_results]
