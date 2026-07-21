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
    """ฟังก์ชันใหม่: สร้างบริบทเวลาปัจจุบันให้ AI รับรู้"""
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
    prompt = f"""คุณคือระบบ AI วิเคราะห์ประเภทเนื้อหาบนอินเทอร์เน็ต (Content Classifier)
    หน้าที่ของคุณคือวิเคราะห์ว่าข้อความนี้ "จัดอยู่ในหมวดหมู่ใด" และ "ควรนำไปตรวจสอบข้อเท็จจริง (Fact-Check) หรือไม่"

    [ข้อควรระวังสำคัญ]: ข้อความที่ส่งมาอาจเป็นเพียง "หัวข้อข่าว" หรือ "แคปชั่นสั้นๆ" (ยาว 1-3 บรรทัด) ห้ามปฏิเสธการวิเคราะห์เด็ดขาด ให้พยายามดึงใจความสำคัญเพื่อนำไปตรวจสอบเสมอ

    [หมวดหมู่เนื้อหา]
    1. 📰 NEWS_AND_CLAIMS (ข่าวสารและคำกล่าวอ้าง): ข่าว, การเมือง, แจ้งเตือน, ภัยพิบัติ, คำกล่าวอ้างทางโซเชียล
       ✅ ให้ตอบ: PROCEED
    2. 🛒 CLASSIFIEDS_AND_ADS: ประกาศซื้อขายทั่วไป
       ❌ ให้ตอบ: DROP
    3. 💬 PERSONAL_POSTS: โพสต์บ่น, ไดอารี่ส่วนตัว
       ❌ ให้ตอบ: DROP
    4. 🎭 FICTION_AND_ENTERTAINMENT: เรื่องแต่ง, นิยาย
       ❌ ให้ตอบ: DROP
    5. ⚠️ SYSTEM_ERRORS: Error 404, Login page
       ❌ ให้ตอบ: DROP
    6. ❓ UNKNOWN_OR_HYBRID: ไม่แน่ใจ หรือเนื้อหากำกวม
       ✅ ให้ตอบ: PROCEED

    ข้อความที่ต้องพิจารณา:
    {text_chunk}

    จงตอบกลับ 2 บรรทัดดังนี้เท่านั้น:
    RESULT: [PROCEED หรือ DROP]
    REASON: [เหตุผลภาษาไทยสั้นๆ]
    """
    
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a content classifier. You must output exactly two lines. Line 1: 'RESULT: PROCEED' or 'RESULT: DROP'. Line 2: 'REASON: [Thai reason]'."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }),
                timeout=15
            )
            response.raise_for_status()
            raw_content = clean_llm_output(response.json()['choices'][0]['message']['content'])
            
            match_result = re.search(r'RESULT\s*:\s*(PROCEED|DROP)', raw_content, re.IGNORECASE)
            match_reason = re.search(r'REASON\s*:\s*(.*)', raw_content, re.IGNORECASE)
            
            result_type = match_result.group(1).upper() if match_result else "PROCEED"
            reason = match_reason.group(1).strip() if match_reason else "อนุญาตให้ตรวจสอบอัตโนมัติ"
            return result_type, reason
        except Exception:
            if attempt == 2: return "PROCEED", "ระบบ API ล่าช้า ส่งเข้ากระบวนการตรวจสอบอัตโนมัติ"
            time.sleep(1.5)

