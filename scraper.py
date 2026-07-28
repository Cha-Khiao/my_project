import os
import re
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote, urlparse, parse_qs
from curl_cffi import requests

try:
    import streamlit as st
except ImportError:
    st = None

def clean_mobile_url(url: str) -> str:
    url = unquote(url.strip())
    
    if "l.facebook.com/l.php?u=" in url:
        try:
            url = unquote(url.split("u=")[1].split("&")[0])
        except Exception:
            pass
            
    url = url.replace("://m.facebook.com", "://www.facebook.com")
    url = url.replace("://mobile.twitter.com", "://twitter.com")
    url = url.replace("://x.com", "://twitter.com")
    
    if "?" in url:
        base_url, query_str = url.split("?", 1)
        fragment = ""
        
        if "#" in query_str:
            query_str, fragment = query_str.split("#", 1)
            if fragment: 
                fragment = "#" + fragment
                
        params = query_str.split("&")
        
        junk_params = (
            'mibextid=', 'igsh=', 'si=', 'fbclid=', 'is_from_webapp=', 
            'h=', 's=', 't=', 'rdid=', 'share_url=', 'utm_', 'c='
        )
        
        clean_params = [
            p for p in params 
            if not p.lower().startswith(junk_params)
        ]
        
        if clean_params:
            url = f"{base_url}?{'&'.join(clean_params)}{fragment}"
        else:
            url = f"{base_url}{fragment}"
            
    url = url.rstrip('#')
    return url

