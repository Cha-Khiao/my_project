import re
import requests
import html
import codecs
import os
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote, urlparse, parse_qs, urlencode, urlunparse
from dotenv import load_dotenv

load_dotenv()

try:
    APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
except Exception:
    APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# ==========================================
# 1. ระบบทำความสะอาดและด่านกรองขยะ
# ==========================================
def clean_mobile_url(url: str) -> str:
    url = unquote(url.strip())
    url_match = re.search(r'(https?://[^\s]+)', url)
    if url_match: url = url_match.group(1)
    if url.endswith('#'): url = url[:-1]
    
    if "l.facebook.com/l.php?u=" in url:
        try: url = unquote(url.split("u=")[1].split("&")[0])
        except Exception: pass
            
    url = url.replace("://m.facebook.com", "://www.facebook.com")
    url = url.replace("://mobile.twitter.com", "://twitter.com")
    
    parsed = urlparse(url)
    if parsed.query:
        query_dict = parse_qs(parsed.query)
        spam_params = ['mibextid', 'igsh', 'si', 'fbclid', 'is_from_webapp', 'h', 's', 't', 'rdid', 'share_url', 'utm_']
        clean_query = {k: v for k, v in query_dict.items() if not any(k.startswith(spam) for spam in spam_params)}
        parsed = parsed._replace(query=urlencode(clean_query, doseq=True))
        url = urlunparse(parsed)
    return url

def decode_thai_text(text: str) -> str:
    if not text: return ""
    if r'\u' in text:
        try: text = re.sub(r'\\u[0-9a-fA-F]{4}', lambda m: codecs.decode(m.group(), 'unicode_escape'), text)
        except Exception: pass
    if 'à¸' in text or 'à¹' in text:
        try: text = text.encode('latin1').decode('utf-8')
        except Exception: pass
    return text

def is_system_garbage(text: str) -> bool:
    """ด่านประหารขยะ: ป้องกันระบบส่งหน้า Login หรือโฆษณาไปให้ AI"""
    text_lower = text.lower()
    ui_keywords = ['ลืมรหัสผ่าน', 'เข้าสู่ระบบ', 'log in to', 'อีเมลหรือโทรศัพท์', 'สร้างบัญชีใหม่', 'ไม่ใช่ตอนนี้', 'รหัสผ่านของคุณ']
    if any(keyword in text_lower for keyword in ui_keywords): return True
    if len(text) < 80 and ('facebook' in text_lower or 'messenger' in text_lower) and ('ดาวน์โหลด' in text_lower or 'แอป' in text_lower): return True
    return False

