import os
import requests
import re
import concurrent.futures
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# 📋 Source Tier Registry — ใช้รับรองความน่าเชื่อถือของแหล่งข้อมูล
# =========================================================
TIER0_GOV_DOMAINS = [
    # รัฐบาลไทยและหน่วยงานราชการ
    "go.th", "thaigov.go.th", "mfa.go.th", "moi.go.th", "moph.go.th",
    "nesdc.go.th", "boi.go.th", "egp.go.th", "ratchakitchanubeksa.go.th",
    "fpo.go.th", "bot.or.th", "sec.or.th", "nacc.go.th", "ombudsman.go.th",
    "prd.go.th", "nso.go.th", "dopa.go.th", "dbd.go.th", "doh.go.th",
    # องค์กรระหว่างประเทศและสถานทูต
    "un.org", "who.int", "unicef.org", "unhcr.org", "undp.org",
    "worldbank.org", "imf.org", "asean.org", "apec.org",
    "thaiembassy.org", "thaiembdc.org", "royalthai.org",
    # ศูนย์ตรวจสอบข่าว
    "antifakenewscenter.com", "sure.factcheckthailand.org",
    "cofact.org", "factcheck.org", "poynter.org",
]

TIER1_TRUSTED_MEDIA = [
    'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'news.ch7.com', 'ch3plus.com',
    '3plusnews.com', 'one31.net', 'amarintv.com', 'nationtv.tv', 'tnnthailand.com',
    'springnews.co.th', 'mcot.net', 'tna.mcot.net', 'workpointtoday.com', 'thaich8.com',
    'thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th',
    'thaipost.net', 'komchadluek.net', 'naewna.com', 'siamrath.co.th',
    'bangkokbiznews.com', 'prachachat.net', 'thansettakij.com', 'posttoday.com',
    'mgronline.com', 'prachatai.com', 'isranews.org', 'thestandard.co',
    'thematter.co', 'the101.world', 'thaipublica.org', 'voicetv.co.th',
    'moneyandbanking.co.th', 'efinancethai.com', 'bbc.com', 'bbc.co.uk',
    'reuters.com', 'apnews.com', 'afp.com', 'bloomberg.com',
    'sanook.com', 'kapook.com', 'today.line.me', 'voathai.com',
]

BLACKLISTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'tiktok.com', 'facebook.com', 'instagram.com',
    'x.com', 'twitter.com', 'vimeo.com', 'dailymotion.com', 'line.me',
    'blockdit.com', 'pantip.com', 'wikipedia.org', 'wiktionary.org',
    'longdo.com', 'thai-language.com',
]

def get_domain(url: str) -> str:
    try:
        return urlparse(url.lower()).netloc.replace('www.', '')
    except Exception:
        return ""

def classify_tier(domain: str) -> int:
    if any(domain.endswith(d) or domain == d for d in TIER0_GOV_DOMAINS):
        return 0
    if any(d in domain for d in TIER1_TRUSTED_MEDIA):
        return 1
    return 2

# =========================================================
# 🔍 Exa AI — Semantic Search
# =========================================================
def fetch_exa_api(payload: dict, api_key: str, timeout: int = 25) -> list:
    url = "https://api.exa.ai/search"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-api-key": api_key,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        print(f"Exa API Error: {e}")
        return []

# =========================================================
# 🔍 Serper — Google Search (fallback + official sources)
# =========================================================
def fetch_serper_api(query: str, api_key: str, num: int = 20, timeout: int = 20) -> list:
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "gl": "th",
        "hl": "th",
        "num": num,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("organic", []):
            results.append({
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "text": item.get("snippet", ""),
                "publishedDate": item.get("date", "ไม่ระบุ"),
                "_source": "serper",
            })
        return results
    except Exception as e:
        print(f"Serper API Error: {e}")
        return []

def fetch_serper_gov_only(query: str, api_key: str, timeout: int = 20) -> list:
    """ค้นหาเฉพาะเว็บรัฐบาลไทยและองค์กรนานาชาติ"""
    gov_query = f"{query} site:go.th OR site:un.org OR site:who.int OR site:mfa.go.th OR site:thaigov.go.th"
    return fetch_serper_api(gov_query, api_key, num=10, timeout=timeout)

