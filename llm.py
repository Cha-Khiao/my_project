import streamlit as st
import requests
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def clean_llm_output(text: str) -> str:
    """ระบบกำจัดภาษาต่างประเทศและแท็กแปลกปลอม <think>"""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'^(Here is the .*?|The result is.*?)\n', '', text, flags=re.IGNORECASE)
    return text.strip()

def classify_content(news_text: str) -> tuple:
    """Stage 1: ด่านคัดกรองแบบจัดเต็ม (แยกแยะข่าว vs ไม่ใช่ข่าว)"""
    
    # 🚫 ด่านที่ 0: ป้องกันโฆษณา/ขายของ หลุดเข้ามาเพราะมีตัวเลข
    ad_keywords = r'(ราคา|บาท|โปรโมชั่น|สั่งซื้อ|ลดราคา|ส่งฟรี|พร้อมส่ง|Shopee|Lazada|TikTok Shop|ตะกร้า|งวดนี้|เลขเด็ด|คูปอง)'
    if re.search(ad_keywords, news_text, re.IGNORECASE):
        # ถ้าพบคำกลุ่มโฆษณา บังคับให้ข้ามกฎเหล็กข้อล่าง เพื่อให้ AI เป็นคนตัดสินใจว่า DROP หรือไม่
        pass
    # 🛡️ กฎเหล็ก (Heuristic Bypass): ถ้าเจอตัวเลข สถิติ เปอร์เซ็นต์ บังคับผ่าน 100% แก้อาการ AI มักง่ายปัดตกข่าวสถิติ
    elif re.search(r'\d{1,3}(,\d{3})+|\d+(\.\d+)?\s?(%|เปอร์เซ็นต์|ล้าน|แสน|หมื่น|เสียง|คะแนน)', news_text):
        return "PROCEED", "ตรวจพบสถิติ ตัวเลข หรือข้อมูลเชิงปริมาณ จึงส่งเข้าตรวจสอบความจริงทันที"

    text_chunk = news_text[:2500]
    
    prompt = f"""คุณคือผู้เชี่ยวชาญด้านการคัดกรองข้อมูลหน้าด่าน
    หน้าที่: พิจารณาว่าข้อความนี้มี "คำกล่าวอ้าง/การรายงานเหตุการณ์สาธารณะ" หรือไม่?

    🟢 ให้ตอบ PROCEED เมื่อเนื้อหาจัดอยู่ในกลุ่ม:
    - ข่าวสาร, เหตุการณ์, อาชญากรรม, การเมือง, ภัยพิบัติ
    - มีการอ้างอิงถึง บุคคลสาธารณะ, ดารา, หรือหน่วยงาน
    ⚠️ กฎเหล็ก: แม้ข้อความจะสั้นกุดเหมือนแคปชั่น แต่ถ้ามีเค้าโครงของเหตุการณ์สาธารณะ ต้องให้ PROCEED ทันที ห้ามปัดตก!

    🔴 ให้ตอบ DROP เฉพาะเมื่อเนื้อหา "ทั้งก้อน" เป็นเพียง:
    - โฆษณาขายสินค้า หรือ โปรโมชัน
    - แคปชั่นบ่นเรื่องส่วนตัวลอยๆ (เช่น หิวข้าว, ปวดหลัง) ที่ไม่มีเหตุการณ์สาธารณะมาเกี่ยวข้อง
    - ข้อความขยะจากหน้าเว็บ (เช่น ยอมรับคุกกี้, Access Denied)

    ข้อความที่ต้องพิจารณา:
    {text_chunk}

    จงตอบกลับด้วยรูปแบบนี้เท่านั้น (ห้ามมีคำอธิบายเพิ่มเติม):
    RESULT: [เลือก 1 คำ: PROCEED หรือ DROP]
    REASON: [อธิบายเหตุผลสั้นๆ เป็นภาษาไทย]
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": "qwen/qwen-2.5-7b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            })
        )
        raw_content = clean_llm_output(response.json()['choices'][0]['message']['content'])
        
        match_result = re.search(r'RESULT\s*:\s*(PROCEED|DROP)', raw_content, re.IGNORECASE)
        match_reason = re.search(r'REASON\s*:\s*(.*)', raw_content, re.IGNORECASE)
        
        result_type = match_result.group(1).upper() if match_result else "PROCEED"
        reason = match_reason.group(1).strip() if match_reason else "ระบบประเมินว่าควรได้รับการตรวจสอบ"
        
        return result_type, reason
    except Exception:
        return "PROCEED", "ระบบคัดกรองขัดข้อง เข้าสู่กระบวนการค้นหาเพื่อความปลอดภัย"

def generate_search_keywords(news_text: str) -> str:
    """Stage 2: เครื่องยนต์สกัดคีย์เวิร์ดแบบละเอียด"""
    text_chunk = news_text[:2500]
    
    prompt = f"""คุณคือผู้เชี่ยวชาญด้าน Search Engine Optimization (SEO) 
    หน้าที่ของคุณคือสกัด "กลุ่มคำค้นหา (Keywords)" จากเนื้อหาด้านล่าง เพื่อนำไปใช้เสิร์ชหาข่าวใน Google
    
    เนื้อหา:
    {text_chunk}

    กฎการสร้างคำค้นหา:
    1. สกัดเฉพาะ "คำนามหลัก (ชื่อคน/สถานที่)" และ "กริยา/ตัวเลขสำคัญ"
    2. คืนค่าเป็นกลุ่มคำสั้นๆ 3-6 คำ คั่นด้วยช่องว่าง
    3. ห้ามพิมพ์คำว่า "คำค้นหา:" หรือ "คีย์เวิร์ด:" นำหน้าคำตอบเด็ดขาด!
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": "qwen/qwen-2.5-7b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            })
        )
        keywords = clean_llm_output(response.json()['choices'][0]['message']['content'])
        keywords = keywords.replace('"', '').replace("'", "").replace("**", "")
        keywords = re.sub(r'^(คำค้นหา|คีย์เวิร์ด|Keywords?|Search Query)[\s\:\-]*', '', keywords, flags=re.IGNORECASE).strip()
        return keywords
    except Exception:
        return ""

