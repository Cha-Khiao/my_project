import streamlit as st
import re
import datetime
import time
import os
import csv
import concurrent.futures
import threading

# สร้างกุญแจล็อกไฟล์ ป้องกันการแย่งเขียน CSV พร้อมกัน
csv_lock = threading.Lock() 

from scraper import extract_text_from_url
from search import search_news_references
from llm import analyze_news_with_qwen, generate_search_keywords, classify_content

@st.cache_data(ttl=3600, show_spinner=False)
def cached_extract_text(url):
    return extract_text_from_url(url)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_classify(text):
    return classify_content(text)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_generate_keywords(text):
    return generate_search_keywords(text)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(query):
    return search_news_references(query, num_results=5)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_analyze(news_text, references, current_date):
    return analyze_news_with_qwen(news_text, references, current_date)

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Fact-Check AI", page_icon="🕵️‍♂️", layout="centered", initial_sidebar_state="expanded")

# 🌟 ปรับแต่ง CSS: จัดการลิงก์ยาว, ซ่อนปุ่ม Deploy (แต่เก็บเมนูเปลี่ยนธีมไว้), ตกแต่งขอบ
st.markdown("""
<style>
    /* ซ่อนปุ่ม Deploy ที่เกะกะ แต่ยังเก็บเมนู 3 จุดไว้ให้ผู้ใช้เปลี่ยนธีมได้ */
    .stDeployButton {display: none;}
    footer {visibility: hidden;}
    
    /* บังคับลิงก์ยาวๆ ให้ปัดบรรทัด ไม่ให้ดันกรอบจนเบี้ยว */
    .stMarkdown a {
        word-wrap: break-word;
        word-break: break-all;
    }
    .stMarkdown p {
        word-wrap: break-word;
    }
    
    /* แต่งกล่องให้ดูมนขึ้น */
    div[data-testid="stContainer"] {
        border-radius: 16px;
        padding: 15px;
    }
</style>
""", unsafe_allow_html=True)

def save_system_log(input_type, input_data, search_query, references, ai_result, process_time):
    filename = "thesis_system_logs.csv"
    file_exists = os.path.isfile(filename)
    score = "N/A"
    try:
        lines = ai_result.split('\n')
        for line in lines:
            if "ระดับความน่าเชื่อถือ:" in line:
                score = line.replace("**ระดับความน่าเชื่อถือ:**", "").strip()
                break
    except Exception:
        score = "Error Parsing"
    short_input = input_data[:100].replace('\n', ' ') + "..." if len(input_data) > 100 else input_data.replace('\n', ' ')
    ref_details = " | ".join([f"{idx+1}. {r['title']} ({r['href']})" for idx, r in enumerate(references)]) if references else "ไม่พบอ้างอิงสืบค้น"
    
    with csv_lock: 
        with open(filename, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["วัน-เวลาที่ทดสอบ", "ประเภทข้อมูล", "ข้อความ (ย่อ)", "AI คีย์เวิร์ด", "จำนวนอ้างอิง", "รายละเอียดแหล่งอ้างอิง", "ผลประเมิน", "เวลาประมวลผล (วินาที)"])
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([current_time, input_type, short_input, search_query, len(references), ref_details, score, process_time])

