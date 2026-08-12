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
        "verdict_summary": "ไม่สามารถเปรียบเทียบข้อมูลได้",
        "supported_points": ["ไม่พบข้อมูลที่สอดคล้องกับแหล่งอ้างอิง"],
        "conflicting_points": ["ไม่พบข้อมูลที่ขัดแย้ง หรือแหล่งอ้างอิงไม่เพียงพอต่อการเปรียบเทียบ"],
        "comparative_analysis": "ระบบไม่สามารถวิเคราะห์เปรียบเทียบเชิงลึกได้อย่างสมบูรณ์",
        "score": 3,
        "relevant_ref_ids": []
    }
    
    if not isinstance(parsed_dict, dict) or not parsed_dict:
        if raw_output:
            template["comparative_analysis"] = f"❌ โครงสร้างข้อมูลผิดพลาด\n\n[Raw Data]:\n{raw_output[:500]}"
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
# ⚡ STEP 1: Search Planner (บังคับสร้างคีย์เวิร์ดราชการ + แบนภาษาอื่น)
# =========================================================
def analyze_intent_and_plan_search(news_text: str) -> tuple:
    text_for_analysis = news_text
    if "]:\n" in news_text: 
        text_for_analysis = news_text.split("]:\n")[-1] 
        
    text_chunk = sanitize_for_api(text_for_analysis[:1500])
    tz = pytz.timezone('Asia/Bangkok')
    current_year_th = datetime.now(tz).year + 543
    
    prompt = f"""ข้อความที่ต้องการตรวจสอบ: 
"{text_chunk}"

หน้าที่: สกัด "ข้อมูลสำหรับค้นหา" (Optimized for Search Engine)
กฎ:
1. `search_query`: สร้างกลุ่มคำสั้นๆ สำหรับสืบค้น (ห้ามแต่งเป็นประโยคยาว ห้ามใส่เลขปี)
2. `locations`: สกัด "สถานที่" (ชื่อจังหวัด, อำเภอ) 
3. `core_keywords`: ⚠️ สำคัญมาก! ให้ดึงแก่นเรื่อง และ **"แปลเป็นคำพ้องความหมายที่เป็นภาษาราชการ/ทางการ"** แนบมาด้วยเสมอ (เช่น ถ้าเจอคำว่า "สายไฟลงดิน" ให้ใส่ "สายไฟฟ้าใต้ดิน" หรือ "ระบบจำหน่ายไฟฟ้า" มาด้วย, ถ้าเจอ "แจกเงิน" ให้ใส่ "มาตรการกระตุ้นเศรษฐกิจ") รวม 3-5 คำ เพื่อให้ระบบหาเว็บหน่วยงานรัฐ (go.th) เจอ!
4. `target_year`: สกัด "ปี พ.ศ." (ตัวเลข 4 หลัก) ถ้าไม่มีให้ใช้ '{current_year_th}'
5. หากข้อความไม่มีเนื้อหาสาระ ให้ action = "DROP"

⚠️ คำเตือนขั้นเด็ดขาด: ห้ามสร้างข้อความภาษาจีน (Chinese) หรือภาษาอื่นที่ไม่ใช่ภาษาไทยเด็ดขาด! ตอบกลับเป็นภาษาไทยและอังกฤษตามความจำเป็นเท่านั้น!

ตอบกลับเป็น JSON รูปแบบนี้เท่านั้น:
{{
    "action": "SEARCH หรือ DROP",
    "search_query": "กลุ่มคำสั้นๆ",
    "locations": ["จังหวัด"],
    "core_keywords": ["คำพูดทั่วไป", "คำศัพท์ราชการ/ทางการ"],
    "target_year": "2569",
    "topic_summary": "สรุปประเด็นหลัก 1 ประโยค"
}}"""
    res_data = call_openrouter(prompt, "Extract SEO keywords including formal official synonyms for gov sites. STRICTLY THAI LANGUAGE ONLY. NO CHINESE ALLOWED. Output strictly in JSON format.")
    
    action = str(res_data.get("action", "SEARCH")).upper()
    
    raw_query = res_data.get("search_query", text_chunk[:80])
    if isinstance(raw_query, list):
        raw_query = " ".join([str(q) for q in raw_query])
    raw_query = str(raw_query)
    
    clean_query = re.sub(r'(?i)(facebook|fb|twitter|x|tiktok|youtube|ข่าวล่าสุด|รัฐบาลไทย|\||\.\.\.)', '', raw_query).strip()
    
    locations = res_data.get("locations", [])
    if isinstance(locations, str): locations = [locations]
    
    core_keywords = res_data.get("core_keywords", [])
    if isinstance(core_keywords, str): core_keywords = [core_keywords]
        
    target_year = str(res_data.get("target_year", current_year_th)).strip()
    topic_summary = str(res_data.get("topic_summary", "เปรียบเทียบและวิเคราะห์เนื้อหา")).strip()
    
    if action == "DROP": return "DROP", "", res_data.get("reason", "ไม่ใช่เนื้อหาที่สามารถเปรียบเทียบได้"), [], [], ""
    return "SEARCH", clean_query, topic_summary, locations, core_keywords, target_year

