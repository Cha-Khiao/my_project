import requests
import json
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv
import pytz

load_dotenv()

try:
    import streamlit as st
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
except Exception:
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def get_current_thai_time():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    months_th = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"วันนี้คือ {now.strftime('%A')} ที่ {now.day} {months_th[now.month - 1]} พ.ศ. {now.year + 543} เวลา {now.strftime('%H:%M')} น."

def clean_llm_output(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'^(Here is the .*?|The result is.*?)\n', '', text, flags=re.IGNORECASE)
    return text.strip()

def classify_content(news_text: str) -> tuple:
    text_chunk = news_text[:2500]
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
            # 🛠️ แก้ไข URL ที่พิมพ์ผิด (openopenrouter) เป็น openrouter.ai เรียบร้อยครับ
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [{"role": "system", "content": "Output exactly two lines."}, {"role": "user", "content": prompt}],
                    "temperature": 0.0
                }),
                timeout=15
            )
            response.raise_for_status()
            raw_content = clean_llm_output(response.json()['choices'][0]['message']['content'])
            match_result = re.search(r'RESULT\s*:\s*(PROCEED|DROP)', raw_content, re.IGNORECASE)
            match_reason = re.search(r'REASON\s*:\s*(.*)', raw_content, re.IGNORECASE)
            return match_result.group(1).upper() if match_result else "PROCEED", match_reason.group(1).strip() if match_reason else "อนุญาตให้ตรวจสอบอัตโนมัติ"
        except Exception:
            if attempt == 2: return "PROCEED", "ระบบ API ล่าช้า ส่งเข้ากระบวนการตรวจสอบอัตโนมัติ"
            time.sleep(1.5)

def generate_search_keywords(news_text: str) -> str:
    text_chunk = news_text[:2500]
    prompt = f"""สกัด "กลุ่มคำค้นหา (Keywords)" จากเนื้อหาด้านล่าง เพื่อนำไปค้นหาความจริงใน Google
    เนื้อหา:
    {text_chunk}
    ตอบแค่กลุ่มคำ 3-6 คำ เว้นวรรคระหว่างคำ ห้ามแปลภาษา ห้ามมีคำอธิบาย
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [{"role": "system", "content": "Output ONLY THAI keywords."}, {"role": "user", "content": prompt}],
                    "temperature": 0.0
                }),
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
        snippet = r.get('snippet', 'ไม่มีข้อมูลย่อ')
        ref_text_list.append(f"- แหล่งที่มา: {link}\n  พาดหัวข่าว: {title}\n  เนื้อหาย่อ: {snippet}")
        
    ref_text = "\n".join(ref_text_list) if references else "ไม่มีข้อมูลค้นหาที่เกี่ยวข้องเลย"

    prompt = f"""คุณคือ AI Fact-Checker หน้าที่ของคุณคือฟันธงความจริงด้วยหลักตรรกะและเหตุผลที่เป็นกลาง

    [บริบทเวลาปัจจุบัน]
    🚨 {current_time_context}
    
    [ข้อความที่ต้องตรวจสอบ]
    "{news_text}"
    
    [ผลการสืบค้นจากอินเทอร์เน็ต (พาดหัวข่าวและเนื้อหาย่อ)]
    {ref_text}
    
    =========================================
    🚨 กฎการประเมินและให้คะแนน (คิดให้รอบคอบก่อนตัดสินใจ):
    
    - 🟢 ระดับ 5 (95%): ข่าวจริงชัวร์! มีแหล่งอ้างอิงจากสื่อหลักยืนยันเหตุการณ์ตรงกันอย่างชัดเจน
    - 🟡 ระดับ 4 (75%): ความจริงส่วนใหญ่สอดคล้องกับสื่อหลัก แต่อาจมีรายละเอียดเล็กน้อยหรือตัวเลขที่คาดเคลื่อน
    - 🟠 ระดับ 3 (50%): ข้อมูลไม่เพียงพอ! ใช้ในกรณีที่เป็น "ข่าวทั่วไป" หรือ "เรื่องระดับท้องถิ่น" ที่ยังหาแหล่งอ้างอิงจากสื่อหลักไม่พบ (ห้ามตีเป็นข่าวปลอม หากไม่ใช่เรื่องเพ้อฝัน)
    - 🔴 ระดับ 2 (25%): ข้อมูลบิดเบือน นำข่าวเก่ามาปั่นกระแสให้คนเข้าใจผิดว่าเป็นเรื่องปัจจุบัน 
    - ❌ ระดับ 1 (10%): ข่าวปลอม 100%! ใช้เฉพาะกรณีที่: 
        1. ขัดแย้งกับหลักความเป็นจริงอย่างรุนแรง (เช่น ไทยใช้นิวเคลียร์, ซอมบี้)
        2. เป็นเหตุการณ์ระดับชาติหรือระดับโลกที่ "ถ้าจริงต้องเป็นข่าวใหญ่" แต่กลับหาในกูเกิลไม่เจอเลย
    
    ⚠️ คำเตือนเรื่องรูปแบบ: 
    บรรทัด "ระดับความน่าเชื่อถือ:" คุณต้องพิมพ์คำว่า "ระดับ " ตามด้วยตัวเลข 1, 2, 3, 4 หรือ 5 เท่านั้น ห้ามมีคำอื่น

    ตอบกลับในรูปแบบ Markdown ตามโครงสร้างนี้เป๊ะๆ:
    ## 📌 1. สรุปประเด็นสำคัญ
    - (สรุปความสอดคล้องหรือขัดแย้งของข้อความ กับหลักฐานที่ค้นพบ)
    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** ระดับ [ตัวเลข 1 ถึง 5]
    **เหตุผลประกอบการประเมิน:** (อธิบายเหตุผลอย่างเป็นกลาง โดยอิงจากบริบทเวลา และหลักฐานสื่ออ้างอิง)
    ## 🔗 3. แหล่งอ้างอิง
    - (สรุปรายชื่อเว็บไซต์ที่ใช้อ้างอิง หากไม่มีผลการสืบค้นที่เกี่ยวข้อง ให้ตอบว่า "ผลการสืบค้นไม่พบข่าวที่เกี่ยวข้องจากสื่อหลัก")
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a balanced and logical Fact-Checker. You evaluate evidence fairly without defaulting entirely to Level 1 or Level 3 unneccessarily. Output exact Markdown."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0 
                }),
                timeout=30
            )
            response.raise_for_status()
            return clean_llm_output(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            if attempt == 2:
                return f"## 📌 1. สรุปประเด็นสำคัญ\nเกิดข้อผิดพลาดในการเชื่อมต่อ AI\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ระดับ 3\n**เหตุผลประกอบการประเมิน:** เซิร์ฟเวอร์ขัดข้อง\n## 🔗 3. แหล่งอ้างอิง\n- ไม่มี"
            time.sleep(2)