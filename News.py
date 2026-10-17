import streamlit as st
import feedparser
import urllib.parse
import sqlite3
import requests
import re
import urllib3
import difflib
import json
import os

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="미술관TS그룹 뉴스 모니터링", layout="wide")

# 1) 최상단 헤더/툴바 여백 극소화 + 2) 양 사이드 패널 상단 고정(flex-start + sticky) 스타일
_lt, _gt = chr(60), chr(62)
st.markdown(
    f"""{_lt}style{_gt}
    header[data-testid="stHeader"] {{
        height: 1.5rem !important;
        min-height: 1.5rem !important;
        background: transparent !important;
    }}
    .block-container {{
        padding-top: 0.35rem !important;
        padding-bottom: 0.8rem !important;
    }}
    /* 메인 3단 컬럼이 중앙 정렬로 밀려 내려가지 않도록 최상단(flex-start)에 고정 */
    div[data-testid="stHorizontalBlock"] {{
        gap: 0.22rem !important;
        align-items: flex-start !important;
    }}
    /* 화면 스크롤 시에도 좌(1번째)·우(3번째) 사이드 패널이 상단에 따라붙도록 sticky 처리 */
    div[data-testid="stMainBlockContainer"] {_gt} div {_gt} div {_gt} div[data-testid="stHorizontalBlock"] {_gt} div[data-testid="column"]:nth-child(1),
    div[data-testid="stMainBlockContainer"] {_gt} div {_gt} div {_gt} div[data-testid="stHorizontalBlock"] {_gt} div[data-testid="column"]:nth-child(3),
    div[data-testid="stMainBlockContainer"] {_gt} div {_gt} div {_gt} div[data-testid="stHorizontalBlock"] {_gt} div[data-testid="stColumn"]:nth-child(1),
    div[data-testid="stMainBlockContainer"] {_gt} div {_gt} div {_gt} div[data-testid="stHorizontalBlock"] {_gt} div[data-testid="stColumn"]:nth-child(3) {{
        position: sticky !important;
        top: 0.5rem !important;
        align-self: flex-start !important;
    }}
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
    div.stButton {_gt} button,
    div.stDownloadButton {_gt} button {{
        padding: 0.15rem 0.25rem !important;
        height: 2.0rem !important;
        min-height: 2.0rem !important;
        border-radius: 6px !important;
        border: 1px solid rgba(128, 128, 128, 0.4) !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }}
    div.stButton {_gt} button p,
    div.stDownloadButton {_gt} button p {{
        font-size: 0.76rem !important;
        line-height: 1.1 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        margin: 0 !important;
    }}
    div.stDownloadButton {_gt} button {{
        padding: 0.2rem 0.35rem !important;
        height: 2.15rem !important;
        min-height: 2.15rem !important;
        border-radius: 6px !important;
        font-weight: 700 !important;
        white-space: nowrap !important;
    }}
    div.stDownloadButton {_gt} button p {{
        font-size: 0.8rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
    }}
    hr {{
        margin-top: 0.25rem !important;
        margin-bottom: 0.4rem !important;
    }}
    /* 3대 핵심 패널(제외 / 맞춤검색 / 감시) 시인성 강화를 위한 컬러 테마 구분 */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-marker-exclude) {{
        border: 2px solid #ef4444 !important;
        border-top: 6px solid #dc2626 !important;
        background-color: rgba(254, 242, 242, 0.65) !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 6px rgba(220, 38, 38, 0.08) !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-marker-search) {{
        border: 2px solid #3b82f6 !important;
        border-top: 6px solid #2563eb !important;
        background-color: rgba(239, 246, 255, 0.65) !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 6px rgba(37, 99, 235, 0.08) !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-marker-monitor) {{
        border: 2px solid #10b981 !important;
        border-top: 6px solid #059669 !important;
        background-color: rgba(236, 253, 245, 0.65) !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 6px rgba(5, 150, 105, 0.08) !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-marker-backup) {{
        border: 2px solid #f59e0b !important;
        background-color: rgba(255, 251, 235, 0.85) !important;
        border-radius: 8px !important;
    }}
    .panel-banner {{
        padding: 0.38rem 0.65rem;
        border-radius: 6px;
        font-weight: 800;
        font-size: 0.95rem;
        margin-bottom: 0.45rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        letter-spacing: -0.02em;
    }}
    .panel-banner-exclude {{
        background: linear-gradient(90deg, #dc2626 0%, #ef4444 100%);
        color: #ffffff !important;
    }}
    .panel-banner-search {{
        background: linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%);
        color: #ffffff !important;
    }}
    .panel-banner-monitor {{
        background: linear-gradient(90deg, #047857 0%, #10b981 100%);
        color: #ffffff !important;
    }}
    .panel-badge {{
        font-size: 0.72rem;
        font-weight: 600;
        padding: 0.1rem 0.45rem;
        border-radius: 999px;
        background-color: rgba(255, 255, 255, 0.22);
        color: #ffffff;
    }}
    {_lt}/style{_gt}""",
    unsafe_allow_html=True
)

