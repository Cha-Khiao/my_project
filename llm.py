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
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
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
        if numbers:
            score_val = int(numbers[0])
            parsed_dict["score"] = max(1, min(5, score_val))
        else:
            parsed_dict["score"] = 3
    except: 
        parsed_dict["score"] = 3
        
    try:
        rel_val = parsed_dict.get("relevant_ref_ids", "")
        if isinstance(rel_val, list):
            parsed_dict["relevant_ref_ids"] = [int(x) for x in rel_val if str(x).isdigit() and int(x) != 0]
        else:
            numbers = re.findall(r'\d+', str(rel_val))
            parsed_dict["relevant_ref_ids"] = [int(n) for n in numbers if int(n) != 0]
    except:
        parsed_dict["relevant_ref_ids"] = []
        
    # ดักกรองเลข 999 
    parsed_dict["relevant_ref_ids"] = [x for x in parsed_dict["relevant_ref_ids"] if x != 999]
    return parsed_dict

# =========================================================
# ⚡ STEP 1: Agent 1 (Search Planner)
# =========================================================
def analyze_intent_and_plan_search(news_text: str) -> tuple:
    text_chunk = sanitize_for_api(news_text[:2000])
    
    prompt = f"""วิเคราะห์ข้อความนี้เพื่อสร้างคีย์เวิร์ดค้นหา (SEO Keywords):
"{text_chunk}"

หน้าที่ของคุณ:
1. หากเป็น "เรื่องส่วนตัวล้วนๆ, มุกตลก, นิทาน" ให้ action = "DROP"
2. หากเป็น "ข่าวลือ, ข่าวสาร, หรือข้อกล่าวอ้าง" ให้ action = "SEARCH"
3. การสร้าง queries: 🚨 ให้สกัดคีย์เวิร์ด "อย่างน้อย 2-3 คำ" โดยต้องมีทั้ง "ชื่อบุคคล/สถานที่" และ "บริบทเหตุการณ์" (เช่น ["อิงฟ้า เพื่อนรัก น้ำฝน"]) ห้ามตั้งคีย์เวิร์ดกว้างๆ เด็ดขาด!

คุณต้องตอบกลับเป็น JSON รูปแบบนี้เท่านั้น:
{{
    "action": "SEARCH หรือ DROP",
    "reason": "เหตุผลสั้นๆ",
    "queries": ["คีย์เวิร์ด 1", "คีย์เวิร์ด 2"], 
    "topic_summary": "สรุปสั้นๆ 1 ประโยค"
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
                    {"role": "system", "content": "You are an SEO keyword extractor. Generate highly specific, space-separated queries. Output ONLY valid JSON in THAI."},
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
# ⚖️ STEP 2: Agent 3 (Analyzer)
# =========================================================
def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> dict:
    current_time_context = get_current_thai_time()
    
    ref_text_list = []
    for i, r in enumerate(references):
        title = r.get('title', 'ไม่มีหัวข้อ')
        pub_date = r.get('pub_date', 'ไม่ระบุ')
        snippet = r.get('snippet', 'ไม่มีข้อมูลย่อ')
        href = r.get('href', '')
        ref_text_list.append(f"[รหัสอ้างอิง {i+1}]: พาดหัว: {title} | วันที่: {pub_date} | สรุป: {snippet}")
        
    ref_text = "\n".join(ref_text_list) if references else "ไม่มีอ้างอิงสืบค้นจากสำนักข่าว"
    clean_news_text = sanitize_for_api(news_text)

    prompt = f"""คุณคือนักวิเคราะห์ข้อเท็จจริง AI
[บริบทเวลาปัจจุบัน]: {current_time_context}
[เนื้อหาที่ต้องการตรวจสอบ]: "{clean_news_text}"
[ข้อมูลอ้างอิงที่ระบบหามาได้]: 
{ref_text}

จงประเมินความน่าเชื่อถือตาม "ตรรกะสากล (Universal Logic)":
1. การคัดกรองอ้างอิง (relevant_ref_ids): 
   - 🎯 ให้เลือกรหัสอ้างอิง "เฉพาะ" ข่าวที่ตรงกับเหตุการณ์ที่คุณกำลังตรวจสอบเป๊ะๆ เท่านั้น
   - 🚨 เน้น "คุณภาพ" มากกว่า "ปริมาณ" หากอ่านแล้วพบว่าเป็นข่าวคนละบริบท (เช่น มีแค่ชื่อคนเหมือนกันแต่คนละเรื่อง) ให้คัดทิ้งทันที ห้ามนำมาใส่เด็ดขาด
   - หากหาข่าวที่ตรงเป๊ะไม่ได้เลย ให้เปลี่ยนเป็น []
