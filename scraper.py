import re
import requests
import html
import codecs
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote, urlparse, parse_qs, urlencode, urlunparse

# ==========================================
# 1. ระบบทำความสะอาดและตรวจสอบ URL
# ==========================================
def clean_mobile_url(url: str) -> str:
    url = unquote(url.strip())
    
    # ดึงเฉพาะ URL ออกจากข้อความ (เผื่อผู้ใช้แชร์จากมือถือแล้วมีข้อความภาษาไทยปนมา)
    url_match = re.search(r'(https?://[^\s]+)', url)
    if url_match:
        url = url_match.group(1)
        
    if url.endswith('#'): url = url[:-1]
    
    # แกะลิงก์ Redirect ของ Facebook
    if "l.facebook.com/l.php?u=" in url:
        try: url = unquote(url.split("u=")[1].split("&")[0])
        except Exception: pass
            
    url = url.replace("://m.facebook.com", "://www.facebook.com")
    url = url.replace("://mobile.twitter.com", "://twitter.com")
    
    # จัดการ Query Parameters ที่เป็น Tracking ด้วย urlparse (ปลอดภัยและรองรับอนาคตได้ดีกว่า)
    parsed = urlparse(url)
    if parsed.query:
        query_dict = parse_qs(parsed.query)
        # รายชื่อพารามิเตอร์ขยะที่มาจากมือถือและโซเชียล
        spam_params = ['mibextid', 'igsh', 'si', 'fbclid', 'is_from_webapp', 'h', 's', 't', 'rdid', 'share_url', 'utm_']
        
        # คัดเอาเฉพาะ Parameter ที่ไม่ใช่ขยะ
        clean_query = {k: v for k, v in query_dict.items() if not any(k.startswith(spam) for spam in spam_params)}
        
        # ประกอบ URL กลับคืน
        parsed = parsed._replace(query=urlencode(clean_query, doseq=True))
        url = urlunparse(parsed)
        
    return url

def expand_url(url: str) -> str:
    redirectors = ['shorturl.', 'bit.ly', 'tinyurl.', 't.co', 'cutt.ly', 'rebrand.ly', 'lnkd.in', 'vt.tiktok.com', 'vm.tiktok.com', 'youtu.be', 'line.me', 'liff.line.me']
    if any(r in url.lower() for r in redirectors):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"}
            res = requests.get(url, headers=headers, allow_redirects=True, timeout=12)
            res.encoding = 'utf-8'
            final_url = res.url
            meta_match = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=["\']?([^"\'>]+)["\']?', res.text, re.IGNORECASE)
            if meta_match: final_url = meta_match.group(1)
            js_match = re.search(r'window\.location\.(?:href|replace)\s*=\s*["\'](.*?)["\']', res.text, re.IGNORECASE)
            if js_match: final_url = js_match.group(1)
            return final_url
        except Exception: pass
    return url

# ==========================================
# 2. เครื่องมือถอดรหัสและตรวจสอบความถูกต้องของข้อความ
# ==========================================
def decode_thai_text(text: str) -> str:
    if not text: return ""
    if r'\u' in text:
        try: text = re.sub(r'\\u[0-9a-fA-F]{4}', lambda m: codecs.decode(m.group(), 'unicode_escape'), text)
        except Exception: pass
    if 'à¸' in text or 'à¹' in text:
        try: text = text.encode('latin1').decode('utf-8')
        except Exception: pass
    return text

