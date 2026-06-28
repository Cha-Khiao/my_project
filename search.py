import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
import re

def fetch_rss(search_term: str, num_results: int) -> list:
    """ฟังก์ชันย่อยสำหรับยิงเข้า Google News"""
    if not search_term.strip():
        return []
    try:
        rss_url = f"https://news.google.com/rss/search?q={quote(search_term)}&hl=th&gl=TH&ceid=TH:th"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(rss_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return []
            
        root = ET.fromstring(response.content)
        valid_results = []
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else ""
            link = item.find('link').text if item.find('link') is not None else ""
            
            if title and link and re.search(r'[ก-๙]', title):
                valid_results.append({
                    'title': title,
                    'href': link,
                    'body': "ข้อมูลอ้างอิงจากฐานข้อมูล Google News"
                })
                
            if len(valid_results) == num_results:
                break
        return valid_results
    except Exception as e:
        print(f"RSS Fetch Error: {e}")
        return []

def search_news_references(query: str, num_results: int = 3) -> list:
    """ระบบค้นหาแบบอัจฉริยะ (ถ้าคำเกริ่นนำยาวไป จะตัดทิ้งแล้วหาจากใจความสำคัญแทน)"""
    # 1. ทำความสะอาดคีย์เวิร์ด
    clean_query = re.sub(r'(?i)(title|description|หัวข้อ|รายละเอียด|ข่าว|พรีวิว)[:\s\-]*', '', query)
    clean_query = re.sub(r'[^\w\sก-๙]', ' ', clean_query)
    search_term = " ".join(clean_query.split()).strip()
    
    if not search_term:
        return []
        
    # สเต็ปที่ 1: ค้นหาแบบเต็มประโยค (สำหรับข่าวที่พาดหัวตรงเป๊ะ)
    results = fetch_rss(search_term, num_results)
    if results:
        return results
        
    words = search_term.split()
    
    # สเต็ปที่ 2: ถ้าไม่เจอ (เพราะคำเกริ่นนำกว้างเกินไป) ให้ตัด 3 คำแรกทิ้ง แล้วเอาส่วนท้ายไปค้น
    # เช่น ตัด "ทบทวนความทรงจำ รวมเหตุการณ์ร้อน ย้อนข่าว..." ทิ้งไป ให้เหลือแต่ชื่อเหตุการณ์จริงๆ
    if len(words) > 4:
        tail_term = " ".join(words[3:])
        results = fetch_rss(tail_term, num_results)
        if results:
            return results
            
    # สเต็ปที่ 3: แผนสำรองสุดท้าย ดึงเฉพาะ 3 คำสุดท้ายจริงๆ (มักเป็นชื่อบุคคล/สถานที่/ประเด็น)
    if len(words) > 6:
        end_term = " ".join(words[-3:])
        results = fetch_rss(end_term, num_results)
        if results:
            return results
            
    return []