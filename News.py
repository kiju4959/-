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



TELEGRAM_TOKEN = "8606963961:AAH7AkdcYuj8a5GIrbnIABSI2XLPsqDFOEg"

TELEGRAM_CHAT_ID = "590917314"



BREAK_KEYWORDS = ["속보", "긴급", "breaking", "Breaking"]



# ---------------------------------------------------------

# DB 초기화 및 영구 저장 함수

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

    conn.commit()

    return conn



db_conn = init_db()



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

# 세션 상태(Session State) 초기화

# ---------------------------------------------------------

defaults = {

    "run_search": False,

    "active_search_keywords": [],

    "active_excl_keywords": [],

    "monitoring": False,

    "monitor_start_time": None,

    "s_input": "",

    "e_input": "",

    "m_input": ""

}



for k, v in defaults.items():

    if k not in st.session_state:

        st.session_state[k] = v



# ---------------------------------------------------------

# 키워드 추가 / 삭제 / 검색 실행 콜백 함수

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



def trigger_manual_search():

    # 입력창에 아직 추가 버튼을 누르지 않은 텍스트가 남아있다면 자동으로 목록에 반영

    if st.session_state.s_input.strip():

        cb_add_search_kw()

    if st.session_state.e_input.strip():

        cb_add_exclude_kw()

    st.session_state.active_search_keywords = get_saved_list("search")

    st.session_state.active_excl_keywords = get_saved_list("exclude")

    st.session_state.run_search = True



# ---------------------------------------------------------

# 뉴스 RSS 수집 및 통합 제외 단어 필터링

# ---------------------------------------------------------

@st.cache_data(ttl=60)

def fetch_feed(query_str):

    url = (

        "https://news.google.com/rss/search?q="

        f"{urllib.parse.quote(query_str)}"

        "&hl=ko&gl=KR&ceid=KR:ko"

    )

    return feedparser.parse(url)



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

        for n in feed.entries:

            title = n.title

            link = n.link

            if title in seen:

                continue

            seen.add(title)



            # 통합 제외 단어가 제목에 포함된 경우 2차 필터링으로 완벽 차단

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



st.markdown("&lt;h1 style=&#39;text-align:center;&#39;&gt;📊 [미술관TS그룹] 뉴스 모니터링 대시보드&lt;/h1&gt;", unsafe_allow_html=True)

st.divider()



now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)



# DB에서 현재 저장된 3가지 목록 불러오기

search_keywords_db = get_saved_list("search")

exclude_keywords_db = get_saved_list("exclude")

monitor_keywords_db = get_saved_list("monitor")



left, center, right = st.columns([2.2, 4.6, 2.2])



# =========================================================

# 좌측 패널: 1) 맞춤 검색 + 2) 통합 제외 단어

# =========================================================

with left:

    st.subheader("🎛️ 맞춤 검색")

    st.caption("검색어를 추가해 두면 웹을 껐다 켜도 목록이 그대로 유지됩니다.")



    with st.expander("➕ 맞춤 검색어 추가", expanded=not bool(search_keywords_db)):

        st.text_area(

            "🟢 검색어 입력 (엔터로 여러 개 줄바꿈 입력)",

            placeholder="예)\n삼성\n에스원\n삼성 집회\n리움미술관",

            key="s_input",

            height=110

        )

        st.button("📥 맞춤 검색 목록에 추가", use_container_width=True, on_click=cb_add_search_kw)



    col_s_title, col_s_clear = st.columns([3, 2])

    with col_s_title:

        st.markdown(f"**📋 맞춤 검색 목록 ({len(search_keywords_db)}개)**")

    with col_s_clear:

        if search_keywords_db:

            st.button("🗑️ 전체 삭제", key="clear_s", use_container_width=True, on_click=cb_clear_search_kw)



    if not search_keywords_db:

        st.info("등록된 맞춤 검색어가 없습니다.")

    else:

        for i, kw in enumerate(search_keywords_db):

            c_kw, c_rm = st.columns([4, 1])

            with c_kw:

                st.markdown(f"• **{kw}**")

            with c_rm:

                st.button("❌", key=f"rm_s_{i}_{kw}", on_click=cb_rm_search_kw, args=(kw,))



    st.write("")

    period = st.selectbox("검색 기간", ["1시간", "24시간", "48시간", "7일", "전체"], index=1)

    max_news = st.slider("최대 뉴스 수 (키워드당)", 10, 100, 30)



    st.button("🔍 맞춤 검색 시작", type="primary", use_container_width=True, on_click=trigger_manual_search)



    period_map = {

        "1시간": timedelta(hours=1),

        "24시간": timedelta(hours=24),

        "48시간": timedelta(hours=48),

        "7일": timedelta(days=7),

    }

    search_limit = now - period_map.get(period, timedelta(days=9999)) if period != "전체" else None



    st.divider()



    # -----------------------------------------------------

    # 통합 제외 단어 영역 (맞춤 검색 바로 하단 배치)

    # -----------------------------------------------------

    st.subheader("🚫 통합 제외 단어")

    st.caption("여기에 등록된 단어는 [맞춤 검색]과 [감시 패널] 양쪽 모두에서 자동으로 제외됩니다.")



    st.text_input(

        "🔴 제외할 단어 입력 (공백/쉼표로 여러 개 입력 가능)",

        placeholder="예) 야구 스포츠 라이온즈",

        key="e_input",

        on_change=cb_add_exclude_kw

    )

    st.button("📥 통합 제외 단어 추가", use_container_width=True, on_click=cb_add_exclude_kw)



    col_e_title, col_e_clear = st.columns([3, 2])

    with col_e_title:

        st.markdown(f"**📋 제외 단어 목록 ({len(exclude_keywords_db)}개)**")

    with col_e_clear:

        if exclude_keywords_db:

            st.button("🗑️ 전체 삭제", key="clear_e", use_container_width=True, on_click=cb_clear_exclude_kw)



    if not exclude_keywords_db:

        st.info("등록된 통합 제외 단어가 없습니다.")

    else:

        for i, kw in enumerate(exclude_keywords_db):

            c_kw, c_rm = st.columns([4, 1])

            with c_kw:

                st.markdown(f"• `{kw}`")

            with c_rm:

                st.button("❌", key=f"rm_e_{i}_{kw}", on_click=cb_rm_exclude_kw, args=(kw,))



