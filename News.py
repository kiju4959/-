import streamlit as st
import feedparser
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import urllib.parse

# -------------------------
# 기본 설정
# -------------------------
st.set_page_config(page_title="뉴스 앱", layout="wide")

st.title("📊 뉴스 모니터링 앱")

# -------------------------
# 입력창 (왼쪽 사이드바)
# -------------------------
with st.sidebar:
    st.header("설정")

    keywords_input = st.text_area(
        "키워드 (한 줄에 하나씩)",
        placeholder="삼성\nAI\n반도체"
    )

    period = st.selectbox(
        "기간",
        ["24시간", "48시간", "7일", "전체"]
    )

    search = st.button("검색")

# -------------------------
# 키워드 처리
# -------------------------
keywords = [k.strip() for k in keywords_input.split("\n") if k.strip()]

now = datetime.utcnow()

if period == "24시간":
    limit = now - timedelta(hours=24)
elif period == "48시간":
    limit = now - timedelta(hours=48)
elif period == "7일":
    limit = now - timedelta(days=7)
else:
    limit = None

# -------------------------
# 속보 키워드
# -------------------------
BREAK = ["속보", "긴급", "breaking", "Breaking"]

data = []
seen = set()

# -------------------------
# 실행
# -------------------------
if search:

    if not keywords:
        st.warning("키워드를 입력하세요")
        st.stop()

    for kw in keywords:

        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(kw)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)

        for n in feed.entries:

            title = n.title
            link = n.link

            if title in seen:
                continue
            seen.add(title)

            try:
                pub = parsedate_to_datetime(n.published).replace(tzinfo=None)
            except:
                continue

            if limit and pub < limit:
                continue

            is_breaking = any(b in title for b in BREAK)

            data.append({
                "title": title,
                "link": link,
                "breaking": is_breaking,
                "keyword": kw,
                "date": pub  # 날짜 정렬을 위해 날짜 데이터 추가
            })

    if not data:
        st.warning("뉴스 없음")
        st.stop()

    # ⭐ [수정된 부분] 수집된 모든 기사를 날짜 기준(내림차순, 최신순)으로 정렬합니다.
    data = sorted(data, key=lambda x: x["date"], reverse=True)

    breaking = [d for d in data if d["breaking"]]
    normal = [d for d in data if not d["breaking"]]

    tab1, tab2 = st.tabs(["전체", "속보"])

    with tab1:

        if breaking:
            st.subheader("🚨 속보")
            for n in breaking:
                st.markdown(f"### 🚨 [{n['title']}]({n['link']})")

        st.subheader("📰 일반 뉴스")
        for n in normal:
            st.markdown(f"### [{n['title']}]({n['link']})")

    with tab2:

        if not breaking:
            st.info("속보 없음")
        else:
            for n in breaking:
                st.markdown(f"### 🚨 [{n['title']}]({n['link']})")

else:
    st.info("왼쪽에서 키워드 입력 후 검색하세요")