def get_system_stats():
    filename = "thesis_system_logs.csv"
    total_checks, fake_news = 0, 0
    if os.path.isfile(filename):
        with open(filename, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_checks += 1
                if row.get("ผลประเมิน") and ("ระดับ 1" in row["ผลประเมิน"] or "ระดับ 2" in row["ผลประเมิน"] or "ข่าวปลอม" in row["ผลประเมิน"]):
                    fake_news += 1
    return total_checks, fake_news

# ================= ส่วนแถบด้านข้าง (Sidebar) =================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2921/2921222.png", width=100)
    st.title("News Fact-Checker")
    st.markdown("ระบบประเมินความน่าเชื่อถือของข่าวสาร")
    st.divider()
    st.subheader("📊 สถิติการตรวจสอบ")
    total, fake = get_system_stats()
    col_stat1, col_stat2 = st.columns(2)
    col_stat1.metric("ใช้งานแล้ว", f"{total} ครั้ง")
    col_stat2.metric("พบข่าวปลอม", f"{fake} ข่าว")

# ================= ส่วนหน้าจอหลัก (Main UI) =================

# 🌟 ย้ายปุ่ม "ล้างแคช" มาไว้มุมขวาบนให้สมมาตรกับชื่อหัวข้อ
col1, col2 = st.columns([0.8, 0.2])
with col1:
    st.title("🕵️‍♂️ ตรวจสอบข่าวออนไลน์")

st.markdown("วางลิงก์ข่าวหรือข้อความที่น่าสงสัย เพื่อให้ AI ประมวลผลข้อเท็จจริง")

tab1, tab2 = st.tabs(["🔗 วางลิงก์ (URL)", "📝 วางข้อความโดยตรง"])

news_content, original_url, url_input, input_method_used = "", "", "", ""

VIDEO_PATTERNS = [
    r'youtube\.com/watch', r'youtu\.be', r'youtube\.com/shorts',
    r'tiktok\.com', r'vt\.tiktok\.com',
    r'fb\.watch', r'facebook\.com/watch', r'/videos/', r'/reel/',
    r'/share/v/', r'/share/r/', r'instagram\.com/reel',
    r'vimeo\.com', r'dailymotion\.com'
]

with tab1:
    url_input = st.text_input("🔗 ใส่ลิงก์ข่าว หรือ ลิงก์โซเชียลมีเดียที่นี่:", placeholder="https://www.example.com/...")
    if st.button("🔍 วิเคราะห์จากลิงก์", type="primary", use_container_width=True):
        if url_input:
            input_method_used = "URL Link"
            if any(re.search(pattern, url_input.lower()) for pattern in VIDEO_PATTERNS):
                news_content = "VIDEO_DETECTED"
                original_url = url_input
            else:
                with st.spinner("⏳ กำลังเตรียมข้อมูล..."):
                    extracted_data = cached_extract_text(url_input)
                    if isinstance(extracted_data, dict):
                        news_content = extracted_data.get("error", extracted_data.get("content", ""))
                        original_url = extracted_data.get("actual_url", url_input)
                    else:
                        news_content = str(extracted_data)
                    
                    if not news_content or str(news_content).strip() == "":
                        news_content = "EMPTY_CONTENT"
        else:
            st.warning("⚠️ กรุณาใส่ URL ก่อนครับ")

with tab2:
    text_input = st.text_area("📝 วางเนื้อหาข่าว แคปชั่น หรือข้อความ:", height=150)
    if st.button("🔍 วิเคราะห์จากข้อความ", type="primary", use_container_width=True):
        if text_input.strip():
            input_method_used = "Direct Text"
            news_content = text_input
            original_url = "" 
        else:
            st.warning("⚠️ กรุณาใส่เนื้อหาข่าวก่อนครับ")

# ================= กระบวนการประมวลผล (ซ่อนโค้ดเทคนิคจากสายตาผู้ใช้) =================
if news_content:
    st.divider()
    start_process_time = time.time()
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    now = datetime.datetime.now()
    current_date_str = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
    
    references, result, search_query = [], "", "SKIP_SEARCH"
    
    # ใช้ st.status เพื่อให้มีแถบโหลดนุ่มนวล และจะพับเก็บ(collapsed)เมื่อทำงานเสร็จ
    with st.status("🚀 AI กำลังประมวลผลข้อเท็จจริง...", expanded=True) as status:
        
        if news_content == "VIDEO_DETECTED":
            status.update(label="ตรวจพบวิดีโอคลิป", state="error")
            result = "## 💡 สรุปประเด็น\n- ลิงก์ที่ระบุเป็นคลิปวิดีโอ ระบบอัตโนมัติไม่สามารถตรวจสอบภาพและเสียงในคลิปได้\n\n## 📊 การประเมินความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ⚪ อยู่นอกเหนือขอบเขต\n\n**เหตุผล:** กรุณาคัดลอกเฉพาะข้อความบรรยายหรือคำพูดมาวางในแท็บ 'วางข้อความโดยตรง' ครับ\n\n## 🔗 แหล่งที่มา\n- ไม่สามารถสืบค้นได้"
        elif news_content == "GAMBLING_DETECTED":
            status.update(label="ตรวจพบเว็บไซต์อันตราย", state="error")
            result = "## 💡 สรุปประเด็น\n- ลิงก์เชื่อมโยงไปยังเว็บไซต์การพนันออนไลน์หรือสิ่งผิดกฎหมาย\n\n## 📊 การประเมินความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ☠️ ข่าวปลอม / เว็บไซต์อันตราย\n\n**เหตุผล:** แพลตฟอร์มมักใช้คำโฆษณาเกินจริง ระบบจึงระงับการเชื่อมต่อเพื่อความปลอดภัยของผู้ใช้งาน\n\n## 🔗 แหล่งที่มา\n- ระงับการสืบค้นอัตโนมัติ"
        elif news_content in ["LINK_UNSUPPORTED", "EMPTY_CONTENT"] or "ไม่สามารถดึงข้อมูล" in news_content:
            status.update(label="ไม่สามารถดึงข้อมูลได้", state="error")
            result = "## 💡 สรุปประเด็น\n- เว็บไซต์มีระบบป้องกันบอท หรือไม่มีตัวหนังสือให้วิเคราะห์\n\n## 📊 การประเมินความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ⚪ ข้อมูลไม่เพียงพอ\n\n**เหตุผล:** กรุณาคัดลอกเนื้อหามาวางด้วยตนเองในแท็บ 'วางข้อความโดยตรง' ครับ\n\n## 🔗 แหล่งที่มา\n- ไม่สามารถสืบค้นได้"
        else:
            news_content_th_check = re.sub(r'[\u4e00-\u9fff]+', '', news_content) 
            if not re.search(r'[ก-๙]', news_content_th_check):
                status.update(label="ไม่พบข้อมูลภาษาไทย", state="error")
                result = "## 💡 สรุปประเด็น\n- ตรวจไม่พบข้อความภาษาไทยในเนื้อหา\n\n## 📊 การประเมินความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ⚪ ข้อมูลไม่เพียงพอ\n\n**เหตุผล:** ระบบรองรับการประมวลผลข้อความภาษาไทยเป็นหลักครับ"
            else:
                text_for_keyword = news_content.split("]:\n")[-1] if "[เนื้อหาข่าวจริง" in news_content else news_content
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    future_classify = executor.submit(cached_classify, text_for_keyword)
                    future_keywords = executor.submit(cached_generate_keywords, text_for_keyword)
                    
                    result_type, extracted_reason = future_classify.result()

                    if result_type == "DROP":
                        status.update(label="ข้อมูลไม่อยู่ในขอบเขตข่าวสาร", state="complete")
                        search_query = "SKIP_SEARCH"
                        result = f"## 💡 สรุปประเด็น\n- เนื้อหาดังกล่าวไม่ใช่โครงสร้างของข่าวหรือคำกล่าวอ้างสาธารณะ\n\n## 📊 การประเมินความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ⚪ ข้อมูลไม่เพียงพอ/ไม่ใช่ข่าว\n\n**เหตุผลจาก AI:** {extracted_reason}\n\n## 🔗 แหล่งที่มา\n- ยุติการสืบค้นอัตโนมัติ"
                    else:
                        status.update(label="กำลังเทียบเคียงหลักฐานจากฐานข้อมูล...")
                        raw_query = future_keywords.result()
                        search_query = re.sub(r'[^\w\sก-๙]', ' ', raw_query).strip()
                        if not search_query: search_query = re.sub(r'http[s]?://\S+|\[.*?\]', '', text_for_keyword)[:60].strip()
                        
                        references = cached_search(search_query)
                            
                        status.update(label="กำลังวิเคราะห์และสรุปผล...")
                        raw_result = cached_analyze(news_content, references, current_date_str)
                        
                        # ทำความสะอาด Markdown ให้สวยงามก่อนโชว์ผู้ใช้
                        result = raw_result.replace("## 📌 1. สรุปประเด็นสำคัญ", "## 💡 สรุปประเด็น")
                        result = re.sub(r'## 📊 2\. การประเมินระดับความน่าเชื่อถือ.*?เหตุผลประกอบการประเมิน:', '## 🔍 เหตุผลจาก AI:', result, flags=re.DOTALL)
                        result = result.replace("## 🔗 3. แหล่งอ้างอิง", "## 🔗 แหล่งที่มาดั้งเดิม")
                        
                        if references:
                            result += "\n\n---\n## 📰 ข่าวที่สืบค้นพบเพิ่มเติม:"
                            for r in references: result += f"\n- [{r['title']}]({r['href']})"
                        else:
                            result += "\n\n---\n## 📰 ข่าวที่สืบค้นพบเพิ่มเติม:\n- ไม่พบข้อมูลอ้างอิงเพิ่มเติมจากอินเทอร์เน็ต"
                            
                        total_time_taken = round(time.time() - start_process_time, 2)
                        status.update(label=f"✅ วิเคราะห์เสร็จสิ้น (ใช้เวลา {total_time_taken} วินาที)", state="complete", expanded=False)

    # ================= ส่วนแสดงผลลัพธ์ (ผลประเมิน) =================
    if "ระดับ 5" in result or "ระดับ 4" in result or "🟢" in result or "🟡" in result:
        st.success("✅ **ประเมินเบื้องต้น:** ข้อมูลนี้มีแนวโน้มเป็นความจริงและมีความน่าเชื่อถือ")
    elif "ระดับ 1" in result or "ระดับ 2" in result or "ข่าวปลอม" in result or "☠️" in result or "🔴" in result or "เว็บไซต์อันตราย" in result:
        st.error("🚨 **ประเมินเบื้องต้น:** เตือนภัย! ตรวจพบข้อมูลบิดเบือน หรือลิงก์อันตราย")
    elif "N/A" in result or "⚪" in result or "อยู่นอกเหนือ" in result:
        st.info("ℹ️ **ประเมินเบื้องต้น:** ไม่ใช่รูปแบบของข่าว หรือไม่สามารถดึงข้อมูลได้")
    else:
        st.warning("⚠️ **ประเมินเบื้องต้น:** ข้อมูลก้ำกึ่ง โปรดอ่านรายละเอียดด้านล่าง")

    with st.container(border=True):
        st.markdown(result)
        
    with st.expander("🛠️ ข้อมูลเชิงเทคนิค (สำหรับนักพัฒนา)"):
        st.markdown(f"**คำค้นหาที่ AI ดึงออกมา:** `{search_query}`")
            
    try:
        log_input_data = original_url if original_url else news_content
        save_system_log(input_method_used, log_input_data, search_query, references, result, total_time_taken)
    except Exception:
        pass