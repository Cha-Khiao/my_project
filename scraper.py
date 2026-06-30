import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote

def extract_social_metadata(url: str) -> str:
    """ดึงแคปชั่นพรีวิวจาก Social Media เท่าที่ระบบมันจะยอมให้ดึง"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        
        title = og_title["content"] if og_title else ""
        desc = og_desc["content"] if og_desc else ""
        
        return f"{title}\n{desc}"
    except Exception as e:
        return f"Error: การสกัดข้อมูล Social Media ล้มเหลว - {str(e)}"

def force_extract_news_link(social_url: str) -> str:
    """ท่าไม้ตายสาย Hacker: ควานหาลิงก์ข่าวจาก Source Code ดิบของ Facebook โดยตรง"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        # 1. ดึงโค้ดดิบมาทั้งหน้า (วิ่งตามลิงก์ย่อให้สุดทาง)
        response = requests.get(social_url, headers=headers, timeout=15, allow_redirects=True)
        
        # 2. ถอดรหัส URL ที่ซ่อนอยู่ในโค้ด (แปลง %3A%2F%2F ให้เป็น ://)
        decoded_html = unquote(response.text)
        
        # 3. กำหนดเป้าหมายโดเมนข่าวหลัก
        whitelist = [
            'thairath.co.th', 'khaosod.co.th', 'matichon.co.th', 'dailynews.co.th', 
            'sanook.com', 'prachachat.net', 'bangkokbiznews.com', 'mgronline.com', 
            'thaipbs.or.th', 'pptvhd36.com', 'ch7.com', 'thestandard.co', 'workpointtoday.com',
            'amarintv.com', 'nationtv.tv', 'tnnthailand.com', 'springnews.co.th'
        ]
        
        # 4. ใช้ Regex กวาดหาทุกลิงก์ที่ตรงกับ Whitelist ออกมาจากโค้ดดิบ
        domain_pattern = "|".join([d.replace('.', r'\.') for d in whitelist])
        regex = rf'https?://(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:{domain_pattern})[^\s"\'<>\\]*'
        
        found_links = re.findall(regex, decoded_html)
        
        # กรองลิงก์ขยะ เอาเฉพาะลิงก์ที่เป็นหน้าข่าวจริงๆ (Path ยาวๆ)
        for link in found_links:
            clean_link = link.split('?')[0] # ตัดพวก Parameter ติดตามตัวของ Facebook ทิ้ง
            if len(clean_link.split('/')) >= 4 and not clean_link.endswith('/home'): 
                return clean_link
                
        return ""
    except Exception:
        return ""

def fetch_with_fallback(url: str) -> str:
    """🌟 ฟังก์ชันย่อยตัวใหม่: ใช้ดึงข้อมูลเว็บข่าว พร้อมระบบสลับช่องทางอัตโนมัติ (แก้ปัญหา 500 Error)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    
    # ช่องทางที่ 1: Jina Reader
    try:
        jina_url = f"https://r.jina.ai/{url}"
        response = requests.get(jina_url, headers=headers, timeout=20)
        if response.status_code == 200:
            content = response.text
            if len(content.strip()) > 100:
                return content
        raise Exception(f"Jina Reader Error {response.status_code}")
    except Exception:
        # ช่องทางที่ 2: BeautifulSoup (Fallback หาก Jina ล่ม หรือติดบล็อกเช่นเว็บ Sanook)
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            if res.encoding is None or res.encoding.lower() == 'iso-8859-1':
                res.encoding = res.apparent_encoding or 'utf-8'
            
            soup = BeautifulSoup(res.text, 'html.parser')
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
                element.extract()
                
            clean_text = re.sub(r'\s+', ' ', soup.get_text(separator=' ', strip=True)).strip()
            if len(clean_text) > 100:
                return clean_text
        except Exception:
            pass
            
    return ""

def extract_text_from_url(url: str) -> dict:
    """ศูนย์กลางสกัดข้อมูล คืนค่าเนื้อหาและลิงก์จริงเสมอ"""
    try:
        social_domains = ["facebook.com", "fb.watch", "x.com", "twitter.com", "tiktok.com", "instagram.com"]
        is_social = any(domain in url.lower() for domain in social_domains)
        
        content = ""
        actual_primary_url = url
        
        if is_social:
            # 1. ดึงแคปชั่นชั้นนอกมาก่อน
            content = extract_social_metadata(url)
            if "Error" in content:
                return {"error": content}
                
            # 2. ⚡ ใช้งานระบบสแกนโค้ดหลังบ้าน เจาะหาลิงก์ข่าวจริง
            hidden_news_url = force_extract_news_link(url)
            
            if hidden_news_url:
                actual_primary_url = hidden_news_url # เปลี่ยนลิงก์โซเชียล เป็นลิงก์ข่าวจริงทันที!
                
                # 3. ใช้งานระบบดึงข้อมูลแบบมี Fallback ป้องกันเว็บล่ม
                actual_news_content = fetch_with_fallback(actual_primary_url)
                
                if actual_news_content:
                    final_content = f"[พรีวิวจากโซเชียล]:\n{content}\n\n[เนื้อหาข่าวจริงที่ซ่อนอยู่ ({actual_primary_url})]:\n{actual_news_content}"
                    return {"content": final_content, "actual_url": actual_primary_url}
            
            # ถ้าเจาะไม่เข้าจริงๆ (ไม่มีลิงก์ข่าวในโพสต์นั้นเลย) ก็คืนค่าแค่แคปชั่นไป
            return {"content": content, "actual_url": actual_primary_url}
            
        else:
            # กรณีเว็บข่าวปกติ ให้ใช้ระบบดึงข้อมูลแบบมี Fallback กันเว็บล่ม (แก้ปัญหา Sanook)
            actual_news_content = fetch_with_fallback(url)
            if actual_news_content:
                return {"content": actual_news_content, "actual_url": url}
            else:
                return {"error": "Error: ไม่สามารถดึงข้อมูลเว็บข่าวได้ หรือเซิร์ฟเวอร์ปฏิเสธการเข้าถึง"}
                
    except Exception as e:
        return {"error": f"Error: ระบบสกัดข้อมูลขัดข้อง - {str(e)}"}