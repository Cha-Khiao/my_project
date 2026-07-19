import re
import requests
import html
import codecs
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote

def clean_mobile_url(url: str) -> str:
    url = unquote(url.strip())
    if url.endswith('#'): url = url[:-1]
    if "l.facebook.com/l.php?u=" in url:
        try: url = unquote(url.split("u=")[1].split("&")[0])
        except Exception: pass
            
    url = url.replace("://m.facebook.com", "://www.facebook.com")
    url = url.replace("://mobile.twitter.com", "://twitter.com")
    
    if "?" in url:
        base_url, query_str = url.split("?", 1)
        fragment = ""
        if "#" in query_str:
            query_str, fragment = query_str.split("#", 1)
            fragment = "#" + fragment
        params = query_str.split("&")
        clean_params = [
            p for p in params 
            if not p.startswith(('mibextid=', 'igsh=', 'si=', 'fbclid=', 'is_from_webapp=', 'h=', 's=', 't=', 'rdid=', 'share_url=', 'utm_'))
        ]
        if clean_params: url = f"{base_url}?{'&'.join(clean_params)}{fragment}"
        else: url = f"{base_url}{fragment}"
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

def resolve_facebook_redirects(url: str) -> str:
    if "facebook.com/share/" not in url.lower() and "fb.watch" not in url.lower(): return url
    try:
        bot_headers = {"User-Agent": "facebookexternalhit/1.1", "Accept-Language": "th-TH,th;q=0.9"}
        res = requests.get(url, headers=bot_headers, timeout=10, allow_redirects=False)
        res.encoding = 'utf-8'
        loc = ""
        if res.status_code in [301, 302, 303, 307, 308]: loc = res.headers.get('Location', '')
        elif res.status_code == 200:
            js_match = re.search(r'location\.(?:replace|href)\s*=?\s*\(?["\'](.*?)["\']\)?', res.text, re.IGNORECASE)
            meta_match = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=["\']?([^"\'>]+)["\']?', res.text, re.IGNORECASE)
            if js_match: loc = js_match.group(1).replace('\\/', '/')
            elif meta_match: loc = meta_match.group(1)
        if loc:
            if loc.startswith('/'): loc = "https://www.facebook.com" + loc
            if "next=" in loc.lower():
                real_url = unquote(loc.split("next=")[1].split("&")[0])
                if "facebook.com/share/" not in real_url.lower() and "login" not in real_url.lower(): return real_url
            elif "facebook.com/share/" not in loc.lower() and "login" not in loc.lower(): return loc
    except Exception: pass

    try:
        proxy_url = f"https://api.allorigins.win/get?url={quote(url)}"
        res_proxy = requests.get(proxy_url, timeout=15)
        if res_proxy.status_code == 200:
            final_url = res_proxy.json().get("status", {}).get("url", url)
            if "facebook.com/share/" not in final_url.lower() and "login" not in final_url.lower(): return final_url
            if "next=" in final_url.lower():
                real_url = unquote(final_url.split("next=")[1].split("&")[0])
                if "facebook.com/share/" not in real_url.lower() and "login" not in real_url.lower(): return real_url
    except Exception: pass
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
                        og_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
                        if og_desc and og_desc.get("content"): return f"โพสต์จาก Instagram:\n{og_desc['content'].strip()}"
                except Exception: pass
            return "Error: ไม่สามารถทะลวงระบบความปลอดภัยของ Instagram ได้ในขณะนี้"

        elif "facebook.com" in url or "fb.watch" in url:
            fb_text = ""
            
            try:
                req_headers = {"User-Agent": "facebookexternalhit/1.1", "Accept-Language": "th-TH,th;q=0.9"}
                res_meta = requests.get(url, headers=req_headers, timeout=15, allow_redirects=True)
                res_meta.encoding = 'utf-8'
                soup = BeautifulSoup(res_meta.text, 'html.parser')
                og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
                og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
                temp = f"{og_title['content'] if og_title else ''}\n{og_desc['content'] if og_desc else ''}".strip()
                if temp and not re.search(r'(log in to facebook|เข้าสู่ระบบ|security check|โซเชียลยูทิลิตี้|แอปพลิเคชัน messenger)', temp, re.IGNORECASE):
                    fb_text = temp
            except Exception: pass

            if not fb_text:
                try:
                    res_jina = requests.get(f"https://r.jina.ai/{quote(url)}", headers={"X-Retain-Images": "none"}, timeout=15)
                    if res_jina.status_code == 200:
                        temp = res_jina.text[:2000] 
                        if temp and not re.search(r'(log in to facebook|เข้าสู่ระบบ|security check|แอปพลิเคชัน messenger)', temp, re.IGNORECASE):
                            fb_text = temp
                except Exception: pass

            if not fb_text:
                try:
                    res_ml = requests.get(f"https://api.microlink.io/?url={quote(url)}", timeout=12)
                    if res_ml.status_code == 200:
                        data = res_ml.json().get("data", {})
                        temp = f"{data.get('title', '')}\n{data.get('description', '')}".strip()
                        if temp and not re.search(r'(log in|เข้าสู่ระบบ|messenger)', temp, re.IGNORECASE): fb_text = temp
                except Exception: pass
                
            fb_text = decode_thai_text(fb_text)
            fb_text = html.unescape(fb_text)
            fb_text = re.sub(r'<[^>]+>', ' ', fb_text) 
            fb_text = re.sub(r'\{.*?\}', '', fb_text) 
            fb_text = re.sub(r'function\s*\(.*?\)\s*\{.*?\}', '', fb_text) 
            fb_text = re.sub(r'\s+', ' ', fb_text).strip()
            
            # 🚨 [เพิ่ม Blacklist] บล็อกคำโปรโมทแอป Messenger ที่ Cloud ชอบโดนยัดเยียด
            garbage_patterns = r'(log in to facebook|เข้าสู่ระบบ|error 404|page not found|ไม่พบหน้านี้|สมัครใช้งาน|create new account|forgotten password|security check|สร้างบัญชีหรือเข้าสู่ระบบ|เชื่อมต่อกับเพื่อน|แชร์รูปภาพและวิดีโอ|ส่งข้อความและรับการอัปเดต|connect with friends|share photos and videos|send messages and get updates|เข้าสู่ระบบ facebook เพื่อเริ่มแชร์|to start sharing and connecting|หาเพื่อนบน facebook|find your friends|โซเชียลยูทิลิตี้|social utility|แอปพลิเคชัน messenger|แอป messenger|ดาวน์โหลด messenger|download messenger|ฟีเจอร์แอปพลิเคชัน|ไปที่ messenger|go to messenger|ส่งข้อความถึง|join the conversation)'
            
            # 🚨 เช็คแบบตรงตัว ถ้าดึงมาแล้วได้คำพวกนี้เดี่ยวๆ ให้เตะทิ้ง
            if fb_text.lower().strip() in ['messenger', 'facebook', 'facebook messenger']:
                return "Error: โดนบล็อกด้วยหน้าเพจระบบ (Messenger/Facebook Wall)"
            
            if not fb_text or re.search(garbage_patterns, fb_text, re.IGNORECASE):
                return "Error: Facebook บล็อกแคปชั่น (ติดหน้า Login / Messenger Promo)"
                
            # ยางลบ ลบคำที่เป็นปุ่มกด UI ทิ้ง
            ui_patterns = r'(ดูโพสต์เพิ่มเติมจาก|ดูเพิ่มเติมจาก|See more of|บน Facebook|on Facebook|ไม่ใช่ตอนนี้|Not Now|วิดีโอที่เกี่ยวข้อง|Related videos|แนะนำสำหรับคุณ|Suggested for you|Facebook กำลังแสดงข้อมูล|หาเพื่อนบน Facebook|เข้าสู่ระบบ|Log In|สมัครใช้งาน|Create New Account|ลืมรหัสผ่าน|โซเชียลยูทิลิตี้|เปิดใน Messenger|Open in Messenger|ใช้ Messenger)'
            cleaned_fb_text = re.sub(ui_patterns, '', fb_text, flags=re.IGNORECASE).strip()
            
            if len(cleaned_fb_text) < 40:
                return "Error: ดึงมาได้เพียงข้อความระบบ (ไม่มีเนื้อหาแคปชั่นข่าวที่ยาวพอ)"
                
            return f"โพสต์จาก Facebook:\n{cleaned_fb_text}"

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
    if "x.com" in social_url.lower() or "twitter.com" in social_url.lower(): return ""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if "facebook.com" in social_url.lower() or "fb.watch" in social_url.lower():
        headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
    
    try:
        response = requests.get(social_url, headers=headers, timeout=15, allow_redirects=True)
        response.encoding = 'utf-8'
        decoded_html = unquote(response.text).replace('\\/', '/')
        
        valid_external_links = []
        l_php_links = re.findall(r'l\.facebook\.com/l\.php\?u=([^&"\'<>\\]+)', response.text)
        for link in l_php_links:
            clean_l = unquote(link).split('?')[0]
            valid_external_links.append(clean_l)
            
        general_url_pattern = r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s"\'<>\\]*)?'
        all_links = re.findall(general_url_pattern, decoded_html)
        
        exclude_domains = [
            'facebook.com', 'fb.com', 'fb.watch', 'messenger.com', 'instagram.com', 'whatsapp.com', 
            'x.com', 'twitter.com', 'tiktok.com', 'line.me', 'liff.line.me', 'fbcdn.net', 'akamaihd.net', 
            'google-analytics.com', 'googletagmanager.com', 'doubleclick.net', 'youtube.com', 'youtu.be',
            'w3.org', 'schema.org', 'ogp.me', 'purl.org', 'play.google.com', 'apps.apple.com', 'googleapis.com'
        ]
        exclude_exts = ('.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.mp4', '.mp3')
        
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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        content_type = res.headers.get('Content-Type', '').lower()
        if 'javascript' in content_type or 'css' in content_type or 'json' in content_type or 'image' in content_type or 'xml' in content_type:
            return ""
            
        if res.status_code == 200:
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): element.extract()
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            clean_text = decode_thai_text(clean_text)
            
            if clean_text.count('{') > 5 and clean_text.count('}') > 5 and 'function' in clean_text:
                return ""
                
            if len(clean_text) > 100 and not re.search(anti_bot_patterns, clean_text, re.IGNORECASE):
                return clean_text
    except Exception: pass

    try:
        response = requests.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/plain", "X-Retain-Images": "none"}, timeout=20)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            content = decode_thai_text(response.text)
            if content.strip().startswith('{') and content.strip().endswith('}'): return ""
            if len(content.strip()) > 100 and not re.search(anti_bot_patterns, content, re.IGNORECASE): 
                return content
    except Exception: pass
    return ""

