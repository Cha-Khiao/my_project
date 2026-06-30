import streamlit as st
import requests
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def clean_llm_output(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'^(Here is the .*?|The result is.*?)\n', '', text, flags=re.IGNORECASE)
    return text.strip()

def classify_content(news_text: str) -> tuple:
    """Stage 1: ด่านคัดกรองอัจฉริยะ"""
    
    if re.search(r'(ราคาทอง|น้ำมัน|หุ้น|เงินเฟ้อ|บาท/ดอลลาร์|ชัชชาติ|พิธา|ประยุทธ์|ทักษิณ|เศรษฐา|อุ๊งอิ๊ง|นายก|สส\.|พรรค|รัฐบาล|เลือกตั้ง|คะแนน|มิจฉาชีพ|แจกเงิน|รับสมัคร|มหาวิทยาลัย|เปิดสอบ|สมัครงาน)', news_text):
        return "PROCEED", "ตรวจพบประเด็นสาธารณะ การเมือง เศรษฐกิจ หรือประกาศจากหน่วยงาน"

    text_chunk = news_text[:2500]
    
    prompt = f"""คุณคือผู้เชี่ยวชาญด้านการคัดกรองข้อมูลหน้าด่านเพื่อตรวจสอบข่าวปลอม
    หน้าที่: พิจารณาว่าข้อความนี้ควรถูกส่งไปตรวจสอบข้อเท็จจริงหรือไม่?

    🟢 ให้ตอบ PROCEED ในกรณีดังต่อไปนี้ (ข่าวปลอมมักแฝงอยู่ในรูปแบบเหล่านี้):
    1. ข่าวสารสาธารณะ, การเมือง (คะแนนโหวต/ผลการเลือกตั้ง), อาชญากรรม, ภัยพิบัติ 
    2. โพสต์แคปชั่นสั้นๆ (เช่น จาก X/Twitter หรือ Facebook) ที่กล่าวถึงบุคคลสาธารณะ ตัวเลขสถิติ หรือเหตุการณ์สังคม
    3. ประกาศจากหน่วยงาน/มหาวิทยาลัย: เช่น การเปิดรับสมัครงาน, เปิดรับนักศึกษา, สอบบรรจุ (เพื่อป้องกันข่าวปลอมหลอกรับสมัครงาน)
    4. การประกาศแจกของรางวัล แจกเงิน หรือโปรโมชันที่ดูเกินจริง
    5. โพสต์แจ้งราคาจากร้านค้าท้องถิ่น (เช่น ราคาทอง)
    ⚠️ กฎเหล็ก: ข่าวปลอมมักมาในรูปแบบโพสต์สั้นๆ หรือการแอบอ้างหน่วยงานรับสมัครงาน ห้ามปัดตกเด็ดขาด!

    🔴 ให้ตอบ DROP (ทิ้งไปเลย) เฉพาะใน 3 กรณีนี้เท่านั้น:
    1. คำบ่นอารมณ์ความรู้สึกส่วนตัวล้วนๆ ที่ไม่เกี่ยวกับคนอื่น (เช่น "วันนี้ฝนตก รถติดมาก", "หิวข้าว", "ปวดหลัง")
    2. โพสต์ขายของจุกจิกส่วนตัวของบุคคลธรรมดา (เช่น "ส่งต่อเสื้อยืดมือสอง", "รับหิ้วขนม")
    3. ข้อความขยะจากระบบเว็บ (เช่น "404 Not Found", "Access Denied")

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
            }),
            timeout=10
        )
        raw_content = clean_llm_output(response.json()['choices'][0]['message']['content'])
        
        match_result = re.search(r'RESULT\s*:\s*(PROCEED|DROP)', raw_content, re.IGNORECASE)
        match_reason = re.search(r'REASON\s*:\s*(.*)', raw_content, re.IGNORECASE)
        
        result_type = match_result.group(1).upper() if match_result else "PROCEED"
        reason = match_reason.group(1).strip() if match_reason else "ส่งเข้าตรวจสอบความน่าเชื่อถือ"
        return result_type, reason
    except Exception:
        return "PROCEED", "ระบบคัดกรองขัดข้อง ส่งเข้ากระบวนการตรวจสอบอัตโนมัติ"

def generate_search_keywords(news_text: str) -> str:
    """Stage 2: เครื่องยนต์สกัดคีย์เวิร์ด (แก้บั๊ก AI Hallucination)"""
    text_chunk = news_text[:2500]
    prompt = f"""คุณคือผู้เชี่ยวชาญด้าน Search Engine Optimization (SEO)
    หน้าที่ของคุณคือสกัด "กลุ่มคำค้นหา (Keywords)" จากเนื้อหาด้านล่าง เพื่อหาข่าวที่เกี่ยวข้อง
    
    เนื้อหา:
    {text_chunk}

    กฎการสร้างคำค้นหา:
    1. สกัดเฉพาะ "ชื่อหน่วยงาน/บุคคล", "เหตุการณ์หลัก", และ "ชื่อสถานที่/จังหวัด" ที่ปรากฏอยู่ในเนื้อหา
    2. ⚠️ กฎเหล็ก: ห้ามคิดคำค้นหาขึ้นมาเองเด็ดขาด! ให้สกัดเฉพาะคำที่มีอยู่จริงใน "เนื้อหา" เท่านั้น (เช่น หากในเนื้อหาไม่ได้ระบุชื่อจังหวัด ก็ห้ามใส่ชื่อจังหวัดใดๆ ลงไปในคำตอบเด็ดขาด)
    3. คืนค่าเป็นกลุ่มคำสั้นๆ 3-6 คำ คั่นด้วยช่องว่าง
    4. ห้ามพิมพ์คำว่า "คำค้นหา:" หรือ "คีย์เวิร์ด:" นำหน้าเด็ดขาด
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": "qwen/qwen-2.5-7b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            }),
            timeout=10 
        )
        keywords = clean_llm_output(response.json()['choices'][0]['message']['content'])
        keywords = keywords.replace('"', '').replace("'", "").replace("**", "")
        keywords = re.sub(r'^(คำค้นหา|คีย์เวิร์ด|Keywords?|Search Query)[\s\:\-]*', '', keywords, flags=re.IGNORECASE).strip()
        return keywords
    except Exception:
        return ""