def is_valid_content(title: str, text: str, url: str) -> bool:
    """
    ด่านตรวจคนเข้าเมือง: กฎเหล็กคัดกรองขยะออกจากเนื้อหาจริง
    """
    combined = f"{title} {text}".lower()
    
    # 1. เช็ค URL ปลายทางว่าโดนเตะเข้าหน้าแอปหรือ Login หรือไม่
    bad_urls = ['messenger.com', 'apps.apple.com', 'play.google.com', 'facebook.com/login', 'm.facebook.com/login']
    if any(bad in url.lower() for bad in bad_urls):
        return False
        
    # 2. เช็ค Title (หัวเรื่อง) ดักจับคำที่มาจากหน้าบล็อกของ Facebook/Messenger
    bad_exact_titles = [
        'facebook', 'messenger', 'log in', 'เข้าสู่ระบบ', 'log in to facebook', 
        'messenger - text and video chat for free', 'messenger - โทรและส่งข้อความฟรี',
        'facebook - เข้าสู่ระบบหรือสมัครใช้งาน', 'ยินดีต้อนรับสู่ facebook'
    ]
    if title.strip().lower() in bad_exact_titles:
        return False
        
    # 3. สแกนหาความหนาแน่นของคำโฆษณาระบบ (ถ้าเจอเยอะเกินไปคือหน้า Login แน่นอน)
    system_keywords = [
        'เข้าสู่ระบบ', 'สมัครใช้งาน', 'ลืมรหัสผ่าน', 'เชื่อมต่อกับเพื่อน', 'social utility',
        'ส่งข้อความ', 'วิดีโอคอล', 'ฟีเจอร์', 'แอปพลิเคชัน', 'ดาวน์โหลด', 'messenger',
        'เข้าสู่ระบบ facebook', 'สร้างบัญชีใหม่'
    ]
    hit_count = sum(1 for word in system_keywords if word in combined)
    if hit_count >= 3: 
        return False
        
    # 4. ล้าง HTML และจัดระเบียบ ก่อนเช็คความยาวจริง
    clean_text = html.unescape(text)
    clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
    clean_text = re.sub(r'\{.*?\}', '', clean_text)
    
    # ลบคำที่เป็นปุ่ม UI ออก เพื่อวัดเนื้อหาที่แท้จริง
    ui_patterns = r'(ดูโพสต์เพิ่มเติมจาก|ดูเพิ่มเติมจาก|บน Facebook|ไม่ใช่ตอนนี้|วิดีโอที่เกี่ยวข้อง|แนะนำสำหรับคุณ|หาเพื่อนบน Facebook|เปิดใน Messenger)'
    pure_content = re.sub(ui_patterns, '', clean_text, flags=re.IGNORECASE).strip()
    
    # ถ้าเนื้อหาเพียวๆ น้อยกว่า 40 ตัวอักษร ถือว่าไม่มีข่าว
    if len(pure_content) < 40:
        return False
        
    return True

