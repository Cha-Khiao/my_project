import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote

def clean_mobile_url(url: str) -> str:
    """เคลียร์ Tracking และปรับมาตรฐานการเข้ารหัสของลิงก์จากมือถือ"""
    url = unquote(url.strip()) 
    
    if "google.com/amp/s/" in url:
        url = url.replace("google.com/amp/s/", "").replace("https://www.", "https://")
        
    if "l.facebook.com/l.php?u=" in url:
        try:
            url = unquote(url.split("u=")[1].split("&")[0])
        except Exception: pass
            
    url = url.replace("://m.facebook.com", "://www.facebook.com")
    url = url.replace("://mobile.twitter.com", "://twitter.com")
    
    if "?" in url:
        base_url, query_str = url.split("?", 1)
        params = query_str.split("&")
        clean_params = [
            p for p in params 
            if not p.startswith(('mibextid=', 'igsh=', 'si=', 'fbclid=', 'is_from_webapp=', 'h=', 's=', 't=', 'utm_', 'line='))
        ]
        if clean_params: url = f"{base_url}?{'&'.join(clean_params)}"
        else: url = base_url
            
    return url

def resolve_facebook_mobile(url: str) -> str:
    """🌟 พระเอกของงาน: ดักฉกลิงก์โพสต์จริงจาก Facebook มือถือ ก่อนมันจะบังคับเข้าหน้า Login"""
    if "facebook.com/share/" in url.lower() or "fb.watch" in url.lower():
        try:
            # ใช้มือถือหลอก Facebook และ 🚨 ห้ามตามลิงก์ (allow_redirects=False) เด็ดขาด
            headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
            res = requests.get(url, headers=headers, allow_redirects=False, timeout=10)
            
            # เฟซบุ๊กจะส่ง Header 'Location' มาเพื่อเตะเราไปหน้า Login เราจะฉกลิงก์จากตรงนี้
            loc = res.headers.get("Location", "")
            if loc:
                if "next=" in loc: # ลิงก์จริงจะซ่อนอยู่ใน next=
                    real_url = unquote(loc.split("next=")[1].split("&")[0])
                    return real_url.replace("m.facebook.com", "www.facebook.com")
                elif "login" not in loc.lower() and "facebook.com" in loc:
                    return loc.replace("m.facebook.com", "www.facebook.com")
                    
            # แผนสำรอง: ถ้าไม่ได้มาจาก Header ให้ดึงจากโค้ด Javascript แทน
            res2 = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            js_match = re.search(r'location\.(?:replace|href)\s*=?\s*\(?["\'](.*?)["\']\)?', res2.text, re.IGNORECASE)
            if js_match:
                js_url = js_match.group(1).replace('\\/', '/')
                if "login" not in js_url.lower():
                    if js_url.startswith('/'): js_url = f"https://www.facebook.com{js_url}"
                    return js_url.split('?')[0]
        except Exception: pass
    return url

def expand_url(url: str) -> str:
    """แกะลิงก์ที่ถูกย่อมา (ห้ามยุ่งกับ Facebook เพราะเดี๋ยว resolve_facebook_mobile จัดการเอง)"""
    if "facebook.com" in url.lower(): return url 
    
    redirectors = ['shorturl.', 'bit.ly', 'tinyurl.', 't.co', 'cutt.ly', 'rebrand.ly', 'lnkd.in', 'vt.tiktok.com', 'vm.tiktok.com', 'youtu.be', 'line.me', 'today.line.me']
    if any(r in url.lower() for r in redirectors):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            res = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            if "login" not in res.url.lower() and "captcha" not in res.url.lower(): 
                return res.url 
        except Exception: pass
    return url

def resolve_short_url(url: str) -> str:
    return expand_url(url) 

