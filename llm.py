import requests
import json
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv
import pytz

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
try:
    import streamlit as st
    if "OPENROUTER_API_KEY" in st.secrets:
        OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"].strip()
except Exception:
    pass

def get_current_thai_time():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    months_th = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"วันนี้คือ วัน{now.strftime('%A')}ที่ {now.day} เดือน{months_th[now.month - 1]} ปี พ.ศ. {now.year + 543} (ค.ศ. {now.year}) เวลา {now.strftime('%H:%M')} น."

def clean_llm_output(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'^(Here is the .*?|The result is.*?)\n', '', text, flags=re.IGNORECASE)
    return text.strip()

def sanitize_for_api(text: str) -> str:
    if not text: return ""
    clean = re.sub(r'[<>{}\\]', ' ', text)
    clean = clean.encode('utf-8', 'ignore').decode('utf-8')
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def classify_content(news_text: str) -> tuple:
    text_chunk = sanitize_for_api(news_text[:2500])
    prompt = f"""คุณคือระบบ AI วิเคราะห์ประเภทเนื้อหา
    
    [หมวดหมู่เนื้อหา]
    1. 📰 NEWS_AND_CLAIMS: ข่าว, คำกล่าวอ้าง, ประเด็นสังคม -> ตอบ: PROCEED
    2. 🛒 CLASSIFIEDS_AND_ADS: ประกาศซื้อขายทั่วไป -> ตอบ: DROP
    3. 💬 PERSONAL_POSTS: โพสต์ส่วนตัว -> ตอบ: DROP
    4. 🎭 FICTION_AND_ENTERTAINMENT: เรื่องแต่ง -> ตอบ: DROP
    5. ⚠️ SYSTEM_ERRORS: Error 404 -> ตอบ: DROP
    6. ❓ UNKNOWN_OR_HYBRID: ไม่แน่ใจ -> ตอบ: PROCEED

    ข้อความที่ต้องพิจารณา:
    {text_chunk}

    จงตอบกลับ 2 บรรทัดดังนี้เท่านั้น (ห้ามมีคำอื่นปน):
    RESULT: [PROCEED หรือ DROP]
    REASON: [เหตุผลภาษาไทยสั้นๆ]
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}", 
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://factchecker.local", 
                    "X-Title": "AI Fact-Checker" 
                },
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [{"role": "system", "content": "Output exactly two lines."}, {"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "seed": 42
                }).encode('utf-8'),
                timeout=15
            )
            response.raise_for_status()
            raw_content = clean_llm_output(response.json()['choices'][0]['message']['content'])
            match_result = re.search(r'RESULT\s*:\s*(PROCEED|DROP)', raw_content, re.IGNORECASE)
            match_reason = re.search(r'REASON\s*:\s*(.*)', raw_content, re.IGNORECASE)
            return match_result.group(1).upper() if match_result else "PROCEED", match_reason.group(1).strip() if match_reason else "อนุญาตให้ตรวจสอบอัตโนมัติ"
        except Exception as e:
            if attempt == 2: return "PROCEED", f"ระบบ API ขัดข้อง ({e}) ส่งเข้ากระบวนการตรวจสอบอัตโนมัติ"
            time.sleep(1.5)

def generate_search_keywords(news_text: str) -> str:
    text_chunk = sanitize_for_api(news_text[:2500])
    
    prompt = f"""สกัด "คำสำคัญ (Keywords)" จากเนื้อหาด้านล่าง เพื่อนำไปค้นหาความจริงใน Search Engine
    เนื้อหา:
    {text_chunk}
    กฎ: 
    1. ตอบแค่กลุ่มคำ 3-5 คำ (เว้นวรรคระหว่างคำ)
    2. เน้นเฉพาะ "ชื่อบุคคล", "สถานที่", "เหตุการณ์เฉพาะเจาะจง" และระบุ "ปี พ.ศ. หรือ ค.ศ." ด้วยหากในเนื้อหามีการอ้างถึง
    3. ห้ามแปลภาษา และห้ามมีคำอธิบายใดๆ ทั้งสิ้น
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}", 
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://factchecker.local", 
                    "X-Title": "AI Fact-Checker" 
                },
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [{"role": "system", "content": "Output ONLY THAI keywords."}, {"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "seed": 42
                }).encode('utf-8'),
                timeout=15 
            )
            response.raise_for_status()
            keywords = clean_llm_output(response.json()['choices'][0]['message']['content'])
            keywords = re.sub(r'^(คำค้นหา|คีย์เวิร์ด|Keywords?|Search Query)[\s\:\-]*', '', keywords.replace('"', '').replace("'", "").replace("**", ""), flags=re.IGNORECASE).strip()
            return keywords
        except Exception:
            if attempt == 2: return ""
            time.sleep(1.5)