def generate_search_keywords(news_text: str) -> str:
    text_chunk = news_text[:2500]
    prompt = f"""สกัด "กลุ่มคำค้นหา (Keywords)" จากเนื้อหาด้านล่าง เพื่อนำไปค้นหาความจริงใน Google
    
    เนื้อหา:
    {text_chunk}

    กฎ: 
    1. สกัดเฉพาะ "ชื่อบุคคล", "สถานที่", "เหตุการณ์" หรือ "คีย์เวิร์ดสำคัญ"
    2. ห้ามแปลเป็นภาษาอังกฤษ
    3. ตอบแค่กลุ่มคำ 3-6 คำ เว้นวรรคระหว่างคำ
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are an SEO expert. Output ONLY THAI keywords. No explanations."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }),
                timeout=15 
            )
            response.raise_for_status()
            keywords = clean_llm_output(response.json()['choices'][0]['message']['content'])
            keywords = keywords.replace('"', '').replace("'", "").replace("**", "")
            keywords = re.sub(r'^(คำค้นหา|คีย์เวิร์ด|Keywords?|Search Query)[\s\:\-]*', '', keywords, flags=re.IGNORECASE).strip()
            return keywords
        except Exception:
            if attempt == 2: return ""
            time.sleep(1.5)

def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> str:
    # 🌟 สร้างระบบบริบทเวลาให้ AI รู้ว่าวันนี้คือวันอะไร
    current_time_context = get_current_thai_time()
    
    ref_text = "\n".join([f"- {r['title']} (URL: {r['href']})" for r in references]) if references else "ไม่มีข้อมูลอ้างอิงจากสื่อหลักที่ตรงกับบริบท"
    
    prompt = f"""คุณคือ AI Fact-Checker ระดับโลก คุณต้องเป็นกลาง เด็ดขาด และรู้เท่าทันข้อมูล
    
    [บริบทเวลาปัจจุบันของคุณ]
    🚨 {current_time_context}
    คุณต้องใช้บริบทเวลานี้ เพื่อตรวจสอบคำว่า "วันนี้", "เมื่อวาน", "ล่าสุด" ในข้อความที่ถูกกล่าวอ้าง
    หากข้อความกล่าวอ้างถึงเหตุการณ์ "วันนี้" แต่ข่าวอ้างอิงเป็นเรื่องของ "อดีต (เช่น ปีที่แล้ว)" ให้ถือว่าข้อมูลอ้างอิงนั้น "ไม่เกี่ยวข้องกัน" และอาจเป็นข่าวปลอมที่นำเรื่องเก่ามาเล่าใหม่

    [ข้อความที่ต้องตรวจสอบ]
    "{news_text}"
    
    [ข้อมูลเปรียบเทียบจากสื่อหลัก (เพื่อใช้ตรวจสอบข้อความด้านบน)]
    {ref_text}
    
    =========================================
    🚨 กฎเหล็กขั้นเด็ดขาด (ห้ามฝ่าฝืน):
    1. ความเชื่อมโยงของเวลา (Time Relevance): ข่าวอ้างอิงต้องเป็นเหตุการณ์ที่เกิดขึ้นในช่วงเวลาที่สอดคล้องกับข้อความกล่าวอ้าง หากข้อความบอกว่าเกิด "วันนี้" แต่ไม่มีข่าวอ้างอิงในวันนี้เลย ให้ถือว่าเป็น "ข่าวลือ/ข่าวปลอม"
    2. ความตรงประเด็น (Factual Consistency): หากข้อความมีคีย์เวิร์ดที่เกินจริงอย่างชัดเจน (เช่น "ระเบิดนิวเคลียร์", "มนุษย์ต่างดาว", "ซอมบี้") และไม่มีสำนักข่าวหลักยืนยันสิ่งเหล่านั้น "ให้ตีตกเป็น ข่าวปลอม (ระดับ 1) ทันที" แม้ว่าบริบทอื่นในข่าว (เช่น ชื่อประเทศ) จะถูกต้องก็ตาม
    3. การประเมินคะแนนที่เด็ดขาด:
       - 🟢 ระดับ 5: ข้อมูลจริง 100% มีแหล่งข่าวหลักยืนยันตรงกันทุกประการ
       - 🟡 ระดับ 4: ข้อมูลส่วนใหญ่เป็นจริง แต่อาจมีรายละเอียดเล็กน้อยที่คลาดเคลื่อน
       - 🟠 ระดับ 3: ข้อมูลก้ำกึ่งมาก, ขาดข้อมูลสนับสนุนที่ชัดเจน, หรือเป็นเพียงความคิดเห็น/ข่าวลือที่ยังไม่ได้รับการยืนยัน
       - 🔴 ระดับ 2: ข้อมูลเกินจริงไปมาก, นำข่าวเก่ามาปั่นกระแส, หรือมีแนวโน้มบิดเบือนสูง
       - ❌ ระดับ 1 (ข่าวปลอม): ข้อมูลเป็นเท็จ 100%, ขัดแย้งกับหลักความเป็นจริงอย่างสิ้นเชิง (เช่น ไทยใช้ระเบิดนิวเคลียร์), เป็นเฟกนิวส์เพื่อสร้างความแตกตื่น
    
    ตอบกลับในรูปแบบ Markdown ตามโครงสร้างนี้เท่านั้น:
    ## 📌 1. สรุปประเด็นสำคัญ
    - (สรุปว่าข้อความกล่าวอ้างคืออะไร และความจริงที่พบคืออะไร)
    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [ระบุระดับ 1-5 ตามกฎด้านบน]
    **เหตุผลประกอบการประเมิน:** (อธิบายเหตุผลโดยอิงจากความสอดคล้องของเวลา และความขัดแย้งของเหตุการณ์)
    ## 🔗 3. แหล่งอ้างอิง
    - (ใส่แหล่งอ้างอิงที่เกี่ยวข้อง หากไม่มีให้เขียนว่า "ไม่พบข้อมูลอ้างอิงจากสื่อหลักที่เชื่อถือได้")
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a ruthless Fact-Checker. You detect fake news, outdated news reused as fresh, and illogical claims. You MUST respond in THAI. Start with '## 📌 1.'"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1 
                }),
                timeout=30
            )
            response.raise_for_status()
            return clean_llm_output(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            if attempt == 2:
                return f"### ❌ เกิดข้อผิดพลาด: เซิร์ฟเวอร์ AI ขัดข้องหรือตอบสนองช้าเกินไป โปรดทดสอบใหม่อีกครั้ง"
            time.sleep(2)