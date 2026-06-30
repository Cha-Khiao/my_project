import streamlit as st
import re
import datetime
import time
import os
import csv
from scraper import extract_text_from_url
from search import search_news_references
from llm import analyze_news_with_qwen, generate_search_keywords, classify_content

# ================= ฟังก์ชัน Caching ที่ปรับปรุงไม่ให้จำ Error =================
@st.cache_data(ttl=3600, show_spinner=False)
def cached_extract_text(url):
    result = extract_text_from_url(url)
    
    # ถ้าดึงมาแล้วเป็น dict และมีคำว่า error (เช่น 500 Internal Server Error)
    if isinstance(result, dict) and "error" in result:
        # ใช้ raise Exception เพื่อบังคับให้ Streamlit "ไม่จำ" ค่านี้ลง Cache
        raise Exception(result["error"])
        
    # ถ้าดึงมาแล้วได้เป็น string ธรรมดา แต่มีข้อความ Error โผล่มา
    if isinstance(result, str) and ("500 Internal Server Error" in result or "Error" in result):
        raise Exception(result)
        
    return result

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

# ================= ตั้งค่าหน้าเพจ & ซ่อนเมนู Streamlit =================
st.set_page_config(page_title="Fact-Check AI", page_icon="🕵️‍♂️", layout="centered", initial_sidebar_state="expanded")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stAlert {border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)

# ================= ฟังก์ชันสำหรับจัดการ Log =================
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

