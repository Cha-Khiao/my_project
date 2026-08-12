import os
import re
import json
import concurrent.futures
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
        
    # ⚡ ทำงานขนานกันระหว่าง Googlebot และ Jina AI
    def try_googlebot():
        try:
            bot_headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            res = requests.get(url, headers=bot_headers, timeout=8, allow_redirects=False)
            
            if res.status_code in [301, 302, 303, 307] and 'Location' in res.headers:
                real_url = res.headers['Location']
                if "facebook.com/share/" not in real_url.lower() and "login" not in real_url.lower():
                    return real_url
                    
            res_full = requests.get(url, headers=bot_headers, timeout=8, allow_redirects=True)
            meta_match = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=["\']?([^"\'>]+)["\']?', res_full.text, re.IGNORECASE)
            if meta_match:
                refresh_url = meta_match.group(1).replace('&amp;', '&')
                if "facebook.com/share/" not in refresh_url.lower() and "login" not in refresh_url.lower():
                    return refresh_url
                    
            canonical = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']', res_full.text, re.IGNORECASE)
            if canonical:
                canonical_url = canonical.group(1).replace('&amp;', '&')
                if "facebook.com/share/" not in canonical_url.lower() and "login" not in canonical_url.lower():
                    return canonical_url
        except Exception:
            pass
        return None

    def try_jina():
        try:
            jina_req = requests.get(f"https://r.jina.ai/{url}", headers={"Accept": "application/json"}, timeout=8)
            if jina_req.status_code == 200:
                resolved_url = jina_req.json().get("data", {}).get("url", url)
                if "facebook.com/share/" not in resolved_url.lower() and "login" not in resolved_url.lower():
                    return resolved_url
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(try_googlebot), executor.submit(try_jina)]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                return result
                
    return url

