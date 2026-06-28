import streamlit as st
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

@st.cache_data(ttl=3600, show_spinner=False)
def generate_search_keywords(news_text: str) -> str:
    """ให้ AI สกัดคีย์เวิร์ดที่แม่นยำที่สุด (มี Caching จำผลลัพธ์ 1 ชม.)"""
    prompt = f"""คุณคือผู้เชี่ยวชาญด้าน Search Engine 
    กรุณาอ่านเนื้อหาด้านล่างและสกัด "คีย์เวิร์ดสำคัญ" เพื่อนำไปค้นหาใน Google
    
    เนื้อหา:
    {news_text[:800]} 

    กฎการสกัดคีย์เวิร์ด:
    1. ต้องระบุ "บุคคล/หน่วยงาน" และ "การกระทำ/เหตุการณ์ที่เจาะจง"
    2. หากมี "ปี พ.ศ. / ค.ศ." ต้องนำมาใส่เป็นคีย์เวิร์ดด้วยเสมอ
    3. ตัดคำเกริ่นนำ คำขยะ (เช่น ด่วน, ช็อก) ทิ้งให้หมด
    4. คืนค่าเป็นคำสั้นๆ 3-5 คำ (คั่นด้วยสเปซบาร์เท่านั้น) ห้ามพิมพ์คำอธิบายอื่น
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
        return keywords.replace('"', '').replace("'", "").replace("**", "").replace(",", "")
    except Exception:
        return "" 

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> str:
    """สั่ง AI ประเมินความน่าเชื่อถือ (มี Caching จำผลลัพธ์ 1 ชม.)"""
    ref_text = ""
    if references:
        ref_text = "\n".join([f"- {r['title']}" for r in references])
    else:
        ref_text = "ไม่มีข้อมูลจากสำนักข่าวอื่นบนอินเทอร์เน็ตที่สอดคล้องกับเหตุการณ์นี้"
        
    prompt = f"""You are a Fact-Checker. You MUST respond in THAI LANGUAGE ONLY. 
    
    [บริบทเชิงเวลา] วันนี้คือวันที่: {current_date}

    [ข้อความที่ต้องการตรวจสอบ]
    {news_text}
    
    [ข้อมูลเปรียบเทียบจากสำนักข่าวอื่น]
    {ref_text}
    
    =========================================
    กรุณาพิจารณาข้อความก่อน หากพบว่าเป็นเพียง "โพสต์ทั่วไป, การบ่นส่วนตัว, คำคม, นิยาย, หรือการขายสินค้า" ให้ประเมินในระดับ "N/A"
    
    กรุณาตอบกลับโดยใช้รูปแบบ Markdown ดังต่อไปนี้เท่านั้น:

    ## 📌 1. สรุปประเด็นสำคัญของข้อความ
    - **[ประเด็นที่ 1]:** ...

    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [เลือก 1 ระดับ: 🟢 ระดับ 5: น่าเชื่อถือสูงมาก / 🟡 ระดับ 4: น่าเชื่อถือ / 🟠 ระดับ 3: ข้อมูลบิดเบือน / 🔴 ระดับ 2: ไม่น่าเชื่อถือ / ☠️ ระดับ 1: ข่าวปลอม / ⚪ N/A: ไม่ใช่ข่าวหรือข้อมูลที่ตรวจสอบได้]
    
    **เหตุผลประกอบการประเมิน:** (อธิบายสั้นๆ ว่าเหตุใดจึงให้คะแนนระดับนี้)
    
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
                    {"role": "system", "content": "You are a Thai Fact-Checker. DO NOT output references or URLs."},
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