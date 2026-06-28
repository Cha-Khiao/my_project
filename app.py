import streamlit as st
import re
import datetime
import time
import os
import csv
from scraper import extract_text_from_url
from search import search_news_references
from llm import analyze_news_with_qwen, generate_search_keywords

# ================= ฟังก์ชันสำหรับเก็บ Log ลง CSV =================
def save_system_log(input_type, input_data, search_query, references, ai_result, process_time):
    """ฟังก์ชันจดบันทึกการทำงานลงไฟล์ CSV พร้อมจับเวลาและเก็บลิงก์อ้างอิงอย่างละเอียด"""
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

    # 📌 สกัดชื่อพาดหัวและลิงก์ข่าวอ้างอิงทั้งหมด มารวมเป็นข้อความเดียวเพื่อเซฟลง CSV
    ref_details = ""
    if references:
        ref_details = " | ".join([f"{idx+1}. {r['title']} ({r['href']})" for idx, r in enumerate(references)])
    else:
        ref_details = "ไม่พบแหล่งอ้างอิงบนอินเทอร์เน็ต"

    with open(filename, mode='a', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            # เพิ่มคอลัมน์ "รายละเอียดแหล่งอ้างอิง" เข้าไปในหัวตาราง
            writer.writerow(["วัน-เวลาที่ทดสอบ", "ประเภทข้อมูล", "ข้อความ (ย่อ)", "AI คีย์เวิร์ด", "จำนวนอ้างอิง", "รายละเอียดแหล่งอ้างอิง", "ผลประเมิน (ระดับความน่าเชื่อถือ)", "เวลาประมวลผล (วินาที)"])
        
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # บันทึกข้อมูลทั้งหมดลงในไฟล์
        writer.writerow([current_time, input_type, short_input, search_query, len(references), ref_details, score, process_time])

# ================= ส่วนหน้าเว็บแอปพลิเคชัน =================
st.set_page_config(page_title="News Fact-Checker", page_icon="🕵️‍♂️", layout="centered")
st.title("🕵️‍♂️ ระบบวิเคราะห์ความน่าเชื่อถือของข่าวออนไลน์")
st.markdown("**โมเดล:** Qwen-2.5 (7B) | **สืบค้น:** AI Search Engine")

tab1, tab2 = st.tabs(["🔗 ตรวจสอบจากลิงก์ (URL)", "📝 วางข้อความ"])

news_content = ""
original_url = "" 
url_input = "" 
input_method_used = "" 

with tab1:
    url_input = st.text_input("ใส่ลิงก์ข่าว หรือ ลิงก์โซเชียลมีเดีย:")
    if st.button("🔍 วิเคราะห์จากลิงก์", type="primary"):
        if url_input:
            input_method_used = "URL Link"
            with st.spinner("⏳ กำลังสกัดเนื้อหาข้อมูล..."):
                extracted_data = extract_text_from_url(url_input)
                if isinstance(extracted_data, dict):
                    if "error" in extracted_data:
                        st.error(extracted_data["error"])
                    else:
                        news_content = extracted_data.get("content", "")
                        original_url = extracted_data.get("actual_url", url_input)
                else:
                    news_content = extracted_data
                    original_url = url_input 
                if news_content:
                    st.success("✅ สกัดเนื้อหาสำเร็จ!")
        else:
            st.warning("กรุณาใส่ URL ก่อนครับ")

with tab2:
    text_input = st.text_area("วางเนื้อหาข่าว หรือ แคปชั่นที่นี่:", height=200)
    if st.button("🔍 วิเคราะห์จากข้อความ", type="primary"):
        if text_input.strip():
            input_method_used = "Direct Text"
            news_content = text_input
            original_url = "" 
        else:
            st.warning("กรุณาใส่เนื้อหาข่าวก่อนครับ")

# ================= กระบวนการทำงานหลัก =================
if news_content:
    st.divider()
    
    # เริ่มจับเวลา
    start_process_time = time.time()
    
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    now = datetime.datetime.now()
    current_date_str = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
    
    with st.spinner("🧠 ให้ AI วิเคราะห์คีย์เวิร์ดสำหรับสืบค้นความจริง..."):
        text_for_keyword = news_content
        if "[เนื้อหาข่าวจริง" in news_content:
            text_for_keyword = news_content.split("]:\n")[-1]
            
        search_query = generate_search_keywords(text_for_keyword)
        if not search_query:
            clean_text = re.sub(r'http[s]?://\S+|\[.*?\]', '', text_for_keyword)
            search_query = clean_text[:60].strip()
            
    st.caption(f"🔑 **คีย์เวิร์ดสืบค้น (AI Generated):** {search_query}")
    
    with st.spinner("🌐 กำลังสืบค้นข้อมูลเปรียบเทียบจากสื่อกระแสหลัก..."):
        references = search_news_references(search_query, num_results=5)
        if not references:
            st.warning("⚠️ ไม่พบข้อมูลข่าวสารที่สอดคล้องในฐานข้อมูลสื่อหลัก")
            
    with st.spinner("🧠 Qwen-2.5 กำลังตรวจสอบและร่างรายงาน..."):
        result = analyze_news_with_qwen(news_content, references, current_date_str)
        
        # สิ้นสุดการจับเวลา
        end_process_time = time.time()
        total_time_taken = round(end_process_time - start_process_time, 2)
        
        st.subheader("📊 รายงานผลการประเมินความน่าเชื่อถือ")
        st.markdown(result)
        
        st.markdown("## 🌐 3. แหล่งข่าวอ้างอิงสำหรับตรวจสอบ")
        if references:
            for idx, r in enumerate(references):
                st.write(f"{idx+1}. [{r['title']}]({r['href']})")
        else:
            st.write("*ไม่พบแหล่งข่าวอ้างอิงที่สอดคล้องกันบนอินเทอร์เน็ต*")
            
        st.caption(f"⏱️ *ใช้เวลาประมวลผลรวมทั้งสิ้น: {total_time_taken} วินาที*")
            
        # 📌 ส่งตัวแปร references ทั้งชุดเข้าไปเก็บลง CSV
        try:
            log_input_data = original_url if original_url else news_content
            save_system_log(input_method_used, log_input_data, search_query, references, result, total_time_taken)
        except Exception:
            pass