def expand_url(url: str) -> str:
    redirectors = ['shorturl.', 'bit.ly', 'tinyurl.', 't.co', 'cutt.ly', 'rebrand.ly', 'lnkd.in', 'vt.tiktok.com', 'vm.tiktok.com', 'youtu.be', 'line.me', 'liff.line.me']
    if any(r in url.lower() for r in redirectors):
        try:
            res = requests.get(url, impersonate="safari", allow_redirects=True, timeout=8)
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
                res = requests.get(api_url, impersonate="chrome", timeout=8)
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
                    res = requests.get(embed_url, impersonate="chrome", timeout=8)
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
                    response = requests.get(ig_proxy_url, impersonate="chrome", timeout=8)
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
            clean_url = url
            
            # ⚡ ทำงานขนานกันระหว่าง Iframe, Jina และ Meta
            def fb_iframe():
                try:
                    embed_url = f"https://www.facebook.com/plugins/post.php?href={quote(clean_url)}&show_text=true"
                    res_embed = requests.get(embed_url, impersonate="chrome", timeout=8)
                    if res_embed.status_code == 200:
                        soup_embed = BeautifulSoup(res_embed.text, 'html.parser')
                        for element in soup_embed(["script", "style", "form", "button", "a"]): 
                            element.extract()
                        extracted = soup_embed.get_text(separator='\n', strip=True)
                        extracted = re.sub(r'(ดูโพสต์เพิ่มเติมจาก|เข้าสู่ระบบ|ลืมรหัสผ่าน|หาเพื่อนบน Facebook|บน Facebook|Log In|Sign Up).*', '', extracted, flags=re.IGNORECASE).strip()
                        if extracted and not re.search(r'(error 404|content not found|ไม่พบเนื้อหา)', extracted, re.IGNORECASE):
                            if extracted.lower() not in ["facebook", "facebook app", "meta"]:
                                if len(extracted) >= 10:
                                    return extracted, "[ดึงด้วย: FB Embed Iframe 🌐]"
                except Exception:
                    pass
                return None, None

            def fb_jina():
                try:
                    jina_req = requests.get(f"https://r.jina.ai/{clean_url}", impersonate="chrome", headers={"Accept": "application/json"}, timeout=8)
                    if jina_req.status_code == 200:
                        jina_data = jina_req.json().get("data", {})
                        title = jina_data.get("title", "")
                        content = jina_data.get("content", "")
                        combined = f"{title}\n{content}".strip()
                        combined = re.sub(r'(ดูโพสต์เพิ่มเติมจาก|เข้าสู่ระบบ|ลืมรหัสผ่าน|หาเพื่อนบน Facebook|บน Facebook|Log In|Sign Up).*', '', combined, flags=re.IGNORECASE).strip()
                        if combined and not re.search(r'(error 404|ไม่พบเนื้อหา)', combined, re.IGNORECASE):
                            if combined.lower() not in ["facebook", "facebook app", "meta"]:
                                if len(combined) >= 10:
                                    return combined, "[ดึงด้วย: Headless Cloud Browser ☁️]"
                except Exception:
                    pass
                return None, None

            def fb_meta():
                try:
                    meta_res = requests.get(clean_url, impersonate="chrome", timeout=8, allow_redirects=True)
                    meta_res.encoding = 'utf-8'
                    soup_meta = BeautifulSoup(meta_res.text, 'html.parser')
                    og_title = soup_meta.find("meta", property="og:title") or soup_meta.find("meta", attrs={"name": "og:title"})
                    og_desc = soup_meta.find("meta", property="og:description") or soup_meta.find("meta", attrs={"name": "og:description"})
                    title = og_title["content"] if og_title else ""
                    desc = og_desc["content"] if og_desc else ""
                    combined = f"{title}\n{desc}".strip()
                    combined = re.sub(r'(ดูโพสต์เพิ่มเติมจาก|เข้าสู่ระบบ|ลืมรหัสผ่าน|หาเพื่อนบน Facebook|บน Facebook|Log In|Sign Up).*', '', combined, flags=re.IGNORECASE).strip()
                    if combined and not re.search(r'(error 404|ไม่พบเนื้อหา)', combined, re.IGNORECASE):
                        if combined.lower() not in ["facebook", "facebook app", "meta"]:
                            if len(combined) >= 10:
                                return combined, "[ดึงด้วย: Chrome Impersonation 🤖]"
                except Exception:
                    pass
                return None, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(fb_iframe), executor.submit(fb_jina), executor.submit(fb_meta)]
                for future in concurrent.futures.as_completed(futures):
                    res_text, method = future.result()
                    if res_text:
                        return f"โพสต์จาก Facebook {method}:\n{res_text}"
                        
            return "Error: Facebook บล็อกเนื้อหา (อาจเป็นโพสต์กลุ่มปิด หรือถูกตั้งเป็นส่วนตัว)"

        response = requests.get(url, impersonate="chrome", timeout=8)
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
        response = requests.get(social_url, impersonate="chrome", timeout=8, allow_redirects=True)
        decoded_html = unquote(response.text)
        whitelist = ['thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 'prachachat.net', 'bangkokbiznews.com', 'mgronline.com', 'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'thestandard.co', 'workpointtoday.com', 'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 'springnews.co.th', '77kaoded.com', 'voathai.com', 'xinhuathai.com']
        domain_pattern = "|".join([d.replace('.', r'\.') for d in whitelist])
        regex = rf'https?://(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:{domain_pattern})[^\s"\'<>\\]*'
        found_links = re.findall(regex, decoded_html)
        
        for link in found_links:
            clean_link = link.split('?')[0] 
            if len(clean_link.split('/')) >= 4 and not clean_link.endswith('/home'): return clean_link
        return ""
    except Exception:
        return ""


def _clean_extracted_text(text: str) -> str:
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', str(text or ''))
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:12000]


def _article_json_ld_candidates(value):
    candidates = []
    if isinstance(value, list):
        for item in value:
            candidates.extend(_article_json_ld_candidates(item))
    elif isinstance(value, dict):
        graph = value.get('@graph')
        if graph:
            candidates.extend(_article_json_ld_candidates(graph))
        raw_type = value.get('@type', '')
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(article_type in ['Article', 'NewsArticle', 'ReportageNewsArticle'] for article_type in types):
            body = value.get('articleBody', '')
            headline = value.get('headline', '')
            if body:
                candidates.append(f"{headline}\n{body}".strip())
    return candidates


