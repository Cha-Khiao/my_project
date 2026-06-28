import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> str:
    """สั่ง AI ทำแค่ประเมิน ไม่ต้องแปะแหล่งอ้างอิง (Streamlit จะเป็นคนแปะเอง)"""
    
    ref_text = ""
    if references:
        ref_text = "\n".join([f"- {r['title']}" for r in references])
    else:
        ref_text = "ไม่มีข้อมูลจากสำนักข่าวอื่นบนอินเทอร์เน็ต"
        
    prompt = f"""You are a Fact-Checker. You MUST respond in THAI LANGUAGE ONLY. ห้ามตอบเป็นภาษาจีน
    
    [บริบทเชิงเวลา] วันนี้คือวันที่: {current_date}

    [ข่าวที่ต้องการตรวจสอบ]
    {news_text}
    
    [ข้อมูลเปรียบเทียบจากสำนักข่าวอื่น]
    {ref_text}
    
    =========================================
    กรุณาตอบกลับโดยใช้รูปแบบ Markdown ดังต่อไปนี้เท่านั้น:

    ## 📌 1. สรุปประเด็นสำคัญของข่าว
    - **[ประเด็นที่ 1]:** ...

    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [เลือก 1 ระดับ: 🟢 ระดับ 5: น่าเชื่อถือสูงมาก / 🟡 ระดับ 4: น่าเชื่อถือ / 🟠 ระดับ 3: ข้อมูลบิดเบือน / 🔴 ระดับ 2: ไม่น่าเชื่อถือ / ☠️ ระดับ 1: ข่าวปลอม]
    
    **เหตุผลประกอบการประเมิน:** (อธิบายสั้นๆ โดยอ้างอิงวันที่ และข้อมูลเปรียบเทียบ)
    
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
                    {"role": "system", "content": "You are a Thai Fact-Checker. Output strictly in Thai. DO NOT output references or URLs."},
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