# =========================================================
# ⚖️ STEP 2: The Analyzer (กฎเหล็กแบนภาษาจีน)
# =========================================================
def analyze_news_with_qwen(news_text: str, references: list, current_date: str, source_url: str = "") -> dict:
    clean_claim = sanitize_for_api(news_text[:2000])
    ref_text = "\n\n".join([f"[อ้างอิง {i+1}]: {r['title']} | วันที่: {r.get('pub_date', 'ไม่ระบุ')}\nเนื้อหา: {r.get('snippet', '')}" for i, r in enumerate(references)]) if references else "ไม่มีอ้างอิง"
    
    is_official_source = bool(source_url and (".go.th" in source_url.lower() or ".gov" in source_url.lower() or 'antifakenewscenter.com' in source_url.lower()))
    origin_info = f"ดึงมาจากเว็บไซต์ทางการ (Official Source): {source_url}" if is_official_source else "ข้อความทั่วไป / โซเชียลมีเดีย"
    current_time_context = get_current_thai_time()

    prompt = f"""คุณคือ AI ผู้เชี่ยวชาญด้านการวิเคราะห์และเปรียบเทียบเนื้อหาข่าว (Comparative Analyst)

เวลาปัจจุบัน: {current_time_context}
[ข้อความต้นฉบับ]: "{clean_claim}"
[แหล่งที่มา]: {origin_info}

[แหล่งข้อมูลอ้างอิงที่ระบบคัดกรองมาให้]:
{ref_text}

กระบวนการเปรียบเทียบเนื้อหา:
1. ⚖️ เปรียบเทียบความสอดคล้อง: หากต้นฉบับพูดกว้างๆ แต่อ้างอิงระบุรายละเอียดราชการลึกกว่า ให้ถือว่า "สอดคล้องกัน" ห้ามมองว่าขัดแย้ง!
2. 📌 relevant_ref_ids: ให้ดึงรหัสของแหล่งอ้างอิงที่รายงานเรื่องเดียวกันกับข้อความต้นฉบับ มาแสดงเพื่อเป็นหลักฐานอ้างอิง
3. 🏛️ น้ำหนักข้อมูล: หากแหล่งที่มาคือ เว็บรัฐบาล (Official Source) ให้ประเมินว่ามีความน่าเชื่อถือสูงสุด

⚠️ คำเตือนขั้นเด็ดขาด: ห้ามสร้างข้อความ หรือ Thought process เป็นภาษาจีน (Chinese) หรือภาษาอื่นที่ไม่ใช่ภาษาไทยเด็ดขาด! ตอบกลับเป็นภาษาไทยเท่านั้น!

เกณฑ์คะแนน (ความสอดคล้อง): 
5=เนื้อหาสอดคล้อง 100%, 4=สอดคล้องส่วนใหญ่, 3=ก้ำกึ่ง, 2=พบการบิดเบือนข้อมูลจากสื่อหลัก, 1=ขัดแย้งอย่างสิ้นเชิง หรือไม่มีแหล่งอ้างอิงสอดคล้องเลย

ตอบกลับเป็น JSON รูปแบบนี้เท่านั้น:
{{
    "thought": "คิดวิเคราะห์เป็นภาษาไทยเท่านั้น ห้ามใช้ภาษาจีน",
    "verdict_summary": "สรุปผลการเปรียบเทียบ 1 ประโยค",
    "supported_points": ["ประเด็นที่สอดคล้องกับแหล่งอ้างอิง"],
    "conflicting_points": ["ประเด็นที่ขัดแย้งอย่างชัดเจน (หากไม่มี ให้เว้นว่าง)"],
    "comparative_analysis": "อธิบายผลการเปรียบเทียบอย่างเป็นเหตุเป็นผล",
    "relevant_ref_ids": [ระบุรหัสอ้างอิงของข่าวที่เกี่ยวข้องจริงๆ],
    "score": ตัวเลข 1-5
}}"""
    
    final_result = call_openrouter(prompt, "You are a Comparative Analyst. STRICTLY THAI LANGUAGE ONLY. DO NOT OUTPUT CHINESE CHARACTERS. Output strictly in JSON format in THAI.")
    if not final_result:
        return validate_ai_response({"comparative_analysis": "❌ ข้อผิดพลาด: AI ไม่สามารถประมวลผลการเปรียบเทียบได้"})
        
    return validate_ai_response(final_result)

def critic_review_analysis(news_text: str, references: list, initial_analysis: dict) -> dict:
    return validate_ai_response(initial_analysis)