def _content_quality_score(text: str) -> float:
    text = _clean_extracted_text(text)
    if not text:
        return 0.0
    length_score = min(len(text), 6000)
    sentence_score = min(1000, len(re.findall(r'[.!?。]|ครับ|ค่ะ|ว่า|โดย|เมื่อ', text)) * 20)
    boilerplate_hits = len(re.findall(
        r'(cookie|privacy policy|สมัครสมาชิก|เข้าสู่ระบบ|เมนู|หน้าหลัก|ติดตามเรา|สงวนลิขสิทธิ์)',
        text,
        re.IGNORECASE
    ))
    return length_score + sentence_score - (boilerplate_hits * 120)


def _extract_article_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html or '', 'html.parser')
    candidates = []

    for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        try:
            candidates.extend(
                (value, 1800.0)
                for value in _article_json_ld_candidates(json.loads(script.string or script.get_text()))
            )
        except Exception:
            pass

    for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "form", "button"]):
        element.extract()

    selectors = [
        ('[itemprop="articleBody"]', 1800.0), ('article', 1500.0), ('main', 900.0),
        ('.article-content', 1400.0), ('.article-body', 1400.0),
        ('.entry-content', 1200.0), ('.post-content', 1200.0),
        ('.story-content', 1200.0), ('.news-content', 1200.0),
        ('#article-content', 1400.0), ('#article-body', 1400.0)
    ]
    for selector, structure_bonus in selectors:
        for node in soup.select(selector):
            text = node.get_text(separator=' ', strip=True)
            if len(text) >= 100:
                candidates.append((text, structure_bonus))

    body_text = soup.get_text(separator=' ', strip=True)
    if body_text:
        candidates.append((body_text, 0.0))

    cleaned_candidates = []
    for value, structure_bonus in candidates:
        clean_value = _clean_extracted_text(value)
        if clean_value:
            cleaned_candidates.append((clean_value, structure_bonus))
    if not cleaned_candidates:
        return ""
    best_text, _ = max(
        cleaned_candidates,
        key=lambda item: _content_quality_score(item[0]) + item[1]
    )
    return best_text

def fetch_with_fallback(url: str) -> str:
    anti_bot_patterns = r'(cloudflare|500 internal server error|403 forbidden|access denied|captcha|not acceptable|checking your browser|security check|just a moment|log in to facebook|เข้าสู่ระบบ|error 404|404 not found|page not found|ไม่พบหน้านี้|ไม่พบเนื้อหา|content not found|this page isn\'t available|หน้านี้ไม่พร้อมใช้งาน|อาจเสียหรือถูกลบไปแล้ว)'
    
    # ⚡ ทำงานขนานกันระหว่าง Native Curl และ Jina AI
    def fetch_native():
        try:
            res = requests.get(url, impersonate="chrome", timeout=8, allow_redirects=True)
            if res.status_code == 200:
                if res.encoding is None or res.encoding.lower() == 'iso-8859-1':
                    res.encoding = res.apparent_encoding or 'utf-8'
                clean_text = _extract_article_text_from_html(res.text)
                if len(clean_text) > 100 and not re.search(anti_bot_patterns, clean_text, re.IGNORECASE):
                    return clean_text
        except Exception:
            pass
        return None

    def fetch_jina():
        try:
            jina_url = f"https://r.jina.ai/{url}"
            response = requests.get(jina_url, impersonate="chrome", headers={"Accept": "text/plain", "X-Retain-Images": "none"}, timeout=8)
            if response.status_code == 200:
                content = _clean_extracted_text(response.text)
                if len(content.strip()) > 100 and not re.search(anti_bot_patterns, content, re.IGNORECASE): 
                    return content
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(fetch_native), executor.submit(fetch_jina)]
        candidates = []
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                candidates.append(res)
        if candidates:
            return max(candidates, key=_content_quality_score)
                
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