import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote

def clean_mobile_url(url: str) -> str:
    """เคลียร์ Tracking และ Redirect ของลิงก์มือถือ"""
    # 🛠️ [แก้บั๊กที่ 1]: แปลงลิงก์มือถือที่มีภาษาไทยดิบๆ ให้อยู่ในมาตรฐานเดียวกัน
    url = unquote(url.strip())
    
    # เคลียร์ AMP ของ Google ที่แอปมือถือชอบใช้
    if "google.com/amp/s/" in url:
        url = url.replace("google.com/amp/s/", "").replace("https://www.", "https://")
        
    # จัดการ Redirect ของ Facebook
    if "l.facebook.com/l.php?u=" in url:
        try:
            url = unquote(url.split("u=")[1].split("&")[0])
        except Exception: 
            pass
            
    url = url.replace("://m.facebook.com", "://www.facebook.com")
    url = url.replace("://mobile.twitter.com", "://twitter.com")
    
    # ตัดพารามิเตอร์ขยะ
    if "?" in url:
        base_url, query_str = url.split("?", 1)
        params = query_str.split("&")
        
        # ตัดตัวติดตามต่างๆ รวมถึง utm_ และ line
        clean_params = [
            p for p in params 
            if not p.startswith(('mibextid=', 'igsh=', 'si=', 'fbclid=', 'is_from_webapp=', 'h=', 's=', 't=', 'utm_', 'line='))
        ]
        
        if clean_params: 
            url = f"{base_url}?{'&'.join(clean_params)}"
        else: 
            url = base_url
            
    return url

def expand_url(url: str) -> str:
    """แกะลิงก์ที่ถูกย่อมา ให้เป็นลิงก์เต็ม"""
    
    # 🚨 [เพิ่มโค้ดส่วนนี้] ดักจับเฉพาะลิงก์แชร์จากมือถือ Facebook โดยเฉพาะ
    if "facebook.com/share/" in url.lower():
        try:
            # 1. จำลองเป็นมือถือ iPhone เพื่อให้ Facebook ยอมคายลิงก์
            headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"}
            
            # 2. หัวใจสำคัญ: allow_redirects=False ห้ามตามลิงก์ไปเด็ดขาดเพื่อไม่ให้โดนเตะเข้าหน้า Login
            res = requests.get(url, headers=headers, allow_redirects=False, timeout=10)
            
            # 3. ฉกเอาลิงก์ข่าวของจริงที่ซ่อนอยู่ใน Header 'Location'
            if res.status_code in [301, 302, 303, 307, 308]:
                loc = res.headers.get('Location')
                if loc and "login" not in loc.lower():
                    # แปลงลิงก์มือถือ (m.facebook) กลับเป็นเว็บปกติ (www.facebook) 
                    # เพื่อส่งกลับไปให้โค้ดดึงข้อมูลเดิมของคุณทำงานต่อได้ตามปกติ!
                    return loc.replace("://m.facebook.com", "://www.facebook.com")
        except Exception:
            pass
        return url # ถ้าดักจับไม่ได้ ให้ส่งลิงก์เดิมกลับไป จะได้ไม่กระทบระบบหลัก

    # ================= โค้ดเดิมของคุณทั้งหมด (คงไว้เหมือนเดิมเป๊ะๆ) =================
    redirectors = [
        'shorturl.', 'bit.ly', 'tinyurl.', 't.co', 'cutt.ly', 'rebrand.ly', 
        'lnkd.in', 'fb.watch', '/share/', 'vt.tiktok.com', 'vm.tiktok.com', 
        'youtu.be', 'line.me', 'today.line.me'
    ]
    
    if any(r in url.lower() for r in redirectors):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
            res = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            final_url = res.url
            
            if "login" in final_url.lower() or "captcha" in final_url.lower() or "challenge" in final_url.lower(): 
                return url 
                
            meta_match = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=["\']?([^"\'>]+)["\']?', res.text, re.IGNORECASE)
            if meta_match: 
                final_url = meta_match.group(1)
                if final_url.startswith('/'):
                    from urllib.parse import urlparse
                    parsed = urlparse(res.url)
                    final_url = f"{parsed.scheme}://{parsed.netloc}{final_url}"
            return final_url
            
        except Exception: 
            pass
            
    return url