def extract_text_from_url(url: str) -> dict:
    try:
        url = clean_mobile_url(url)
        url = resolve_facebook_redirects(url) 
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
            content = extract_social_metadata(url)
            
            hidden_news_url = force_extract_news_link(url)
            actual_news_content = ""
            
            if hidden_news_url:
                actual_primary_url = hidden_news_url
                actual_news_content = fetch_with_fallback(hidden_news_url)
                
            final_content = ""
            if "Error" not in content:
                clean_social = content.replace("โพสต์จาก Facebook:", "").strip()
                if len(clean_social) > 40:
                    final_content += f"{content}\n\n"
                    
            if actual_news_content:
                final_content += f"[เนื้อหาข่าวจริงที่ซ่อนอยู่ ({actual_primary_url})]:\n{actual_news_content}"
                
            final_content = final_content.strip()
            
            # 🚨 ถ้าระบบหาแคปชั่นยาวๆ ไม่เจอ และหาเว็บข่าวซ่อนก็ไม่เจอ ให้เด้ง Error ขึ้นหน้าเว็บเลย ห้ามส่งให้ AI ตรวจ!
            if not final_content:
                return {"error": "ไม่พบเนื้อหาข่าวในลิงก์นี้ (เซิร์ฟเวอร์โดนปิดกั้น หรือเป็นลิงก์โพสต์วิดีโอ)"}
                
            if re.search(gambling_keywords, final_content, re.IGNORECASE): 
                return {"error": "GAMBLING_DETECTED"}
                
            return {"content": final_content, "actual_url": actual_primary_url}
            
        else:
            actual_news_content = fetch_with_fallback(url)
            if actual_news_content:
                if re.search(gambling_keywords, actual_news_content, re.IGNORECASE): return {"error": "GAMBLING_DETECTED"}
                return {"content": actual_news_content, "actual_url": url}
            else:
                return {"error": "Error: ไม่สามารถดึงข้อมูลเว็บข่าวได้ หรือเซิร์ฟเวอร์ปฏิเสธการเข้าถึง"}
                
    except Exception as e:
        return {"error": f"Error: ระบบสกัดข้อมูลขัดข้อง - {str(e)}"}