# ==========================================
# 2. ระบบสกัดข้อมูลแบบหลายชั้น (Multi-Layer Fault-Tolerant Pipeline)
# ==========================================
def get_facebook_data_hybrid(url: str) -> str:
    """
    ระบบพยายามดึงข้อมูล 3 ชั้น เพื่อแก้ปัญหาการพึ่งพาเครื่องมือเดียว
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 🔴 LAYER 1: APIFY ACTOR (เครื่องมือหลัก)
    if APIFY_TOKEN:
        actor_id = "apify~facebook-posts-scraper"
        api_url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={APIFY_TOKEN}"
        payload = {"startUrls": [{"url": url}], "resultsLimit": 1}
        try:
            res = requests.post(api_url, json=payload, timeout=20)
            if res.status_code in [200, 201]:
                data = res.json()
                if data and len(data) > 0:
                    text = data[0].get("text", "")
                    if text and not is_system_garbage(text):
                        return f"โพสต์จาก Facebook:\n{text}"
        except Exception: pass

    # 🟡 LAYER 2: MBASIC + PROXY (ตัวชน ทะลวงข่าวที่ Apify มองไม่เห็น)
    try:
        # แปลงเป็นเว็บมือถือรุ่นเก่าที่บังคับแสดง HTML
        mbasic_url = url.replace('www.facebook.com', 'mbasic.facebook.com')
        # ใช้ AllOrigins บัง IP ของ Cloud
        proxy_url = f"https://api.allorigins.win/get?url={quote(mbasic_url)}"
        res = requests.get(proxy_url, timeout=12)
        if res.status_code == 200:
            html_content = res.json().get('contents', '')
            soup = BeautifulSoup(html_content, 'html.parser')
            for element in soup(["script", "style", "form", "header", "footer"]): element.extract()
            text = soup.get_text(separator=' ', strip=True)
            text = decode_thai_text(text)
            
            # ลบเมนูภาษาไทยของ Facebook ทิ้ง
            pure_text = re.sub(r'(ดูโพสต์เพิ่มเติมจาก|บน Facebook|เข้าสู่ระบบ|ลืมบัญชี|สร้างบัญชี|ดูเพิ่มเติม).*', '', text, flags=re.IGNORECASE).strip()
            pure_text = re.sub(r'\s+', ' ', pure_text)
            
            if len(pure_text) > 40 and not is_system_garbage(pure_text):
                return f"โพสต์จาก Facebook (Layer 2):\n{pure_text}"
    except Exception: pass

    # 🟢 LAYER 3: SEARCH ENGINE CACHE (ตัวกวาดพื้น หากโดนบล็อกทั้งหมด)
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={quote(url)}"
        res = requests.get(ddg_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for div in soup.find_all('a', class_='result__snippet'):
            text = div.get_text(strip=True)
            if len(text) > 30 and not is_system_garbage(text):
                return f"โพสต์จาก Facebook (Layer 3):\n{text}"
    except Exception: pass

    return "Error: SOCIAL_BLOCKED"

# ==========================================
# 3. ระบบดึงเว็บข่าวทั่วไป 
# ==========================================
def fetch_normal_website(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "th-TH,th;q=0.9",
    }
    try:
        res = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if res.status_code == 200:
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside"]): element.extract()
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            clean_text = decode_thai_text(clean_text)
            if len(clean_text) > 100:
                return clean_text
    except Exception: pass
    return ""

# ==========================================
# 4. ฟังก์ชันหลักในการควบคุม (The Controller)
# ==========================================
def extract_text_from_url(url: str) -> dict:
    try:
        url = clean_mobile_url(url)
        
        VIDEO_PATTERNS = [
            r'youtube\.com/watch', r'youtu\.be', r'youtube\.com/shorts',
            r'tiktok\.com', r'vt\.tiktok\.com', r'vm\.tiktok\.com',
            r'facebook\.com/.*/videos/', r'fb\.watch', r'/share/v/', r'/share/r/', 
            r'vimeo\.com', r'dailymotion\.com'
        ]
        if any(re.search(p, url.lower()) for p in VIDEO_PATTERNS): return {"error": "VIDEO_DETECTED"}

        gambling_keywords = r'(สล็อต|บาคาร่า|เว็บตรง|pg slot|คาสิโน|แทงบอล|หวยออนไลน์|ฝากถอนไม่มีขั้นต่ำ|แตกง่าย|ปั่นสล็อต|เครดิตฟรี|เว็บพนัน|สล็อตออนไลน์)'
        if re.search(r'(slot|casino|ufa\d+|pgslot|เว็บพนัน)', url.lower()): return {"error": "GAMBLING_DETECTED"}

        actual_primary_url = url
        
        # 🚦 ระบบ Routing: แยกทางทำงาน
        if "facebook.com" in url.lower() or "fb.watch" in url.lower():
            
            # เรียกใช้ระบบ 3 ชั้น (Hybrid)
            final_content = get_facebook_data_hybrid(url)
            
            if "Error:" in final_content:
                return {"error": "SOCIAL_BLOCKED"}
                
            if re.search(gambling_keywords, final_content, re.IGNORECASE): 
                return {"error": "GAMBLING_DETECTED"}
                
            return {"content": final_content, "actual_url": actual_primary_url}
            
        elif "x.com" in url.lower() or "twitter.com" in url.lower():
            match = re.search(r'(?:x|twitter)\.com(/.*)', url)
            if match:
                clean_path = match.group(1).split('?')[0] 
                res = requests.get("https://api.vxtwitter.com" + clean_path, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    content = f"{data.get('user_name', 'ผู้ใช้งาน X')}\n{data.get('text', '')}".strip()
                    return {"content": content, "actual_url": actual_primary_url}
            return {"error": "SOCIAL_BLOCKED"}
            
        else:
            actual_news_content = fetch_normal_website(url)
            if actual_news_content:
                if re.search(gambling_keywords, actual_news_content, re.IGNORECASE): return {"error": "GAMBLING_DETECTED"}
                return {"content": actual_news_content, "actual_url": url}
            else:
                return {"error": "ไม่สามารถดึงข้อมูล"}
                
    except Exception as e:
        return {"error": f"Error: ระบบขัดข้อง - {str(e)}"}