def resolve_short_url(url: str) -> str:
    # เรียกใช้ฟังก์ชันแกะลิงก์
    return expand_url(url) 

def extract_social_metadata(url: str) -> str:
    """สกัดเฉพาะข้อความ/แคปชั่นจาก Social Media"""
    
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    }
    
    try:
        # ================= 1. Twitter (X) =================
        if "x.com/" in url or "twitter.com/" in url:
            match = re.search(r'(?:x|twitter)\.com(/.*)', url)
            if match:
                clean_path = match.group(1).split('?')[0] 
                api_url = "https://api.vxtwitter.com" + clean_path
                res = requests.get(api_url, timeout=10)
                
                if res.status_code == 200:
                    data = res.json()
                    title = data.get("user_name", "ผู้ใช้งาน X")
                    desc = data.get("text", "")
                    return f"{title}\n{desc}".strip()
                else: 
                    return f"Error: API ของ X ปฏิเสธการดึงข้อมูล ({res.status_code})"

        # ================= 2. Instagram =================
        elif "instagram.com/" in url:
            match = re.search(r'instagram\.com/(?:p|reel|tv)/([^/?]+)', url)
            if match:
                shortcode = match.group(1)
                embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
                
                try:
                    res = requests.get(embed_url, headers=headers, timeout=12)
                    if res.status_code == 200:
                        soup = BeautifulSoup(res.text, 'html.parser')
                        caption_div = soup.find(class_='Caption')
                        
                        if caption_div:
                            user_tag = caption_div.find(class_='CaptionUsername')
                            if user_tag: 
                                user_tag.extract() 
                                
                            text = caption_div.get_text(separator='\n', strip=True)
                            if text: 
                                return f"โพสต์จาก Instagram:\n{text}"
                                
                        og_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
                        if og_desc and og_desc.get("content"): 
                            return f"โพสต์จาก Instagram:\n{og_desc['content'].strip()}"
                except Exception: 
                    pass

            # สำรองของ IG
            try:
                match_path = re.search(r'instagram\.com(/.*)', url)
                if match_path:
                    clean_path = match_path.group(1).split('?')[0]
                    ig_proxy_url = "https://ddinstagram.com" + clean_path
                    response = requests.get(ig_proxy_url, headers=headers, timeout=12)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
                        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
                        
                        title = og_title["content"] if og_title and og_title.get("content") else ""
                        desc = og_desc["content"] if og_desc and og_desc.get("content") else ""
                        
                        if title or desc:
                            if "Login" not in title and "เข้าสู่ระบบ" not in desc: 
                                return f"{title}\n{desc}".strip()
            except Exception: 
                pass
                
            return "Error: ไม่สามารถทะลวงระบบความปลอดภัยของ Instagram ได้ในขณะนี้"

        # ================= 3. Facebook (ดึงผ่าน Embed API) =================
        elif "facebook.com" in url or "fb.watch" in url:
            try:
                # 🛠️ [ไม้ตายที่ 2 แก้บั๊ก Facebook มือถือ]: ใช้ Facebook Plugin Embed 
                # เป็นช่องทางที่ Facebook อนุญาตให้เว็บอื่นดึงไปแสดงผลได้โดยไม่ติด Login
                safe_url = quote(url, safe=":/%?=&-_.#")
                embed_url = f"https://www.facebook.com/plugins/post.php?href={safe_url}"
                res_fb = requests.get(embed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
                
                if res_fb.status_code == 200:
                    soup_fb = BeautifulSoup(res_fb.text, 'html.parser')
                    # คัดกรองเอาเฉพาะแท็ก <p> หรือ <span> ที่มีข้อความยาวเกิน 20 ตัวอักษร
                    text_parts = [p.get_text(strip=True) for p in soup_fb.find_all(['p', 'span']) if len(p.get_text(strip=True)) > 20]
                    
                    if text_parts:
                        fb_text = "\n".join(set(text_parts))
                        # เช็คเพื่อความชัวร์ว่าไม่ได้ไปดึงปุ่ม "Log In" มา
                        if "เข้าสู่ระบบ" not in fb_text and "Log In" not in fb_text:
                            return f"โพสต์จาก Facebook:\n{fb_text}"
            except Exception:
                pass
            # ถ้าดึง Embed พลาด จะปล่อยให้มันไหลลงไปดึงแบบปกติด้านล่าง

        # ================= 4. Social Media ทั่วไป (และตัวสำรอง Facebook) =================
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
        
        title = og_title["content"] if og_title else (soup.title.string if soup.title else "")
        desc = og_desc["content"] if og_desc else ""
        
        if "facebook.com" in url or "fb.watch" in url:
            title_lower = title.strip().lower()
            if not desc and (title_lower == "facebook" or "log in" in title_lower or "เข้าสู่ระบบ" in title_lower):
                return "Error: Facebook บล็อกด้วยหน้า Login Wall"
                
        return f"{title}\n{desc}".strip()
        
    except Exception as e:
        return f"Error: การสกัดข้อมูล Social Media ล้มเหลว - {str(e)}"
    
def force_extract_news_link(social_url: str) -> str:
    """ขุดหาลิงก์ข่าวจริงที่ซ่อนอยู่ในโพสต์ Facebook"""
    
    if "x.com" in social_url.lower() or "twitter.com" in social_url.lower(): 
        return ""
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    
    try:
        response = requests.get(social_url, headers=headers, timeout=15, allow_redirects=True)
        decoded_html = unquote(response.text)
        
        whitelist = [
            'thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 
            'sanook.com', 'prachachat.net', 'bangkokbiznews.com', 'mgronline.com', 
            'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'thestandard.co', 
            'workpointtoday.com', 'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 
            'springnews.co.th'
        ]
        
        domain_pattern = "|".join([d.replace('.', r'\.') for d in whitelist])
        regex = rf'https?://(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:{domain_pattern})[^\s"\'<>\\]*'
        
        found_links = re.findall(regex, decoded_html)
        for link in found_links:
            clean_link = link.split('?')[0] 
            if len(clean_link.split('/')) >= 4 and not clean_link.endswith('/home'): 
                return clean_link
                
        return ""
    except Exception: 
        return ""

def fetch_with_fallback(url: str) -> str:
    """ระบบ 3-Layer Bypass สำหรับทะลวงกำแพงเว็บข่าว"""
    
    anti_bot_patterns = r'(cloudflare|500 internal server error|403 forbidden|access denied|captcha|not acceptable|checking your browser|security check|just a moment)'
    
    def is_valid_text(text):
        clean = text.strip()
        # 🛠️ [แก้บั๊กที่ 3]: ลดความยาวจาก 50 เหลือ 30 เพื่อให้ผ่านข่าวสั้นบนมือถือได้
        if len(clean) < 30: 
            return False 
        # ถ้าข้อความสั้นกว่า 800 ตัวอักษร และมีคำว่า Cloudflare อยู่ แสดงว่าโดนบล็อก
        if len(clean) < 800 and re.search(anti_bot_patterns, clean, re.IGNORECASE): 
            return False 
        return True

    # ================= [Layer 1]: ดึงปกติ (Googlebot) =================
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", 
        "Accept": "*/*"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if res.status_code == 200:
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): 
                element.extract()
                
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            
            if is_valid_text(clean_text): 
                return clean_text
    except Exception: 
        pass

    # ================= [Layer 2]: Jina AI =================
    try:
        # 🛠️ [แก้บั๊กที่ 4 - สำคัญที่สุด]: เข้ารหัส URL ภาษาไทยก่อนส่งให้ Jina
        safe_url = quote(url, safe=":/%?=&-_.#")
        jina_url = f"https://r.jina.ai/{safe_url}"
        response = requests.get(jina_url, headers={"Accept": "text/plain", "X-Retain-Images": "none"}, timeout=15)
        
        if response.status_code == 200 and is_valid_text(response.text):
            return response.text
    except Exception: 
        pass
    
    # ================= [Layer 3]: Proxy (AllOrigins) =================
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={quote(url)}"
        res = requests.get(proxy_url, timeout=15)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): 
                element.extract()
                
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            
            if is_valid_text(clean_text): 
                return clean_text
    except Exception: 
        pass

    return ""

