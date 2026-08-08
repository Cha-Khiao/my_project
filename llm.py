import requests
import json
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv
import pytz

load_dotenv()

HOST_URL = "https://openrouter.ai"
API_URL = HOST_URL + "/api/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "qwen/qwen3-8b").strip()

try:
    import streamlit as st
    if "OPENROUTER_API_KEY" in st.secrets: OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"].strip()
    if "AI_MODEL" in st.secrets: AI_MODEL = st.secrets["AI_MODEL"].strip()
except Exception: pass

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

def validate_ai_response(parsed_dict: dict, raw_output: str = "") -> dict:
    template = {
        "verdict_summary": "ไม่สามารถสรุปคำตัดสินได้",
        "facts": ["ไม่พบข้อมูลส่วนที่เป็นความจริง"],
        "distortions": ["ไม่พบข้อมูลส่วนที่บิดเบือน หรือข้อมูลไม่เพียงพอ"],
        "ai_insights": "ระบบไม่สามารถวิเคราะห์เชิงลึกได้อย่างสมบูรณ์",
        "score": 3,
        "relevant_ref_ids": []
    }
    
    if not isinstance(parsed_dict, dict) or not parsed_dict:
        if raw_output:
            template["ai_insights"] = f"❌ โครงสร้างข้อมูลผิดพลาด\n\n[Raw Data]:\n{raw_output[:500]}"
        return template
        
    for key in template.keys():
        if key not in parsed_dict or parsed_dict[key] in [None, ""]: parsed_dict[key] = template[key]
            
    try:
        score_str = str(parsed_dict["score"])
        numbers = re.findall(r'\d+', score_str)
        parsed_dict["score"] = max(1, min(5, int(numbers[0]))) if numbers else 3
    except: parsed_dict["score"] = 3
        
    try:
        rel_val = parsed_dict.get("relevant_ref_ids", "")
        if isinstance(rel_val, list):
            parsed_dict["relevant_ref_ids"] = [int(x) for x in rel_val if str(x).isdigit() and int(x) != 0]
        else:
            numbers = re.findall(r'\d+', str(rel_val))
            parsed_dict["relevant_ref_ids"] = [int(n) for n in numbers if int(n) != 0]
    except: parsed_dict["relevant_ref_ids"] = []
        
    return parsed_dict

def call_openrouter(prompt: str, system_msg: str) -> dict:
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": AI_MODEL, "messages": [{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}], "temperature": 0.0}
    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=45)
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content']
        return parse_json_safely(content)
    except Exception as e:
        print(f"API Error: {e}")
        return {}

# =========================================================
# ⚡ STEP 1: Search Planner (ระบบค้นหาแบบ Advanced Google Operators)
# =========================================================
def analyze_intent_and_plan_search(news_text: str) -> tuple:
    text_for_analysis = news_text
    if "]:\n" in news_text: 
        text_for_analysis = news_text.split("]:\n")[-1] 
        
    text_chunk = sanitize_for_api(text_for_analysis[:1500])
    current_time_context = get_current_thai_time()
    
    prompt = f"""ข้อความที่ดึงมาจากเว็บไซต์: 
"{text_chunk}"

หน้าที่: สกัด "คำค้นหาขั้นสูง (Advanced Google Query)" เพื่อบังคับให้ Google หาเฉพาะข่าวที่เกี่ยวข้องกันเป๊ะๆ
กฎเหล็กขั้นเด็ดขาด:
1. `search_query`: ⚠️ บังคับให้ใช้เครื่องหมายฟันหนู (Double Quotes) `""` คร่อมคำนาม/สถานที่/เหตุการณ์ที่สำคัญ เพื่อสั่งให้ Google ทำการ Exact Match (เช่น `"พลพีร์" "สายไฟลงดิน" "สุรินทร์"` หรือ `"มท.2" "จัดระเบียบสายไฟ" "สุรินทร์"`) ห้ามแต่งเป็นประโยคยาวๆ ที่ไม่มีฟันหนูเด็ดขาด!
2. `must_have_keywords`: สกัดชื่อสถานที่หรือบุคคล 1-2 คำ (เช่น ["สุรินทร์", "สายไฟ"]) เพื่อใช้เป็นตาข่ายชั้นที่ 2
3. หากข้อความเป็นเรื่องทักทาย ให้ action = "DROP"

ตอบกลับเป็น JSON รูปแบบนี้เท่านั้น:
{{
    "action": "SEARCH หรือ DROP",
    "search_query": "คีย์เวิร์ดที่ถูกคร่อมด้วยฟันหนู (Advanced Search)",
    "must_have_keywords": ["คำบังคับที่1", "คำบังคับที่2"],
    "topic_summary": "สรุปประเด็นหลัก 1 ประโยค"
}}"""
    res_data = call_openrouter(prompt, "You MUST use Double Quotes (\"\") around core entities to force Exact Match on Google. Output strictly in JSON format in THAI.")
    
    action = res_data.get("action", "SEARCH").upper()
    
    raw_query = res_data.get("search_query", text_chunk[:80])
    # คลีนคำขยะแต่รักษาฟันหนูไว้
    clean_query = re.sub(r'(ข่าว|ล่าสุด|รัฐบาลไทย|\||\.\.\.)', '', raw_query).strip()
    must_have_keywords = res_data.get("must_have_keywords", [])
    topic_summary = res_data.get("topic_summary", "ตรวจสอบข้อเท็จจริง")
    
    if action == "DROP": return "DROP", "", res_data.get("reason", "ไม่ใช่ข่าวสาร"), []
    return "SEARCH", clean_query, topic_summary, must_have_keywords

