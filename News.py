import streamlit as st

import feedparser

import urllib.parse

import sqlite3

import requests

import re

import urllib3

import difflib



from concurrent.futures import ThreadPoolExecutor

from datetime import datetime, timedelta

from email.utils import parsedate_to_datetime

from zoneinfo import ZoneInfo

from streamlit_autorefresh import st_autorefresh



urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)



st.set_page_config(page_title="미술관TS그룹 뉴스 모니터링", layout="wide")



# 입력창 테두리 및 배경색 강조 스타일 (HTML 태그 깨짐 방지를 위해 chr(60), chr(62) 사용)

_lt, _gt = chr(60), chr(62)

st.markdown(

    f"""{_lt}style{_gt}

    div[data-baseweb="input"] {_gt} div,

    div[data-baseweb="textarea"] {_gt} div {{

        background-color: rgba(128, 128, 128, 0.08) !important;

        border: 1.5px solid rgba(128, 128, 128, 0.45) !important;

        border-radius: 6px !important;

    }}

    div[data-baseweb="input"]:focus-within {_gt} div,

    div[data-baseweb="textarea"]:focus-within {_gt} div {{

        border: 2px solid #2b6cb0 !important;

        background-color: rgba(43, 108, 176, 0.05) !important;

    }}

    {_lt}/style{_gt}""",

    unsafe_allow_html=True

)



TELEGRAM_TOKEN = "8606963961:AAH7AkdcYuj8a5GIrbnIABSI2XLPsqDFOEg"

TELEGRAM_CHAT_ID = "590917314"



BREAK_KEYWORDS = ["속보", "긴급", "breaking", "Breaking"]



# ---------------------------------------------------------

# DB 초기화 및 영구 저장 함수 (감시 상태까지 DB에 영구 저장)

# ---------------------------------------------------------

@st.cache_resource