# ================= แถบด้านข้าง (Sidebar) =================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2921/2921222.png", width=100)
    st.title("News Fact-Checker")
    st.markdown("ระบบวิเคราะห์ความน่าเชื่อถือของข่าวด้วย **AI (Qwen-2.5)**")
    
    st.divider()
    
    # ปุ่มลับสำหรับ Dev ไว้กดเคลียร์แคชเวลามีปัญหา
    if st.button("🗑️ ล้างหน่วยความจำ (Clear Cache)", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ ล้างข้อมูลที่จำไว้เรียบร้อย! ลองกดค้นหาใหม่อีกครั้งครับ")
        
    st.divider()
    st.subheader("📊 สถิติระบบ (Live)")
    total, fake = get_system_stats()
    col1, col2 = st.columns(2)
    col1.metric("ตรวจสอบแล้ว", f"{total} ครั้ง")
    col2.metric("พบข่าวปลอม", f"{fake} ข่าว")

# ================= ส่วนหน้าเว็บแอปพลิเคชันหลัก =================
st.title("🕵️‍♂️ ตรวจสอบความจริงข่าวออนไลน์")
st.markdown("วางลิงก์ข่าวหรือข้อความที่น่าสงสัย เพื่อให้ระบบ AI ช่วยวิเคราะห์ข้อเท็จจริง")

tab1, tab2 = st.tabs(["🔗 ตรวจสอบจากลิงก์ (URL)", "📝 วางข้อความโดยตรง"])

news_content = ""
original_url = "" 
url_input = "" 
input_method_used = "" 

with tab1:
    url_input = st.text_input("🔗 ใส่ลิงก์ข่าว หรือ ลิงก์โซเชียลมีเดียที่นี่:", placeholder="https://www.example.com/news...")
    if st.button("🔍 เริ่มวิเคราะห์จากลิงก์", type="primary", use_container_width=True):
        if url_input:
            input_method_used = "URL Link"
            with st.spinner("⏳ กำลังสกัดเนื้อหาข้อมูล..."):
                try:
                    # ดึงข้อมูลผ่าน Cache ที่มีระบบดีด Error ทิ้ง
                    extracted_data = cached_extract_text(url_input)
                    if isinstance(extracted_data, dict):
                        news_content = extracted_data.get("content", "")
                        original_url = extracted_data.get("actual_url", url_input)
                    else:
                        news_content = extracted_data
                        original_url = url_input 
                except Exception as e:
                    # ถ้าระบบโยน Error ออกมา จะมาเข้าตรงนี้แทน และหยุดการทำงานขั้นถัดไป
                    st.error(f"❌ ระบบไม่สามารถดึงข้อมูลจากเว็บนี้ได้ชั่วคราว: {e}")
                    news_content = "" # เคลียร์ค่าเพื่อให้ระบบไม่ไปต่อ
        else:
            st.warning("กรุณาใส่ URL ก่อนครับ")

with tab2:
    text_input = st.text_area("📝 วางเนื้อหาข่าว แคปชั่น หรือข้อความที่ส่งต่อกันมา:", height=150)
    if st.button("🔍 เริ่มวิเคราะห์จากข้อความ", type="primary", use_container_width=True):
        if text_input.strip():
            input_method_used = "Direct Text"
            news_content = text_input
            original_url = "" 
        else:
            st.warning("กรุณาใส่เนื้อหาข่าวก่อนครับ")

# ================= กระบวนการทำงานหลัก =================
if news_content:
    st.divider()
    start_process_time = time.time()
    
    news_content = re.sub(r'[\u4e00-\u9fff]+', '', news_content) 
    if not re.search(r'[ก-๙]', news_content):
        news_content = "เนื้อหาไม่มีภาษาไทยปะปนอยู่เลย ไม่สามารถประมวลผลได้"
    
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    now = datetime.datetime.now()
    current_date_str = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
    
    references = []
    result = ""
    search_query = ""
    
    with st.status("🚀 ระบบกำลังตรวจสอบข้อมูลในระบบท่อส่งสัญญาณ...", expanded=True) as status:
        
        st.write("🧠 [ด่านที่ 1]: สแกนหาคำกล่าวอ้างเชิงข้อเท็จจริง...")
        text_for_keyword = news_content.split("]:\n")[-1] if "[เนื้อหาข่าวจริง" in news_content else news_content
        
        result_type, extracted_reason = cached_classify(text_for_keyword)
        
        if result_type == "DROP":
            st.write(f"⏭️ [ผลการกรอง]: เนื้อหาไม่ใช่ข่าวสารสาธารณะ ยุติการทำงานเพื่อความรวดเร็ว (Fail-Fast)")
            search_query = "SKIP_SEARCH"
            result = f"""## 📌 1. สรุปประเด็นสำคัญ\n- ไม่พบโครงสร้างของ 'คำกล่าวอ้างที่ตรวจสอบได้'\n\n## 📊 2. การประเมินระดับความน่าเชื่อถือ\n**ระดับความน่าเชื่อถือ:** ⚪ N/A: ไม่ใช่ข่าวหรือข้อมูลที่ตรวจสอบได้\n\n**เหตุผลประกอบการประเมิน:** {extracted_reason}\n\n## 🔗 3. แหล่งอ้างอิง\n- **แหล่งอ้างอิงที่อ้างในข้อความต้นฉบับ:** ไม่ระบุ\n- **อ้างอิงจากการสืบค้น (สื่อหลัก):** ระบบยุติการสืบค้นอัตโนมัติ"""
        
        else:
            st.write(f"🟢 [ผลการกรอง]: {extracted_reason} กำลังส่งต่อไปยังด่านสกัดคำค้นหา...")
            search_query = cached_generate_keywords(text_for_keyword)
            if not search_query: search_query = re.sub(r'http[s]?://\S+|\[.*?\]', '', text_for_keyword)[:60].strip()
            
            st.write(f"🌐 [ด่านที่ 2]: กำลังสืบค้นข้อมูลพร้อมกัน 3 แหล่ง ด้วยคำค้นหา: `{search_query}`")
            references = cached_search(search_query)
                
            st.write("⚖️ [ด่านที่ 3]: ข้อมูลพร้อมแล้ว! กำลังวิเคราะห์เปรียบเทียบสถิติและข้อเท็จจริง...")
            result = cached_analyze(news_content, references, current_date_str)
            
            ref_markdown = "\n- **อ้างอิงจากการสืบค้น (สื่อหลัก):**"
            if references:
                for idx, r in enumerate(references):
                    ref_markdown += f"\n   {idx+1}. [{r['title']}]({r['href']})"
            else:
                ref_markdown += " ไม่พบข้อมูลจากการสืบค้นบนอินเทอร์เน็ต"
                
            result += ref_markdown 
        
        end_process_time = time.time()
        total_time_taken = round(end_process_time - start_process_time, 2)
        
        status.update(label=f"✅ ประมวลผลเสร็จสิ้น! (ใช้เวลา {total_time_taken} วินาที)", state="complete", expanded=False)
    
    # ================= ส่วนจัดแต่งแสดงผลลัพธ์หน้าบ้าน =================
    st.subheader("📊 รายงานผลการประเมิน")
    
    if "ระดับ 5" in result or "ระดับ 4" in result or "🟢" in result or "🟡" in result:
        st.success("✅ **ผลประเมินเบื้องต้น:** ข้อมูลนี้มีแนวโน้มเป็นความจริงและมีความน่าเชื่อถือ")
    elif "ระดับ 1" in result or "ระดับ 2" in result or "ข่าวปลอม" in result or "☠️" in result or "🔴" in result:
        st.error("🚨 **ผลประเมินเบื้องต้น:** เตือนภัย! ตรวจพบข้อมูลบิดเบือน หรือข่าวปลอม")
    elif "N/A" in result or "⚪" in result:
        st.info("ℹ️ **ผลประเมินเบื้องต้น:** ไม่ใช่รูปแบบของข่าวหรือคำกล่าวอ้างที่ตรวจสอบได้")
    else:
        st.warning("⚠️ **ผลประเมินเบื้องต้น:** ข้อมูลก้ำกึ่ง โปรดอ่านรายละเอียดด้านล่าง")

    with st.container(border=True):
        st.markdown(result)
        
    with st.expander("🔑 ข้อมูลเชิงเทคนิค (AI Search Query)"):
        st.markdown(f"**คีย์เวิร์ดที่ AI ใช้สืบค้น:** `{search_query}`")
            
    try:
        log_input_data = original_url if original_url else news_content
        save_system_log(input_method_used, log_input_data, search_query, references, result, total_time_taken)
    except Exception:
        pass