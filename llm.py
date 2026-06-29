import streamlit as st
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def generate_search_keywords(news_text: str) -> str:
    """ให้ AI สกัดคีย์เวิร์ดแบบ 'ต้องได้คำค้นหาเสมอ' (ไม่ให้ข้ามการค้นหาอีกต่อไป)"""
    prompt = f"""คุณคือผู้เชี่ยวชาญด้าน Search Engine Optimization (SEO)
    หน้าที่ของคุณคือสกัด "กลุ่มคำค้นหา (Keywords)" จากข้อความด้านล่าง เพื่อนำไปค้นหาความจริงในอินเทอร์เน็ต
    
    ข้อความที่ได้รับ (อาจมีเมนูเว็บ ขยะ หรือเป็นแค่โพสต์สั้นๆ):
    {news_text[:1200]} 

    กฎการสร้างคำค้นหา:
    1. จงมองข้ามคำขยะ (เช่น สมัครสมาชิก, ยอมรับคุกกี้, ดูดวง, โฆษณา) และพยายามหา "เหตุการณ์/บุคคล/สถานที่" ที่เป็นใจความสำคัญที่สุดให้เจอ
    2. สกัดเป็นกลุ่มคำ 3-6 คำ (เช่น "ไฟไหม้ ตลาดจตุจักร" หรือ "นายก ลงพื้นที่ เชียงราย")
    3. บังคับ: คุณต้องสร้างคำค้นหาออกมาเสมอ ห้ามตอบว่าหาไม่เจอ ห้ามปฏิเสธการตอบ
    4. ห้ามอธิบาย ตอบกลับมาแค่ "คำค้นหา" เพียวๆ เท่านั้น
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
    """สั่ง AI ประเมินความน่าเชื่อถือ โดยเน้นย้ำว่าโพสต์จาก X (Twitter) ก็คือข่าว"""
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
    🚨 กฎการให้ระดับ N/A (ใช้อย่างระมัดระวังที่สุด):
    - ให้ระดับ N/A **เฉพาะเมื่อ** เนื้อหา "ทั้งก้อน" เป็นเพียงโฆษณาสินค้า, แคปชั่นบ่นเรื่องส่วนตัว(เช่น วันนี้ฝนตก รถติดจัง), หรือแชทบอท ที่ไม่มีการกล่าวอ้างถึงเหตุการณ์สาธารณะใดๆ เลย
    - ⚠️ ข้อยกเว้นเด็ดขาด: หากข้อความเป็น "โพสต์ข่าวสั้นๆ จาก X (Twitter), Facebook, หรือบรรทัดเดียว" ที่รายงานเหตุการณ์ (เช่น อาชญากรรม, การเมือง, ภัยพิบัติ) **ห้ามให้ N/A เด็ดขาด** ให้คุณประเมินระดับ 1-5 ทันที!
    - หากมีคำขยะจากหน้าเว็บปนมา ให้มองข้ามและตัดสินเฉพาะส่วนที่เป็นเนื้อหา
    
    กรุณาตอบกลับโดยใช้รูปแบบ Markdown ดังต่อไปนี้เท่านั้น:

    ## 📌 1. สรุปประเด็นสำคัญ
    (สรุปใจความหลัก หากเป็นข่าวให้ใช้ 5W1H หากเป็นเนื้อหาอื่นให้สรุปว่าคืออะไร)
    - **[ประเด็นที่ 1]:** ...
    - **[ประเด็นที่ 2]:** ...

    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [เลือก 1 ระดับ: 🟢 ระดับ 5: น่าเชื่อถือสูงมาก / 🟡 ระดับ 4: น่าเชื่อถือ / 🟠 ระดับ 3: ข้อมูลบิดเบือน / 🔴 ระดับ 2: ไม่น่าเชื่อถือ / ☠️ ระดับ 1: ข่าวปลอม / ⚪ N/A: ไม่ใช่ข่าวหรือข้อมูลที่ตรวจสอบได้]
    
    **เหตุผลประกอบการประเมิน:** (อธิบายเหตุผลสั้นๆ โดยอิงจากข้อมูลเปรียบเทียบ)
    
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
                    {"role": "system", "content": "You are a highly detailed Thai Fact-Checker. NEVER mark short news tweets or social media news updates as N/A. Evaluate them normally."},
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