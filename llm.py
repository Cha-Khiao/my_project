import requests
import json
import os
import re
from datetime import datetime
from dotenv import load_dotenv
import pytz

load_dotenv()

HOST_URL = "https://openrouter.ai"
API_URL = HOST_URL + "/api/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "qwen/qwen3-8b").strip()

def get_current_thai_time():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    months_th = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"วันที่ {now.day} {months_th[now.month - 1]} พ.ศ. {now.year + 543} (ค.ศ.{now.year})"

def sanitize_for_api(text: str) -> str:
    if not text: return ""
    clean = re.sub(r'[<>{}\\]', ' ', text)
    clean = clean.encode('utf-8', 'ignore').decode('utf-8')
    return re.sub(r'\s+', ' ', clean).strip()

def parse_json_safely(text: str) -> dict:
    if not text: return {}
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE)
    if match:
        try: return json.loads(match.group(1))
        except Exception: pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try: return json.loads(match.group(0))
        except Exception: pass
    return {}

def call_openrouter(prompt: str, system_msg: str) -> dict:
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": AI_MODEL, "messages": [{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}], "temperature": 0.0}
    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=30) # ลด timeout ลงเพื่อไม่ให้รอนานเกินไป
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content']
        return parse_json_safely(content)
    except Exception as e:
        return {}

def analyze_intent_and_plan_search(news_text: str) -> tuple:
    text_for_analysis = news_text.split("]:\n")[-1] if "]:\n" in news_text else news_text
    text_chunk = sanitize_for_api(text_for_analysis[:1000])
    current_year_th = datetime.now(pytz.timezone('Asia/Bangkok')).year + 543
    
    prompt = f"""ข้อความ: "{text_chunk}"
หน้าที่: สกัดข้อมูล
กฎ:
1. หากเป็น "ความคิดเห็นส่วนตัว", "คำด่าทอ" ให้ action = "DROP"
2. หากเป็นข่าว ให้ action = "SEARCH"
3. `search_query`: กลุ่มคำสั้นๆ 1-3 คำ (ห้ามยาว)
4. `core_keywords`: คำเดี่ยวๆ (Single words) ที่เป็นทางการ ห้ามเขียนเป็นประโยค

ตอบกลับ JSON รูปแบบเป๊ะๆ:
{{
    "action": "SEARCH หรือ DROP",
    "search_query": "กลุ่มคำ",
    "locations": ["จังหวัด"],
    "core_keywords": ["คำเดี่ยว", "คำราชการ"],
    "target_year": "2569",
    "topic_summary": "สรุปสั้นๆ"
}}"""
    res_data = call_openrouter(prompt, "Output strictly in JSON format.")
    
    action = str(res_data.get("action", "SEARCH")).upper()
    raw_query = res_data.get("search_query", text_chunk[:50])
    if isinstance(raw_query, list): raw_query = " ".join([str(q) for q in raw_query])
    clean_query = re.sub(r'(?i)(facebook|fb|twitter|x|tiktok|youtube|ข่าวล่าสุด|รัฐบาลไทย|\||\.\.\.)', '', str(raw_query)).strip()
    
    locations = res_data.get("locations", [])
    if isinstance(locations, str): locations = [locations]
    core_keywords = res_data.get("core_keywords", [])
    if isinstance(core_keywords, str): core_keywords = [core_keywords]
        
    target_year = str(res_data.get("target_year", current_year_th)).strip()
    topic_summary = str(res_data.get("topic_summary", "ประเมินเนื้อหา")).strip()
    
    if action == "DROP": return "DROP", "", topic_summary, [], [], ""
    return "SEARCH", clean_query, topic_summary, locations, core_keywords, target_year

def analyze_news_with_qwen(news_text: str, references: list, current_date: str) -> dict:
    clean_claim = sanitize_for_api(news_text[:1500])
    ref_text = "\n\n".join([f"[อ้างอิง {i+1}]: {r['title']}\nเนื้อหา: {r.get('snippet', '')}" for i, r in enumerate(references)])
    
    prompt = f"""[ต้นฉบับ]: "{clean_claim}"

[แหล่งอ้างอิง 1 ถึง {len(references)}]:
{ref_text}

คำสั่ง: ประเมินว่า 'แหล่งข้อมูลอ้างอิงแต่ละแหล่ง' ระบุข้อมูลที่มีทิศทาง support หรือ contradict กับต้นฉบับ หากไม่เกี่ยวให้ตอบ neutral
⚠️ เพื่อความเร็ว ห้ามเขียนเหตุผล (reason) เด็ดขาด ให้ตอบแค่ ref_id และ stance

ตัวอย่าง JSON ที่ถูกต้อง:
{{
    "verdict_summary": "พบว่าข้อความดังกล่าวเป็นความจริง [1], [2]",
    "evidence_assessments": [
        {{"ref_id": 1, "stance": "support"}},
        {{"ref_id": 2, "stance": "contradict"}},
        {{"ref_id": 3, "stance": "neutral"}}
    ]
}}

ตอบ JSON ของคุณด้านล่างนี้:"""
    
    result = call_openrouter(prompt, "You are a precise JSON bot. No markdown, no explanations, strictly valid JSON.")
    if not result or "evidence_assessments" not in result:
        return {"verdict_summary": "ระบบไม่สามารถสรุปข้อมูลได้", "evidence_assessments": []}
    return result

def critic_review_analysis(news_text: str, references: list, initial_analysis: dict) -> dict:
    return initial_analysis