# =========================================================
# 🧹 Article Quality Filter
# =========================================================
def is_actual_article(url: str, title: str) -> bool:
    parsed = urlparse(url.lower())
    path = parsed.path
    path_parts = [p for p in path.split('/') if p]
    title_lower = title.lower()

    if re.search(r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx)($|\?)', url.lower()):
        return False
    if '[pdf]' in title_lower or 'pdf' in title_lower:
        return False
    if not path_parts:
        return False
    if path in ['/', '/th', '/en', '/th/', '/en/', '/index.html', '/index.php', '/default.aspx', '/home']:
        return False

    aggregator_keywords = [
        'category', 'topic', 'tag', 'tags', 'author', 'page',
        'search', 'archive', 'archives', 'gallery', 'calendar', 'sitemap',
    ]
    if any(keyword in path_parts for keyword in aggregator_keywords):
        return False

    if len(path_parts) == 1:
        single_path = path_parts[0]
        if single_path in ['news', 'latest', 'pr', 'article', 'articles', 'update', 'ข่าวด่วน', 'ข่าว']:
            return False
        if len(single_path) < 10 and not re.search(r'\.(html|htm|php|aspx)', single_path):
            return False

    generic_titles = ['หน้าแรก', 'หน้าหลัก', 'รวมข่าว', 'ข่าวล่าสุด', 'ข่าวด่วน', 'home', 'official website', 'เว็บไซต์ทางการ']
    if any(g in title_lower for g in generic_titles) and len(title_lower) < 30:
        return False

    if len(title.strip().split()) <= 2 and len(title) < 20:
        return False

    return True

# =========================================================
# ⚖️ Soft-Score Reranker
# =========================================================
def score_result(item: dict, locations: list, core_keywords: list, target_year: str) -> int:
    text_content = (item.get('title', '') + ' ' + item.get('snippet', '')).lower()
    domain = get_domain(item.get('href', ''))
    tier = item.get('tier', 2)
    score = 0

    # Tier bonus
    if tier == 0:
        score += 30
    elif tier == 1:
        score += 10

    # Serper-source bonus (Google index เจอ = คนหาเจอ)
    if item.get('_source') == 'serper':
        score += 5

    # Keyword match (คำพูดทั่วไป + คำราชการ)
    if core_keywords:
        has_core = False
        for kw in core_keywords:
            if kw.lower() in text_content:
                has_core = True
                score += 15
                if kw.lower() in item.get('title', '').lower():
                    score += 20
        if not has_core:
            return -1  # เตะทิ้ง

    # Location match
    if locations and any(loc.lower() in text_content for loc in locations):
        score += 20

    # Year match
    if target_year:
        try:
            ty_th = str(target_year).strip()
            ty_en = str(int(ty_th) - 543)
            has_year = ty_th in text_content or ty_en in text_content
            years_in_text = re.findall(r'\b(25\d{2}|20\d{2})\b', text_content)
            if years_in_text and not has_year:
                old_years = [y for y in years_in_text if
                             (int(y) < int(ty_th) and int(y) > 2500) or
                             (int(y) < int(ty_en) and int(y) > 2000)]
                if old_years:
                    return -1  # ข่าวเก่าเกินไป เตะทิ้ง
            if has_year:
                score += 20
        except Exception:
            pass

    return score

