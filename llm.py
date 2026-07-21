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
    
    # 🌟 เก็บระบบอ้างอิงเวอร์ชันที่ดีที่สุดไว้ ดึง Snippet มาอ่านให้ได้ความ Real-time
    ref_text_list = []
    for r in references:
        title = r.get('title', 'ไม่มีหัวข้อ')
        link = r.get('href', 'ไม่มีลิงก์')
        snippet = r.get('snippet', 'ไม่มีข้อมูลย่อ')
        ref_text_list.append(f"- แหล่งที่มา: {link}\n  พาดหัวข่าว: {title}\n  เนื้อหาย่อ: {snippet}")
        
    ref_text = "\n".join(ref_text_list) if references else "ไม่มีข้อมูลค้นหาที่เกี่ยวข้อง"

    prompt = f"""คุณคือ AI Fact-Checker ผู้ชาญฉลาด มีวิจารณญาณแบบมนุษย์ และรู้เท่าทันข้อมูลบิดเบือน

    [บริบทเวลาปัจจุบัน]
    🚨 {current_time_context}
    
    [ข้อความที่ต้องตรวจสอบ]
    "{news_text}"
    
    [ผลการสืบค้นจากอินเทอร์เน็ตล่าสุด]
    {ref_text}
    
    =========================================
    🚨 กฎการวิเคราะห์ข้อมูลแบบมนุษย์ (Contextual Understanding):
    1. การเชื่อมโยงบริบท: ผลการสืบค้นอาจจะไม่ได้เขียนตรงกับข้อความที่ตรวจสอบเป๊ะๆ ให้คุณพิจารณา "ความเกี่ยวข้องแวดล้อม" (เช่น ข่าวลือบอกว่าใช้นิวเคลียร์รบกัน แต่ข่าวค้นหาเจอแค่การปะทะด้วยอาวุธปืนตามชายแดน) ให้คุณนำข่าวการปะทะนั้นมาอธิบายว่า "มีความขัดแย้งจริง แต่เรื่องนิวเคลียร์เป็นเรื่องบิดเบือน"
    2. การจับโป๊ะ: หากข้อความมีเรื่องเกินจริง/เพ้อฝัน (เช่น อาวุธทำลายล้างที่ประเทศนั้นไม่มี) ให้ใช้หลักสามัญสำนึกตีตกเป็นข่าวปลอมหรือข่าวบิดเบือนทันที แม้จะมีชื่อประเทศหรือสถานที่ตรงกับข่าวจริงก็ตาม
    
    🚨 กฎการให้คะแนน (ห้ามแทงกั๊ก):
    - 🟢 ระดับ 5 (95%): เป็นความจริง สื่อหลักยืนยันตรงกันอย่างชัดเจน
    - 🟡 ระดับ 4 (75%): ส่วนใหญ่เป็นความจริง มีสื่อรายงานตรงกัน แต่อาจมีรายละเอียดเล็กน้อยผิดเพี้ยน
    - 🟠 ระดับ 3 (50%): ก้ำกึ่ง ข้อมูลไม่เพียงพอจริงๆ (ใช้เมื่อไม่มีแม้แต่ข่าวแวดล้อมที่นำมาเชื่อมโยงได้)
    - 🔴 ระดับ 2 (25%): ข้อมูลบิดเบือน (Misleading)! มีมูลความจริงบางส่วน (เช่น เกิดเหตุการณ์นั้นจริง) แต่ถูกนำมาแต่งเติมเนื้อหาให้เกินจริงไปมาก สร้างความตื่นตระหนก
    - ❌ ระดับ 1 (10%): ข่าวปลอม 100%! ขัดแย้งกับหลักความเป็นจริงอย่างสิ้นเชิง และไม่มีสื่อใดรายงานเรื่องนี้เลย
    
    ⚠️ คำเตือนเรื่องรูปแบบ: 
    บรรทัด "ระดับความน่าเชื่อถือ:" คุณต้องพิมพ์คำว่า "ระดับ " ตามด้วยตัวเลข 1, 2, 3, 4 หรือ 5 เท่านั้น

    ตอบกลับในรูปแบบ Markdown ตามโครงสร้างนี้เป๊ะๆ:
    ## 📌 1. สรุปประเด็นสำคัญ
    - (สรุปเปรียบเทียบระหว่างข้อความกล่าวอ้าง กับความจริงที่อนุมานได้จากสื่ออ้างอิง)
    ## 📊 2. การประเมินระดับความน่าเชื่อถือ
    **ระดับความน่าเชื่อถือ:** ระดับ [ตัวเลข 1 ถึง 5]
    **เหตุผลประกอบการประเมิน:** (อธิบายอย่างชาญฉลาด โดยนำข่าวที่ค้นพบมาเชื่อมโยง เพื่อหักล้างหรือสนับสนุนข้อความนั้น)
    ## 🔗 3. แหล่งอ้างอิง
    - (นำรายชื่อเว็บไซต์หรือพาดหัวข่าวที่ใกล้เคียงมาแสดง เพื่อให้ผู้อ่านเห็นว่า AI นำข่าวไหนมาประเมิน)
    """
    for attempt in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "qwen/qwen-2.5-7b-instruct",
                    "messages": [
                        {"role": "system", "content": "You are a smart, context-aware Fact-Checker. You connect related news to debunk fake aspects of a claim. Output exact Markdown."},
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
                return f"## 📌 1. สรุปประเด็นสำคัญ\nเกิดข้อผิดพลาดในการเชื่อมต่อเซิร์ฟเวอร์ AI\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ระดับ 3\n**เหตุผลประกอบการประเมิน:** เซิร์ฟเวอร์ไม่ตอบสนอง กรุณาลองใหม่อีกครั้ง\n## 🔗 3. แหล่งอ้างอิง\n- ไม่มี"
            time.sleep(2)