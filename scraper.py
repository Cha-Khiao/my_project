import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote

def clean_mobile_url(url: str) -> str:
    """เคลียร์ Tracking และปรับมาตรฐานการเข้ารหัสของลิงก์จากมือถือ"""
    url = unquote(url.strip())
    
    if url.endswith('#'):
        url = url[:-1]
        
    if "l.facebook.com/l.php?u=" in url:
        try:
            url = unquote(url.split("u=")[1].split("&")[0])
        except Exception:
            pass
            
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
        
        if clean_params:
            url = f"{base_url}?{'&'.join(clean_params)}{fragment}"
        else:
            url = f"{base_url}{fragment}"
            
    return url

def resolve_facebook_redirects(url: str) -> str:
    """ทะลวงลิงก์ Facebook Share ข้ามการบล็อก IP บน Cloud ด้วยกุญแจผี"""
    if "facebook.com/share/" not in url.lower() and "fb.watch" not in url.lower():
        return url
        
    try:
        # 🚀 ท่าที่ 1: ใช้กุญแจผี WhatsApp ข้าม WAF ของ Cloud แบบไม่ตาม Redirect เพื่อดักจับเป้าหมาย
        bot_headers = {
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        res = requests.get(url, headers=bot_headers, timeout=10, allow_redirects=False)
        
        loc = ""
        if res.status_code in [301, 302, 303, 307, 308]:
            loc = res.headers.get('Location', '')
        elif res.status_code == 200:
            js_match = re.search(r'location\.(?:replace|href)\s*=?\s*\(?["\'](.*?)["\']\)?', res.text, re.IGNORECASE)
            meta_match = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=["\']?([^"\'>]+)["\']?', res.text, re.IGNORECASE)
            if js_match:
                loc = js_match.group(1).replace('\\/', '/')
            elif meta_match:
                loc = meta_match.group(1)
                
        if loc:
            if loc.startswith('/'):
                loc = "https://www.facebook.com" + loc
            
            if "next=" in loc.lower():
                real_url = unquote(loc.split("next=")[1].split("&")[0])
                if "facebook.com/share/" not in real_url.lower() and "login" not in real_url.lower():
                    return real_url
            elif "facebook.com/share/" not in loc.lower() and "login" not in loc.lower():
                return loc
    except Exception:
        pass

    # 🚀 ท่าที่ 2: สำรองด้วย Proxy เผื่อเจอกรณีแปลกๆ
    try:
        proxy_url = f"https://api.allorigins.win/get?url={quote(url)}"
        res_proxy = requests.get(proxy_url, timeout=15)
        if res_proxy.status_code == 200:
            data = res_proxy.json()
            final_url = data.get("status", {}).get("url", url)
            
            if "facebook.com/share/" not in final_url.lower() and "login" not in final_url.lower():
                return final_url
                
            if "next=" in final_url.lower():
                real_url = unquote(final_url.split("next=")[1].split("&")[0])
                if "facebook.com/share/" not in real_url.lower() and "login" not in real_url.lower():
                    return real_url
    except Exception:
        pass
        
    return url

def expand_url(url: str) -> str:
    """แกะลิงก์ย่อต่างๆ ให้เป็นลิงก์เต็ม"""
    # 🚨 ลบ Facebook และ /share/ ออกจากตรงนี้ เพื่อไม่ให้ Cloud โดนแบนเวลาใช้ UA ของ iPhone
    redirectors = ['shorturl.', 'bit.ly', 'tinyurl.', 't.co', 'cutt.ly', 'rebrand.ly', 'lnkd.in', 'vt.tiktok.com', 'vm.tiktok.com', 'youtu.be', 'line.me', 'liff.line.me']
    
    if any(r in url.lower() for r in redirectors):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"}
            res = requests.get(url, headers=headers, allow_redirects=True, timeout=12)
            
            final_url = res.url
            
            meta_match = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=["\']?([^"\'>]+)["\']?', res.text, re.IGNORECASE)
            if meta_match: 
                final_url = meta_match.group(1)
                
            js_match = re.search(r'window\.location\.(?:href|replace)\s*=\s*["\'](.*?)["\']', res.text, re.IGNORECASE)
            if js_match: 
                final_url = js_match.group(1)
                
            return final_url
        except Exception:
            pass
    return url

def extract_social_metadata(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"}
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
                            if user_tag: user_tag.extract() 
                            text = caption_div.get_text(separator='\n', strip=True)
                            if text: return f"โพสต์จาก Instagram:\n{text}"
                        og_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
                        if og_desc and og_desc.get("content"):
                            return f"โพสต์จาก Instagram:\n{og_desc['content'].strip()}"
                except Exception:
                    pass

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

        # ================= 3. Facebook =================
        elif "facebook.com" in url or "fb.watch" in url:
            fb_text = ""
            
            try:
                safe_url = quote(url, safe=":/%?=&-_.#")
                embed_url = f"https://www.facebook.com/plugins/post.php?href={safe_url}"
                res_fb = requests.get(embed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if res_fb.status_code == 200:
                    soup_fb = BeautifulSoup(res_fb.text, 'html.parser')
                    text_parts = [p.get_text(strip=True) for p in soup_fb.find_all(['p', 'span']) if len(p.get_text(strip=True)) > 20]
                    if text_parts:
                        ext_text = "\n".join(set(text_parts))
                        if not re.search(r'(เข้าสู่ระบบ|Log In|Log in to Facebook)', ext_text, re.IGNORECASE):
                            fb_text = ext_text
            except Exception:
                pass
                
            req_headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
            res_meta = requests.get(url, headers=req_headers, timeout=15, allow_redirects=True)
            res_meta.encoding = 'utf-8'
            soup_meta = BeautifulSoup(res_meta.text, 'html.parser')
            
            og_title = soup_meta.find("meta", property="og:title") or soup_meta.find("meta", attrs={"name": "og:title"})
            og_desc = soup_meta.find("meta", property="og:description") or soup_meta.find("meta", attrs={"name": "og:description"})
            
            title = og_title["content"] if og_title else ""
            desc = og_desc["content"] if og_desc else ""
            meta_text = f"{title}\n{desc}".strip()
            
            final_fb_content = f"{meta_text}\n\n{fb_text}".strip()
            
            if not final_fb_content or re.search(r'(log in to facebook|เข้าสู่ระบบ)', final_fb_content, re.IGNORECASE):
                return "Error: Facebook บล็อกด้วยหน้า Login Wall"
            elif len(final_fb_content) < 60: 
                return "Error: เนื้อหาสั้นเกินไป ระบบจะพยายามค้นหาลิงก์ข่าวที่ซ่อนอยู่"
                
            return f"โพสต์จาก Facebook:\n{final_fb_content}"

        # ================= 4. Social ทั่วไปอื่นๆ =================
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
        
        title = og_title["content"] if og_title else (soup.title.string if soup.title else "")
        desc = og_desc["content"] if og_desc else ""
        
        return f"{title}\n{desc}".strip()
        
    except Exception as e:
        return f"Error: การสกัดข้อมูล Social Media ล้มเหลว - {str(e)}"

def force_extract_news_link(social_url: str) -> str:
    if "x.com" in social_url.lower() or "twitter.com" in social_url.lower(): return ""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"}
    
    if "facebook.com" in social_url.lower() or "fb.watch" in social_url.lower():
        headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
        
    try:
        response = requests.get(social_url, headers=headers, timeout=15, allow_redirects=True)
        decoded_html = unquote(response.text)
        whitelist = ['thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 'sanook.com', 'prachachat.net', 'bangkokbiznews.com', 'mgronline.com', 'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'thestandard.co', 'workpointtoday.com', 'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 'springnews.co.th']
        domain_pattern = "|".join([d.replace('.', r'\.') for d in whitelist])
        regex = rf'https?://(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:{domain_pattern})[^\s"\'<>\\]*'
        found_links = re.findall(regex, decoded_html)
        
        for link in found_links:
            clean_link = link.split('?')[0] 
            if len(clean_link.split('/')) >= 4 and not clean_link.endswith('/home'): return clean_link
        return ""
    except Exception:
        return ""

def fetch_with_fallback(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", 
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if res.status_code == 200:
            if res.encoding is None or res.encoding.lower() == 'iso-8859-1':
                res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): 
                element.extract()
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            
            if len(clean_text) > 100 and not re.search(r'(500 internal server error|403 forbidden|access denied)', clean_text, re.IGNORECASE):
                return clean_text
    except Exception:
        pass

    try:
        jina_url = f"https://r.jina.ai/{url}"
        response = requests.get(jina_url, headers={"Accept": "text/plain", "X-Retain-Images": "none"}, timeout=20)
        if response.status_code == 200:
            content = response.text
            if len(content.strip()) > 100 and not re.search(r'(500 internal server error|403 forbidden|access denied)', content, re.IGNORECASE): 
                return content
    except Exception:
        pass
        
    return ""

def extract_text_from_url(url: str) -> dict:
    """ศูนย์กลางสกัดข้อมูล"""
    try:
        url = clean_mobile_url(url)
        url = resolve_facebook_redirects(url) # 🚀 ย้ายมาใช้เครื่องมือใหม่ 
        url = expand_url(url)
        url = clean_mobile_url(url) 
        
        VIDEO_PATTERNS = [
            r'youtube\.com/watch', r'youtu\.be', r'youtube\.com/shorts',
            r'tiktok\.com', r'vt\.tiktok\.com', r'vm\.tiktok\.com',
            r'facebook\.com/.*/videos/', r'fb\.watch', r'/share/v/', r'/share/r/', 
            r'vimeo\.com', r'dailymotion\.com'
        ]
        
        if any(re.search(p, url.lower()) for p in VIDEO_PATTERNS):
            return {"error": "VIDEO_DETECTED"}

        gambling_keywords = r'(สล็อต|บาคาร่า|เว็บตรง|pg slot|คาสิโน|แทงบอล|หวยออนไลน์|ฝากถอนไม่มีขั้นต่ำ|แตกง่าย|ปั่นสล็อต|เครดิตฟรี|เว็บพนัน|สล็อตออนไลน์)'
        if re.search(r'(slot|casino|ufa\d+|pgslot|เว็บพนัน)', url.lower()):
            return {"error": "GAMBLING_DETECTED"}

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
                if fallback_content: content = fallback_content
                else: 
                    pass
                
            hidden_news_url = force_extract_news_link(url)
            if hidden_news_url:
                actual_primary_url = hidden_news_url
                actual_news_content = fetch_with_fallback(actual_primary_url)
                
                if actual_news_content:
                    final_content = f"[พรีวิวจากโซเชียล]:\n{content}\n\n[เนื้อหาข่าวจริงที่ซ่อนอยู่ ({actual_primary_url})]:\n{actual_news_content}"
                    if re.search(gambling_keywords, final_content, re.IGNORECASE): return {"error": "GAMBLING_DETECTED"}
                    return {"content": final_content, "actual_url": actual_primary_url}
            
            if "Error" in content:
                return {"error": "ไม่สามารถดึงข้อมูลข่าวสารที่มีเนื้อหาเพียงพอจากโพสต์นี้ได้"}
                
            return {"content": content, "actual_url": actual_primary_url}
            
        else:
            actual_news_content = fetch_with_fallback(url)
            if actual_news_content:
                if re.search(gambling_keywords, actual_news_content, re.IGNORECASE): return {"error": "GAMBLING_DETECTED"}
                return {"content": actual_news_content, "actual_url": url}
            else:
                return {"error": "Error: ไม่สามารถดึงข้อมูลเว็บข่าวได้ หรือเซิร์ฟเวอร์ปฏิเสธการเข้าถึง"}
                
    except Exception as e:
        return {"error": f"Error: ระบบสกัดข้อมูลขัดข้อง - {str(e)}"}