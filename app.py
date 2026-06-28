import streamlit as st
import re
import datetime
from scraper import extract_text_from_url
from search import search_news_references
from llm import analyze_news_with_qwen

st.set_page_config(page_title="News Fact-Checker", page_icon="🕵️‍♂️", layout="centered")
st.title("🕵️‍♂️ ระบบวิเคราะห์ความน่าเชื่อถือของข่าวออนไลน์")
st.markdown("**โมเดล:** Qwen-2.5 (7B) | **สืบค้น:** Google News RSS")

tab1, tab2 = st.tabs(["🔗 ตรวจสอบจากลิงก์ (URL)", "📝 วางข้อความ"])

news_content = ""
original_url = "" 
url_input = "" 

with tab1:
    url_input = st.text_input("ใส่ลิงก์ข่าว หรือ ลิงก์โซเชียลมีเดีย:")
    if st.button("🔍 วิเคราะห์จากลิงก์", type="primary"):
        if url_input:
            with st.spinner("⏳ กำลังสกัดเนื้อหา และทะลวงหาลิงก์ข่าวจริง..."):
                extracted_data = extract_text_from_url(url_input)
                
                if isinstance(extracted_data, dict):
                    if "error" in extracted_data:
                        st.error(extracted_data["error"])
                    else:
                        news_content = extracted_data.get("content", "")
                        original_url = extracted_data.get("actual_url", url_input)
                else:
                    if extracted_data.startswith("Error"):
                        st.error(extracted_data)
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
            news_content = text_input
            original_url = "" 
        else:
            st.warning("กรุณาใส่เนื้อหาข่าวก่อนครับ")

# ================= กระบวนการทำงานหลัก =================
if news_content:
    st.divider()
    
    display_url = original_url if original_url else url_input
    
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    now = datetime.datetime.now()
    current_date_str = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
    
    # 📌 สกัดคีย์เวิร์ด
    text_for_keyword = news_content
    if "[เนื้อหาข่าวจริง" in news_content:
        text_for_keyword = news_content.split("]:\n")[-1]
        
    text_clean = re.sub(r'http[s]?://\S+', '', text_for_keyword)
    text_clean = re.sub(r'\[.*?\][:\s]*', '', text_clean)
    text_clean = re.sub(r'(?i)(title|description|หัวข้อ|รายละเอียด|พรีวิว)[:\s\-]*', '', text_clean)
    
    boilerplate_words = ['ไทยรัฐ', 'thairath', 'ข่าวสด', 'khaosod', 'มติชน', 'matichon', 'หน้าแรก', 'เข้าสู่ระบบ', 'สมัครสมาชิก', 'ข่าวล่าสุด']
    
    valid_lines = []
    for line in text_clean.split('\n'):
        clean_line = re.sub(r'[^\w\sก-๙]', ' ', line)
        clean_line = " ".join(clean_line.split()).strip()
        
        if len(clean_line) > 20:
            is_boilerplate = any(bp in clean_line.lower() for bp in boilerplate_words)
            if not is_boilerplate or len(clean_line) > 50: 
                valid_lines.append(clean_line)
            
    if valid_lines:
        # 📌 ขยายความยาวเป็น 120 ตัวอักษร เพื่อไม่ให้รายละเอียดสำคัญตกหล่น
        search_query = valid_lines[0][:120].strip() 
    else:
        fallback_text = re.sub(r'[^\w\sก-๙]', ' ', text_clean)
        search_query = " ".join(fallback_text.split())[:120].strip()
        
    st.caption(f"🔑 **คีย์เวิร์ดสืบค้น:** {search_query}")
    
    with st.spinner("🌐 กำลังสืบค้นเปรียบเทียบจาก Google News..."):
        references = search_news_references(search_query)
        if not references:
            st.warning("⚠️ ไม่พบข่าวนี้ในสำนักข่าวหลักบนอินเทอร์เน็ต (อาจเป็นข่าวปลอม ข่าวลือ หรือข่าวเฉพาะกลุ่ม)")
            
    with st.spinner("🧠 Qwen-2.5 กำลังวิเคราะห์..."):
        result = analyze_news_with_qwen(news_content, references, current_date_str)
        
        st.subheader("📊 รายงานผลการประเมินความน่าเชื่อถือ")
        
        st.markdown(result)
        
        st.markdown("## 🌐 3. แหล่งข่าวอ้างอิงสำหรับตรวจสอบ")
        
        if references:
            for idx, r in enumerate(references):
                st.write(f"{idx+1}. [{r['title']}]({r['href']})")
        else:
            st.write("*ไม่พบแหล่งอ้างอิงจากสำนักข่าวหลักบนอินเทอร์เน็ต*")