def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> str:
    """Stage 3: เครื่องยนต์ประเมินผลต้านความลำเอียง"""
    ref_text = ""
    if references:
        ref_text = "\n".join([f"- {r['title']} (URL: {r['href']})" for r in references])
    else:
        ref_text = "⚠️ ไม่พบข้อมูลจากการสืบค้นบนอินเทอร์เน็ต (สื่อหลักไม่ได้รายงานเรื่องนี้โดยตรง)"
        
    prompt = f"""You are a Fact-Checker. You MUST respond in THAI LANGUAGE ONLY. DO NOT output `<think>` tags.
    
    [ข้อความที่ต้องตรวจสอบ]
    {news_text}
    
    [ข้อมูลเปรียบเทียบจากสื่อหลัก (ถ้ามี)]
    {ref_text}
    
    =========================================
    🚨 กฎเหล็กสำหรับการตรวจสอบ (อ่านอย่างละเอียดและปฏิบัติตามอย่างเคร่งครัด):
    
    1. 🛡️ กฎต้านความลำเอียง (Anti-Brand Bias): 
       หากข้อความเป็น "โพสต์แจ้งราคาทองคำ" หรือราคาหน้าการขายของ "ร้านค้าท้องถิ่น" (เช่น ห้างเพชรทองกิมปั้ง, ร้านทองในตลาด) 
       - ห้ามหักคะแนน หรือระบุว่าเป็น "ข้อมูลบิดเบือน" เพียงเพราะคุณไม่รู้จักชื่อร้านนั้น หรือค้นหาชื่อร้านในสื่อหลักไม่เจอ
       - ให้คุณประเมินจาก "ตัวเลขราคา" ในข้อความ ว่าใกล้เคียงกับราคากลางในตลาดหรือไม่
       - หากตัวเลขราคาสมเหตุสมผลและสอดคล้องกับกลไกปกติ ให้ถือว่า "🟢 น่าเชื่อถือ" ได้ทันที

    2. 🔍 การประเมินคะแนน:
       - 🟢 ระดับ 5-4: ข้อมูลสอดคล้องกับความเป็นจริง สมเหตุสมผล เป็นการประกาศรับสมัครงานจริง หรือเป็นโพสต์แจ้งราคาที่ปกติ
       - 🟠 ระดับ 3: ข้อมูลมีส่วนที่เกินจริงไปบ้าง หรือไม่สามารถยืนยันได้ทั้งหมดแต่ไม่เป็นอันตราย
       - 🔴 ระดับ 1-2 (ข่าวปลอม/บิดเบือน): ข้อมูลผิดเพี้ยนไปจากความจริง อ้างสรรพคุณเกินจริง หรือมีลักษณะหลอกลวงให้โอนเงิน/หลอกทำงาน
    
    3. บังคับให้ประเมินคะแนน 1-5 เท่านั้น ห้ามตอบ N/A 
    4. เริ่มต้นคำตอบด้วย '## 📌 1. สรุปประเด็นสำคัญ' ทันที
    
    กรุณาตอบกลับโดยใช้รูปแบบ Markdown ดังต่อไปนี้เท่านั้น:

    ## 📌 1. สรุปประเด็นสำคัญ
    - **[ประเด็นที่ 1]:** ...

    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** [เลือก 1 ระดับ: 🟢 ระดับ 5: น่าเชื่อถือสูงมาก / 🟡 ระดับ 4: น่าเชื่อถือ / 🟠 ระดับ 3: ข้อมูลบิดเบือน / 🔴 ระดับ 2: ไม่น่าเชื่อถือ / ☠️ ระดับ 1: ข่าวปลอม]
    
    **เหตุผลประกอบการประเมิน:** (อธิบายเหตุผลอย่างมีตรรกะ โดยเน้นที่ "เนื้อหาหรือตัวเลข" มากกว่า "ความน่าเชื่อถือของชื่อแหล่งที่มา")

    ## 🔗 3. แหล่งอ้างอิง
    - **แหล่งอ้างอิงที่อ้างในข้อความต้นฉบับ:** (ระบุผู้โพสต์/ชื่อร้าน/แหล่งที่มาในข้อความต้นฉบับ หากไม่มีให้ระบุว่า 'ไม่ระบุ')
    
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
            }),
            timeout=25 
        )
        return clean_llm_output(response.json()['choices'][0]['message']['content'])
    except requests.exceptions.Timeout:
        return f"### ❌ เกิดข้อผิดพลาด: เซิร์ฟเวอร์ AI มีคนใช้งานหนาแน่นและตอบสนองช้าเกินเวลาที่กำหนด (Timeout) โปรดกดทดสอบใหม่อีกครั้ง"
    except Exception:
        return f"### ❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ AI"