# =========================================================
# 🚀 Main Search Function
# =========================================================
def search_news_references(
    query: str,
    locations: list,
    core_keywords: list,
    target_year: str,
    num_results: int = 12,
    source_url: str = "",
) -> list:
    if not query.strip() or query == "SKIP_SEARCH":
        return []

    # โหลด API Keys
    exa_api_key = os.getenv("EXA_API_KEY", "").strip()
    serper_api_key = os.getenv("SERPER_API_KEY", "").strip()

    try:
        import streamlit as st
        if not exa_api_key:
            exa_api_key = st.secrets.get("EXA_API_KEY", "").strip()
        if not serper_api_key:
            serper_api_key = st.secrets.get("SERPER_API_KEY", "").strip()
    except Exception:
        pass

    if not exa_api_key and not serper_api_key:
        print("System Error: ไม่พบ EXA_API_KEY หรือ SERPER_API_KEY")
        return []

    clean_query = query.replace('"', '').replace("'", "")
    clean_source_url = source_url.split('?')[0].rstrip('/').lower() if source_url else ""

    # สร้าง query variants สำหรับ multi-query strategy
    kw_str = ' '.join(core_keywords[:4]) if core_keywords else ""
    loc_str = ' '.join(locations[:2]) if locations else ""
    gov_query = f"{clean_query} {kw_str}".strip()          # Query A+B: ทั่วไป + ราชการ
    local_query = f"{clean_query} {loc_str}".strip() if loc_str else clean_query  # Query C: เน้นพื้นที่

    # ---- Exa Payloads ----
    exa_gov_payload = {
        "query": gov_query,
        "type": "auto",
        "useAutoprompt": True,
        "numResults": 20,
        "includeDomains": ["go.th", "prd.go.th", "mfa.go.th", "thaigov.go.th",
                           "antifakenewscenter.com", "sure.factcheckthailand.org",
                           "cofact.org", "un.org", "who.int", "asean.org"],
        "contents": {"text": {"maxCharacters": 1500}},
    }
    exa_media_payload = {
        "query": local_query,
        "type": "auto",
        "useAutoprompt": False,
        "numResults": 30,
        "includeDomains": TIER1_TRUSTED_MEDIA,
        "contents": {"text": {"maxCharacters": 1500}},
    }

    # ---- เรียกทุก API พร้อมกัน (Concurrent) ----
    raw_results = []
    tasks = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        if exa_api_key:
            tasks['exa_gov'] = executor.submit(fetch_exa_api, exa_gov_payload, exa_api_key)
            tasks['exa_media'] = executor.submit(fetch_exa_api, exa_media_payload, exa_api_key)

        if serper_api_key:
            # Serper: Google Search ทั่วไป (ครอบคลุมสิ่งที่คนหาเจอด้วยมือ)
            tasks['serper_general'] = executor.submit(fetch_serper_api, clean_query, serper_api_key, 20)
            # Serper: เน้นเว็บรัฐบาลไทย + องค์กรนานาชาติ
            tasks['serper_gov'] = executor.submit(fetch_serper_gov_only, gov_query, serper_api_key)

        for name, future in tasks.items():
            try:
                results = future.result()
                for r in results:
                    r['_source'] = r.get('_source', name)
                raw_results.extend(results)
            except Exception as e:
                print(f"Task {name} failed: {e}")

    # ---- Normalize + Deduplicate + Filter ----
    urls_seen = set()
    candidates = []

    for item in raw_results:
        link = item.get("url", "").strip()
        title = (item.get("title", "") or "ข่าวที่เกี่ยวข้อง").strip()
        content = item.get("text", "")[:1500]
        pub_date = item.get("publishedDate", "ไม่ระบุ")
        source_tag = item.get("_source", "")

        if not link:
            continue

        domain = get_domain(link)
        link_clean = link.lower().split('?')[0].rstrip('/')

        # กรองออก
        if re.search(r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx)($|\?)', link.lower()):
            continue
        if '[pdf]' in title.lower():
            continue
        if clean_source_url and clean_source_url == link_clean:
            continue
        if link in urls_seen:
            continue
        if any(b in domain for b in BLACKLISTED_DOMAINS):
            continue

        tier = classify_tier(domain)

        # Tier-2 ต้องผ่าน article quality check ก่อน
        if tier == 2 and not is_actual_article(link, title):
            continue

        urls_seen.add(link)
        candidates.append({
            'title': title,
            'href': link,
            'pub_date': pub_date[:10] if pub_date != "ไม่ระบุ" else pub_date,
            'snippet': content,
            'tier': tier,
            '_source': source_tag,
        })

    # ---- Soft-Score Reranking ----
    scored = []
    for item in candidates:
        s = score_result(item, locations, core_keywords, target_year)
        if s >= 0:
            item['_score'] = s
            scored.append(item)

    scored.sort(key=lambda x: (-x['_score'], x['tier']))

    # ---- Clean up internal fields before returning ----
    final = []
    for r in scored[:num_results]:
        final.append({
            'title': r['title'],
            'href': r['href'],
            'pub_date': r['pub_date'],
            'snippet': r['snippet'],
        })

    return final