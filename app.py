import streamlit as st
import re
import datetime
import time
import os
import csv
import concurrent.futures
import threading 

# 🌟 สร้างกุญแจล็อกไฟล์ ป้องกันการแย่งเขียน CSV
csv_lock = threading.Lock() 

from scraper import extract_text_from_url
from search import search_news_references
from llm import analyze_news_with_qwen, generate_search_keywords, classify_content

@st.cache_data(ttl=3600, show_spinner=False)
def cached_extract_text(url): return extract_text_from_url(url)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_classify(text): return classify_content(text)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_generate_keywords(text): return generate_search_keywords(text)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(query): return search_news_references(query, num_results=5)
@st.cache_data(ttl=3600, show_spinner=False)
def cached_analyze(news_text, references, current_date): return analyze_news_with_qwen(news_text, references, current_date)

# ================= 1. ตั้งค่าหน้าจอ & CSS =================
st.set_page_config(page_title="AI Fact-Checker", page_icon="🛡️", layout="centered")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
    
    h1, h2, h3, h4, h5, h6, p, a, button, input, textarea, label, li, span {
        font-family: 'Prompt', sans-serif !important;
    }
    
    [data-testid="stIconMaterial"], .material-icons, .stIcon {
        font-family: 'Material Symbols Rounded' !important;
    }
    
    footer {visibility: hidden;} 
    .stAlert {border-radius: 12px;}
    
    .stButton>button {
        border-radius: 8px !important; 
        font-weight: 500 !important;
        padding: 0.5rem 2rem !important; 
    }
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #2563eb !important; 
        color: #ffffff !important; 
        border: none !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #1e40af !important; 
        opacity: 1 !important;
    }
    
    .stMarkdown a {
        word-wrap: break-word; overflow-wrap: break-word; word-break: break-all;
        color: #1e40af !important; 
        text-decoration: underline !important;
        text-underline-offset: 4px !important;
        font-weight: 500 !important;
        opacity: 1 !important; 
    }
    .stMarkdown a:hover {
        color: #0f172a !important; 
        opacity: 1 !important;
    }
    @media (prefers-color-scheme: dark) {
        .stMarkdown a {
            color: #38bdf8 !important; 
        }
        .stMarkdown a:hover { 
            color: #bae6fd !important; 
            opacity: 1 !important;
        }
    }
    
    div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"] { gap: 1.2rem !important; }
    p, li { line-height: 1.7 !important; font-size: 1.05rem !important; }
    
    div[data-testid="stButton"] button[kind="secondary"] {
        position: fixed !important; bottom: 15px !important; right: 15px !important;
        opacity: 0.0 !important; transition: all 0.3s ease-in-out !important;
        z-index: 99999 !important; width: 45px !important; height: 45px !important;
        border-radius: 50% !important; padding: 0 !important;
        border: none !important; box-shadow: none !important;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        opacity: 1.0 !important; background-color: #ffffff !important;
        box-shadow: 0 4px 10px rgba(0,0,0,0.15) !important;
        border: 1px solid #e2e8f0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ================= 2. ฟังก์ชันจัดการข้อมูลและคะแนน =================
def stream_text(text, delay=0.012):
    text = text.replace("*", "") 
    for word in text.split(" "):
        yield word + " "
        time.sleep(delay)

def extract_score_info(text):
    pct, color, bg_color, border_color, label = "N/A", "#94a3b8", "rgba(148, 163, 184, 0.1)", "rgba(148, 163, 184, 0.4)", "ไม่สามารถประเมินได้"
    if "ระดับ 5" in text:
        pct, color, bg_color, border_color, label = "95%", "#10b981", "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.4)", "มีความน่าเชื่อถือสูง"
    elif "ระดับ 4" in text:
        pct, color, bg_color, border_color, label = "75%", "#10b981", "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.4)", "มีความน่าเชื่อถือ"
    elif "ระดับ 3" in text:
        pct, color, bg_color, border_color, label = "50%", "#f59e0b", "rgba(245, 158, 11, 0.1)", "rgba(245, 158, 11, 0.4)", "ข้อมูลก้ำกึ่ง / ไม่เพียงพอ"
    elif "ระดับ 2" in text:
        pct, color, bg_color, border_color, label = "25%", "#ef4444", "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.4)", "มีความเสี่ยงเป็นข่าวบิดเบือน"
    elif "ระดับ 1" in text or "ข่าวปลอม" in text or "เว็บไซต์อันตราย" in text:
        pct, color, bg_color, border_color, label = "10%", "#ef4444", "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.4)", "ข่าวปลอม / บิดเบือน"
    return pct, color, bg_color, border_color, label

def parse_result_to_chunks(text):
    summary, reason = "", ""
    summary_match = re.search(r'## 📌 1\. สรุปประเด็นสำคัญ(.*?)(?=## 📊 2\. การประเมินระดับความน่าเชื่อถือ|$)', text, re.DOTALL)
    if summary_match: summary = summary_match.group(1).strip()
    reason_match = re.search(r'## 📊 2\. การประเมินระดับความน่าเชื่อถือ(.*?)(?=## 🔗 3\. แหล่งอ้างอิง|---|$)', text, re.DOTALL)
    if reason_match: 
        raw_reason = reason_match.group(1).strip()
        raw_reason = re.sub(r'\*?\*?ระดับความน่าเชื่อถือ.*?\n', '', raw_reason, flags=re.IGNORECASE)
        raw_reason = re.sub(r'\*?\*?เหตุผลประกอบการประเมิน[^\n]*\n?', '', raw_reason, flags=re.IGNORECASE)
        reason = raw_reason.strip()
    if not summary and not reason: summary = text.replace("*", "")
    return summary, reason

# ================= 3. ระบบฐานข้อมูล =================
def save_system_log(input_type, input_data, search_query, references, ai_result, process_time):
    filename = "thesis_system_logs.csv"
    file_exists = os.path.isfile(filename)
    score = "N/A"
    try:
        match = re.search(r'ระดับความน่าเชื่อถือ:.*?(1|2|3|4|5)', ai_result)
        if match: score = f"ระดับ {match.group(1)}"
    except Exception: score = "Error"
    short_input = input_data[:100].replace('\n', ' ') + "..." if len(input_data) > 100 else input_data.replace('\n', ' ')
    ref_details = " | ".join([f"{idx+1}. {r['title']} ({r['href']})" for idx, r in enumerate(references)]) if references else "ไม่พบอ้างอิงสืบค้น"
    with csv_lock: 
        with open(filename, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["วัน-เวลาที่ทดสอบ", "ประเภทข้อมูล", "ข้อความ (ย่อ)", "คำค้นหา", "จำนวนอ้างอิง", "แหล่งอ้างอิง", "ประเมิน", "เวลา(วินาที)"])
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([current_time, input_type, short_input, search_query, len(references), ref_details, score, process_time])

# ================= 4. ส่วนหัว (Header) =================
st.markdown("""
<div style='text-align: center;'>
    <h1 style='font-size: 2.5rem; margin-bottom: 0px;'>🛡️ AI Fact-Checker</h1>
    <p style='font-size: 1.1rem; opacity: 0.8; margin-top: 5px;'>ระบบประเมินความน่าเชื่อถือของข่าว โดยใช้ปัญญาประดิษฐ์</p>
</div>
""", unsafe_allow_html=True)
st.write("") 

# ================= 5. ส่วนรับข้อมูล =================
tab1, tab2 = st.tabs(["🌐 ตรวจสอบจากลิงก์ (URL)", "📄 ตรวจสอบจากข้อความ"])

news_content, original_url, url_input, input_method_used = "", "", "", ""
VIDEO_PATTERNS = [
    r'youtube\.com/watch', r'youtu\.be', r'youtube\.com/shorts', 
    r'tiktok\.com', r'vt\.tiktok\.com', 
    r'fb\.watch', r'facebook\.com/watch', r'/videos/', r'vimeo\.com', r'dailymotion\.com'
]

with tab1:
    st.write("")
    url_input = st.text_input("🔗 วางลิงก์ข่าว หรือ โพสต์จากโซเชียลมีเดีย:", placeholder="ตัวอย่าง: https://www.facebook.com/...")
    st.write("") 
    
    col_l, col_btn, col_r = st.columns([1, 1, 1])
    with col_btn:
        btn_url = st.button("🔍 เริ่มการประเมิน", key="btn_url", type="primary")
        
    if btn_url:
        if url_input:
            input_method_used = "URL Link"
            
            # 🛠️ ระบบป้องกันข้อความขยะจากมือถือ: สกัดเฉพาะลิงก์ออกมา 
            url_match = re.search(r'(https?://[^\s]+)', url_input)
            clean_url = url_match.group(1) if url_match else url_input
            
            if any(re.search(pattern, clean_url.lower()) for pattern in VIDEO_PATTERNS):
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
    with col_btn2:
        btn_text = st.button("🔍 เริ่มการประเมิน", key="btn_text", type="primary")
        
    if btn_text:
        if text_input.strip():
            input_method_used = "Direct Text"
            news_content = text_input
        else: st.warning("⚠️ กรุณาระบุเนื้อหาก่อนทำการวิเคราะห์")

# ================= 6. ส่วนประมวลผล =================
if news_content:
    st.divider()
    start_process_time = time.time()
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    now = datetime.datetime.now()
    current_date_str = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
    references, result, search_query = [], "", "SKIP_SEARCH"
    
    with st.status("⚙️ ระบบกำลังประมวลผลข้อมูล...", expanded=True) as status:
        if news_content == "VIDEO_DETECTED":
            st.write("🛡️ ตรวจพบรูปแบบวิดีโอคลิป")
            result = f"## 📌 1. สรุปประเด็นสำคัญ\nแพลตฟอร์มปลายทางเป็นรูปแบบวิดีโอ ซึ่งระบบไม่สามารถสกัดภาพและเสียงมาประมวลผลแทนได้\n\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** N/A\n\nเพื่อความแม่นยำ กรุณาคัดลอกเฉพาะข้อความบรรยายหรือคำพูดที่สำคัญ มาวางในแท็บ **'ตรวจสอบจากข้อความ'** ครับ"
        elif news_content == "GAMBLING_DETECTED":
            st.write("🚫 ตรวจพบเนื้อหาความเสี่ยงสูง")
            result = f"## 📌 1. สรุปประเด็นสำคัญ\nลิงก์เชื่อมโยงไปยังเว็บไซต์การพนันออนไลน์ สแปม หรือเนื้อหาหลอกลวงเกินจริง\n\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ระดับ 1\n\nระบบดำเนินการระงับการเชื่อมต่อเพื่อป้องกันความปลอดภัยของอุปกรณ์ผู้ใช้"
        
        elif "ทะลวงระบบ" in news_content or "Error:" in news_content or "SOCIAL_BLOCKED" in news_content:
            st.write("⚠️ ระบบความปลอดภัย: โซเชียลมีเดียปลายทางปฏิเสธการดึงข้อมูล")
            result = f"## 📌 1. สรุปประเด็นสำคัญ\nแพลตฟอร์มโซเชียลมีเดียมีระบบป้องกันการดึงข้อมูล (Anti-Scraping) ทำให้เซิร์ฟเวอร์ Cloud ของเราไม่สามารถเข้าถึงข้อความในโพสต์นี้ได้\n\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** N/A\n\n**ข้อแนะนำ:** เนื่องจากระบบความปลอดภัยของโซเชียลมีเดีย กรุณาคัดลอกเนื้อหาหรือแคปชั่น มาวางด้วยตนเองในแท็บ **'ตรวจสอบจากข้อความ'** ครับ"
            
        elif news_content in ["LINK_UNSUPPORTED", "EMPTY_CONTENT"] or "ไม่สามารถดึงข้อมูล" in news_content:
            st.write("⚠️ เว็บไซต์ปลายทางปฏิเสธการเชื่อมต่อ")
            result = f"## 📌 1. สรุปประเด็นสำคัญ\nเว็บไซต์มีระบบป้องกันการดึงข้อมูลอัตโนมัติ (Anti-bot) หรือไม่พบเนื้อหาที่เป็นข้อความเพียงพอต่อการวิเคราะห์\n\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** N/A\n\nกรุณาคัดลอกเนื้อหาที่ต้องการตรวจสอบ มาวางด้วยตนเองในแท็บ **'ตรวจสอบจากข้อความ'** ครับ"
        else:
            st.write("🧠 กำลังวิเคราะห์และจัดหมวดหมู่เนื้อหา...")
            text_for_keyword = news_content.split("]:\n")[-1] if "[เนื้อหาข่าวจริง" in news_content else news_content
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_classify = executor.submit(cached_classify, text_for_keyword)
                future_keywords = executor.submit(cached_generate_keywords, text_for_keyword)
                result_type, extracted_reason = future_classify.result()

                if result_type == "DROP":
                    st.write(f"⏭️ ยุติการตรวจสอบ: ข้อมูลไม่อยู่ในเงื่อนไขการประเมิน")
                    search_query = "SKIP_SEARCH"
                    result = f"## 📌 1. สรุปประเด็นสำคัญ\nไม่พบโครงสร้างของ 'ข้อเท็จจริงที่มีผลกระทบต่อสังคม' ในเนื้อหาที่ระบุ\n\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** N/A\n\n{extracted_reason}"
                else:
                    st.write(f"✅ การวิเคราะห์บริบทเสร็จสิ้น: {extracted_reason}")
                    raw_query = future_keywords.result()
                    search_query = re.sub(r'[^\w\sก-๙]', ' ', raw_query).strip()
                    if not search_query: search_query = text_for_keyword[:60].strip()
                    
                    st.write("🌐 กำลังสืบค้นข้อมูลจากฐานข้อมูลที่น่าเชื่อถือ...")
                    references = cached_search(search_query)
                        
                    st.write("⚖️ กำลังประมวลผลและสร้างบทวิเคราะห์...")
                    result = cached_analyze(news_content, references, current_date_str)
        
        total_time_taken = round(time.time() - start_process_time, 2)
        status.update(label=f"ประเมินผลเสร็จสิ้น (ใช้เวลา {total_time_taken} วินาที)", state="complete", expanded=False)
    
    # ================= 7. ส่วนแสดงผลลัพธ์ =================
    
    pct, color, bg_color, border_color, label = extract_score_info(result)
    
    score_card_html = f"""
    <div style="text-align: center; padding: 25px; background-color: {bg_color}; border-radius: 16px; margin-bottom: 25px; border: 2px solid {border_color};">
        <p style="margin: 0; font-size: 1.1rem; font-weight: 500; opacity: 0.8;">ผลการประเมินความน่าเชื่อถือโดย AI</p>
        <h1 style="margin: 10px 0; font-size: 5.5rem; color: {color}; font-weight: 700; line-height: 1;">{pct}</h1>
        <span style="background-color: {color}; color: white; padding: 6px 20px; border-radius: 20px; font-weight: 500; font-size: 1.05rem; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">{label}</span>
    </div>
    """
    st.markdown(score_card_html, unsafe_allow_html=True)

    summary_text, reason_text = parse_result_to_chunks(result)

    with st.container(border=True):
        st.subheader("🎯 สรุปประเด็น")
        st.write_stream(stream_text(summary_text))
        
    if reason_text:
        with st.container(border=True):
            st.subheader("💡 บทวิเคราะห์จาก AI")
            st.write_stream(stream_text(reason_text))

    if references:
        with st.container(border=True):
            st.subheader("🔗 แหล่งข้อมูลอ้างอิง")
            for idx, r in enumerate(references):
                st.markdown(f"{idx+1}. [{r['title']}]({r['href']})")
    elif "SKIP_SEARCH" not in search_query:
        with st.container(border=True):
            st.subheader("🔗 แหล่งข้อมูลอ้างอิง")
            st.info("ไม่พบข้อมูลอ้างอิงที่ตรงกันจากแหล่งข่าวอินเทอร์เน็ต")
            
    try:
        log_input_data = original_url if original_url else news_content
        save_system_log(input_method_used, log_input_data, search_query, references, result, total_time_taken)
    except Exception: pass

# ================= 8. ปุ่มลับ ⚙️ (ล้างแคช) =================
if st.button("⚙️", key="clear_cache_btn"):
    st.cache_data.clear()