import streamlit as st
import requests
import json
import os
import re
import time  # 🌟 เพิ่ม time สำหรับการหน่วงเวลา Retry
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def clean_llm_output(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'^(Here is the .*?|The result is.*?)\n', '', text, flags=re.IGNORECASE)
    return text.strip()

def classify_content(news_text: str) -> tuple:
    text_chunk = news_text[:2500]
    prompt = f"""คุณคือระบบ AI วิเคราะห์ประเภทเนื้อหาบนอินเทอร์เน็ต (Content Classifier)
    หน้าที่ของคุณคือวิเคราะห์ว่าข้อความนี้ "จัดอยู่ในหมวดหมู่ใด" และ "ควรนำไปตรวจสอบข้อเท็จจริง (Fact-Check) หรือไม่"

    [หมวดหมู่เนื้อหาบนโลกอินเทอร์เน็ต]
    1. 📰 NEWS_AND_CLAIMS (ข่าวสารและคำกล่าวอ้าง): ข่าวการเมือง, เศรษฐกิจ, สังคม, ภัยพิบัติ, แจ้งเตือน, ประกาศจากหน่วยราชการ, ราคาสินค้าอ้างอิง หรือ โฆษณาหลอกลวงเกินจริง
       ✅ การตัดสินใจ: ให้ตอบ PROCEED

    2. 🛒 CLASSIFIEDS_AND_ADS (ประกาศซื้อขาย/เช่าทั่วไป): ประกาศหาคนเช่าห้อง, ขายบ้าน, ขายรถ, รีวิวร้านอาหาร, ธุรกิจทั่วไป
       ❌ การตัดสินใจ: ให้ตอบ DROP (พร้อมระบุว่าเป็นประกาศซื้อขาย/บริการทั่วไป)

    3. 💬 PERSONAL_POSTS (โพสต์ส่วนตัว/ถามตอบ): คำบ่น, ไดอารี่, ถามคำถามทั่วไป
       ❌ การตัดสินใจ: ให้ตอบ DROP (พร้อมระบุว่าเป็นโพสต์ส่วนตัว/ถามตอบ)

    4. 🎭 FICTION_AND_ENTERTAINMENT (เรื่องแต่งและบันเทิง): เล่าพล็อตนิยาย, สปอยล์ภาพยนตร์, อนิเมะ, เรื่องแต่ง (ยกเว้นประกาศแจ้งข่าววงการบันเทิง ถือเป็นหมวด 1)
       ❌ การตัดสินใจ: ให้ตอบ DROP (พร้อมระบุว่าเป็นเนื้อหาบันเทิงหรือเรื่องแต่ง)

    5. ⚠️ SYSTEM_ERRORS (ข้อความระบบ): Error 404, Captcha, หน้าเว็บที่ถูกบล็อก
       ❌ การตัดสินใจ: ให้ตอบ DROP 

    6. ❓ UNKNOWN_OR_HYBRID (เนื้อหาแปลกใหม่/กำกวม/ไม่แน่ใจ): โพสต์ผสมผสาน หรือเป็นเรื่องที่คุณไม่รู้จัก
       ✅ การตัดสินใจ: ให้ตอบ PROCEED ทันที 

    ข้อความที่ต้องพิจารณา:
    {text_chunk}

    จงตอบกลับในรูปแบบนี้เท่านั้น:
    RESULT: [เลือก PROCEED หรือ DROP]
    REASON: [อธิบายเหตุผลสั้นๆ เป็นภาษาไทย ว่าทำไมถึงจัดอยู่ในหมวดหมู่นั้น]
    """
    
    # 🌟 ระบบ Auto-Retry (ลองยิง API สูงสุด 3 ครั้ง ป้องกันเซิร์ฟเวอร์ล่ม)
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a content classifier. You must output exactly two lines. Line 1: 'RESULT: PROCEED' or 'RESULT: DROP'. Line 2: 'REASON: [Thai reason]'. Never output anything else."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }),
                timeout=15 # 🌟 เผื่อเวลาให้ API คิดนานขึ้น
            )
            response.raise_for_status() # ตรวจสอบ Error Code
            raw_content = clean_llm_output(response.json()['choices'][0]['message']['content'])
            
            match_result = re.search(r'RESULT\s*:\s*(PROCEED|DROP)', raw_content, re.IGNORECASE)
            match_reason = re.search(r'REASON\s*:\s*(.*)', raw_content, re.IGNORECASE)
            
            result_type = match_result.group(1).upper() if match_result else "PROCEED"
            reason = match_reason.group(1).strip() if match_reason else "อนุญาตให้ตรวจสอบอัตโนมัติ"
            return result_type, reason
            
        except Exception:
            if attempt == 2: # ถ้ารอบที่ 3 ยังพัง ค่อยยอมแพ้
                return "PROCEED", "ระบบ API ล่าช้า ส่งเข้ากระบวนการตรวจสอบอัตโนมัติ"
            time.sleep(1.5) # พักหายใจ 1.5 วินาทีก่อนยิงใหม่