def extract_text_from_url(url: str) -> dict:
    """ฟังก์ชันหลัก: ศูนย์กลางควบคุมการสกัดข้อมูล"""
    try:
        # 1. ทำความสะอาดและคลายปมลิงก์
        url = clean_mobile_url(url)
        url = expand_url(url)
        url = clean_mobile_url(url) 
        
        # 2. ตรวจสอบวิดีโอ
        VIDEO_PATTERNS = [
            r'youtube\.com/watch', r'youtu\.be', r'youtube\.com/shorts',
            r'tiktok\.com', r'vt\.tiktok\.com', r'vm\.tiktok\.com',
            r'facebook\.com/.*/videos/', r'fb\.watch', r'/share/v/', r'/share/r/', 
            r'vimeo\.com', r'dailymotion\.com'
        ]
        
        if any(re.search(p, url.lower()) for p in VIDEO_PATTERNS): 
            return {"error": "VIDEO_DETECTED"}

        # 3. ตรวจสอบเว็บพนัน
        gambling_keywords = r'(สล็อต|บาคาร่า|เว็บตรง|pg slot|คาสิโน|แทงบอล|หวยออนไลน์|ฝากถอนไม่มีขั้นต่ำ|แตกง่าย|ปั่นสล็อต|เครดิตฟรี|เว็บพนัน|สล็อตออนไลน์)'
        if re.search(r'(slot|casino|ufa\d+|pgslot|เว็บพนัน)', url.lower()): 
            return {"error": "GAMBLING_DETECTED"}

        # 4. แยกการทำงานระหว่าง โซเชียล กับ เว็บข่าว
        social_domains = ["facebook.com", "fb.watch", "x.com", "twitter.com", "tiktok.com", "instagram.com"]
        is_social = any(domain in url.lower() for domain in social_domains)
        
        content = ""
        actual_primary_url = url
        
        if is_social:
            content = extract_social_metadata(url)
            
            if content and re.search(gambling_keywords, content, re.IGNORECASE): 
                return {"error": "GAMBLING_DETECTED"}
                
            if "Error" in content:
                fallback_content = fetch_with_fallback(actual_primary_url)
                if fallback_content: 
                    content = fallback_content
                else: 
                    # 🛠️ [แก้บั๊กที่ 5]: ลบคำว่า "Error:" ออก เพื่อไม่ให้ UI ตีความว่าโดนบล็อคจากโซเชียลแบบผิดๆ
                    return {"error": "ไม่สามารถดึงข้อมูลเว็บข่าวได้"}
                
            hidden_news_url = force_extract_news_link(url)
            if hidden_news_url:
                actual_primary_url = hidden_news_url
                actual_news_content = fetch_with_fallback(actual_primary_url)
                
                if actual_news_content:
                    final_content = f"[พรีวิวจากโซเชียล]:\n{content}\n\n[เนื้อหาข่าวจริงที่ซ่อนอยู่ ({actual_primary_url})]:\n{actual_news_content}"
                    
                    if re.search(gambling_keywords, final_content, re.IGNORECASE): 
                        return {"error": "GAMBLING_DETECTED"}
                        
                    return {"content": final_content, "actual_url": actual_primary_url}
            
            return {"content": content, "actual_url": actual_primary_url}
            
        else:
            # ดึงข้อมูลจากเว็บข่าวทั่วไป
            actual_news_content = fetch_with_fallback(url)
            
            if actual_news_content:
                if re.search(gambling_keywords, actual_news_content, re.IGNORECASE): 
                    return {"error": "GAMBLING_DETECTED"}
                return {"content": actual_news_content, "actual_url": url}
            else:
                return {"error": "ไม่สามารถดึงข้อมูลเว็บข่าวได้ หรือเซิร์ฟเวอร์ปฏิเสธการเข้าถึง"}
                
    except Exception as e:
        return {"error": "ระบบสกัดข้อมูลขัดข้อง"}