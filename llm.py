import streamlit as st
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def generate_search_keywords(news_text: str) -> str:
    """ให้ AI สกัด 'วลีคำค้นหาแบบเจาะจง (Long-tail Keyword)'"""
    prompt = f"""คุณคือผู้เชี่ยวชาญด้านข่าวกรอง (Intelligence Analyst)
    หน้าที่ของคุณคืออ่านเนื้อหาด้านล่าง แล้วสร้าง "ประโยคคำค้นหา (Search Query)" ที่มีความเฉพาะเจาะจงสูงมาก เพื่อนำไปสืบค้นหาข่าวนี้ให้เจอตรงเป๊ะ
    
    เนื้อหา:
    {news_text[:1000]} 

    กฎการสร้างคำค้นหา (ต้องทำตามอย่างเคร่งครัด):
    1. ห้ามใช้คำกว้างๆ หรือสั้นเกินไป ต้องระบุบริบทให้ชัดเจน (เช่น ห้ามใช้แค่ "ไฟไหม้โรงงาน" แต่ต้องเป็น "ไฟไหม้โรงงานกระดาษ สมุทรปราการ 2567")
    2. ต้องดึง "ชื่อบุคคลสำคัญ", "สถานที่", "หน่วยงาน", หรือ "ตัวเลข/วันที่" จากเนื้อหามาใส่ในคำค้นหาด้วยเสมอ
    3. ความยาวของคำค้นหาควรอยู่ระหว่าง 6 ถึง 12 คำ เพื่อให้ Google ดึงข่าวที่เนื้อหาตรงกันมาให้
    4. ตัดคำขยะ (เช่น ด่วนที่สุด, ช็อก, ลือ, แชร์ว่อนเน็ต) ทิ้งไป
    5. ตอบกลับมาแค่ "คำค้นหา" เท่านั้น ห้ามพิมพ์ข้อความอธิบายใดๆ ทั้งสิ้น
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": "qwen/qwen-2.5-7b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            })
        )
        result = response.json()
        keywords = result['choices'][0]['message']['content'].strip()
        return keywords.replace('"', '').replace("'", "").replace("**", "")
    except Exception:
        return "" 

def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> str:
    """สั่ง AI ประเมินความน่าเชื่อถือ และบังคับให้สรุปเนื้อหาอย่างละเอียด"""
    ref_text = ""
    if references:
        ref_text = "\n".join([f"- {r['title']}" for r in references])
    else:
        ref_text = "ไม่มีข้อมูลจากสำนักข่าวอื่นบนอินเทอร์เน็ตที่สอดคล้องกับเหตุการณ์นี้"
        
    prompt = f"""You are a Fact-Checker. You MUST respond in THAI LANGUAGE ONLY. 
    
    [บริบทเชิงเวลา] วันนี้คือวันที่: {current_date}

    [ข่าวที่ต้องการตรวจสอบ]
    {news_text}
    
    [ข้อมูลเปรียบเทียบจากสำนักข่าวอื่น]
    {ref_text}
    
    =========================================
    กรุณาตอบกลับโดยใช้รูปแบบ Markdown ดังต่อไปนี้เท่านั้น:

    ## 📌 1. สรุปประเด็นสำคัญของข่าว
    (กฎ: ห้ามก๊อปปี้แค่พาดหัวข่าวมาวาง คุณต้องอ่านเนื้อหาทั้งหมดแล้วสรุปความแบบ 5W1H (ใคร ทำอะไร ที่ไหน เมื่อไหร่ ทำไม/อย่างไร) เป็นข้อๆ ให้ผู้อ่านเข้าใจเนื้อหาข่าวอย่างทะลุปรุโปร่ง)
    - **[ประเด็นที่ 1]:** ...
    - **[ประเด็นที่ 2]:** ...
    - **[ประเด็นที่ 3]:** ...

    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [เลือก 1 ระดับ: 🟢 ระดับ 5: น่าเชื่อถือสูงมาก / 🟡 ระดับ 4: น่าเชื่อถือ / 🟠 ระดับ 3: ข้อมูลบิดเบือน / 🔴 ระดับ 2: ไม่น่าเชื่อถือ / ☠️ ระดับ 1: ข่าวปลอม / ⚪ N/A: ไม่ใช่ข่าวหรือข้อมูลที่ตรวจสอบได้]
    
    **เหตุผลประกอบการประเมิน:** (อธิบายสั้นๆ ว่าเหตุใดจึงให้คะแนนระดับนี้ อ้างอิงจุดจับผิด ข้อมูลเปรียบเทียบ หรือความสมเหตุสมผลของเนื้อหาข่าว)
    
    (หยุดการตอบเพียงเท่านี้ ห้ามสร้างหัวข้อแหล่งอ้างอิง ห้ามแปะลิงก์ใดๆ ทั้งสิ้น)
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": "qwen/qwen-2.5-7b-instruct",
                "messages": [
                    {"role": "system", "content": "You are a highly detailed Thai Fact-Checker. DO NOT output references or URLs."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1 
            })
        )
        result = response.json()
        if 'choices' not in result:
            return f"### ❌ เกิดข้อผิดพลาดจาก API"
        return result['choices'][0]['message']['content']
    except Exception:
        return f"### ❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ AI"