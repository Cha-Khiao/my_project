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
def cached_extract_text(url): return extract_text_from_url(url)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_plan_search(text): return analyze_intent_and_plan_search(text)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(query, must_have_keywords, source_url=""): return search_news_references(query, num_results=10, must_have_keywords=must_have_keywords, source_url=source_url)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_analyze(news_text, references, current_date, source_url=""): return analyze_news_with_qwen(news_text, references, current_date, source_url)

def smooth_progress(progress_bar, start_val, end_val, text_label, delay=0.001):
    for i in range(start_val, end_val + 1):
        progress_bar.progress(i, text=text_label)
        if delay > 0: time.sleep(delay)

# ================= 2. ตั้งค่าหน้าจอ & CSS =================
st.set_page_config(page_title="AI Fact-Checker", page_icon="🛡️", layout="centered", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
    h1, h2, h3, h4, h5, h6, p, a, button, input, textarea, label, li { font-family: 'Prompt', sans-serif !important; }
    footer {visibility: hidden;} 
    .stAlert {border-radius: 12px;}
    .stButton>button { border-radius: 8px !important; font-weight: 500 !important; padding: 0.5rem 2rem !important; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #1e3a8a !important; color: #ffffff !important; border: none !important; transition: all 0.3s; }
    div[data-testid="stButton"] button[kind="primary"]:hover { background-color: #2563eb !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .stMarkdown a { word-wrap: break-word; color: #2563eb !important; text-decoration: none !important; font-weight: 500 !important; }
    .stMarkdown a:hover { text-decoration: underline !important; }
    </style>
""", unsafe_allow_html=True)

# ================= 3. แถบด้านข้าง (Sidebar) =================
with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: #1e3a8a;'>🛡️ AI Fact-Checker</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 0.9rem; opacity: 0.8;'>ระบบประเมินความน่าเชื่อถือของข่าว</p>", unsafe_allow_html=True)
    st.divider()
    
    st.markdown("### 🏛️ สถาปัตยกรรมระบบ")
    st.info("""
    **🚀 ประมวลผลแบบ Real-time (Stateless)**
    เพื่อประสิทธิภาพและความเร็วสูงสุดในการตรวจสอบ ระบบนี้ถูกออกแบบมาโดย **ไม่ใช้ฐานข้อมูล (No Database)** ข้อมูลที่ท่านตรวจสอบจะไม่ถูกบันทึกเป็นประวัติส่วนตัว เพื่อปกป้องความเป็นส่วนตัวขั้นสูงสุด
    """)
    
    with st.expander("ℹ️ มาตรฐานการประเมิน (IFCN)"):
        st.markdown("""
        ประยุกต์ใช้ตรรกะ **Truth-O-Meter**:
        *   **95%:** มีหลักฐานยืนยันชัดเจน
        *   **75%:** จริงส่วนใหญ่ อาจคลาดเคลื่อนเล็กน้อย
        *   **50%:** ก้ำกึ่ง ไม่มีหลักฐาน หรือข้อมูลขัดแย้ง
        *   **25%:** มีเค้าโครงจริง แต่บิดเบือนบริบท
        *   **10%:** ข่าวปลอม หรือข้อกล่าวอ้างที่ไร้หลักฐาน
        """)
        
    st.divider()
    st.markdown("### ⚙️ เครื่องมือช่วยเหลือ")
    if st.button("🗑️ ล้างข้อมูลระบบ (Clear Memory)", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ ล้างหน่วยความจำสำเร็จ!")

# ================= 4. ฟังก์ชันจัดการคะแนน =================
def get_score_ui_config(level):
    try: level = int(level)
    except: return "N/A", "#94a3b8", "rgba(148, 163, 184, 0.1)", "rgba(148, 163, 184, 0.4)", "ไม่สามารถประเมินได้"
        
    if level == 5: return "95%", "#10b981", "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.4)", "มีความน่าเชื่อถือสูง"
    elif level == 4: return "75%", "#10b981", "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.4)", "น่าเชื่อถือส่วนใหญ่"
    elif level == 3: return "50%", "#f59e0b", "rgba(245, 158, 11, 0.1)", "rgba(245, 158, 11, 0.4)", "ข้อมูลก้ำกึ่ง / ขัดแย้ง"
    elif level == 2: return "25%", "#ef4444", "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.4)", "บิดเบือนความจริง"
    elif level == 1: return "10%", "#ef4444", "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.4)", "ข่าวปลอม / ไร้หลักฐาน"
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

# ================= 5. ส่วนแสดงผล UI =================
st.markdown("""<div style='text-align: center; margin-bottom: 2rem;'>
    <h1 style='font-size: 2.5rem; margin-bottom: 0px; color: #1e3a8a;'>🛡️ AI Fact-Checker</h1>
    <p style='font-size: 1.1rem; opacity: 0.8; margin-top: 5px;'>ระบบประเมินความน่าเชื่อถือของข่าวสารด้วยปัญญาประดิษฐ์</p>
    </div>""", unsafe_allow_html=True)

st.write("")
st.info("""
**🏛️ มาตรฐานการประเมินและสถาปัตยกรรมระบบ (Methodology & Standards)**
ระบบนี้ทำงานโดยสกัดข้อเท็จจริงและให้คะแนนตามมาตรฐาน **IFCN (International Fact-Checking Network)** และเกณฑ์ **Truth-O-Meter**:
* **ความน่าเชื่อถือของแหล่งอ้างอิง:** ระบบถูกตั้งค่าให้อัลกอริทึมค้นหา (Deep Search) ให้ความสำคัญขั้นสูงสุดกับข้อมูลจาก **หน่วยงานรัฐบาล (โดเมน .go.th, .gov), องค์กรระหว่างประเทศ, และสถานทูต** ก่อนสำนักข่าวทั่วไป
* **กระบวนการทำงานแบบเป็นระบบ:** ทำการจำลองการค้นหาแบบมนุษย์ -> คัดกรองแหล่งอ้างอิง -> วิเคราะห์บริบท -> และตัดสินตามพยานหลักฐานเชิงประจักษ์
""")
st.write("") 

tab1, tab2 = st.tabs(["🌐 ตรวจสอบจากลิงก์ (URL)", "📄 ตรวจสอบจากข้อความ"])

news_content, original_url, url_input, input_method_used = "", "", "", ""
VIDEO_PATTERNS = [r'youtube\.com/watch', r'youtu\.be', r'youtube\.com/shorts', r'tiktok\.com', r'vt\.tiktok\.com', r'vm\.tiktok\.com', r'fb\.watch', r'facebook\.com/.*/videos/', r'/share/v/', r'/share/r/', r'vimeo\.com', r'dailymotion\.com']

with tab1:
    st.write("")
    url_input = st.text_input("🔗 วางลิงก์ข่าว หรือ โพสต์จากโซเชียลมีเดีย:", placeholder="ตัวอย่าง: https://www.facebook.com/...")
    st.write("") 
    col_l, col_btn, col_r = st.columns([1, 1, 1])
    with col_btn: btn_url = st.button("🔍 เริ่มการประเมิน", key="btn_url", type="primary", use_container_width=True)
        
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
    with col_btn2: btn_text = st.button("🔍 เริ่มการประเมิน", key="btn_text", type="primary", use_container_width=True)
        
    if btn_text:
        if text_input.strip():
            input_method_used = "Direct Text"
            news_content = text_input
        else: st.warning("⚠️ กรุณาระบุเนื้อหาก่อนทำการวิเคราะห์")

# ================= 6. ส่วนประมวลผลหลัก =================
if news_content:
    if not os.getenv("OPENROUTER_API_KEY"):
        st.error("❌ ไม่พบ OPENROUTER_API_KEY ในระบบ")
        st.stop()
        
    st.divider()
    start_process_time = time.time()
    
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    now = datetime.datetime.now()
    current_date_str = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
    
    references = []
    result_dict = {"verdict_summary": "N/A", "facts": [], "distortions": [], "ai_insights": "N/A", "score": "N/A", "relevant_ref_ids": []}
    search_query = "SKIP_SEARCH"
    total_time_taken = 0.0
    
    progress_bar = st.progress(0, text="กำลังเตรียมการวิเคราะห์ (0%)")
    smooth_progress(progress_bar, 0, 5, "กำลังเริ่มต้นกระบวนการตรวจสอบ (5%)")
    
    with st.container(border=True):
        st.markdown("### ⚙️ กระบวนการประมวลผลของระบบ")
            
        if news_content == "VIDEO_DETECTED":
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%)")
            st.markdown("🛡️ **ตรวจพบวิดีโอคลิป**\n\nระบบยังไม่รองรับการถอดเสียงอัตโนมัติ กรุณาคัดลอกข้อความมาวางแทน")
            result_dict.update({"verdict_summary": "พบวิดีโอคลิป"})
            
        elif news_content == "GAMBLING_DETECTED":
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%)")
            st.markdown("🚫 **ระงับการเชื่อมต่อ**\n\nตรวจพบความเสี่ยงจากลิงก์อันตราย (เว็บไซต์หลอกลวง/พนัน)")
            result_dict.update({"score": 1, "verdict_summary": "เนื้อหามีความเสี่ยงต่อความปลอดภัย"})
            
        elif "ทะลวงระบบ" in news_content or "Error:" in news_content or "SOCIAL_BLOCKED" in news_content:
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%)")
            st.markdown("⚠️ **ต้นทางปฏิเสธการเข้าถึง**\n\nเว็บไซต์หรือโพสต์ถูกตั้งเป็นส่วนตัว กรุณานำข้อความมาวางตรวจสอบโดยตรง")
            result_dict.update({"verdict_summary": "ไม่สามารถดึงข้อมูลได้"})
            
        elif news_content in ["LINK_UNSUPPORTED", "EMPTY_CONTENT"] or "ไม่สามารถดึงข้อมูล" in news_content or re.search(r'(Error 404|404 Not Found|Page Not Found)', news_content, re.IGNORECASE):
            total_time_taken = round(time.time() - start_process_time, 2)
            smooth_progress(progress_bar, 5, 100, f"ประเมินเสร็จสมบูรณ์ (100%)")
            st.markdown("⚠️ **ไม่พบเนื้อหา**\n\nลิงก์ดังกล่าวไม่มีข้อความข่าวสารที่สามารถตรวจสอบได้")
            result_dict.update({"verdict_summary": "ไม่มีเนื้อหา"})
            
        else:
            smooth_progress(progress_bar, 5, 25, "🧠 AI กำลังสกัดประเด็นและวางแผนการค้นหา (25%)")
            text_for_keyword = news_content.split("]:\n")[-1] if "[เนื้อหาข่าวจริง" in news_content else news_content
            
            action, search_query, topic_summary, must_have_keywords = cached_plan_search(text_for_keyword)

            if action == "DROP":
                total_time_taken = round(time.time() - start_process_time, 2)
                smooth_progress(progress_bar, 25, 100, f"ประเมินเสร็จสมบูรณ์ (100%)")
                st.markdown(f"⏭️ **ยุติการตรวจสอบ:** {search_query}")
                search_query = "SKIP_SEARCH"
                result_dict.update({"verdict_summary": "เนื้อหาทั่วไป/เรื่องส่วนตัว"})
            else:
                st.markdown(f"📌 **ประเด็นที่วิเคราะห์:** {topic_summary}")
                
                if search_query:
                    st.info(f"🔍 **กลยุทธ์การสืบค้น:** `{search_query}` \n\n🎯 **คำบังคับเพื่อกรองขยะ:** `{must_have_keywords}`")
                
                smooth_progress(progress_bar, 25, 55, "🌐 กำลังกวาดข้อมูลเจาะลึกจากสื่อหลักและภาครัฐ (55%)")
                
                references = []
                if search_query:
                    references = cached_search(search_query, must_have_keywords, original_url)
                
                st.markdown(f"🔎 **ดึงข้อมูลอ้างอิงเบื้องต้น (หลังกรองขยะ) จำนวน {len(references)} แหล่ง**")
                smooth_progress(progress_bar, 55, 85, "⚖️ AI กำลังประมวลผลข้อเท็จจริง และเปรียบเทียบข้อมูล (85%)")
                st.markdown("⚖️ **กำลังเทียบเคียงหลักฐานกับข้อกล่าวอ้าง...**")
                
                ai_dict = cached_analyze(news_content, references, current_date_str, original_url)
                if ai_dict:
                    result_dict = ai_dict
                    total_time_taken = round(time.time() - start_process_time, 2)
                    progress_bar.progress(100, text=f"ประเมินเสร็จสมบูรณ์ (100%) (ใช้เวลา {total_time_taken} วินาที)")
                    st.markdown("✨ **ประเมินผลสำเร็จ!**")
    
    # ================= 7. การแสดงผลลัพธ์แบบ Hybrid =================
    has_system_error = "Error" in result_dict.get("ai_insights", "") or "โครงสร้างข้อมูลผิดพลาด" in result_dict.get("ai_insights", "")
    
    if has_system_error:
        st.error("⚠️ **ระบบวิเคราะห์ขัดข้อง:** โมเดล AI ประมวลผลผิดพลาดหรือไม่สามารถเชื่อมต่อได้ กรุณากดปุ่ม 'ล้างข้อมูลระบบ' แล้วลองใหม่อีกครั้ง")
        with st.expander("ดูข้อมูลข้อผิดพลาด"):
            st.write(result_dict.get("ai_insights", ""))
    else:
        pct, color, bg_color, border_color, label = get_score_ui_config(result_dict.get("score"))
        score_card_html = f"""
        <div style="text-align: center; padding: 30px; background-color: {bg_color}; border-radius: 16px; margin-bottom: 30px; border: 2px solid {border_color}; margin-top: 20px;">
            <p style="margin: 0; font-size: 1.2rem; font-weight: 500; opacity: 0.8; color: #334155;">ความน่าเชื่อถือของเนื้อหา</p>
            <h1 style="margin: 15px 0; font-size: 6rem; color: {color}; font-weight: 700; line-height: 1;">{pct}</h1>
            <span style="background-color: {color}; color: white; padding: 8px 24px; border-radius: 30px; font-weight: 500; font-size: 1.15rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">{label}</span>
        </div>
        """
        st.markdown(score_card_html, unsafe_allow_html=True)

        st.markdown(f"### 🎯 สรุปคำตัดสิน (Verdict)\n**{result_dict.get('verdict_summary', 'ไม่มีข้อมูลสรุป')}**")
        st.write("")

        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("<h4 style='color: #15803d;'>✅ ส่วนที่เป็นความจริง</h4>", unsafe_allow_html=True)
                facts = result_dict.get("facts", [])
                if facts and isinstance(facts, list) and facts[0] != "ไม่พบข้อมูลส่วนที่เป็นความจริง":
                    for f in facts: st.markdown(f"- {f}")
                else: st.markdown("- *ไม่พบข้อมูลที่ยืนยันได้ว่าเป็นความจริง*")
                
        with col2:
            with st.container(border=True):
                st.markdown("<h4 style='color: #b91c1c;'>❌ ส่วนที่บิดเบือน / ไร้หลักฐาน</h4>", unsafe_allow_html=True)
                dists = result_dict.get("distortions", [])
                if dists and isinstance(dists, list) and dists[0] != "ไม่พบข้อมูลส่วนที่บิดเบือน หรือข้อมูลไม่เพียงพอ":
                    for d in dists: st.markdown(f"- {d}")
                else: st.markdown("- *ไม่พบข้อมูลส่วนที่บิดเบือนอย่างชัดเจน*")

        st.write("")
        
        with st.container(border=True):
            st.markdown("### 🕵️‍♂️ บทวิเคราะห์เชิงลึกจาก AI")
            st.markdown(result_dict.get('ai_insights', 'ไม่มีบทวิเคราะห์เพิ่มเติม'))

        rel_ids = result_dict.get("relevant_ref_ids", [])
        
        with st.container(border=True):
            st.subheader("📚 แหล่งข่าวทั้งหมดที่ระบบค้นพบ (All Sources Found)")
            if references:
                for idx, ref in enumerate(references):
                    is_used = any(str(idx + 1) == str(rel_id) for rel_id in rel_ids)
                    badge = " ✅ *(AI นำมาอ้างอิง)*" if is_used else ""
                    st.markdown(f"{idx+1}. [{ref.get('title', 'ลิงก์อ้างอิง')}]({ref.get('href', '#')}){badge}")
            else:
                st.info("ไม่พบข่าวสารจากสื่อหลัก หรือประกาศจากหน่วยงานรัฐที่มีเนื้อหาตรงกับข้อกล่าวอ้างนี้ (ประเมินว่าไร้หลักฐาน)")

    try:
        log_input_data = original_url if original_url else news_content
        save_system_log(input_method_used, log_input_data, search_query, references, result_dict, total_time_taken)
    except Exception: pass