def resolve_facebook_redirects(url: str) -> str:
    if "facebook.com/share/" not in url.lower() and "fb.watch" not in url.lower():
        return url
    try:
        res = requests.get(url, impersonate="chrome", timeout=10, allow_redirects=True)
        
        meta_match = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=["\']?([^"\'>]+)["\']?', res.text, re.IGNORECASE)
        if meta_match:
            refresh_url = meta_match.group(1).replace('&amp;', '&')
            if "facebook.com/share/" not in refresh_url.lower() and "login" not in refresh_url.lower():
                return refresh_url

        js_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\'](.*?)["\']', res.text, re.IGNORECASE)
        if js_match:
            js_url = js_match.group(1).replace('\\/', '/')
            if "facebook.com/share/" not in js_url.lower() and "login" not in js_url.lower():
                return js_url

        if "login" in res.url.lower():
            parsed = urlparse(res.url)
            qs = parse_qs(parsed.query)
            if 'next' in qs:
                real_url = unquote(qs['next'][0])
                if "facebook.com/share/" not in real_url.lower() and "login" not in real_url.lower():
                    return real_url
            return url

        meta_og = re.search(r'property=["\']og:url["\']\s+content=["\']([^"\']+)["\']', res.text, re.IGNORECASE)
        if meta_og:
            og_url = meta_og.group(1).replace('&amp;', '&')
            if "facebook.com/share/" not in og_url.lower() and "login" not in og_url.lower():
                return og_url
                
        if "login" not in res.url.lower() and "facebook.com/share/" not in res.url.lower():
            return res.url
    except Exception:
        pass

    try:
        proxy_url = f"https://api.allorigins.win/get?url={quote(url)}"
        res_proxy = requests.get(proxy_url, impersonate="chrome", timeout=10)
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
    redirectors = ['shorturl.', 'bit.ly', 'tinyurl.', 't.co', 'cutt.ly', 'rebrand.ly', 'lnkd.in', 'vt.tiktok.com', 'vm.tiktok.com', 'youtu.be', 'line.me', 'liff.line.me']
    if any(r in url.lower() for r in redirectors):
        try:
            res = requests.get(url, impersonate="safari", allow_redirects=True, timeout=10)
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
    try:
        if "x.com/" in url or "twitter.com/" in url:
            match = re.search(r'(?:x|twitter)\.com(/.*)', url)
            if match:
                clean_path = match.group(1).split('?')[0] 
                api_url = "https://api.vxtwitter.com" + clean_path
                res = requests.get(api_url, impersonate="chrome", timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    title = data.get("user_name", "ผู้ใช้งาน X")
                    desc = data.get("text", "")
                    return f"{title}\n{desc}".strip()
                else:
                    return f"Error: API ของ X ปฏิเสธการดึงข้อมูล ({res.status_code})"

        elif "instagram.com/" in url:
            match = re.search(r'instagram\.com/(?:p|reel|tv)/([^/?]+)', url)
            if match:
                shortcode = match.group(1)
                embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
                try:
                    res = requests.get(embed_url, impersonate="chrome", timeout=10)
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
                    response = requests.get(ig_proxy_url, impersonate="chrome", timeout=10)
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

        # --- Facebook ---
        elif "facebook.com" in url or "fb.watch" in url:
            fb_text = ""
            clean_url = url
            method_used = "" 

            # 💡 ท่าไม้ตาย: ปลอมตัวเป็นระบบ Preview ของแอปแชท (WhatsApp/LINE) 
            # Facebook จะยอมคายเนื้อหาโพสต์เต็มๆ ออกมาในรูปแบบ og:description ให้กับบอทนี้เสมอ
            try:
                bot_headers = {
                    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
                    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                }
                # สังเกตว่าเราไม่ตั้งค่า impersonate="chrome" เพื่อบังคับให้ส่ง Header เป็นบอทจริงๆ
                meta_res = requests.get(clean_url, headers=bot_headers, timeout=10, allow_redirects=True)
                meta_res.encoding = 'utf-8'
                soup_meta = BeautifulSoup(meta_res.text, 'html.parser')

                og_title = soup_meta.find("meta", property="og:title") or soup_meta.find("meta", attrs={"name": "og:title"})
                og_desc = soup_meta.find("meta", property="og:description") or soup_meta.find("meta", attrs={"name": "og:description"})
                
                title = og_title["content"] if og_title else ""
                desc = og_desc["content"] if og_desc else ""
                
                combined = f"{title}\n{desc}".strip()
                
                # ล้างข้อความขยะระบบของ Facebook ที่มักติดมาตอนดึงข้อมูล
                combined = re.sub(r'(ดูโพสต์เพิ่มเติมจาก|เข้าสู่ระบบ|ลืมรหัสผ่าน|หาเพื่อนบน Facebook|บน Facebook|Log In|Sign Up).*', '', combined, flags=re.IGNORECASE).strip()

                if combined and not re.search(r'(log in to facebook|เข้าสู่ระบบ|error 404|ไม่พบเนื้อหา)', combined, re.IGNORECASE):
                    if combined.lower() not in ["facebook", "facebook app", "meta"]:
                        if len(combined) >= 10:
                            fb_text = combined
                            method_used = "[ดึงด้วย: WhatsApp/LINE Preview Bot 🚀]"
            except Exception:
                pass

            # ท่าสำรอง: ดึงผ่าน Iframe
            if not fb_text:
                try:
                    embed_url = f"https://www.facebook.com/plugins/post.php?href={quote(clean_url)}&show_text=true"
                    res_embed = requests.get(embed_url, impersonate="chrome", timeout=10)
                    
                    if res_embed.status_code == 200:
                        soup_embed = BeautifulSoup(res_embed.text, 'html.parser')
                        for element in soup_embed(["script", "style", "form", "button"]): 
                            element.extract()
                            
                        extracted = soup_embed.get_text(separator=' ', strip=True)
                        
                        if extracted and not re.search(r'(log in to facebook|เข้าสู่ระบบ|error 404|content not found|ไม่พบเนื้อหา)', extracted, re.IGNORECASE):
                            extracted = re.sub(r'(เข้าสู่ระบบ|ลืมรหัสผ่าน|Log In|Sign Up).*', '', extracted, flags=re.IGNORECASE).strip()
                            if len(extracted) >= 5:
                                fb_text = extracted
                                method_used = "[ดึงด้วย: FB Embed Iframe 🌐]"
                except Exception:
                    pass

            if not fb_text or re.search(r'(log in to facebook|เข้าสู่ระบบ|error 404|page not found|ไม่พบเนื้อหา)', fb_text, re.IGNORECASE):
                return "Error: Facebook บล็อกเนื้อหา (อาจเป็นโพสต์กลุ่มปิด หรือถูกตั้งเป็นส่วนตัว)"
            
            return f"โพสต์จาก Facebook {method_used}:\n{fb_text}"

        response = requests.get(url, impersonate="chrome", timeout=10)
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
    try:
        response = requests.get(social_url, impersonate="chrome", timeout=10, allow_redirects=True)
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
    anti_bot_patterns = r'(cloudflare|500 internal server error|403 forbidden|access denied|captcha|not acceptable|checking your browser|security check|just a moment|log in to facebook|เข้าสู่ระบบ|error 404|404 not found|page not found|ไม่พบหน้านี้|ไม่พบเนื้อหา|content not found|this page isn\'t available|หน้านี้ไม่พร้อมใช้งาน|อาจเสียหรือถูกลบไปแล้ว)'
    
    try:
        res = requests.get(url, impersonate="chrome", timeout=8, allow_redirects=True)
        if res.status_code == 200:
            if res.encoding is None or res.encoding.lower() == 'iso-8859-1':
                res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]): 
                element.extract()
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            
            if len(clean_text) > 100 and not re.search(anti_bot_patterns, clean_text, re.IGNORECASE):
                return clean_text
    except Exception:
        pass

    try:
        jina_url = f"https://r.jina.ai/{url}"
        response = requests.get(jina_url, impersonate="chrome", headers={"Accept": "text/plain", "X-Retain-Images": "none"}, timeout=10)
        if response.status_code == 200:
            content = response.text
            if len(content.strip()) > 100 and not re.search(anti_bot_patterns, content, re.IGNORECASE): 
                return content
    except Exception:
        pass
        
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
                return {"error": "ไม่สามารถดึงข้อมูลข่าวสารที่มีเนื้อหาเพียงพอจากโพสต์นี้ได้ (ติดการป้องกันของแพลตฟอร์ม)"}
                
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