def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> str:
    """Stage 3: เครื่องยนต์ประเมินผลที่รัดกุมที่สุด"""
    ref_text = ""
    if references:
        ref_text = "\n".join([f"- {r['title']}" for r in references])
    else:
        ref_text = "⚠️ ไม่พบข้อมูลจากการสืบค้นบนอินเทอร์เน็ต"
        
    prompt = f"""You are a Fact-Checker. You MUST respond in THAI LANGUAGE ONLY. DO NOT output `<think>` tags.
    
    [ข้อความที่ต้องตรวจสอบ]
    {news_text}
    
    [ข้อมูลเปรียบเทียบจากสื่อหลัก]
    {ref_text}
    
    =========================================
    🚨 กฎเหล็ก:
    - ข้อความนี้ผ่านการคัดกรองมาแล้ว ห้ามตอบ N/A เด็ดขาด บังคับให้ประเมินคะแนน 1-5 เท่านั้น
    - เริ่มต้นคำตอบด้วย '## 📌 1. สรุปประเด็นสำคัญ' ทันที
    
    กรุณาตอบกลับโดยใช้รูปแบบ Markdown ดังต่อไปนี้เท่านั้น:

    ## 📌 1. สรุปประเด็นสำคัญ
    - **[ประเด็นที่ 1]:** ...

    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [เลือก 1 ระดับ: 🟢 ระดับ 5: น่าเชื่อถือสูงมาก / 🟡 ระดับ 4: น่าเชื่อถือ / 🟠 ระดับ 3: ข้อมูลบิดเบือน / 🔴 ระดับ 2: ไม่น่าเชื่อถือ / ☠️ ระดับ 1: ข่าวปลอม]
    
    **เหตุผลประกอบการประเมิน:** (อธิบายเหตุผลโดยอิงจากข้อมูลเปรียบเทียบ)

    ## 🔗 3. แหล่งอ้างอิง
    - **แหล่งอ้างอิงที่อ้างในข้อความต้นฉบับ:** (ระบุผู้โพสต์/แหล่งที่มาในข้อความต้นฉบับ เช่น เพจข่าว หากไม่มีให้ระบุว่า 'ไม่ระบุ')
    
    (หยุดการตอบเพียงเท่านี้ ห้ามสร้างหัวข้ออื่นเพิ่มเติม)
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": "qwen/qwen-2.5-7b-instruct",
                "messages": [
                    {"role": "system", "content": "You are a Fact-Checker. Output ONLY THAI. Start with '## 📌 1.'"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1 
            })
        )
        return clean_llm_output(response.json()['choices'][0]['message']['content'])
    except Exception:
        return f"### ❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ AI"