def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> str:
    current_time_context = get_current_thai_time()
    
    ref_text_list = []
    for r in references:
        title = r.get('title', 'ไม่มีหัวข้อ')
        link = r.get('href', 'ไม่มีลิงก์')
        pub_date = r.get('pub_date', 'ไม่ระบุ')
        snippet = r.get('snippet', 'ไม่มีข้อมูลย่อ')
        ref_text_list.append(f"- แหล่งที่มา: {link}\n  วันที่สำนักข่าวเผยแพร่: {pub_date}\n  พาดหัวข่าว: {title}\n  เนื้อหาย่อ: {snippet}")
        
    ref_text = "\n".join(ref_text_list) if references else "ไม่มีข้อมูลค้นหาที่เกี่ยวข้องเลย"
    clean_news_text = sanitize_for_api(news_text)

    prompt = f"""คุณคือ AI Fact-Checker ระดับผู้เชี่ยวชาญ หน้าที่ของคุณคือสืบสวนความจริงด้วยหลักตรรกะที่ยุติธรรมที่สุด 

    [บริบทเวลาปัจจุบันของโลกจริง]
    🚨 {current_time_context}
    
    [ข้อความที่ต้องตรวจสอบ]
    "{clean_news_text}"
    
    [ผลการสืบค้นจากอินเทอร์เน็ต]
    {ref_text}
    
    =========================================
    🚨 กฎการพิจารณาความเกี่ยวข้อง (Relevance):
    - **ห้ามคิดเหมารวมเด็ดขาด!** สถานที่หรือตัวบุคคลต้อง "ตรงกันเป๊ะ" (ตัวอย่าง: ถ้าข้อความระบุ "ยุโรป" แต่ข่าวอ้างอิงเป็น "ฝรั่งเศส" ให้ถือว่าเป็นคนละเรื่อง หรือถ้าเป็นข่าวรวมมิตรทั่วไป ให้ตีตกทันที)

    🚨 กฎการวิเคราะห์ไทม์ไลน์ (Timeline) - **สำคัญมาก**:
    - **ห้ามเขียนอธิบายแบบย้อนแย้งเด็ดขาด** (เช่น ห้ามพูดว่าวันที่ 10 มิถุนายน ตรงกับ 29 กรกฎาคม เพราะมันคนละเดือนกัน!)
    - หากวันที่เผยแพร่ข่าว ไม่ตรงกับเวลาปัจจุบัน ให้คุณอธิบายตามความจริงด้วยภาษาที่เข้าใจง่าย เช่น "ข่าวนี้ถูกเผยแพร่เมื่อ [วันที่] ซึ่งเป็นเหตุการณ์ที่เกิดขึ้นไปแล้ว ไม่ใช่เรื่องของวันนี้" ไม่ต้องพยายามหาเหตุผลมาแถให้มันตรงกับเวลาปัจจุบัน

    🚨 กฎการประเมินความน่าเชื่อถือ:
    - 🟢 ระดับ 5 (95%): ข้อมูลจริง มีสื่อหลักยืนยันตรงกันอย่างชัดเจน
    - 🟡 ระดับ 4 (75%): ข้อมูลจริงส่วนใหญ่ สื่อหลักยืนยัน แต่อาจคลาดเคลื่อนเรื่องตัวเลขเล็กน้อย
    - 🟠 ระดับ 3 (50%): ข้อมูลก้ำกึ่ง / ไม่เพียงพอ (กรณีที่ไม่พบข่าวที่ตรงกันเป๊ะ ให้ประเมินระดับนี้ และอธิบายว่า "เนื่องจากไม่มีรายงานข่าวจากสื่อหลัก จึงไม่สามารถยืนยันหรือปฏิเสธข้อมูลนี้ได้")
    - 🔴 ระดับ 2 (25%): ข้อมูลบิดเบือน นำข่าวเก่ามาปั่นกระแสให้เข้าใจผิดว่าเป็นเรื่องปัจจุบัน
    - ❌ ระดับ 1 (10%): ข่าวปลอมแต่งขึ้น ขัดแย้งกับหลักความเป็นจริงอย่างชัดเจน
    
    ⚠️ คำเตือนเรื่องรูปแบบการตอบ: 
    - บรรทัด "ระดับความน่าเชื่อถือ:" คุณต้องพิมพ์แค่ตัวเลข 1, 2, 3, 4 หรือ 5 เท่านั้น ห้ามพิมพ์ข้อความอื่นต่อท้าย!
    - แหล่งอ้างอิงข้อที่ 3 ต้องเป็นตัวเลขเรียง 1., 2., 3. เท่านั้น ห้ามใส่ขีด (-) หรือ Bullet นำหน้าตัวเลข

    ตอบกลับในรูปแบบ Markdown ตามโครงสร้างนี้เป๊ะๆ (ห้ามดัดแปลงหัวข้อ):
    ## 🎯 1. สรุปประเด็นสำคัญ
    - **📝 การวิเคราะห์เนื้อหา:** (อธิบายสั้นๆ ว่าข้อความกล่าวถึงเรื่องอะไร)
    - **⏱️ การวิเคราะห์ไทม์ไลน์:** (อธิบายอย่างมีตรรกะว่า ข่าวถูกเผยแพร่เมื่อใด และเหตุการณ์เกิดขึ้นช่วงไหน ห้ามเขียนย้อนแย้ง)
    - **🔗 ความเกี่ยวข้องของอ้างอิง:** (ระบุอย่างเข้มงวดว่าอ้างอิงที่พบ ตรงกับเนื้อหาจริงๆ หรือไม่)
    
    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [ใส่แค่ตัวเลข 1, 2, 3, 4 หรือ 5]
    **เหตุผลประกอบการประเมิน:** (อธิบายเหตุผลฟันธงที่ยุติธรรม)
    
    ## 🌐 3. แหล่งอ้างอิง
    1. [พาดหัวข่าว](URL)
    2. [พาดหัวข่าว](URL)
    (คัดเฉพาะข่าวที่เกี่ยวข้องกันจริงๆ มาเท่านั้น หากไม่เกี่ยวเลยให้ลบทิ้ง และตอบแค่ว่า "ผลการสืบค้นไม่พบข่าวที่เกี่ยวข้องกับเหตุการณ์นี้โดยตรง")
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}", 
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://factchecker.local", 
                    "X-Title": "AI Fact-Checker" 
                },
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a highly analytical, fair, and neutral Fact-Checker. You evaluate chronological timeline intelligently without forcing events to match the current date. Output exact Markdown."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "seed": 42
                }).encode('utf-8'),
                timeout=30
            )
            response.raise_for_status()
            return clean_llm_output(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            if attempt == 2:
                return f"## 🎯 1. สรุปประเด็นสำคัญ\nเกิดข้อผิดพลาดในการเชื่อมต่อ AI\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** 3\n**เหตุผลประกอบการประเมิน:** เซิร์ฟเวอร์ขัดข้อง ({e})\n## 🌐 3. แหล่งอ้างอิง\n- ไม่มี"
            time.sleep(2)