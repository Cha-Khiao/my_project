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
from llm import analyze_intent_and_plan_search, analyze_news_with_qwen

# ================= 1. ตั้งค่าหน้าจอ & CSS =================
st.set_page_config(page_title="AI Fact-Checker", page_icon="🛡️", layout="centered", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
    h1, h2, h3, h4, h5, h6, p, a, button, input, textarea, label, li { font-family: 'Prompt', sans-serif !important; }
    footer {visibility: hidden;} 
    .stAlert {border-radius: 12px;}
    .stButton>button { border-radius: 8px !important; font-weight: 500 !important; padding: 0.5rem 2rem !important; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #1e3a8a !important; color: #ffffff !important; border: none !important; transition: all 0.3s; }
    .stMarkdown a { word-wrap: break-word; color: #2563eb !important; text-decoration: none !important; font-weight: 500 !important; }
    .badge-tier-0 { background-color: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 600;}
    .badge-tier-1 { background-color: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 600;}
    .badge-tier-2 { background-color: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 600;}
    .badge-tier-3 { background-color: #f1f5f9; color: #475569; padding: 2px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 600;}
    </style>
""", unsafe_allow_html=True)

# ================= 2. แถบด้านข้าง (Sidebar) =================
with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: #1e3a8a;'>🛡️ AI Fact-Checker</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 0.9rem; opacity: 0.8;'>ระบบวิเคราะห์ความน่าเชื่อถือด้วย RAG</p>", unsafe_allow_html=True)
    st.divider()
    
    st.markdown("### 🏛️ สถาปัตยกรรม (Fast-Track RAG)")
    st.info("""
    **1. Hybrid Search (Exa + Serper):** สืบค้นขนานกันเพื่อดึงข้อมูลจากเว็บรัฐบาลและสื่อหลัก
    **2. Deterministic Scoring:** AI แยกแยะ Fact และ Python คำนวณเปอร์เซ็นต์ความน่าเชื่อถือ
    """)
    
    with st.expander("ℹ️ ประเภทแหล่งข้อมูล (Source Categories)"):
        st.markdown("""
        *   🏛️ **แหล่งข้อมูลปฐมภูมิ:** หน่วยงานรัฐ (.go.th, .gov) (ความน่าเชื่อถือสูงสุด)
        *   🛡️ **ศูนย์ตรวจสอบข้อเท็จจริง:** ศูนย์ต่อต้านข่าวปลอมต่างๆ (มีน้ำหนักการหักล้างสูงสุด)
        *   📰 **สื่อมวลชนกระแสหลัก:** สำนักข่าวที่ได้รับการรับรอง (น้ำหนักปานกลาง)
        *   📄 **แหล่งข้อมูลทั่วไป:** เว็บไซต์อื่นๆ (น้ำหนักต่ำ)
        """)
        
    st.divider()
    if st.button("🗑️ ล้างข้อมูลระบบ (Clear Memory)", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ ล้างหน่วยความจำสำเร็จ!")

# ================= 3. ฟังก์ชันคำนวณคะแนน (Python Math) =================
def calculate_trust_score(evidence_assessments, references):
    base_score = 50.0 
    supported_points = []
    conflicting_points = []
    
    for ev in evidence_assessments:
        ref_id = ev.get('ref_id', 0)
        # ดักจับค่าให้เป็นพิมพ์เล็กทั้งหมดเพื่อป้องกัน AI Gen เพี้ยน
        stance = str(ev.get('stance', 'neutral')).lower().strip()
        
        if not str(ref_id).isdigit() or int(ref_id) < 1 or int(ref_id) > len(references):
            continue
            
        ref = references[int(ref_id) - 1]
        tier = ref.get('tier', 3)
        
        if stance == 'support':
            if tier == 0: base_score += 25
            elif tier == 2: base_score += 30
            elif tier == 1: base_score += 15
            else: base_score += 5
            supported_points.append(f"[{ref['title']}]({ref['href']})")
            
        elif stance == 'contradict':
            if tier == 0: base_score -= 30
            elif tier == 2: base_score -= 35
            elif tier == 1: base_score -= 20
            else: base_score -= 10
            conflicting_points.append(f"[{ref['title']}]({ref['href']})")
            
    final_score = max(10, min(95, int(base_score)))
    
    if final_score >= 80: return final_score, "#10b981", "สอดคล้องกับแหล่งอ้างอิงชัดเจน", supported_points, conflicting_points
    elif final_score >= 60: return final_score, "#34d399", "มีแนวโน้มสอดคล้อง", supported_points, conflicting_points
    elif final_score >= 40: return final_score, "#f59e0b", "ข้อมูลก้ำกึ่ง / ขัดแย้งบางส่วน", supported_points, conflicting_points
    elif final_score >= 20: return final_score, "#ef4444", "บิดเบือนไปจากสื่อหลัก", supported_points, conflicting_points
    else: return final_score, "#b91c1c", "ข่าวปลอม / ขัดแย้งอย่างสิ้นเชิง", supported_points, conflicting_points

def get_tier_badge(tier):
    if tier == 0: return '<span class="badge-tier-0">🏛️ แหล่งข้อมูลปฐมภูมิ</span>'
    if tier == 1: return '<span class="badge-tier-1">📰 สื่อมวลชนกระแสหลัก</span>'
    if tier == 2: return '<span class="badge-tier-2">🛡️ ศูนย์ตรวจสอบข้อเท็จจริง</span>'
    return '<span class="badge-tier-3">📄 แหล่งข้อมูลทั่วไป</span>'

# ================= 4. ส่วนแสดงผล UI =================
st.markdown("<div style='text-align: center; margin-bottom: 2rem;'><h1 style='font-size: 2.5rem; margin-bottom: 0px; color: #1e3a8a;'>🛡️ AI Fact-Checker</h1><p style='font-size: 1.1rem; opacity: 0.8; margin-top: 5px;'>ระบบวิเคราะห์และเปรียบเทียบความน่าเชื่อถือด้วย RAG</p></div>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🌐 ตรวจสอบจากลิงก์ (URL)", "📄 ตรวจสอบจากข้อความ"])
news_content, url_input = "", ""

with tab1:
    url_input = st.text_input("🔗 วางลิงก์ข่าว หรือ โพสต์:", placeholder="ตัวอย่าง: https://www.facebook.com/...")
    if st.button("🔍 เริ่มการประเมินจากลิงก์", type="primary", use_container_width=True):
        if url_input:
            with st.status("🚀 กำลังสกัดเนื้อหาจากเว็บไซต์ปลายทาง...", expanded=True) as status:
                extracted_data = extract_text_from_url(url_input)
                news_content = extracted_data.get("error", extracted_data.get("content", "")) if isinstance(extracted_data, dict) else str(extracted_data)
                status.update(label="✅ สกัดเนื้อหาสำเร็จ", state="complete", expanded=False)
        else: st.warning("⚠️ กรุณาระบุ URL")

with tab2:
    text_input = st.text_area("📄 วางข้อความ ข่าวลือ ที่ต้องการตรวจสอบ:", height=150)
    if st.button("🔍 เริ่มการประเมินข้อความ", type="primary", use_container_width=True):
        if text_input.strip(): news_content = text_input
        else: st.warning("⚠️ กรุณาระบุเนื้อหา")

# ================= 5. ส่วนประมวลผลหลัก =================
if news_content:
    if "Error" in news_content or "VIDEO_DETECTED" in news_content or "GAMBLING_DETECTED" in news_content:
        st.error(f"⚠️ ระบบไม่สามารถประมวลผลได้: {news_content[:100]}...")
        st.stop()
        
    start_process_time = time.time()
    
    with st.status("🧠 AI กำลังสกัดคีย์เวิร์ด (Step 1/3)...", expanded=True) as main_status:
        action, search_query, topic_summary, locations, core_keywords, target_year = analyze_intent_and_plan_search(news_content)
        
        if action == "DROP":
            main_status.update(label="🛑 ยุติการตรวจสอบ", state="complete")
            st.info(f"**ประเมินว่า:** {topic_summary}\n\nระบบไม่ทำการสืบค้นข้อมูลสำหรับเนื้อหาที่เป็นความคิดเห็นส่วนบุคคลหรือเรื่องส่วนตัว เพื่อประหยัดทรัพยากร")
            st.stop()
            
        st.write(f"🔑 คีย์เวิร์ดที่ใช้: `{', '.join(core_keywords)}`")
        main_status.update(label="🌐 กำลังสืบค้นด้วย Exa และ Serper ขนานกัน (Step 2/3)...")
        
        references = search_news_references(search_query, locations, core_keywords, target_year)
        if not references:
            main_status.update(label="⚠️ ไม่พบแหล่งข้อมูลอ้างอิงที่ผ่านเกณฑ์", state="error")
            st.warning("ไม่พบหลักฐานอ้างอิงจากแหล่งที่เชื่อถือได้ หรือข่าวสารที่ตรงกับข้อความนี้ ระบบจึงไม่สามารถยืนยันข้อเท็จจริงได้")
            st.stop()
            
        st.write(f"✅ พบข้อมูล {len(references)} แหล่งที่นำมาเปรียบเทียบ")
        main_status.update(label="⚖️ AI กำลังตรวจสอบความสอดคล้อง (Step 3/3)...")
        
        now = datetime.datetime.now()
        months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
        ai_dict = analyze_news_with_qwen(news_content, references, f"{now.day} {months_th[now.month - 1]} {now.year + 543}")
        
        total_time = round(time.time() - start_process_time, 2)
        main_status.update(label=f"✨ ประมวลผลเสร็จสิ้นใน {total_time} วินาที!", state="complete", expanded=False)

    # ================= 6. คำนวณและแสดงผลลัพธ์ =================
    final_score, color, label, supp_pts, conf_pts = calculate_trust_score(ai_dict.get('evidence_assessments', []), references)
    
    st.markdown(f"""
    <div style="text-align: center; padding: 25px; background-color: {color}15; border-radius: 12px; border: 2px solid {color}40; margin-bottom: 20px;">
        <p style="margin: 0; font-size: 1.1rem; font-weight: 500; color: #334155;">ดัชนีความน่าเชื่อถือ</p>
        <h1 style="margin: 10px 0; font-size: 5.5rem; color: {color}; font-weight: 700; line-height: 1;">{final_score}%</h1>
        <span style="background-color: {color}; color: white; padding: 6px 20px; border-radius: 20px; font-weight: 500;">{label}</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"### 🎯 บทสรุปจาก AI:\n**{ai_dict.get('verdict_summary', 'ไม่มีข้อมูลสรุป')}**")
    
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("<h4 style='color: #15803d;'>✅ แหล่งอ้างอิงที่สนับสนุน</h4>", unsafe_allow_html=True)
            if supp_pts:
                for pt in supp_pts: st.markdown(f"- {pt}")
            else: st.markdown("- *ไม่มี*")
    with col2:
        with st.container(border=True):
            st.markdown("<h4 style='color: #b91c1c;'>❌ แหล่งอ้างอิงที่หักล้าง</h4>", unsafe_allow_html=True)
            if conf_pts:
                for pt in conf_pts: st.markdown(f"- {pt}")
            else: st.markdown("- *ไม่มี*")
            
    # ================= 7. Audit Trail =================
    with st.expander("🔍 ตรวจสอบเบื้องหลังการทำงาน (Audit Trail)"):
        st.markdown("ระบบวิเคราะห์ความน่าเชื่อถืออย่างโปร่งใส โดยกำหนดค่าคะแนนตามหมวดหมู่ของแหล่งอ้างอิงที่สนับสนุนหรือขัดแย้ง")
        st.markdown(f"**สมมติฐานการสืบค้น:** {topic_summary}")
        for idx, ref in enumerate(references):
            badge = get_tier_badge(ref.get('tier', 3))
            st.markdown(f"**[{idx+1}]** {badge} [{ref['title']}]({ref['href']})")