# ==========================================
# 3. ระบบสกัดข้อมูล (Core Scrapers)
# ==========================================
def extract_social_metadata(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        if "x.com/" in url or "twitter.com/" in url:
            match = re.search(r'(?:x|twitter)\.com(/.*)', url)
            if match:
                clean_path = match.group(1).split('?')[0] 
                res = requests.get("https://api.vxtwitter.com" + clean_path, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    return f"{data.get('user_name', 'ผู้ใช้งาน X')}\n{data.get('text', '')}".strip()
                return "Error: API ของ X ปฏิเสธการดึงข้อมูล"

        elif "instagram.com/" in url:
            match = re.search(r'instagram\.com/(?:p|reel|tv)/([^/?]+)', url)
            if match:
                shortcode = match.group(1)
                try:
                    res = requests.get(f"https://www.instagram.com/p/{shortcode}/embed/captioned/", headers=headers, timeout=12)
                    if res.status_code == 200:
                        res.encoding = 'utf-8'
                        soup = BeautifulSoup(res.text, 'html.parser')
                        caption_div = soup.find(class_='Caption')
                        if caption_div:
                            user_tag = caption_div.find(class_='CaptionUsername')
                            if user_tag: user_tag.extract() 
                            text = caption_div.get_text(separator='\n', strip=True)
                            if text: return f"โพสต์จาก Instagram:\n{text}"
                except Exception: pass
            return "Error: ไม่สามารถทะลวงระบบความปลอดภัยของ Instagram ได้"

        elif "facebook.com" in url or "fb.watch" in url:
            session = requests.Session()
            # ปลอมตัวเป็นระบบพรีวิวของ Facebook (Facebook Crawler) เพื่อลดการถูกบล็อก
            req_headers = {
                "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", 
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "th-TH,th;q=0.9",
                "Connection": "keep-alive"
            }
            
            fb_title = ""
            fb_desc = ""
            final_url = url
            
            try:
                res_meta = session.get(url, headers=req_headers, timeout=15, allow_redirects=True)
                final_url = res_meta.url 
                res_meta.encoding = 'utf-8'
                soup = BeautifulSoup(res_meta.text, 'html.parser')
                og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
                og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
                
                fb_title = decode_thai_text(og_title['content']) if og_title else ""
                fb_desc = decode_thai_text(og_desc['content']) if og_desc else ""
            except Exception: pass

            # นำเข้าสู่ด่านตรวจคนเข้าเมือง (Gateway Validation)
            if not is_valid_content(fb_title, fb_desc, final_url):
                # แจ้ง Error ให้ชัดเจนและแนะนำทางแก้
                return "Error: โพสต์ Facebook ถูกจำกัดการเข้าถึง แนะนำให้คัดลอกข้อความไปวางที่แท็บ 'ตรวจสอบจากข้อความ' ครับ"
            
            # ถ้าผ่านด่านมาได้ แปลว่าเป็นข่าวของจริง ทำการล้างปุ่ม UI ออกก่อนส่งให้ AI
            ui_patterns = r'(ดูโพสต์เพิ่มเติมจาก|ดูเพิ่มเติมจาก|บน Facebook|ไม่ใช่ตอนนี้|วิดีโอที่เกี่ยวข้อง|แนะนำสำหรับคุณ|หาเพื่อนบน Facebook)'
            cleaned_desc = re.sub(ui_patterns, '', fb_desc, flags=re.IGNORECASE).strip()
            
            return f"โพสต์จาก Facebook:\n{fb_title}\n{cleaned_desc}".strip()

        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
        title = og_title["content"] if og_title else (soup.title.string if soup.title else "")
        desc = og_desc["content"] if og_desc else ""
        return f"{decode_thai_text(title)}\n{decode_thai_text(desc)}".strip()
        
    except Exception as e:
        return f"Error: การสกัดข้อมูล Social Media ล้มเหลว - {str(e)}"

def force_extract_news_link(social_url: str) -> str:
    """สกัดลิงก์ข่าวจริงจากโพสต์โซเชียล"""
    if "x.com" in social_url.lower() or "twitter.com" in social_url.lower(): return ""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        session = requests.Session()
        response = session.get(social_url, headers=headers, timeout=15, allow_redirects=True)
        response.encoding = 'utf-8'
        decoded_html = decode_thai_text(unquote(response.text).replace('\\/', '/'))
        
        valid_external_links = []
        l_php_links = re.findall(r'l\.facebook\.com/l\.php\?u=([^&"\'<>\\]+)', response.text)
        for link in l_php_links:
            clean_l = unquote(link).split('?')[0]
            valid_external_links.append(clean_l)
            
        general_url_pattern = r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s"\'<>\\]*)?'
        all_links = re.findall(general_url_pattern, decoded_html)
        
        # บล็อกโดเมนระบบและไฟล์โค้ด
        exclude_domains = [
            'facebook.com', 'fb.com', 'fb.watch', 'messenger.com', 'instagram.com', 'whatsapp.com', 
            'x.com', 'twitter.com', 'tiktok.com', 'line.me', 'liff.line.me', 'fbcdn.net', 'akamaihd.net', 
            'youtube.com', 'youtu.be', 'w3.org', 'schema.org', 'ogp.me', 'play.google.com', 'apps.apple.com'
        ]
        exclude_exts = ('.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.gif', '.mp4')
        
        for link in all_links:
            clean_link = link.split('?')[0] 
            if any(domain in clean_link.lower() for domain in exclude_domains): continue
            if clean_link.lower().endswith(exclude_exts): continue 
            if len(clean_link.split('/')) >= 4 and not clean_link.endswith('/home'):
                valid_external_links.append(clean_link)
                
        if not valid_external_links: return ""

        whitelist = ['thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 'sanook.com', 'prachachat.net', 'bangkokbiznews.com', 'mgronline.com', 'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'thestandard.co', 'workpointtoday.com', 'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 'springnews.co.th']
        
        for link in valid_external_links:
            if any(w in link.lower() for w in whitelist): return link 

        return valid_external_links[0]
        
    except Exception: return ""

def fetch_with_fallback(url: str) -> str:
    anti_bot_patterns = r'(cloudflare|500 internal server error|403 forbidden|access denied|captcha|not acceptable|checking your browser|security check|just a moment)'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "th-TH,th;q=0.9",
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        content_type = res.headers.get('Content-Type', '').lower()
        if any(x in content_type for x in ['javascript', 'css', 'json', 'image', 'xml']):
            return ""
            
        if res.status_code == 200:
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): element.extract()
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            clean_text = decode_thai_text(clean_text)
            
            if len(clean_text) > 100 and not re.search(anti_bot_patterns, clean_text, re.IGNORECASE):
                return clean_text
    except Exception: pass
    return ""

# ==========================================
# 4. ฟังก์ชันหลักในการควบคุม (The Controller)
# ==========================================
def extract_text_from_url(url: str) -> dict:
    try:
        url = clean_mobile_url(url)
        url = expand_url(url)
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

        social_domains = ["facebook.com", "fb.watch", "x.com", "twitter.com", "tiktok.com", "instagram.com"]
        is_social = any(domain in url.lower() for domain in social_domains)
        
        actual_primary_url = url
        
        if is_social:
            # 1. พยายามดึงแคปชั่น
            content = extract_social_metadata(url)
            
            # 2. พยายามหาลิงก์ข่าวที่ซ่อนอยู่ (แม้จะดึงแคปชั่นไม่ได้ ก็จะพยายามหาลิงก์ซ่อนเสมอ)
            hidden_news_url = force_extract_news_link(url)
            actual_news_content = ""
            
            if hidden_news_url:
                actual_primary_url = hidden_news_url
                actual_news_content = fetch_with_fallback(hidden_news_url)
                
            final_content = ""
            
            # ผสมเนื้อหา: เอาแคปชั่นที่ตรวจสอบแล้วว่าถูกต้องมารวมกับเนื้อหาข่าวจริง
            if "Error" not in content:
                final_content += f"{content}\n\n"
            if actual_news_content:
                final_content += f"[เนื้อหาข่าวที่แนบมา ({actual_primary_url})]:\n{actual_news_content}"
                
            final_content = final_content.strip()
            
            # 🚨 ด่านสุดท้าย: ถ้าไม่มีอะไรเหลือเลย ให้รายงานกลับผู้ใช้โดยตรง ไม่กวน AI 
            # 🚨 ด่านสุดท้าย: ถ้าไม่มีอะไรเหลือเลย ให้รายงานกลับผู้ใช้โดยตรง ไม่กวน AI 
            if not final_content:
                return {"error": "Error: SOCIAL_BLOCKED ไม่สามารถตรวจสอบลิงก์นี้ได้ เนื่องจาก Facebook บล็อกระบบ Cloud (กรุณาคัดลอกข้อความไปตรวจสอบด้วยตนเองในแท็บ 'ตรวจสอบจากข้อความ')"}
                
            if re.search(gambling_keywords, final_content, re.IGNORECASE): 
                return {"error": "GAMBLING_DETECTED"}
                
            return {"content": final_content, "actual_url": actual_primary_url}
            
        else:
            # เว็บข่าวทั่วไป
            actual_news_content = fetch_with_fallback(url)
            if actual_news_content:
                if re.search(gambling_keywords, actual_news_content, re.IGNORECASE): return {"error": "GAMBLING_DETECTED"}
                return {"content": actual_news_content, "actual_url": url}
            else:
                return {"error": "ไม่สามารถดึงข้อมูลเนื้อหาจากเว็บไซต์นี้ได้"}
                
    except Exception as e:
        return {"error": f"Error: ระบบขัดข้อง - {str(e)}"}