TELEGRAM_TOKEN = "8606963961:AAH7AkdcYuj8a5GIrbnIABSI2XLPsqDFOEg"
TELEGRAM_CHAT_ID = "590917314"
DASHBOARD_URL = "https://ua2mbkztvt5z76tqwgzrzr.streamlit.app/"

# 사내 공유폴더(PC폴더) 백업 경로 및 파일명
NETWORK_BACKUP_DIR = r"\\114.2.201.62\★상황실★\.직원폴더\안성우\키워드 저장"
BACKUP_FILENAME = "keywords_backup.json"
NETWORK_BACKUP_FILE = os.path.join(NETWORK_BACKUP_DIR, BACKUP_FILENAME)
LOCAL_BACKUP_FILE = BACKUP_FILENAME

BREAK_KEYWORDS = ["속보", "긴급", "breaking", "Breaking"]

# 제외 단어가 포함되어 있더라도 기사를 절대 누락시키지 않는 기본 보호 키워드
DEFAULT_PROTECT_KEYWORDS = [
    "속보", "긴급", "집회", "시위", "테러", "도난",
    "훼손", "사고", "화재", "리움", "호암"
]

# ---------------------------------------------------------
# DB 초기화 및 영구 저장 함수 (활성/비활성 체크 상태까지 DB 저장)
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
        enabled INTEGER DEFAULT 1,
        UNIQUE(category, keyword)
    )''')
    try:
        c.execute("ALTER TABLE saved_lists ADD COLUMN enabled INTEGER DEFAULT 1")
    except Exception:
        pass
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

def get_saved_items(category):
    c = db_conn.cursor()
    c.execute("SELECT keyword, COALESCE(enabled, 1) FROM saved_lists WHERE category = ? ORDER BY id ASC", (category,))
    return [(row[0], bool(row[1])) for row in c.fetchall()]

def get_enabled_list(category):
    c = db_conn.cursor()
    c.execute("SELECT keyword FROM saved_lists WHERE category = ? AND COALESCE(enabled, 1) = 1 ORDER BY id ASC", (category,))
    return [row[0] for row in c.fetchall()]

def add_to_saved_list(category, keyword):
    c = db_conn.cursor()
    c.execute("INSERT OR IGNORE INTO saved_lists (category, keyword, enabled) VALUES (?, ?, 1)", (category, keyword))
    c.execute("UPDATE saved_lists SET enabled = 1 WHERE category = ? AND keyword = ?", (category, keyword))
    db_conn.commit()

def set_keyword_enabled(category, keyword, enabled):
    c = db_conn.cursor()
    c.execute("UPDATE saved_lists SET enabled = ? WHERE category = ? AND keyword = ?", (1 if enabled else 0, category, keyword))
    db_conn.commit()

def set_all_keywords_enabled(category, enabled):
    c = db_conn.cursor()
    c.execute("UPDATE saved_lists SET enabled = ? WHERE category = ?", (1 if enabled else 0, category))
    db_conn.commit()

def remove_from_saved_list(category, keyword):
    c = db_conn.cursor()
    c.execute("DELETE FROM saved_lists WHERE category = ? AND keyword = ?", (category, keyword))
    db_conn.commit()

def clear_saved_list(category):
    c = db_conn.cursor()
    c.execute("DELETE FROM saved_lists WHERE category = ?", (category,))
    db_conn.commit()

# ---------------------------------------------------------
# 통합 백업 & 복구 함수 (버튼 1개로 텔레그램 + PC폴더 동시 저장)
# ---------------------------------------------------------
def export_keywords_dict():
    data = {"updated_at": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")}
    for cat in ["exclude", "protect", "search", "monitor"]:
        data[cat] = [{"keyword": kw, "enabled": en} for kw, en in get_saved_items(cat)]
    return data

def export_keywords_json():
    return json.dumps(export_keywords_dict(), ensure_ascii=False, indent=2)

def import_keywords_dict(data, replace=True):
    if not isinstance(data, dict):
        return 0
    c = db_conn.cursor()
    count = 0
    for cat in ["exclude", "protect", "search", "monitor"]:
        if cat in data and isinstance(data[cat], list):
            if replace:
                c.execute("DELETE FROM saved_lists WHERE category = ?", (cat,))
            for item in data[cat]:
                if isinstance(item, dict) and "keyword" in item:
                    kw = str(item["keyword"]).strip()
                    en = 1 if item.get("enabled", True) else 0
                elif isinstance(item, (list, tuple)) and len(item) >= 1:
                    kw = str(item[0]).strip()
                    en = 1 if (item[1] if len(item) > 1 else True) else 0
                else:
                    kw = str(item).strip()
                    en = 1
                if kw:
                    c.execute(
                        "INSERT OR REPLACE INTO saved_lists (category, keyword, enabled) VALUES (?, ?, ?)",
                        (cat, kw, en)
                    )
                    count += 1
    db_conn.commit()
    set_app_state("protect_seeded", "1")
    return count

def save_to_local_and_network():
    """로컬 작업 폴더 및 사내 네트워크 폴더(\\114.2.201.62\...)에 동시 자동 기록"""
    json_str = export_keywords_json()
    saved_net = False
    try:
        with open(LOCAL_BACKUP_FILE, "w", encoding="utf-8") as f:
            f.write(json_str)
    except Exception:
        pass
    try:
        os.makedirs(NETWORK_BACKUP_DIR, exist_ok=True)
        with open(NETWORK_BACKUP_FILE, "w", encoding="utf-8") as f:
            f.write(json_str)
        saved_net = True
    except Exception:
        saved_net = False
    return saved_net

def save_to_telegram_cloud():
    """텔레그램 채팅방 고정 메시지에 키워드 JSON 백업 저장 (대시보드 링크 유지)"""
    payload_str = json.dumps(export_keywords_dict(), ensure_ascii=False)
    msg_text = (
        f"📌 [미술관TS그룹 뉴스 모니터링 대시보드]\n"
        f"🔗 {DASHBOARD_URL}\n\n"
        f"💾 [키워드 자동백업 데이터]\n"
        f"#KW_BACKUP_START#\n"
        f"{payload_str}\n"
        f"#KW_BACKUP_END#"
    )
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg_text,
                "disable_web_page_preview": True
            },
            timeout=8,
            verify=False
        )
        if res.status_code == 200:
            msg_id = res.json().get("result", {}).get("message_id")
            if msg_id:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/pinChatMessage",
                    data={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "message_id": msg_id,
                        "disable_notification": True
                    },
                    timeout=5,
                    verify=False
                )
            now_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m/%d %H:%M:%S")
            set_app_state("last_backup_time", now_str)
            return True
    except Exception:
        pass
    return False

def load_from_telegram_cloud():
    """텔레그램 고정 메시지에서 키워드 백업 JSON 추출 및 복구"""
    try:
        res = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
            params={"chat_id": TELEGRAM_CHAT_ID},
            timeout=8,
            verify=False
        )
        if res.status_code == 200:
            pinned = res.json().get("result", {}).get("pinned_message", {})
            text = pinned.get("text", "")
            if "#KW_BACKUP_START#" in text and "#KW_BACKUP_END#" in text:
                json_part = text.split("#KW_BACKUP_START#")[1].split("#KW_BACKUP_END#")[0].strip()
                data = json.loads(json_part)
                cnt = import_keywords_dict(data, replace=True)
                if cnt > 0:
                    save_to_local_and_network()
                    return True, f"텔레그램 클라우드에서 키워드 {cnt}개를 복구했습니다."
    except Exception as e:
        return False, f"텔레그램 복구 오류: {e}"
    return False, "텔레그램 고정 메시지에서 백업 데이터를 찾지 못했습니다."

def load_from_pc_or_local():
    """사내 공유폴더(\\114.2.201.62\...) 또는 로컬 파일에서 키워드 복구"""
    for path, label in [(NETWORK_BACKUP_FILE, "사내 공유폴더"), (LOCAL_BACKUP_FILE, "로컬 백업 파일")]:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cnt = import_keywords_dict(data, replace=True)
                if cnt > 0:
                    return True, f"{label}에서 키워드 {cnt}개를 복구했습니다."
        except Exception:
            pass
    return False, "저장된 백업 파일을 찾지 못했습니다."

def auto_sync_all_quiet():
    """키워드 추가/변경/삭제 시 백그라운드로 PC폴더 기록"""
    save_to_local_and_network()

def cb_unified_save_all():
    """
    단 1개의 [💾 현재 키워드 저장] 버튼 클릭 시 실행되는 콜백:
    1) 텔레그램 클라우드 백업 발송 + 상단 핀 고정
    2) 사내 공유폴더(\\114.2.201.62\...) 및 로컬 파일 자동 저장
    3) 동시에 브라우저를 통해 PC 폴더로 백업 파일 다운로드까지 한 번에 수행!
    """
    tg_ok = save_to_telegram_cloud()
    net_ok = save_to_local_and_network()
    if tg_ok and net_ok:
        st.session_state.backup_toast = "✅ 텔레그램 클라우드 + 사내 PC폴더 동시 저장 완료!"
    elif tg_ok:
        st.session_state.backup_toast = "✅ 텔레그램 저장 + PC 백업파일 다운로드 완료!"
    else:
        st.session_state.backup_toast = "✅ PC 백업파일 저장 완료!"

def cb_unified_restore_all():
    """[🔄 키워드 복구] 버튼 클릭 시 텔레그램 클라우드 -> 사내 공유폴더 순으로 자동 복구"""
    ok, msg = load_from_telegram_cloud()
    if not ok:
        ok, msg = load_from_pc_or_local()
    st.session_state.backup_toast = f"{'✅' if ok else '⚠️'} {msg}"

# ---------------------------------------------------------
# 앱 최초 시작 / 서버 초기화 시 자동 복구 및 기본 보호 키워드 등록
# ---------------------------------------------------------
total_existing_kws = sum(len(get_saved_items(c)) for c in ["exclude", "search", "monitor"])
if total_existing_kws == 0 and get_app_state("auto_restored_once", "0") != "1":
    ok_tg, _ = load_from_telegram_cloud()
    if not ok_tg:
        load_from_pc_or_local()
    set_app_state("auto_restored_once", "1")

if get_app_state("protect_seeded", "0") != "1":
    for p_kw in DEFAULT_PROTECT_KEYWORDS:
        add_to_saved_list("protect", p_kw)
    set_app_state("protect_seeded", "1")

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
    "active_protect_keywords": [],
    "monitoring": saved_mon,
    "monitor_start_time": saved_start_dt,
    "s_input": "",
    "e_input": "",
    "p_input": "",
    "m_input": "",
    "backup_toast": ""
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.backup_toast:
    st.toast(st.session_state.backup_toast)
    st.session_state.backup_toast = ""

# ---------------------------------------------------------
# 키워드 추가 / 체크(✅·⬜) / 개별삭제(✕) / 일괄제어 콜백 함수
# ---------------------------------------------------------
def parse_keyword_input(text):
    items = []
    for part in re.split(r'[\n,]+', text.strip()):
        clean_part = re.sub(r'^(\d+\.|-|\*)\s*', '', part.strip()).strip()
        if clean_part and clean_part not in items:
            items.append(clean_part)
    return items

def parse_exclude_input(text):
    items = []
    for token in re.split(r'[\s,]+', text.strip()):
        clean_token = token.lstrip('-').strip()
        if clean_token and clean_token not in items:
            items.append(clean_token)
    return items

def cb_add_search_kw():
    for kw in parse_keyword_input(st.session_state.s_input):
        add_to_saved_list("search", kw)
    st.session_state.s_input = ""
    auto_sync_all_quiet()

def cb_add_exclude_kw():
    for kw in parse_exclude_input(st.session_state.e_input):
        add_to_saved_list("exclude", kw)
    st.session_state.e_input = ""
    auto_sync_all_quiet()

def cb_add_protect_kw():
    for kw in parse_exclude_input(st.session_state.p_input):
        add_to_saved_list("protect", kw)
    st.session_state.p_input = ""
    auto_sync_all_quiet()

def cb_add_monitor_kw():
    for kw in parse_keyword_input(st.session_state.m_input):
        add_to_saved_list("monitor", kw)
    st.session_state.m_input = ""
    auto_sync_all_quiet()

def cb_toggle_kw(category, kw, current_en):
    set_keyword_enabled(category, kw, not current_en)
    auto_sync_all_quiet()

def cb_rm_kw(category, kw):
    remove_from_saved_list(category, kw)
    auto_sync_all_quiet()

def cb_set_all_kw(category, enabled):
    set_all_keywords_enabled(category, enabled)
    auto_sync_all_quiet()

def cb_clear_kw(category):
    clear_saved_list(category)
    if category == "search":
        st.session_state.run_search = False
    auto_sync_all_quiet()

def cb_start_monitoring():
    if st.session_state.m_input.strip():
        cb_add_monitor_kw()
    if st.session_state.e_input.strip():
        cb_add_exclude_kw()
    if st.session_state.p_input.strip():
        cb_add_protect_kw()
    now_dt = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
    st.session_state.monitoring = True
    st.session_state.monitor_start_time = now_dt
    set_app_state("monitoring", "1")
    set_app_state("monitor_start_time", now_dt.strftime("%Y-%m-%d %H:%M:%S"))
    save_to_telegram_cloud()
    save_to_local_and_network()

def cb_stop_monitoring():
    st.session_state.monitoring = False
    set_app_state("monitoring", "0")

def trigger_manual_search():
    if st.session_state.s_input.strip():
        cb_add_search_kw()
    if st.session_state.e_input.strip():
        cb_add_exclude_kw()
    if st.session_state.p_input.strip():
        cb_add_protect_kw()
    st.session_state.active_search_keywords = get_enabled_list("search")
    st.session_state.active_excl_keywords = get_enabled_list("exclude")
    st.session_state.active_protect_keywords = get_enabled_list("protect")
    st.session_state.run_search = True

# ---------------------------------------------------------
# 3열 균일 테두리 박스 ([✅ 키워드] + [✕]) 렌더링 함수
# ---------------------------------------------------------
def render_keyword_grid(items, category, title_label="목록", scroll_threshold=9):
    if not items:
        return

    enabled_cnt = sum(1 for _, en in items if en)

    # 상단 헤더: 목록 개수 + [전체선택 / 전체해제 / 전체삭제] 3개 버튼 (한 줄 고정)
    h_title, h_b1, h_b2, h_b3 = st.columns([1.5, 1.15, 1.15, 1.15])
    with h_title:
        st.markdown(f"**{title_label} ({enabled_cnt}/{len(items)})**")
    with h_b1:
        st.button("전체선택", key=f"all_on_{category}", use_container_width=True, on_click=cb_set_all_kw, args=(category, True))
    with h_b2:
        st.button("전체해제", key=f"all_off_{category}", use_container_width=True, on_click=cb_set_all_kw, args=(category, False))
    with h_b3:
        st.button("전체삭제", key=f"clear_{category}", use_container_width=True, on_click=cb_clear_kw, args=(category,))

    # 3열 그리드: 각 셀마다 뚜렷한 체크 아이콘(✅/⬜)이 들어간 키워드 박스와 ✕ 삭제 버튼을 나란히 배치
    box = st.container(height=145, border=False) if len(items) > scroll_threshold else st.container(border=False)
    with box:
        for row_idx in range(0, len(items), 3):
            cols = st.columns(3)
            for col_idx in range(3):
                item_idx = row_idx + col_idx
                if item_idx < len(items):
                    kw, en = items[item_idx]
                    icon = "✅" if en else "⬜"
                    with cols[col_idx]:
                        c_kw, c_del = st.columns([3.4, 1.0])
                        with c_kw:
                            st.button(
                                f"{icon} {kw}",
                                key=f"tgl_{category}_{item_idx}_{kw}",
                                use_container_width=True,
                                on_click=cb_toggle_kw,
                                args=(category, kw, en)
                            )
                        with c_del:
                            st.button(
                                "✕",
                                key=f"rm_{category}_{item_idx}_{kw}",
                                use_container_width=True,
                                on_click=cb_rm_kw,
                                args=(category, kw)
                            )

# ---------------------------------------------------------
# 뉴스 RSS 수집 및 [절대 보호 키워드 우선순위 예외 처리]
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

def process_news(base_keywords, excl_keywords, protect_keywords=None, limit_time=None):
    result = []
    if not base_keywords:
        return result

    if protect_keywords is None:
        protect_keywords = []

    queries = [kw.strip() for kw in base_keywords if kw.strip()]

    with ThreadPoolExecutor(max_workers=5) as ex:
        feeds = list(ex.map(fetch_feed, queries))

    active_excls = [w.strip().lower() for w in excl_keywords if w.strip()]
    active_protects = [w.strip().lower() for w in protect_keywords if w.strip()]
    break_lowers = [b.lower() for b in BREAK_KEYWORDS]

    for base_kw, feed in zip(queries, feeds):
        seen = set()
        for n in getattr(feed, "entries", []):
            title = n.title
            link = n.link
            if title in seen:
                continue
            seen.add(title)

            title_lower = title.lower()
            matched_excl = [ex_w for ex_w in active_excls if ex_w in title_lower]
            matched_prot = [pr_w for pr_w in active_protects if pr_w in title_lower]
            breaking = any(b in title_lower for b in break_lowers)

            # 제외 단어가 걸렸더라도 절대 보호 키워드나 속보 키워드가 있으면 생존(우선순위 예외 처리)
            is_rescued = False
            if matched_excl:
                if matched_prot or breaking:
                    is_rescued = True
                else:
                    continue

            try:
                pub = parsedate_to_datetime(n.published)
                pub = pub.astimezone(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
            except Exception:
                continue

            if limit_time and pub < limit_time:
                continue

            result.append({
                "title": title,
                "link": link,
                "keyword": base_kw,
                "date": pub,
                "breaking": breaking,
                "rescued": is_rescued,
                "matched_prot": matched_prot
            })
    return result

# ---------------------------------------------------------
# 자동 새로고침 (감시 모드 작동 중일 때 60초 간격)
# ---------------------------------------------------------
if st.session_state.monitoring:
    st_autorefresh(interval=60000, limit=None, key="monitor_refresh")

# 최상단 헤더 영역 (타이틀 + 우측 상단 키워드 통합 저장/복구 바로가기)
top_col1, top_col2, top_col3 = st.columns([5.2, 2.4, 2.4])
with top_col1:
    st.markdown(" ##  📊 [미술관TS그룹] 뉴스 모니터링 대시보드")

st.divider()

now = datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)

search_items_db = get_saved_items("search")
exclude_items_db = get_saved_items("exclude")
protect_items_db = get_saved_items("protect")
monitor_items_db = get_saved_items("monitor")

enabled_search_kws = get_enabled_list("search")
enabled_exclude_kws = get_enabled_list("exclude")
enabled_protect_kws = get_enabled_list("protect")
enabled_monitor_kws = get_enabled_list("monitor")

left, center, right = st.columns([2.6, 3.8, 2.6])

# =========================================================
# 좌측 패널: 1) 통합 제외 단어 & 절대 보호 키워드 + 2) 맞춤 검색
# =========================================================
with left:
    # 1. 통합 제외 단어 + 절대 보호 키워드 (우선순위 예외 처리) - RED 테마
    with st.container(border=True):
        st.markdown(
            f'{_lt}div class="panel-marker-exclude panel-banner panel-banner-exclude"{_gt}'
            f'{_lt}span{_gt}🚫 통합 제외 단어{_lt}/span{_gt}'
            f'{_lt}span class="panel-badge"{_gt}필터링 패널{_lt}/span{_gt}'
            f'{_lt}/div{_gt}',
            unsafe_allow_html=True
        )
        st.text_input(
            "제외 단어 입력",
            key="e_input",
            placeholder="제외할 단어 입력 후 Enter",
            label_visibility="collapsed",
            on_change=cb_add_exclude_kw
        )
        render_keyword_grid(exclude_items_db, category="exclude", title_label="제외 목록")

        with st.expander(f"🛡️ 절대 보호 키워드 ({len(enabled_protect_kws)}/{len(protect_items_db)}) — 제외 단어 무시", expanded=False):
            st.caption("제외 단어가 포함된 기사라도 아래 보호 키워드가 제목에 있으면 탈락시키지 않고 무조건 표시·알림합니다.")
            st.text_input(
                "절대 보호 키워드 입력",
                key="p_input",
                placeholder="보호할 중요 단어 입력 후 Enter (예: 집회, 테러, 리움)",
                label_visibility="collapsed",
                on_change=cb_add_protect_kw
            )
            render_keyword_grid(protect_items_db, category="protect", title_label="보호 목록")

    # 2. 맞춤 검색 - BLUE 테마
    with st.container(border=True):
        st.markdown(
            f'{_lt}div class="panel-marker-search panel-banner panel-banner-search"{_gt}'
            f'{_lt}span{_gt}🎛️ 맞춤 검색 패널{_lt}/span{_gt}'
            f'{_lt}span class="panel-badge"{_gt}수동 조회{_lt}/span{_gt}'
            f'{_lt}/div{_gt}',
            unsafe_allow_html=True
        )
        st.text_input(
            "검색어 입력",
            key="s_input",
            placeholder="입력 시 키워드 자동 추가됨",
            label_visibility="collapsed",
            on_change=cb_add_search_kw
        )
        render_keyword_grid(search_items_db, category="search", title_label="목록")

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
# 우측 패널: 감시 패널 + 통합 키워드 저장/복구 버튼 상시 노출
# =========================================================
with right:
    with st.container(border=True):
        st.markdown(
            f'{_lt}div class="panel-marker-monitor panel-banner panel-banner-monitor"{_gt}'
            f'{_lt}span{_gt}📡 실시간 감시 패널{_lt}/span{_gt}'
            f'{_lt}span class="panel-badge"{_gt}자동 알림{_lt}/span{_gt}'
            f'{_lt}/div{_gt}',
            unsafe_allow_html=True
        )

        st.text_input(
            "감시 키워드 입력",
            key="m_input",
            placeholder="입력 시 키워드 자동 추가됨",
            label_visibility="collapsed",
            on_change=cb_add_monitor_kw
        )

        render_keyword_grid(monitor_items_db, category="monitor", title_label="감시 목록")

        st.divider()

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

        st.divider()

        # 우측 감시 패널 내부에도 눈에 확 띄는 앰버(노란) 박스로 [현재 키워드 저장] + [복구] 버튼 배치
        with st.container(border=True):
            st.markdown(
                f'{_lt}div class="panel-marker-backup" style="font-size:0.8rem; font-weight:800; color:#b45309; margin-bottom:0.25rem;"{_gt}'
                f'💾 키워드 영구 백업 · 원클릭 복구 (전 영역 통합){_lt}/div{_gt}',
                unsafe_allow_html=True
            )
            b_save, b_load = st.columns(2)
            with b_save:
                st.download_button(
                    label="💾 현재 키워드 통합 저장",
                    data=export_keywords_json(),
                    file_name=BACKUP_FILENAME,
                    mime="application/json",
                    on_click=cb_unified_save_all,
                    type="primary",
                    use_container_width=True,
                    key="panel_unified_save_btn"
                )
            with b_load:
                st.button(
                    "🔄 저장된 키워드 복구",
                    on_click=cb_unified_restore_all,
                    use_container_width=True,
                    key="panel_unified_restore_btn"
                )

        with st.expander("📂 PC 백업파일 직접 불러오기 (수동 업로드)", expanded=False):
            st.caption(f"권장 폴더: `{NETWORK_BACKUP_DIR}`")
            uploaded_file = st.file_uploader("keywords_backup.json 선택", type=["json"], label_visibility="collapsed")
            if uploaded_file is not None:
                if st.button("📥 선택한 파일로 즉시 복원", use_container_width=True, key="upload_restore_btn"):
                    try:
                        data = json.load(uploaded_file)
                        cnt = import_keywords_dict(data, replace=True)
                        save_to_telegram_cloud()
                        save_to_local_and_network()
                        st.session_state.backup_toast = f"✅ 파일에서 키워드 {cnt}개 복원 및 동기화 완료!"
                        st.rerun()
                    except Exception as e:
                        st.error(f"파일 읽기 오류: {e}")

        # 감시 상태 표시
        if st.session_state.monitoring:
            current_refresh_time = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S")
            st.success(f"🟢 **감시중** (최근 갱신: `{current_refresh_time}`)")
        else:
            st.error("🔴 **감시 중지됨**")

        last_bk = get_app_state("last_backup_time", "기록 없음")
        st.caption(f"DB 누적 전송: {get_sent_count()}건 | 🛡️ 보호 {len(enabled_protect_kws)}개 | 💾 최근 백업: {last_bk}")

        for log in get_recent_logs(5):
            time_str = log[0].split(" ")[1][:5]
            st.caption(f"{time_str} | [{log[1]}] {log[2][:18]}...")

    # 감시 작동 로직 (절대 보호 키워드 예외 처리 적용)
    if st.session_state.monitoring and enabled_monitor_kws and st.session_state.monitor_start_time:
        monitor_data = process_news(enabled_monitor_kws, enabled_exclude_kws, enabled_protect_kws)
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
                icon = "🚨" if n["breaking"] else ("🛡️" if n.get("rescued") else "📰")
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
# 중앙 패널: 맞춤 검색 결과 출력 (독립 스크롤 컨테이너로 양옆 패널 고정)
# =========================================================
with center:
    if st.session_state.run_search and enabled_search_kws:
        active_kws = enabled_search_kws
        active_excls = enabled_exclude_kws
        active_prots = enabled_protect_kws

        grouped_data = {kw: [] for kw in active_kws}
        total_searched_count = 0

        breaking_news = []
        seen_breaking_links = set()

        raw_data = process_news(active_kws, active_excls, active_prots, search_limit)

        for d in raw_data:
            kw = d["keyword"]
            if kw in grouped_data and len(grouped_data[kw]) < max_news:
                grouped_data[kw].append(d)
                total_searched_count += 1

                if d["breaking"] and d["link"] not in seen_breaking_links:
                    breaking_news.append(d)
                    seen_breaking_links.add(d["link"])

        breakdown_text = ", ".join([f"{kw} {len(articles)}건" for kw, articles in grouped_data.items()])

        st.markdown(f"##### 📰 검색 결과 ({total_searched_count}건) 🔹 `{breakdown_text}`")

        # 검색 결과가 아무리 많아져도 중앙 박스 내부에서만 스크롤되어 좌우 패널이 절대 움직이지 않음
        results_box = st.container(height=760, border=False)
        with results_box:
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
                            icon = "🚨 " if d["breaking"] else ("🛡️ " if d.get("rescued") else "")
                            st.markdown(f"#### {icon}[{d['title']}]({d['link']})")
                            if d.get("rescued"):
                                prot_str = ", ".join(d.get("matched_prot", []))
                                st.caption(f"{d['date'].strftime('%Y-%m-%d %H:%M')} | 🛡️ 보호 키워드({prot_str})로 제외 방지됨")
                            else:
                                st.caption(f"{d['date'].strftime('%Y-%m-%d %H:%M')}")
