import streamlit as st
import feedparser
import urllib.parse
import sqlite3
import requests
import os
import re
import urllib3

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = "8606963961:AAH7AkdcYuj8a5GIrbnIABSI2XLPsqDFOEg"
TELEGRAM_CHAT_ID = "590917314"

SAVED_KEYWORDS = [
    "삼성", "에스원", "집회", "테러", "이재용",
    "홍라희", "이서현", "김재열", "리움미술관", "호암미술관"
]

BREAK_KEYWORDS = ["속보", "긴급", "breaking", "Breaking"]

@st.cache_resource
def init_db():
    conn = sqlite3.connect("monitoring.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sent_news (link TEXT PRIMARY KEY, title TEXT, keyword TEXT, sent_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS monitor_log (id INTEGER PRIMARY KEY AUTOINCREMENT, log_time TIMESTAMP, keyword TEXT, title TEXT, link TEXT)''')
    conn.commit()
    return conn

db_conn = init_db()

def is_news_sent(link):
    c = db_conn.cursor()
    c.execute("SELECT 1 FROM sent_news WHERE link = ?", (link,))
    return c.fetchone() is not None

def save_sent_news(link, title, keyword):
    c = db_conn.cursor()
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR IGNORE INTO sent_news (link, title, keyword, sent_at) VALUES (?, ?, ?, ?)", (link, title, keyword, now_kst))
    db_conn.commit()

def save_monitor_log(keyword, title, link):
    c = db_conn.cursor()
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO monitor_log (log_time, keyword, title, link) VALUES (?, ?, ?, ?)", (now_kst, keyword, title, link))
    db_conn.commit()

def get_recent_logs(limit=5):
    c = db_conn.cursor()
    c.execute("SELECT log_time, keyword, title FROM monitor_log ORDER BY id DESC LIMIT ?", (limit,))
    return c.fetchall()

def get_sent_count():
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM sent_news")
    return c.fetchone()[0]

st.set_page_config(page_title="인텔리전스 뉴스 모니터링", layout="wide")

defaults = {
    "active_search_keywords": [],
    "run_search": False,
    "monitoring": False,
    "monitor_keywords": [],
    "monitor_start_time": None,
    "s_queries": "", "s_excl": "",
    "m_queries": "", "m_excl": ""
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def generate_queries(queries_text, excl_text):
    queries = []
    excl_words = excl_text.split() if excl_text.strip() else []
    excl_part = " ".join(f"-{w}" for w in excl_words)
    
    lines = queries_text.split('\n')
    for line in lines:
        clean_line = re.sub(r'^(\d+\.|-|\*)\s*', '', line.strip()).strip()
        if clean_line:
            q = " ".join(filter(None, [clean_line, excl_part])).strip()
            if q not in queries:
                queries.append(q)
    return queries

def trigger_saved_search(kw):
    st.session_state.active_search_keywords = [kw]
    st.session_state.run_search = True
    st.session_state.s_queries = ""
    st.session_state.s_excl = ""

def trigger_manual_search():
    st.session_state.run_search = True
    queries = generate_queries(st.session_state.s_queries, st.session_state.s_excl)
    if queries:
        st.session_state.active_search_keywords = queries
        
    st.session_state.s_queries = ""
    st.session_state.s_excl = ""

def add_monitor_keyword():
    queries = generate_queries(st.session_state.m_queries, st.session_state.m_excl)
    for q in queries:
        if q and q not in st.session_state.monitor_keywords:
            st.session_state.monitor_keywords.append(q)
            
    st.session_state.m_queries = ""
    st.session_state.m_excl = ""

def remove_monitor_keyword(k):
    st.session_state.monitor_keywords.remove(k)

if st.session_state.monitoring:
    st_autorefresh(interval=60000, limit=None, key="monitor_refresh")

st.markdown("<h1 style='text-align:center;'>📊 [미술관TS그룹] 뉴스 모니터링 대시보드</h1>", unsafe_allow_html=True)
st.divider()

left, center, right = st.columns([2, 5, 2])

with left:
    st.subheader("🔎 검색 패널")
    cols = st.columns(2)
    for i, kw in enumerate(SAVED_KEYWORDS):
        with cols[i % 2]:
            st.button(kw, use_container_width=True, on_click=trigger_saved_search, args=(kw,))

    st.write("---")
    st.write("### 🎛️ 직관적인 맞춤 검색")
    st.caption("메모장처럼 줄을 바꿔서 검색어를 입력하세요.")
    
    st.text_area(
        "🟢 검색어 목록 (엔터로 줄바꿈)", 
        placeholder="예)\n1. 삼성\n2. 에스원\n3. 삼성 집회\n4. 삼성 테러", 
        key="s_queries",
        height=150
    )
    
    st.text_input("🔴 제외할 단어 (선택)", placeholder="예) 야구 스포츠", key="s_excl", on_change=trigger_manual_search)

    period = st.selectbox("기간", ["1시간", "24시간", "48시간", "7일", "전체"])
    max_news = st.slider("최대 뉴스 (키워드당)", 10, 100, 30)

    st.button("🔍 위 조건으로 검색", use_container_width=True, on_click=trigger_manual_search)

with right:
    st.subheader("📡 감시 패널")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🟢 시작", use_container_width=True):
            st.session_state.monitoring = True
            st.session_state.monitor_start_time = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    with c2:
        if st.button("🔴 종료", use_container_width=True):
            st.session_state.monitoring = False
            
    if st.button("🔔 텔레그램 테스트 발송", use_container_width=True):
        test_msg = "🚨 테스트 알림: [시스템 점검]\n\n"
        test_msg += "📰 텔레그램 봇 연동 테스트입니다.\n\n"
        test_msg += "🔗 https://news.google.com"
        
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": test_msg},
                timeout=10,
                verify=False 
            )
            if res.status_code == 200:
                st.toast("✅ 텔레그램으로 테스트 메시지를 성공적으로 전송했습니다!")
            else:
                st.error("❌ 전송 실패. 토큰이나 Chat ID를 확인해주세요.")
        except Exception as e:
            st.error(f"❌ 통신 오류가 발생했습니다: {e}")

    st.divider()
    
    with st.expander("➕ 감시 키워드 일괄 추가", expanded=True):
        st.caption("💡 팁: '속보 삼성' 처럼 단어를 붙여 쓰면 텔레그램 알림을 정교하게 제어할 수 있습니다.")
        st.text_area(
            "🟢 추가할 키워드 목록", 
            key="m_queries", 
            placeholder="예)\n삼성\n속보 에스원\n삼성 집회",
            height=100
        )
        st.text_input("🔴 제외할 단어", placeholder="예) 야구 스포츠 라이온즈", key="m_excl")
        
        st.button("목록에 일괄 추가", on_click=add_monitor_keyword)

    st.write("### 감시 목록")
    for i, k in enumerate(st.session_state.monitor_keywords):
        c1, c2 = st.columns([4, 1])
        with c1:
            if "-" in k:
                parts = k.split("-")
                main_kw = parts[0].strip()
                excl_kws = ", ".join([p.strip() for p in parts[1:]])
                st.markdown(f"**{main_kw}** *(🚫 제외: {excl_kws})*")
            else:
                st.write(f"**{k}**")
                
        with c2:
            st.button("❌", key=f"rm_{i}", on_click=remove_monitor_keyword, args=(k,))

    st.divider()
    st.write("🟢 AI 감시중 (60초 갱신)" if st.session_state.monitoring else "🔴 중지됨")
    st.write(f"DB 누적 전송: {get_sent_count()}건")

    for log in get_recent_logs(5):
        time_str = log[0].split(" ")[1][:5]
        st.caption(f"{time_str} | {log[1]}")
        st.write(f"- {log[2][:20]}...")

now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
period_map = {
    "1시간": timedelta(hours=1), "24시간": timedelta(hours=24),
    "48시간": timedelta(hours=48), "7일": timedelta(days=7),
}
limit = now - period_map.get(period, timedelta(days=9999)) if period != "전체" else None

@st.cache_data(ttl=300)
def fetch_feed(raw_keyword):
    url = (
        "https://news.google.com/rss/search?q="
        f"{urllib.parse.quote(raw_keyword)}"
        "&hl=ko&gl=KR&ceid=KR:ko"
    )
    return raw_keyword, feedparser.parse(url)

def process_news(keywords):
    result = []
    if not keywords: return result

    with ThreadPoolExecutor(max_workers=5) as ex:
        feeds = ex.map(fetch_feed, keywords)

    for kw, feed in feeds:
        seen = set()
        for n in feed.entries:
            title = n.title
            link = n.link
            if title in seen: continue
            seen.add(title)

            try:
                pub = parsedate_to_datetime(n.published)
                pub = pub.astimezone(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
            except: continue

            if limit and pub < limit: continue

            breaking = any(b.lower() in title.lower() for b in BREAK_KEYWORDS)
            result.append({
                "title": title, "link": link, "keyword": kw,
                "date": pub, "breaking": breaking
            })
    return result

if st.session_state.monitoring and st.session_state.monitor_keywords and st.session_state.monitor_start_time:
    monitor_data = process_news(st.session_state.monitor_keywords)
    start = st.session_state.monitor_start_time

    for n in monitor_data:
        if n["date"] <= start: continue

        if not is_news_sent(n["link"]):
            
            alert_icon = "🚨" if n["breaking"] else "🔔"
            tg_msg = f"{alert_icon} 새 기사 감지: [{n['keyword']}]\n\n"
            tg_msg += f"📰 {n['title']}\n\n"
            tg_msg += f"🔗 {n['link']}"
            
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    data={"chat_id": TELEGRAM_CHAT_ID, "text": tg_msg},
                    timeout=10,
                    verify=False  
                )
            except:
                pass

            save_sent_news(n["link"], n["title"], n["keyword"])
            save_monitor_log(n["keyword"], n["title"], n["link"])

with center:
    if st.session_state.run_search and st.session_state.active_search_keywords:
        
        grouped_data = {kw: [] for kw in st.session_state.active_search_keywords}
        total_searched_count = 0
        
        breaking_news = []
        seen_breaking_links = set()
        
        raw_data = process_news(st.session_state.active_search_keywords)
        
        for d in raw_data:
            kw = d["keyword"]
            if len(grouped_data[kw]) < max_news:
                grouped_data[kw].append(d)
                total_searched_count += 1
                
                if d["breaking"] and d["link"] not in seen_breaking_links:
                    breaking_news.append(d)
                    seen_breaking_links.add(d["link"])
                
        breakdown_text = ", ".join([f"{kw} {len(articles)}건" for kw, articles in grouped_data.items()])
        
        st.subheader(f"📰 뉴스 검색 결과 (총 {total_searched_count}건) 🔹 `{breakdown_text}`")
        
        if breaking_news:
            with st.expander(f"🚨 **키워드 통합 주요 속보 ({len(breaking_news)}건)**", expanded=True):
                st.error("💡 아래는 검색된 전체 키워드 중 '속보/긴급'이 포함된 주요 기사입니다.")
                breaking_news.sort(key=lambda x: x["date"], reverse=True)
                for d in breaking_news:
                    st.markdown(f"#### 🚨 [{d['title']}]({d['link']})")
                    st.caption(f"검색된 키워드: {d['keyword']} | {d['date'].strftime('%Y-%m-%d %H:%M')}")
        
        for kw, articles in grouped_data.items():
            is_expanded = len(articles) > 0
            
            with st.expander(f"📌 검색 키워드: **{kw}** ({len(articles)}건)", expanded=is_expanded):
                if not articles:
                    st.info("이 키워드에 해당하는 기사나 속보가 없습니다.")
                else:
                    articles.sort(key=lambda x: x["date"], reverse=True)
                    for d in articles:
                        icon = "🚨 " if d["breaking"] else ""
                        st.markdown(f"#### {icon}[{d['title']}]({d['link']})")
                        st.caption(f"{d['date'].strftime('%Y-%m-%d %H:%M')}")
    else:
        if st.session_state.run_search:
            st.warning("입력된 검색어가 없습니다.")
        else:
            st.info("좌측에서 키워드를 선택하거나 단어를 입력한 후 검색해 보세요.")