# =========================================================

# 우측 패널: 감시 패널

# =========================================================

with right:

    st.subheader("📡 감시 패널")

    c1, c2 = st.columns(2)

    with c1:

        if st.button("🟢 시작", use_container_width=True):

            if st.session_state.m_input.strip():

                cb_add_monitor_kw()

            if st.session_state.e_input.strip():

                cb_add_exclude_kw()

            st.session_state.monitoring = True

            st.session_state.monitor_start_time = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)

            st.rerun()

    with c2:

        if st.button("🔴 종료", use_container_width=True):

            st.session_state.monitoring = False

            st.rerun()



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

                st.toast("✅ 텔레그램으로 테스트 메시지를 성공적으로 전송했습니다!")

            else:

                st.error("❌ 전송 실패. 토큰이나 Chat ID를 확인해주세요.")

        except Exception as e:

            st.error(f"❌ 통신 오류가 발생했습니다: {e}")



    st.divider()



    with st.expander("➕ 감시 키워드 추가", expanded=not bool(monitor_keywords_db)):

        st.caption("💡 팁: '속보 삼성'처럼 단어를 붙여 쓰면 텔레그램 알림을 정교하게 제어할 수 있습니다.")

        st.text_area(

            "🟢 추가할 감시 키워드 목록 (엔터로 줄바꿈)",

            key="m_input",

            placeholder="예)\n삼성\n속보 에스원\n삼성 집회",

            height=100

        )

        st.button("📥 감시 목록에 추가", use_container_width=True, on_click=cb_add_monitor_kw)



    col_m_title, col_m_clear = st.columns([3, 2])

    with col_m_title:

        st.markdown(f"**📋 감시 목록 ({len(monitor_keywords_db)}개)**")

    with col_m_clear:

        if monitor_keywords_db:

            st.button("🗑️ 전체 삭제", key="clear_m", use_container_width=True, on_click=cb_clear_monitor_kw)



    if exclude_keywords_db:

        st.caption(f"🚫 통합 제외 적용 중: `{', '.join(exclude_keywords_db)}`")



    if not monitor_keywords_db:

        st.info("등록된 감시 키워드가 없습니다.")

    else:

        for i, k in enumerate(monitor_keywords_db):

            c_kw, c_rm = st.columns([4, 1])

            with c_kw:

                st.markdown(f"• **{k}**")

            with c_rm:

                st.button("❌", key=f"rm_m_{i}_{k}", on_click=cb_rm_monitor_kw, args=(k,))



    st.divider()



    if st.session_state.monitoring:

        current_refresh_time = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")

        st.success(f"🟢 **AI 감시중** (60초 갱신)\n\n⏱️ 최근 갱신 시간: `{current_refresh_time}`")

    else:

        st.error("🔴 **감시 중지됨**")



    st.write(f"**DB 누적 전송:** {get_sent_count()}건")



    for log in get_recent_logs(5):

        time_str = log[0].split(" ")[1][:5]

        st.caption(f"{time_str} | {log[1]}")

        st.write(f"- {log[2][:20]}...")



    # 감시 작동 로직 (저장된 감시 목록 + 통합 제외 단어 자동 결합)

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

    if st.session_state.run_search:

        # 현재 DB에 저장된 최신 맞춤 검색 목록 및 통합 제외 단어를 기준으로 표시

        active_kws = search_keywords_db

        active_excls = exclude_keywords_db



        if not active_kws:

            st.warning("맞춤 검색 목록에 등록된 키워드가 없습니다. 좌측에서 검색어를 추가해 주세요.")

        else:

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



            st.subheader(f"📰 뉴스 검색 결과 (총 {total_searched_count}건) 🔹 `{breakdown_text}`")

            if active_excls:

                st.caption(f"🚫 적용된 통합 제외 단어: `{', '.join(active_excls)}`")



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

        st.info("좌측에서 **[맞춤 검색 목록]**과 **[통합 제외 단어]**를 확인하신 후 **'🔍 맞춤 검색 시작'** 버튼을 눌러주세요.")

