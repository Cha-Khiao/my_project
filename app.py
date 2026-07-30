import streamlit as st
import re
import datetime
import time
import os
import threading 
from dotenv import load_dotenv
import requests 

load_dotenv()

from scraper import extract_text_from_url
from search import search_news_references
from llm import analyze_intent_and_plan_search, analyze_news_with_qwen, critic_review_analysis

# ================= 1. ตั้งค่า Cache =================
def cached_extract_text(url): 
    return extract_text_from_url(url)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_plan_search(text): 
    return analyze_intent_and_plan_search(text)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(query): 
    return search_news_references(query, num_results=5)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_analyze(news_text, references, current_date): 
    return analyze_news_with_qwen(news_text, references, current_date)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_critic(news_text, references, initial_analysis):
    return critic_review_analysis(news_text, references, initial_analysis)

# 💡 ฟังก์ชัน Progress Bar แอนิเมชันลื่นไหล (ไม่ใช้ Text ซ้ำซ้อน)
def smooth_progress(progress_bar, start_val, end_val, text_label, delay=0.01):
    for i in range(start_val, end_val + 1):
        progress_bar.progress(i, text=text_label)
        time.sleep(delay)

# ================= 2. ตั้งค่าหน้าจอ & CSS =================
st.set_page_config(page_title="AI Fact-Checker", page_icon="🛡️", layout="centered")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
    h1, h2, h3, h4, h5, h6, p, a, button, input, textarea, label, li { font-family: 'Prompt', sans-serif !important; }
    footer {visibility: hidden;} 
    .stAlert {border-radius: 12px;}
    .stButton>button { border-radius: 8px !important; font-weight: 500 !important; padding: 0.5rem 2rem !important; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2563eb !important; color: #ffffff !important; border: none !important; }
    div[data-testid="stButton"] button[kind="primary"]:hover { background-color: #1e40af !important; opacity: 1 !important; }
    .stMarkdown a { word-wrap: break-word; color: #1e40af !important; text-decoration: underline !important; font-weight: 500 !important; }
    div[data-testid="stButton"] button[kind="secondary"] { position: fixed !important; bottom: 15px !important; left: 15px !important; opacity: 0.0 !important; transition: all 0.3s ease-in-out !important; z-index: 99999 !important; width: 45px !important; height: 45px !important; border-radius: 50% !important; padding: 0 !important; }
    div[data-testid="stButton"] button[kind="secondary"]:hover { opacity: 1.0 !important; background-color: #ffffff !important; box-shadow: 0 4px 10px rgba(0,0,0,0.15) !important; }
    </style>
""", unsafe_allow_html=True)

# ================= 3. ฟังก์ชันจัดการคะแนน =================
def get_score_ui_config(level):
    if str(level).strip().upper() in ["N/A", "ERROR", "NONE", ""]:
        return "N/A", "#94a3b8", "rgba(148, 163, 184, 0.1)", "rgba(148, 163, 184, 0.4)", "ไม่สามารถประเมินได้"
        
    try: level = int(level)
    except: return "N/A", "#94a3b8", "rgba(148, 163, 184, 0.1)", "rgba(148, 163, 184, 0.4)", "ไม่สามารถประเมินได้"
        
    if level == 5: return "95%", "#10b981", "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.4)", "มีความน่าเชื่อถือสูง"
    elif level == 4: return "75%", "#10b981", "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.4)", "น่าเชื่อถือส่วนใหญ่"
    elif level == 3: return "50%", "#f59e0b", "rgba(245, 158, 11, 0.1)", "rgba(245, 158, 11, 0.4)", "ข้อมูลก้ำกึ่ง / ไม่ชัดเจน"
    elif level == 2: return "25%", "#ef4444", "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.4)", "มีความเสี่ยงเป็นข่าวบิดเบือน"
    elif level == 1: return "10%", "#ef4444", "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.4)", "ข่าวปลอม / หลอกลวง"
    return "N/A", "#94a3b8", "rgba(148, 163, 184, 0.1)", "rgba(148, 163, 184, 0.4)", "ไม่สามารถประเมินได้"

def save_system_log(input_type, input_data, search_query, references, ai_result_dict, process_time):
    webhook_url = os.getenv("GSHEETS_WEBHOOK_URL", "")
    if "GSHEETS_WEBHOOK_URL" in st.secrets: webhook_url = st.secrets.get("GSHEETS_WEBHOOK_URL", webhook_url)
    if not webhook_url: return 
    
    level = str(ai_result_dict.get("score", "N/A"))
    pct_map = {"5": "95%", "4": "75%", "3": "50%", "2": "25%", "1": "10%"}
    score_log = f"ระดับ {level} ({pct_map.get(level, 'N/A')})" if level in pct_map else "N/A"
        
    short_input = input_data[:200].replace('\n', ' ') + "..." if len(input_data) > 200 else input_data.replace('\n', ' ')
    ref_details = " | ".join([f"{idx+1}. {r['title']} ({r['href']})" for idx, r in enumerate(references)]) if references else "ไม่พบอ้างอิงสืบค้น"
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "timestamp": current_time, "input_type": input_type, "short_input": short_input,
        "search_query": search_query, "ref_count": len(references), "ref_details": ref_details,
        "score": score_log, "process_time": round(process_time, 2)
    }
    threading.Thread(target=lambda: requests.post(webhook_url, json=payload, timeout=10, allow_redirects=True) if webhook_url else None, daemon=True).start()

# ================= 4. ส่วนแสดงผล UI =================
st.markdown("""<div style='text-align: center;'><h1 style='font-size: 2.5rem; margin-bottom: 0px;'>🛡️ AI Fact-Checker</h1><p style='font-size: 1.1rem; opacity: 0.8; margin-top: 5px;'>ระบบประเมินความน่าเชื่อถือของข่าว โดยใช้ปัญญาประดิษฐ์</p></div>""", unsafe_allow_html=True)
st.write("") 

tab1, tab2 = st.tabs(["🌐 ตรวจสอบจากลิงก์ (URL)", "📄 ตรวจสอบจากข้อความ"])

news_content, original_url, url_input, input_method_used = "", "", "", ""
VIDEO_PATTERNS = [r'youtube\.com/watch', r'youtu\.be', r'youtube\.com/shorts', r'tiktok\.com', r'vt\.tiktok\.com', r'vm\.tiktok\.com', r'fb\.watch', r'facebook\.com/.*/videos/', r'/share/v/', r'/share/r/', r'vimeo\.com', r'dailymotion\.com']

with tab1:
    st.write("")
    url_input = st.text_input("🔗 วางลิงก์ข่าว หรือ โพสต์จากโซเชียลมีเดีย:", placeholder="ตัวอย่าง: https://www.facebook.com/...")
    st.write("") 
    col_l, col_btn, col_r = st.columns([1, 1, 1])
    with col_btn: btn_url = st.button("🔍 เริ่มการประเมิน", key="btn_url", type="primary")
        
    if btn_url:
        if url_input:
            input_method_used = "URL Link"
            url_match = re.search(r'(https?://[a-zA-Z0-9./?=_%&+\-#]+)', url_input)
            clean_url = url_match.group(1).rstrip('.,;!?)\'"]') if url_match else url_input.strip()
            if any(re.search(p, clean_url.lower()) for p in VIDEO_PATTERNS):
                news_content = "VIDEO_DETECTED"
                original_url = clean_url
            else:
                with st.spinner("⏳ กำลังเชื่อมต่อและสกัดเนื้อหาจากเว็บไซต์ปลายทาง..."):
                    extracted_data = cached_extract_text(clean_url)
                    if isinstance(extracted_data, dict):
                        news_content = extracted_data.get("error", extracted_data.get("content", ""))
                        original_url = extracted_data.get("actual_url", clean_url)
                    else: news_content = str(extracted_data)
                    if not news_content or str(news_content).strip() == "": news_content = "EMPTY_CONTENT"
        else: st.warning("⚠️ กรุณาระบุ URL ก่อนทำการวิเคราะห์")

with tab2:
    st.write("") 
    text_input = st.text_area("📄 วางข้อความ ข่าวลือ หรือเนื้อหาที่ต้องการตรวจสอบ:", height=150, placeholder="วางเนื้อหาที่น่าสงสัยที่นี่...")
    st.write("") 
    col_l2, col_btn2, col_r2 = st.columns([1, 1, 1])
    with col_btn2: btn_text = st.button("🔍 เริ่มการประเมิน", key="btn_text", type="primary")
        
    if btn_text:
        if text_input.strip():
            input_method_used = "Direct Text"
            news_content = text_input
        else: st.warning("⚠️ กรุณาระบุเนื้อหาก่อนทำการวิเคราะห์")

# ================= 6. ส่วนประมวลผลหลัก =================
if news_content:
    st.divider()
    start_process_time = time.time()
    
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    now = datetime.datetime.now()
    current_date_str = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
    
    references = []
    result_dict = {
        "content_summary": "N/A", "timeline_analysis": "N/A", "relevance_analysis": "N/A",
        "score": "N/A", "reason": "N/A", "relevant_ref_ids": []
    }
    search_query = "SKIP_SEARCH"
    total_time_taken = 0.0
    
    progress_bar = st.progress(0, text="กำลังเตรียมการวิเคราะห์ (0%)")
    smooth_progress(progress_bar, 0, 5, "กำลังเริ่มต้นกระบวนการตรวจสอบ (5%)")
    
    with st.container(border=True):
        st.markdown("### ⚙️ กระบวนการทำงาน")
        
        if news_content == "VIDEO_DETECTED":
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%) (ใช้เวลาตรวจสอบ {total_time_taken} วินาที)", delay=0.005)
            st.markdown("🛡️ **ตรวจพบวิดีโอคลิป**\n\nระบบยังไม่รองรับการถอดเสียงอัตโนมัติ กรุณาคัดลอกข้อความมาวางแทน")
            result_dict.update({"content_summary": "พบวิดีโอคลิป", "reason": "ระบบยังไม่รองรับการถอดเสียงจากวิดีโอ"})
            
        elif news_content == "GAMBLING_DETECTED":
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%) (ใช้เวลาตรวจสอบ {total_time_taken} วินาที)", delay=0.005)
            st.markdown("🚫 **ระงับการเชื่อมต่อ**\n\nตรวจพบความเสี่ยงจากลิงก์อันตราย (เว็บไซต์หลอกลวง/พนัน)")
            result_dict.update({"score": 1, "content_summary": "เว็บไซต์หลอกลวง", "reason": "เนื้อหามีความเสี่ยงต่อความปลอดภัยของผู้ใช้งาน"})
            
        elif "ทะลวงระบบ" in news_content or "Error:" in news_content or "SOCIAL_BLOCKED" in news_content:
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%) (ใช้เวลาตรวจสอบ {total_time_taken} วินาที)", delay=0.005)
            st.markdown("⚠️ **ต้นทางปฏิเสธการเข้าถึง**\n\nเว็บไซต์หรือโพสต์ถูกตั้งเป็นส่วนตัว กรุณานำข้อความมาวางตรวจสอบโดยตรง")
            result_dict.update({"content_summary": "ข้อมูลถูกบล็อก", "reason": "ไม่สามารถดึงข้อมูลได้"})
            
        elif news_content in ["LINK_UNSUPPORTED", "EMPTY_CONTENT"] or "ไม่สามารถดึงข้อมูล" in news_content or re.search(r'(Error 404|404 Not Found|Page Not Found)', news_content, re.IGNORECASE):
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%) (ใช้เวลาตรวจสอบ {total_time_taken} วินาที)", delay=0.005)
            st.markdown("⚠️ **ไม่พบเนื้อหา**\n\nลิงก์ดังกล่าวไม่มีข้อความข่าวสารที่สามารถตรวจสอบได้")
            result_dict.update({"content_summary": "ไม่มีเนื้อหา", "reason": "กรุณาตรวจสอบลิงก์อีกครั้ง"})
            
        else:
            smooth_progress(progress_bar, 5, 25, "🧠 AI กำลังอ่านและวิเคราะห์ประเด็น (25%)")
            
            text_for_keyword = news_content.split("]:\n")[-1] if "[เนื้อหาข่าวจริง" in news_content else news_content
            action, payload, topic_summary = cached_plan_search(text_for_keyword)

            if action == "DROP":
                total_time_taken = round(time.time() - start_process_time, 2)
                smooth_progress(progress_bar, 25, 100, f"ประเมินเสร็จสมบูรณ์ (100%) (ใช้เวลาตรวจสอบ {total_time_taken} วินาที)", delay=0.005)
                st.markdown(f"⏭️ **ยุติการตรวจสอบ:** {payload}")
                search_query = "SKIP_SEARCH"
                result_dict.update({"content_summary": "เนื้อหาทั่วไป/เรื่องส่วนตัว", "reason": payload})
            else:
                st.markdown(f"📌 **ประเด็นที่ตรวจสอบ:** *{topic_summary}*")
                smooth_progress(progress_bar, 25, 45, "🌐 กำลังค้นหาข้อมูลจากแหล่งข่าวที่เชื่อถือได้ (45%)")
                
                references = []
                search_queries_used = []
                
                for q in payload[:2]: 
                    search_queries_used.append(q)
                    refs = cached_search(q)
                    references.extend(refs)
                
                search_query = " | ".join(search_queries_used)
                
                unique_refs = []
                seen_urls = set()
                for r in references:
                    if r['href'] not in seen_urls:
                        seen_urls.add(r['href'])
                        unique_refs.append(r)
                references = unique_refs[:8]
                
                st.markdown(f"🔎 **ค้นพบแหล่งข้อมูลอ้างอิงเบื้องต้นจำนวน {len(references)} แหล่ง**")
                
                smooth_progress(progress_bar, 45, 75, "⚖️ AI กำลังประมวลผลข้อเท็จจริง (75%)")
                st.markdown("⚖️ **กำลังประมวลผลข้อเท็จจริงและให้คะแนน...**")
                
                ai_dict = cached_analyze(news_content, references, current_date_str)
                
                if ai_dict:
                    smooth_progress(progress_bar, 75, 95, "🕵️‍♂️ AI ตรวจทานตรรกะซ้ำเพื่อความแม่นยำ (95%)")
                    st.markdown("🕵️‍♂️ **ทบทวนความถูกต้องขั้นสุดท้าย (Cross-Validation)...**")
                    
                    final_dict = cached_critic(news_content, references, ai_dict)
                    if final_dict:
                        result_dict = final_dict
                        
                        # 💡 2. เปลี่ยนหลอดเป็น 100% และแสดงข้อความเป๊ะๆ ตอนจบ
                        total_time_taken = round(time.time() - start_process_time, 2)
                        progress_bar.progress(100, text=f"ประเมินเสร็จสมบูรณ์ (100%) (ใช้เวลาตรวจสอบ {total_time_taken} วินาที)")
                        st.markdown("✨ **ประเมินผลสำเร็จ!**")
    
    # ================= 7. การแสดงผลลัพธ์ (UI) =================
    pct, color, bg_color, border_color, label = get_score_ui_config(result_dict.get("score"))
    
    score_card_html = f"""
    <div style="text-align: center; padding: 25px; background-color: {bg_color}; border-radius: 16px; margin-bottom: 25px; border: 2px solid {border_color}; margin-top: 20px;">
        <p style="margin: 0; font-size: 1.1rem; font-weight: 500; opacity: 0.8;">ความน่าเชื่อถือประเมินโดย AI</p>
        <h1 style="margin: 10px 0; font-size: 5.5rem; color: {color}; font-weight: 700; line-height: 1;">{pct}</h1>
        <span style="background-color: {color}; color: white; padding: 6px 20px; border-radius: 20px; font-weight: 500; font-size: 1.05rem; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">{label}</span>
    </div>
    """
    st.markdown(score_card_html, unsafe_allow_html=True)

    with st.container(border=True):
        st.subheader("🎯 ประเด็นหลักของเนื้อหา")
        st.markdown(f"**📌 สรุปเหตุการณ์:**\n{result_dict.get('content_summary', 'ไม่มีข้อมูล')}")
        st.markdown(f"**⏱️ ไทม์ไลน์ของเหตุการณ์:**\n{result_dict.get('timeline_analysis', 'ไม่มีข้อมูล')}")
        st.markdown(f"**📰 ข้อมูลเปรียบเทียบจากสื่อหลัก:**\n{result_dict.get('relevance_analysis', 'ไม่มีข้อมูล')}")
        
    with st.container(border=True):
        st.subheader("💡 กระบวนการคิดและบทสรุปจาก AI")
        # 💡 โชว์การถอดรหัส 5W1H และการเทียบกับอ้างอิง
        st.markdown(f"**🧠 สกัดประเด็น (5W1H):**\n{result_dict.get('claim_5w1h', 'ไม่มีข้อมูล')}")
        st.markdown(f"**📰 ตรวจสอบเทียบกับอ้างอิง:**\n{result_dict.get('cross_checking', 'ไม่มีข้อมูล')}")
        st.markdown(f"**⚖️ สรุปฟันธง:**\n{result_dict.get('reason', 'ไม่มีคำอธิบายเพิ่มเติม')}")

    rel_ids = result_dict.get("relevant_ref_ids", [])
    valid_refs = []
    
    if isinstance(rel_ids, list):
        for idx in rel_ids:
            try:
                idx_int = int(idx)
                if 1 <= idx_int <= len(references):
                    valid_refs.append(references[idx_int - 1])
            except (ValueError, TypeError):
                continue

    if valid_refs:
        with st.container(border=True):
            st.subheader("🔗 แหล่งข่าวที่เกี่ยวข้อง (สำหรับอ่านเพิ่มเติม)")
            for idx, ref in enumerate(valid_refs):
                st.markdown(f"{idx+1}. [{ref.get('title', 'ลิงก์อ้างอิง')}]({ref.get('href', '#')})")
    else:
        with st.container(border=True):
            st.subheader("🔗 แหล่งข่าวที่เกี่ยวข้อง (สำหรับอ่านเพิ่มเติม)")
            st.info("ไม่พบข่าวสารจากสื่อหลักที่มีเนื้อหาตรงกัน หรือไม่มีแหล่งอ้างอิงที่สอดคล้องเพียงพอ")
            
    try:
        log_input_data = original_url if original_url else news_content
        save_system_log(input_method_used, log_input_data, search_query, references, result_dict, total_time_taken)
    except Exception: 
        pass

# ================= 8. ปุ่มเคลียร์แคช =================
if st.button("⚙️", key="clear_cache_btn", type="secondary"): 
    st.cache_data.clear()