def generate_search_keywords(news_text: str) -> str:
    text_chunk = news_text[:2500]
    prompt = f"""หน้าที่ของคุณคือสกัด "กลุ่มคำค้นหา (Keywords)" จากเนื้อหาด้านล่าง เพื่อนำไปค้นหาข่าวใน Google
    
    เนื้อหา:
    {text_chunk}

    กฎ: สกัดเฉพาะ "ชื่อหน่วยงาน/บุคคล", "สถานที่", หรือ "เหตุการณ์หลัก" ที่มีอยู่จริงในเนื้อหา ห้ามแปลเป็นอังกฤษ ตอบแค่กลุ่มคำ 3-6 คำ คั่นด้วยช่องว่าง
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are an SEO expert. You MUST output ONLY THAI keywords. NEVER translate to English. DO NOT add explanations."},
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
    ref_text = "\n".join([f"- {r['title']} (URL: {r['href']})" for r in references]) if references else "⚠️ ไม่พบข้อมูลจากการสืบค้นบนอินเทอร์เน็ต (อาจเป็นเรื่องใหม่ หรือข้อมูลไม่เพียงพอ)"
    prompt = f"""You are a Fact-Checker. You MUST respond in THAI LANGUAGE ONLY. DO NOT output `<think>` tags.
    
    [ข้อความที่ต้องตรวจสอบ]
    {news_text}
    
    [ข้อมูลเปรียบเทียบจากสื่อหลัก (ถ้ามี)]
    {ref_text}
    
    =========================================
    🚨 กฎเหล็กสำหรับการตรวจสอบ:
    1. 🛡️ การประเมินอย่างเป็นธรรม: หากไม่เจอข้อมูลอ้างอิง ให้ประเมินเป็น "🟠 ระดับ 3: ข้อมูลไม่เพียงพอ" (ห้ามตีเป็นข่าวปลอมมั่วๆ)
    2. 🔍 การประเมินคะแนน:
       - 🟢 ระดับ 5-4: ข้อมูลสอดคล้องความจริง สมเหตุสมผล
       - 🟠 ระดับ 3: ข้อมูลก้ำกึ่ง, มีส่วนเกินจริงบ้าง, หรือ ไม่มีแหล่งอ้างอิงเพียงพอที่จะยืนยัน
       - 🔴 ระดับ 1-2 (ข่าวปลอม/บิดเบือน): ขัดแย้งกับสื่อหลักชัดเจน, โฆษณาหลอกลวง, แจกเงิน, แชร์ลูกโซ่
    
    ตอบกลับในรูปแบบ Markdown:
    ## 📌 1. สรุปประเด็นสำคัญ
    - ...
    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [เลือกระดับ 1-5 พร้อมไอคอน]
    **เหตุผลประกอบการประเมิน:** ...
    ## 🔗 3. แหล่งอ้างอิง
    - ...
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a Fact-Checker. You MUST output ONLY THAI LANGUAGE. Start with '## 📌 1.'"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1 
                }),
                timeout=30 # 🌟 ขั้นตอนประเมินอาจคิดนาน เผื่อเวลาให้ 30 วิ
            )
            response.raise_for_status()
            return clean_llm_output(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            if attempt == 2:
                return f"### ❌ เกิดข้อผิดพลาด: เซิร์ฟเวอร์ AI ขัดข้องหรือตอบสนองช้าเกินไป โปรดทดสอบใหม่อีกครั้ง"
            time.sleep(2)