def init_db():

    conn = sqlite3.connect("monitoring.db", check_same_thread=False)

    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS sent_news (link TEXT PRIMARY KEY, title TEXT, keyword TEXT, sent_at TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS monitor_log (id INTEGER PRIMARY KEY AUTOINCREMENT, log_time TIMESTAMP, keyword TEXT, title TEXT, link TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS saved_lists (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        category TEXT,

        keyword TEXT,

        UNIQUE(category, keyword)

    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS app_state (

        key TEXT PRIMARY KEY,

        value TEXT

    )''')

    conn.commit()

    return conn



db_conn = init_db()



def get_app_state(key, default=""):

    c = db_conn.cursor()

    c.execute("SELECT value FROM app_state WHERE key = ?", (key,))

    row = c.fetchone()

    return row[0] if row else default



def set_app_state(key, value):

    c = db_conn.cursor()

    c.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)", (key, str(value)))

    db_conn.commit()



def get_saved_list(category):

    c = db_conn.cursor()

    c.execute("SELECT keyword FROM saved_lists WHERE category = ? ORDER BY id ASC", (category,))

    return [row[0] for row in c.fetchall()]



def add_to_saved_list(category, keyword):

    c = db_conn.cursor()

    c.execute("INSERT OR IGNORE INTO saved_lists (category, keyword) VALUES (?, ?)", (category, keyword))

    db_conn.commit()



def remove_from_saved_list(category, keyword):

    c = db_conn.cursor()

    c.execute("DELETE FROM saved_lists WHERE category = ? AND keyword = ?", (category, keyword))

    db_conn.commit()



def clear_saved_list(category):

    c = db_conn.cursor()

    c.execute("DELETE FROM saved_lists WHERE category = ?", (category,))

    db_conn.commit()



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



def clean_title(title):

    title = re.sub(r'\[.*?\]|\(.*\)', '', title)

    title = re.split(r'[-|\||ⓒ]', title)[0]

    return title.strip()



def get_recent_sent_titles(keyword, limit=30):

    c = db_conn.cursor()

    c.execute("SELECT title FROM sent_news WHERE keyword = ? ORDER BY sent_at DESC LIMIT ?", (keyword, limit))

    return [row[0] for row in c.fetchall()]



def is_similar_to_recent(new_title, recent_titles, threshold=0.6):

    cleaned_new = clean_title(new_title)

    for old_title in recent_titles:

        cleaned_old = clean_title(old_title)

        ratio = difflib.SequenceMatcher(None, cleaned_new, cleaned_old).ratio()

        if ratio >= threshold:

            return True

    return False



# ---------------------------------------------------------

# 세션 상태(Session State) 초기화 및 DB 감시 상태 복원

# ---------------------------------------------------------

saved_mon = get_app_state("monitoring", "0") == "1"

saved_start_str = get_app_state("monitor_start_time", "")

saved_start_dt = None

if saved_start_str:

    try:

        saved_start_dt = datetime.strptime(saved_start_str, "%Y-%m-%d %H:%M:%S")

    except Exception:

        saved_start_dt = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)



defaults = {

    "run_search": False,

    "active_search_keywords": [],

    "active_excl_keywords": [],

    "monitoring": saved_mon,

    "monitor_start_time": saved_start_dt,

    "s_input": "",

    "e_input": "",

    "m_input": ""

}



for k, v in defaults.items():

    if k not in st.session_state:

        st.session_state[k] = v



# ---------------------------------------------------------

# 키워드 추가 / 삭제 / 검색 / 감시 제어 콜백 함수

# ---------------------------------------------------------

def parse_multiline_input(text):

    items = []

    for line in text.split('\n'):

        clean_line = re.sub(r'^(\d+\.|-|\*)\s*', '', line.strip()).strip()

        if clean_line and clean_line not in items:

            items.append(clean_line)

    return items



def parse_exclude_input(text):

    items = []

    for token in re.split(r'[\s,]+', text.strip()):

        clean_token = token.lstrip('-').strip()

        if clean_token and clean_token not in items:

            items.append(clean_token)

    return items



def cb_add_search_kw():

    for kw in parse_multiline_input(st.session_state.s_input):

        add_to_saved_list("search", kw)

    st.session_state.s_input = ""



def cb_rm_search_kw(kw):

    remove_from_saved_list("search", kw)



def cb_clear_search_kw():

    clear_saved_list("search")

    st.session_state.run_search = False



def cb_add_exclude_kw():

    for kw in parse_exclude_input(st.session_state.e_input):

        add_to_saved_list("exclude", kw)

    st.session_state.e_input = ""



def cb_rm_exclude_kw(kw):

    remove_from_saved_list("exclude", kw)



def cb_clear_exclude_kw():

    clear_saved_list("exclude")



def cb_add_monitor_kw():

    for kw in parse_multiline_input(st.session_state.m_input):

        add_to_saved_list("monitor", kw)

    st.session_state.m_input = ""



def cb_rm_monitor_kw(kw):

    remove_from_saved_list("monitor", kw)



def cb_clear_monitor_kw():

    clear_saved_list("monitor")



def cb_start_monitoring():

    if st.session_state.m_input.strip():

        cb_add_monitor_kw()

    if st.session_state.e_input.strip():

        cb_add_exclude_kw()

    now_dt = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)

    st.session_state.monitoring = True

    st.session_state.monitor_start_time = now_dt

    set_app_state("monitoring", "1")

    set_app_state("monitor_start_time", now_dt.strftime("%Y-%m-%d %H:%M:%S"))



def cb_stop_monitoring():

    st.session_state.monitoring = False

    set_app_state("monitoring", "0")



def trigger_manual_search():

    if st.session_state.s_input.strip():

        cb_add_search_kw()

    if st.session_state.e_input.strip():

        cb_add_exclude_kw()

    st.session_state.active_search_keywords = get_saved_list("search")

    st.session_state.active_excl_keywords = get_saved_list("exclude")

    st.session_state.run_search = True



# ---------------------------------------------------------

# 뉴스 RSS 수집 및 통합 제외 단어 필터링 (타임아웃 적용으로 먹통 방지)

# ---------------------------------------------------------

def fetch_feed(query_str):

    url = (

        "https://news.google.com/rss/search?q="

        f"{urllib.parse.quote(query_str)}"

        "&hl=ko&gl=KR&ceid=KR:ko"

    )

    try:

        resp = requests.get(

            url,

            headers={"User-Agent": "Mozilla/5.0"},

            timeout=8,

            verify=False

        )

        return feedparser.parse(resp.content)

    except Exception:

        return feedparser.FeedParserDict(entries=[])



def build_query_with_excludes(base_kw, excl_list):

    excl_part = " ".join(f"-{w}" for w in excl_list if w.strip())

    return " ".join(filter(None, [base_kw.strip(), excl_part])).strip()



def process_news(base_keywords, excl_keywords, limit_time=None):

    result = []

    if not base_keywords:

        return result



    queries = [build_query_with_excludes(kw, excl_keywords) for kw in base_keywords]



    with ThreadPoolExecutor(max_workers=5) as ex:

        feeds = list(ex.map(fetch_feed, queries))



    for base_kw, feed in zip(base_keywords, feeds):

        seen = set()

        for n in getattr(feed, "entries", []):

            title = n.title

            link = n.link

            if title in seen:

                continue

            seen.add(title)



            if any(ex_w.lower() in title.lower() for ex_w in excl_keywords if ex_w.strip()):

                continue



            try:

                pub = parsedate_to_datetime(n.published)

                pub = pub.astimezone(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)

            except Exception:

                continue



            if limit_time and pub < limit_time:

                continue



            breaking = any(b.lower() in title.lower() for b in BREAK_KEYWORDS)

            result.append({

                "title": title,

                "link": link,

                "keyword": base_kw,

                "date": pub,

                "breaking": breaking

            })

    return result



# ---------------------------------------------------------

# 자동 새로고침 (감시 모드 작동 중일 때 60초 간격)

# ---------------------------------------------------------

if st.session_state.monitoring:

    st_autorefresh(interval=60000, limit=None, key="monitor_refresh")



st.title("📊 [미술관TS그룹] 뉴스 모니터링 대시보드")

st.divider()



now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)



search_keywords_db = get_saved_list("search")

exclude_keywords_db = get_saved_list("exclude")

monitor_keywords_db = get_saved_list("monitor")



left, center, right = st.columns([2.2, 4.6, 2.2])



# =========================================================

# 좌측 패널: 1) 통합 제외 단어 (상단) + 2) 맞춤 검색 (하단)

# =========================================================

with left:

    # 1. 통합 제외 단어

    with st.container(border=True):

        st.subheader("🚫 통합 제외 단어")

        st.text_input(

            "제외 단어 입력",

            key="e_input",

            placeholder="입력하세요...",

            label_visibility="collapsed",

            on_change=cb_add_exclude_kw

        )

        st.button("➕ 제외 단어 추가", use_container_width=True, on_click=cb_add_exclude_kw)



        if exclude_keywords_db:

            st.divider()

            col_e1, col_e2 = st.columns([3, 2])

            with col_e1:

                st.markdown(f"**목록 ({len(exclude_keywords_db)})**")

            with col_e2:

                st.button("전체 삭제", key="clear_e", use_container_width=True, on_click=cb_clear_exclude_kw)



            for i, kw in enumerate(exclude_keywords_db):

                c_kw, c_rm = st.columns([4, 1])

                with c_kw:

                    st.markdown(f"• {kw}")

                with c_rm:

                    st.button("❌", key=f"rm_e_{i}_{kw}", on_click=cb_rm_exclude_kw, args=(kw,))



    # 2. 맞춤 검색

    with st.container(border=True):

        st.subheader("🎛️ 맞춤 검색")

        st.text_area(

            "검색어 입력",

            key="s_input",

            placeholder="입력하세요...",

            label_visibility="collapsed",

            height=90

        )

        st.button("➕ 검색어 추가", use_container_width=True, on_click=cb_add_search_kw)



        if search_keywords_db:

            st.divider()

            col_s1, col_s2 = st.columns([3, 2])

            with col_s1:

                st.markdown(f"**목록 ({len(search_keywords_db)})**")

            with col_s2:

                st.button("전체 삭제", key="clear_s", use_container_width=True, on_click=cb_clear_search_kw)



            for i, kw in enumerate(search_keywords_db):

                c_kw, c_rm = st.columns([4, 1])

                with c_kw:

                    st.markdown(f"• **{kw}**")

                with c_rm:

                    st.button("❌", key=f"rm_s_{i}_{kw}", on_click=cb_rm_search_kw, args=(kw,))



        st.divider()

        c_p1, c_p2 = st.columns(2)

        with c_p1:

            period = st.selectbox("기간", ["1시간", "24시간", "48시간", "7일", "전체"], index=1)

        with c_p2:

            max_news = st.number_input("최대 건수", min_value=10, max_value=100, value=30, step=10)



        st.button("🔍 맞춤 검색 시작", type="primary", use_container_width=True, on_click=trigger_manual_search)



    period_map = {

        "1시간": timedelta(hours=1),

        "24시간": timedelta(hours=24),

        "48시간": timedelta(hours=48),

        "7일": timedelta(days=7),

    }

    search_limit = now - period_map.get(period, timedelta(days=9999)) if period != "전체" else None



# =========================================================

# 우측 패널: 감시 패널 (입력 -> 감시 목록 -> 버튼 -> 감시 상태)

# =========================================================

with right:

    with st.container(border=True):

        st.subheader("📡 감시 패널")



        st.text_area(

            "감시 키워드 입력",

            key="m_input",

            placeholder="입력하세요...",

            label_visibility="collapsed",

            height=90

        )

        st.button("➕ 감시 키워드 추가", use_container_width=True, on_click=cb_add_monitor_kw)



        st.divider()

        col_m1, col_m2 = st.columns([3, 2])

        with col_m1:

            st.markdown(f"**감시 목록 ({len(monitor_keywords_db)})**")

        with col_m2:

            if monitor_keywords_db:

                st.button("전체 삭제", key="clear_m", use_container_width=True, on_click=cb_clear_monitor_kw)



        for i, k in enumerate(monitor_keywords_db):

            c_kw, c_rm = st.columns([4, 1])

            with c_kw:

                st.markdown(f"• **{k}**")

            with c_rm:

                st.button("❌", key=f"rm_m_{i}_{k}", on_click=cb_rm_monitor_kw, args=(k,))



        st.divider()



        # 감시 목록 바로 밑, 감시 중지됨(상태창) 바로 위에 버튼 배치 (콜백 방식으로 타이머 초기화 방지)

        c1, c2 = st.columns(2)

        with c1:

            st.button("🟢 시작", use_container_width=True, on_click=cb_start_monitoring)

        with c2:

            st.button("🔴 종료", use_container_width=True, on_click=cb_stop_monitoring)



        if st.button("🔔 텔레그램 테스트 발송", use_container_width=True):

            test_msg = "🚨 테스트 알림: [시스템 점검]\n\n📰 텔레그램 봇 연동 테스트입니다.\n\n🔗 https://news.google.com"

            try:

                res = requests.post(

                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",

                    data={"chat_id": TELEGRAM_CHAT_ID, "text": test_msg},

                    timeout=10,

                    verify=False

                )

                if res.status_code == 200:

                    st.toast("✅ 전송 완료")

                else:

                    st.error("❌ 전송 실패")

            except Exception as e:

                st.error(f"❌ 오류: {e}")



        # 감시 상태 표시

        if st.session_state.monitoring:

            current_refresh_time = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S")

            st.success(f"🟢 **감시중** (최근 갱신: `{current_refresh_time}`)")

        else:

            st.error("🔴 **감시 중지됨**")



        st.caption(f"DB 누적 전송: {get_sent_count()}건")



        for log in get_recent_logs(5):

            time_str = log[0].split(" ")[1][:5]

            st.caption(f"{time_str} | [{log[1]}] {log[2][:18]}...")



    # 감시 작동 로직

    if st.session_state.monitoring and monitor_keywords_db and st.session_state.monitor_start_time:

        monitor_data = process_news(monitor_keywords_db, exclude_keywords_db)

        start = st.session_state.monitor_start_time



        new_articles_to_send = []

        recent_titles_cache = {}



        for n in monitor_data:

            if n["date"] <= start:

                continue



            if not is_news_sent(n["link"]):

                kw = n["keyword"]

                if kw not in recent_titles_cache:

                    recent_titles_cache[kw] = get_recent_sent_titles(kw)



                recent_titles = recent_titles_cache[kw]



                if is_similar_to_recent(n["title"], recent_titles, threshold=0.6):

                    save_sent_news(n["link"], n["title"], n["keyword"])

                    continue



                new_articles_to_send.append(n)

                recent_titles_cache[kw].insert(0, n["title"])



                save_sent_news(n["link"], n["title"], n["keyword"])

                save_monitor_log(n["keyword"], n["title"], n["link"])



        if new_articles_to_send:

            breaking_count = sum(1 for n in new_articles_to_send if n["breaking"])

            alert_icon = "🚨" if breaking_count > 0 else "🔔"



            tg_msg = f"{alert_icon} 새 기사 감지 ({len(new_articles_to_send)}건)\n\n"



            for n in new_articles_to_send:

                icon = "🚨" if n["breaking"] else "📰"

                tg_msg += f"[{n['keyword']}] {icon} {n['title']}\n🔗 {n['link']}\n\n"



            try:

                requests.post(

                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",

                    data={"chat_id": TELEGRAM_CHAT_ID, "text": tg_msg[:4000]},

                    timeout=10,

                    verify=False

                )

            except Exception:

                pass



# =========================================================

# 중앙 패널: 맞춤 검색 결과 출력

# =========================================================

with center:

    if st.session_state.run_search and search_keywords_db:

        active_kws = search_keywords_db

        active_excls = exclude_keywords_db



        grouped_data = {kw: [] for kw in active_kws}

        total_searched_count = 0



        breaking_news = []

        seen_breaking_links = set()



        raw_data = process_news(active_kws, active_excls, search_limit)



        for d in raw_data:

            kw = d["keyword"]

            if kw in grouped_data and len(grouped_data[kw]) < max_news:

                grouped_data[kw].append(d)

                total_searched_count += 1



                if d["breaking"] and d["link"] not in seen_breaking_links:

                    breaking_news.append(d)

                    seen_breaking_links.add(d["link"])



        breakdown_text = ", ".join([f"{kw} {len(articles)}건" for kw, articles in grouped_data.items()])



        st.subheader(f"📰 검색 결과 ({total_searched_count}건) 🔹 `{breakdown_text}`")



        if breaking_news:

            with st.expander(f"🚨 주요 속보 ({len(breaking_news)}건)", expanded=True):

                breaking_news.sort(key=lambda x: x["date"], reverse=True)

                for d in breaking_news:

                    st.markdown(f"#### 🚨 [{d['title']}]({d['link']})")

                    st.caption(f"{d['keyword']} | {d['date'].strftime('%Y-%m-%d %H:%M')}")



        for kw, articles in grouped_data.items():

            is_expanded = len(articles) > 0



            with st.expander(f"📌 **{kw}** ({len(articles)}건)", expanded=is_expanded):

                if not articles:

                    st.caption("검색된 기사가 없습니다.")

                else:

                    articles.sort(key=lambda x: x["date"], reverse=True)

                    for d in articles:

                        icon = "🚨 " if d["breaking"] else ""

                        st.markdown(f"#### {icon}[{d['title']}]({d['link']})")

                        st.caption(f"{d['date'].strftime('%Y-%m-%d %H:%M')}")