def extract_social_metadata(url: str) -> str:
    """สกัดเฉพาะข้อความ/แคปชั่นจาก Social Media"""
    # 🔑 กุญแจผี: บอทตัวนี้ โซเชียลทุกค่ายยอมคาย Metadata ให้เสมอ
    headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
    
    try:
        if "x.com/" in url or "twitter.com/" in url:
            match = re.search(r'(?:x|twitter)\.com(/.*)', url)
            if match:
                clean_path = match.group(1).split('?')[0] 
                api_url = "https://api.vxtwitter.com" + clean_path
                res = requests.get(api_url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    return f"{data.get('user_name', 'ผู้ใช้งาน X')}\n{data.get('text', '')}".strip()
                return ""

        elif "instagram.com/" in url:
            match = re.search(r'instagram\.com/(?:p|reel|tv)/([^/?]+)', url)
            if match:
                shortcode = match.group(1)
                embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
                try:
                    res = requests.get(embed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
                    if res.status_code == 200:
                        soup = BeautifulSoup(res.text, 'html.parser')
                        caption_div = soup.find(class_='Caption')
                        if caption_div:
                            user_tag = caption_div.find(class_='CaptionUsername')
                            if user_tag: user_tag.extract() 
                            text = caption_div.get_text(separator='\n', strip=True)
                            if text: return f"โพสต์จาก Instagram:\n{text}"
                except Exception: pass
            return ""

        # Facebook & อื่นๆ
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8' # กันภาษาไทยเพี้ยน
        soup = BeautifulSoup(response.text, 'html.parser')
        
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
        
        title = og_title["content"] if og_title else ""
        desc = og_desc["content"] if og_desc else ""
        content = f"{title}\n{desc}".strip()
        
        # ถ้าระบบยังโดนเด้งหน้า Login อีก (เผื่อไว้) ให้ Jina ทะลวงให้
        if not content or "log in" in content.lower() or "เข้าสู่ระบบ" in content.lower():
            jina_res = requests.get(f"https://r.jina.ai/{quote(url, safe=':/%?=&-_.#')}", headers={"X-Retain-Images": "none"}, timeout=15)
            if jina_res.status_code == 200 and "Log in" not in jina_res.text:
                return jina_res.text[:1000]
            return ""
            
        return content
    except Exception:
        return ""

def force_extract_news_link(social_url: str) -> str:
    """ขุดหาลิงก์ข่าวจริงที่ซ่อนอยู่ในโพสต์"""
    if "x.com" in social_url.lower() or "twitter.com" in social_url.lower(): return ""
    # 🔑 ใช้กุญแจผี เพื่อเข้าถึง Source Code ของ Facebook ที่โซเชียลยอมปล่อย
    headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
    try:
        response = requests.get(social_url, headers=headers, timeout=15)
        decoded_html = unquote(response.text).replace('\\/', '/') # ล้างอักขระที่เฟซบุ๊กซ่อนลิงก์ไว้
        
        whitelist = ['thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 'sanook.com', 'prachachat.net', 'bangkokbiznews.com', 'mgronline.com', 'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'thestandard.co', 'workpointtoday.com', 'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 'springnews.co.th']
        domain_pattern = "|".join([d.replace('.', r'\.') for d in whitelist])
        regex = rf'https?://(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:{domain_pattern})[^\s"\'<>\\]*'
        
        found_links = re.findall(regex, decoded_html)
        for link in found_links:
            clean_link = link.split('?')[0] 
            if len(clean_link.split('/')) >= 4 and not clean_link.endswith('/home'): return clean_link
            
        # แผนสำรอง ให้ Jina ช่วยหาลิงก์
        jina_res = requests.get(f"https://r.jina.ai/{quote(social_url, safe=':/%?=&-_.#')}", timeout=15)
        if jina_res.status_code == 200:
            found_links_jina = re.findall(regex, jina_res.text)
            for link in found_links_jina:
                clean_link = link.split('?')[0] 
                if len(clean_link.split('/')) >= 4 and not clean_link.endswith('/home'): return clean_link
    except Exception: pass
    return ""

def fetch_with_fallback(url: str) -> str:
    """ระบบ 3-Layer Bypass สำหรับทะลวงกำแพงเว็บข่าว"""
    anti_bot_patterns = r'(cloudflare|500 internal server error|403 forbidden|access denied|captcha|not acceptable|checking your browser|security check|just a moment)'
    
    def is_valid_text(text):
        clean = text.strip()
        if len(clean) < 30: return False 
        if len(clean) < 800 and re.search(anti_bot_patterns, clean, re.IGNORECASE): return False 
        return True

    # Layer 1
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Accept": "*/*"}
        res = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if res.status_code == 200:
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): element.extract()
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            if is_valid_text(clean_text): return clean_text
    except Exception: pass

    # Layer 2
    try:
        safe_url = quote(url, safe=":/%?=&-_.#")
        jina_url = f"https://r.jina.ai/{safe_url}"
        response = requests.get(jina_url, headers={"Accept": "text/plain", "X-Retain-Images": "none"}, timeout=15)
        if response.status_code == 200 and is_valid_text(response.text):
            return response.text
    except Exception: pass
    
    # Layer 3
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={quote(url)}"
        res = requests.get(proxy_url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): element.extract()
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            if is_valid_text(clean_text): return clean_text
    except Exception: pass

    return ""

def extract_text_from_url(url: str) -> dict:
    """ฟังก์ชันหลัก: ศูนย์กลางควบคุมการสกัดข้อมูล"""
    try:
        url = clean_mobile_url(url)
        url = resolve_facebook_mobile(url) # 🌟 เรียกใช้พระเอกของเราตรงนี้! ให้เปลี่ยนร่างลิงก์ก่อนเลย!
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
        
        content = ""
        actual_primary_url = url
        
        if is_social:
            content = extract_social_metadata(url)
            
            if content and re.search(gambling_keywords, content, re.IGNORECASE): 
                return {"error": "GAMBLING_DETECTED"}
                
            if not content:
                fallback_content = fetch_with_fallback(actual_primary_url)
                if fallback_content: content = fallback_content
                else: return {"error": "ไม่สามารถดึงข้อมูลเว็บข่าวได้"} # ไม่ใช้คำว่า Error: จะได้ไม่โดนเหมาว่าเป็นบอท
                
            hidden_news_url = force_extract_news_link(url)
            if hidden_news_url:
                actual_primary_url = hidden_news_url
                actual_news_content = fetch_with_fallback(actual_primary_url)
                
                if actual_news_content:
                    final_content = f"[พรีวิวจากโซเชียล]:\n{content}\n\n[เนื้อหาข่าวจริงที่ซ่อนอยู่ ({actual_primary_url})]:\n{actual_news_content}"
                    if re.search(gambling_keywords, final_content, re.IGNORECASE): return {"error": "GAMBLING_DETECTED"}
                    return {"content": final_content, "actual_url": actual_primary_url}
            
            return {"content": content, "actual_url": actual_primary_url}
            
        else:
            actual_news_content = fetch_with_fallback(url)
            if actual_news_content:
                if re.search(gambling_keywords, actual_news_content, re.IGNORECASE): return {"error": "GAMBLING_DETECTED"}
                return {"content": actual_news_content, "actual_url": url}
            else:
                return {"error": "ไม่สามารถดึงข้อมูลเว็บข่าวได้"}
                
    except Exception as e:
        return {"error": "ระบบสกัดข้อมูลขัดข้อง"}