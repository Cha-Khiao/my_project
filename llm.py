import requests
import json
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv
import pytz

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "qwen/qwen-2.5-7b-instruct").strip()

try:
    import streamlit as st
    if "OPENROUTER_API_KEY" in st.secrets:
        OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"].strip()
    if "AI_MODEL" in st.secrets:
        AI_MODEL = st.secrets["AI_MODEL"].strip()
except Exception:
    pass

def get_current_thai_time():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    months_th = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"วันที่ {now.day} {months_th[now.month - 1]} พ.ศ. {now.year + 543} (ค.ศ.{now.year})"

def sanitize_for_api(text: str) -> str:
    if not text: return ""
    clean = re.sub(r'[<>{}\\]', ' ', text)
    clean = clean.encode('utf-8', 'ignore').decode('utf-8')
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def parse_json_safely(text: str) -> dict:
    if not text: return {}
    text = text.replace('```json', '').replace('```', '').strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return {}

def validate_ai_response(parsed_dict: dict) -> dict:
    template = {
        "content_summary": "ไม่สามารถสกัดข้อมูลสรุปได้",
        "claim_5w1h": "ไม่สามารถสกัด 5W1H ได้",
        "cross_checking": "ไม่มีข้อมูลอ้างอิงเปรียบเทียบ",
        "timeline_analysis": "ไม่สามารถระบุช่วงเวลาได้",
        "score": 3,
        "reason": "ระบบไม่สามารถสรุปผลการวิเคราะห์ได้อย่างสมบูรณ์",
        "relevant_ref_ids": []
    }
    
    if not isinstance(parsed_dict, dict) or not parsed_dict: return template
    for key in template.keys():
        if key not in parsed_dict or parsed_dict[key] in [None, ""]: parsed_dict[key] = template[key]
            
    try:
        score_str = str(parsed_dict["score"])
        numbers = re.findall(r'\d+', score_str)
        parsed_dict["score"] = int(numbers[0]) if numbers else 3
    except: parsed_dict["score"] = 3
        
    if not isinstance(parsed_dict["relevant_ref_ids"], list): parsed_dict["relevant_ref_ids"] = []
    return parsed_dict

# =========================================================
# ⚡ STEP 1: Agent 1 (Search Planner) - บังคับค้นหาเป็น Context
# =========================================================
def analyze_intent_and_plan_search(news_text: str) -> tuple:
    text_chunk = sanitize_for_api(news_text[:2000])
    
    prompt = f"""วิเคราะห์ข้อความนี้อย่างรวดเร็ว:
"{text_chunk}"

หากข้อความเป็นเพียง: บทกวี, มุกตลก, หรือไดอารี่บ่นเรื่องส่วนตัวล้วนๆ ที่ไม่มีข้อกล่าวอ้าง (Claim) ให้ตั้งค่า action = "DROP"
แต่ถ้าข้อความเป็น ข่าวสาร, ข่าวลือ, หรือมีข้อกล่าวอ้าง ให้ตั้งค่า action = "SEARCH" เสมอ

คุณต้องตอบกลับเป็น JSON รูปแบบนี้เท่านั้น ห้ามมีข้อความอื่น:
{{
    "action": "SEARCH หรือ DROP",
    "reason": "เหตุผลสั้นๆ",
    "queries": ["ชื่อบุคคล/สถานที่ + เหตุการณ์ 1", "คีย์เวิร์ด 2"], 
    "topic_summary": "สรุปสั้นๆ 1 ประโยคว่าข้อความนี้เกี่ยวกับอะไร"
}}
🚨 กฎสำคัญของ queries: คีย์เวิร์ดต้องประกอบด้วย "ชื่อบุคคล + บริบท/เหตุการณ์" เสมอ (เช่น ["อิงฟ้า วราหะ เพื่อนรัก", "อิงฟ้า น้ำฝน ตามหาเพื่อน"]) ห้ามค้นหาแค่ชื่อบุคคลเดี่ยวๆ เด็ดขาด!
"""
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://factchecker.local",
                "X-Title": "AI Fact-Checker"
            },
            data=json.dumps({
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a fast Search Planner. Generate specific queries containing BOTH entity and event context. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }).encode('utf-8'),
            timeout=15
        )
        response.raise_for_status()
        res_data = parse_json_safely(response.json()['choices'][0]['message']['content'])
        
        action = res_data.get("action", "SEARCH").upper()
        reason = res_data.get("reason", "อนุญาตให้ตรวจสอบอัตโนมัติ")
        queries = res_data.get("queries", [])
        topic = res_data.get("topic_summary", "กำลังวิเคราะห์ประเด็น")
        
        if action == "DROP": return "DROP", reason, ""
        if not isinstance(queries, list) or not queries: queries = [text_chunk[:60]]
        return "SEARCH", queries, topic
        
    except Exception:
        return "SEARCH", [text_chunk[:60]], "ประเด็นทั่วไป"