# =========================================================
# ⚖️ STEP 2: The Analyzer
# =========================================================
def analyze_news_with_qwen(news_text: str, references: list, current_date: str, source_url: str = "") -> dict:
    clean_claim = sanitize_for_api(news_text[:2000])
    ref_text = "\n\n".join([f"[อ้างอิง {i+1}]: {r['title']}\nเนื้อหา: {r.get('snippet', '')}" for i, r in enumerate(references)]) if references else "ไม่มีอ้างอิง"
    
    is_official_source = bool(source_url and (".go.th" in source_url.lower() or ".gov" in source_url.lower()))
    origin_info = f"ดึงมาจากเว็บไซต์ทางการ (Official Source): {source_url}" if is_official_source else "ข้อความทั่วไป / โซเชียลมีเดีย"
    current_time_context = get_current_thai_time()

    if not references and not is_official_source:
        return validate_ai_response({"verdict_summary": "ไม่มีแหล่งข่าวใดนำเสนอเรื่องนี้", "score": 1, "ai_insights": "ระบบไม่พบข้อมูลในสารบบสื่อหลัก คาดว่าเป็นข่าวลือที่แต่งขึ้นมาเอง"})

    prompt = f"""คุณคือนักตรวจสอบข้อเท็จจริง (Fact-Checker)
เวลาปัจจุบัน: {current_time_context}
ข้อความที่ต้องการตรวจสอบ: "{clean_claim}"
แหล่งที่มาของข้อความนี้: {origin_info}

หลักฐานที่ค้นพบจาก Search Engine:
{ref_text}

ขั้นตอนการวิเคราะห์:
1. หากลิงก์ต้นทางเป็นเว็บไซต์รัฐบาล (.go.th) ให้ยึดเจตนาการประกาศของเว็บนั้นเป็นความจริงสูงสุด
2. พิจารณาที่ "แก่นเหตุการณ์ (Core Event)" หากแหล่งข่าวเจาะจงรายงานเหตุการณ์ตรงกัน ให้ถือเป็นความจริง 

เกณฑ์คะแนน: 5=จริง 100%, 4=จริงส่วนใหญ่, 3=ก้ำกึ่ง, 2=บิดเบือน, 1=ปลอม/ไร้หลักฐาน

ตอบกลับเป็น JSON รูปแบบนี้เท่านั้น:
{{
    "thought": "ตรวจสอบแหล่งข่าวว่ารายงานเหตุการณ์ตรงกับข้อความหรือไม่",
    "verdict_summary": "ฟันธงสั้นๆ 1 ประโยค",
    "facts": ["แก่นความจริงที่พบ"],
    "distortions": ["ข้อบิดเบือน (ถ้ามี)"],
    "ai_insights": "สรุปเหตุผลที่ให้คะแนน",
    "relevant_ref_ids": [เฉพาะรหัสอ้างอิงที่เป็น 'ข่าวเจาะจง' และเหตุการณ์ตรงกันเท่านั้น],
    "score": ตัวเลข 1-5
}}"""
    
    final_result = call_openrouter(prompt, "You are a logical Fact-Checker. Match CORE EVENTS and reject homepage/general links. Output strictly in JSON format in THAI.")
    if not final_result:
        return validate_ai_response({"ai_insights": "❌ ข้อผิดพลาด: AI ไม่สามารถประมวลผลได้"})
        
    return validate_ai_response(final_result)

def critic_review_analysis(news_text: str, references: list, initial_analysis: dict) -> dict:
    return validate_ai_response(initial_analysis)