2. การให้คะแนน (Scoring):
   - 5 (จริง 95%): หลักฐานสอดคล้องกับเนื้อหาอย่างสมบูรณ์
   - 4 (จริงส่วนใหญ่ 75%): หลักฐานสนับสนุนเนื้อหาหลัก แต่อาจมีรายละเอียดเล็กน้อยคลาดเคลื่อน
   - 3 (ก้ำกึ่ง 50%): เรื่องทั่วไปหรือเรื่องส่วนตัวที่อาจเกิดขึ้นได้จริง แต่ยังไม่มีหลักฐานแน่ชัด
   - 2 (บิดเบือน 25%): หลักฐานชี้ว่ามีการบิดเบือน
   - 1 (ปลอม 10%): ข่าวระดับชาติ/เหตุการณ์ใหญ่โต ที่หาอ้างอิงยืนยันไม่พบเลย

คุณต้องตอบกลับเป็น JSON รูปแบบนี้เท่านั้น:
{{
    "content_summary": "สรุปเนื้อหา",
    "claim_5w1h": "สกัด ใคร ทำอะไร ที่ไหน เมื่อไหร่ อย่างไร",
    "cross_checking": "อธิบายว่าอ้างอิงแต่ละอันตรงกับเนื้อหาต้นฉบับหรือไม่",
    "timeline_analysis": "สรุปไทม์ไลน์",
    "relevant_ref_ids": [999],
    "score": 0,
    "reason": "เหตุผล"
}}
🚨 กฎบังคับ: 
- ให้แทนที่ score เป็นตัวเลข 1, 2, 3, 4 หรือ 5 เท่านั้น ห้ามลอก 0
- ให้แทนที่ [999] ด้วยอาร์เรย์รหัสอ้างอิงที่ตรงประเด็นจริงๆ เท่านั้น 
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
                        {"role": "system", "content": "You are an analytical fact-checker. Focus on precision and quality over quantity. Reject unrelated context matches. Output ONLY valid JSON in THAI."},
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
# 🕵️‍♂️ STEP 3: Agent 4 (Critic Agent)
# =========================================================
def critic_review_analysis(news_text: str, references: list, initial_analysis: dict) -> dict:
    clean_news_text = sanitize_for_api(news_text)
    
    ref_text_list = []
    for i, r in enumerate(references):
        title = r.get('title', 'ไม่มีหัวข้อ')
        ref_text_list.append(f"[รหัสอ้างอิง {i+1}]: {title}")
    ref_text = "\n".join(ref_text_list) if references else "ไม่มีอ้างอิง"
    
    prompt = f"""คุณคือ Senior Fact-Checker QA ทำหน้าที่ตรวจตรรกะ

[เนื้อหาต้นฉบับ]: "{clean_news_text}"
[ข้อมูลอ้างอิงที่มี]: 
{ref_text}
[ผลการวิเคราะห์จากลูกน้อง]:
{json.dumps(initial_analysis, ensure_ascii=False, indent=2)}

หน้าที่ของคุณ:
1. ความเกี่ยวข้อง (Relevance): 🚨 ตรวจสอบ relevant_ref_ids อีกครั้ง! เน้นคุณภาพมากกว่าปริมาณ หากรหัสไหนเป็นข่าวคนละบริบท ให้ลบทิ้งทันที 
2. ความสมเหตุสมผลของคะแนน (Sanity Check): 
   - 🚨 หากลูกน้องให้คะแนน 3 (50%) กับ "ข้อกล่าวอ้างที่รุนแรงระดับชาติ" ที่หาอ้างอิงสนับสนุนไม่พบเลย ให้คุณบังคับแก้คะแนนเป็น 1 (10%) 
   - นอกเหนือจากนั้น ให้เคารพคะแนนเดิมของลูกน้อง
3. ภาษา: แปลผลลัพธ์ทั้งหมดให้เป็น "ภาษาไทย" 100% 

คุณต้องตอบกลับเป็น JSON รูปแบบนี้เท่านั้น:
{{
    "content_summary": "...",
    "claim_5w1h": "...",
    "cross_checking": "...",
    "timeline_analysis": "...",
    "relevant_ref_ids": [999],
    "score": 0,
    "reason": "..."
}}
🚨 กฎบังคับ: 
- ให้แทนที่ score เป็นตัวเลข 1, 2, 3, 4 หรือ 5
- ให้แทนที่ [999] ด้วยรหัสอ้างอิงที่ตรงประเด็นจริงๆ ที่เหลืออยู่เท่านั้น
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
                    {"role": "system", "content": "You are a QA Critic. Enforce strict relevance. Output ONLY valid JSON in THAI."},
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