# =========================================================
# ⚖️ STEP 2: Agent 3 (Analyzer) - โฟกัสเฉพาะบริบทเดียวกัน
# =========================================================
def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> dict:
    current_time_context = get_current_thai_time()
    
    ref_text_list = []
    for i, r in enumerate(references):
        title = r.get('title', 'ไม่มีหัวข้อ')
        pub_date = r.get('pub_date', 'ไม่ระบุ')
        snippet = r.get('snippet', 'ไม่มีข้อมูลย่อ')
        href = r.get('href', '')
        ref_text_list.append(f"[รหัสอ้างอิง {i+1}]: พาดหัว: {title} | วันที่: {pub_date} | สรุป: {snippet} | ลิงก์: {href}")
        
    ref_text = "\n".join(ref_text_list) if references else "ไม่มีอ้างอิงสืบค้นจากสำนักข่าว"
    clean_news_text = sanitize_for_api(news_text)

    prompt = f"""คุณคือนักวิเคราะห์ข้อเท็จจริง AI (Fact-Checker) ที่มีความยุติธรรมและเฉียบขาด
[บริบทเวลาปัจจุบัน]: {current_time_context}
[เนื้อหาที่ต้องการตรวจสอบ]: "{clean_news_text}"
[ข้อมูลอ้างอิงที่ระบบหามาได้]: 
{ref_text}

กระบวนการคิดวิเคราะห์ (ต้องทำตามลำดับ):
1. สกัด 5W1H (claim_5w1h): เนื้อหาอ้างว่า ใคร ทำอะไร ที่ไหน เมื่อไหร่ อย่างไร?
2. ตรวจสอบไขว้ (cross_checking): เทียบกับข้อมูลอ้างอิง ข้อมูลตรงกัน หรือ ขัดแย้งกัน?
3. คัดกรองอ้างอิง (relevant_ref_ids - สำคัญมาก): 
   - ✅ ใส่รหัสอ้างอิงเฉพาะข่าวที่ "พูดถึงเหตุการณ์เดียวกัน/บริบทเดียวกัน" เท่านั้น! 
   - ❌ หากอ้างอิงนั้นแค่มีชื่อคนเหมือนกัน แต่ "คนละเหตุการณ์" (เช่น ถามเรื่องเพื่อนรักอิงฟ้า แต่ได้ข่าวอิงฟ้าเล่นภาพยนตร์/เป็นกรรมการ) ให้เตะรหัสนั้นทิ้งทันที ห้ามนำมาใส่เด็ดขาด ถือว่าอ้างอิงนั้นขยะ! ปล่อยว่าง [] ไปเลยถ้าไม่มีข่าวไหนตรง
4. การให้คะแนน (Scoring Scale):
   - 5 (จริงแท้ 95%): เหตุการณ์หลักจริงและสอดคล้องกับอ้างอิง
   - 4 (จริงส่วนใหญ่ 75%): เหตุการณ์หลักจริง แต่อาจมีรายละเอียดเล็กน้อยคลาดเคลื่อน
   - 3 (ก้ำกึ่ง 50%): เป็นประเด็นใหม่เอี่ยมที่ไม่มีหลักฐานยืนยัน หรือสื่อรายงานขัดแย้งกันเอง
   - 2 (บิดเบือน 25%): จงใจเอาข่าวเก่ามาเล่าใหม่ให้เข้าใจผิด หรือมีส่วนจริงนิดเดียวแต่แต่งเติมความเท็จเยอะมาก
   - 1 (ปลอม 10%): ขัดแย้งกับอ้างอิง หรือเป็นข่าวลือที่ไม่เจอข่าวอ้างอิงตรงประเด็นเลย

🚨 กฎบังคับ: เขียนทุกฟิลด์เป็น "ภาษาไทย" เท่านั้น (Strictly THAI Language)

คุณต้องตอบกลับเป็น JSON รูปแบบนี้เท่านั้น ห้ามมีข้อความอื่น:
{{
    "content_summary": "สรุปเนื้อหาที่ถูกตรวจสอบ",
    "claim_5w1h": "สกัด ใคร ทำอะไร ที่ไหน เมื่อไหร่ อย่างไร",
    "cross_checking": "วิเคราะห์และเปรียบเทียบข้อความกับแหล่งอ้างอิงอย่างละเอียด",
    "timeline_analysis": "สรุปไทม์ไลน์ของเหตุการณ์",
    "relevant_ref_ids": [1, 2, 3],
    "score": 4,
    "reason": "เหตุผลฟันธงสั้นๆ"
}}
"""

    for attempt in range(2):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://factchecker.local",
                    "X-Title": "AI Fact-Checker"
                },
                data=json.dumps({
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a fair fact-checker. ONLY include relevant_ref_ids if they match the EXACT EVENT. Drop references that only match the person's name but discuss different events. Output valid JSON in THAI."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                }).encode('utf-8'),
                timeout=20
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            parsed_json = parse_json_safely(content)
            if parsed_json: return validate_ai_response(parsed_json)
        except Exception:
            time.sleep(1)

    return validate_ai_response({})

# =========================================================
# 🕵️‍♂️ STEP 3: Agent 4 (Critic Agent) - กรองเหตุการณ์ (Event) ให้เป๊ะ
# =========================================================
def critic_review_analysis(news_text: str, references: list, initial_analysis: dict) -> dict:
    clean_news_text = sanitize_for_api(news_text)
    
    ref_text_list = []
    for i, r in enumerate(references):
        title = r.get('title', 'ไม่มีหัวข้อ')
        ref_text_list.append(f"[รหัสอ้างอิง {i+1}]: {title}")
    ref_text = "\n".join(ref_text_list) if references else "ไม่มีอ้างอิง"
    
    prompt = f"""คุณคือ Senior Fact-Checker ตรวจสอบผลงานของลูกน้อง

[เนื้อหาต้นฉบับ]: "{clean_news_text}"
[ข้อมูลอ้างอิงที่มี]: 
{ref_text}
[ผลการวิเคราะห์จากลูกน้อง]:
{json.dumps(initial_analysis, ensure_ascii=False, indent=2)}

หน้าที่ของคุณ:
1. กรองอ้างอิงให้เป๊ะ (Strict Event Filtering): 🚨 หากลูกน้องเลือกรหัสอ้างอิงที่ "มีแค่ชื่อบุคคลตรงกัน แต่เหตุการณ์ไม่ตรงกันเลย" (เช่น ตรวจสอบเรื่องเพื่อนรักในอดีต แต่ได้ข่าวเล่นภาพยนตร์/เป็นกรรมการ) ให้คุณ "ลบรหัสนั้นออกจาก relevant_ref_ids ทิ้งทันที!" ให้เหลือเป็น [] ถ้าไม่มีอันไหนตรงเลย
2. ตรวจสอบการให้คะแนน (Score Correction): 
   - หากเนื้อหาหลักเป็นความจริง อนุญาตให้ใช้คะแนน 5 หรือ 4 ได้เลย
   - หากหาอ้างอิงที่ "ตรงกับเหตุการณ์" ไม่เจอเลย (relevant_ref_ids เป็น []) และเนื้อหาเป็นการอ้างเรื่องใหญ่โต/ข่าวลือ ให้แก้คะแนนเป็น 1 ทันที
3. เขียนทุกฟิลด์เป็น "ภาษาไทย" เท่านั้น ห้ามมีภาษาจีนหลงเหลืออยู่!

คุณต้องตอบกลับเป็น JSON รูปแบบนี้เท่านั้น ห้ามมีข้อความอื่น:
{{
    "content_summary": "...",
    "claim_5w1h": "...",
    "cross_checking": "...",
    "timeline_analysis": "...",
    "relevant_ref_ids": [1, 2],
    "score": 4,
    "reason": "..."
}}
"""

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://factchecker.local",
                "X-Title": "AI Fact-Checker"
            },
            data=json.dumps({
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a Senior Critic. Drop reference IDs if they match the entity but NOT the event. You MUST output entirely in THAI language. Output ONLY a valid JSON object."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }).encode('utf-8'),
            timeout=20
        )
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        parsed_json = parse_json_safely(content)
        if parsed_json: return validate_ai_response(parsed_json)
    except Exception:
        return validate_ai_response(initial_analysis)

    return validate_ai_response(initial_analysis)