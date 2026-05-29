import streamlit as st
import feedparser
import urllib.parse

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="뉴스 모니터링 앱",layout="wide")

st.title("📊 뉴스 모니터링 앱")

if "selected_keywords" not in st.session_state:
    st.session_state.selected_keywords = []

if "run_search" not in st.session_state:
    st.session_state.run_search = False

SAVED_KEYWORDS = ["삼성","에스원","집회","이재용","홍라희","이서현","리움미술관","호암미술관"]

with st.sidebar:

    st.header("설정")

    st.subheader("📌 저장 키워드")

    cols = st.columns(2)

    for idx, kw in enumerate(SAVED_KEYWORDS):

        with cols[idx % 2]:

            if st.button(kw,use_container_width=True):
                st.session_state.selected_keywords = [kw]
                st.session_state.run_search = True

    st.divider()

    keywords_input = st.text_area("키워드 직접 입력",placeholder="삼성\nAI\n반도체")

    period = st.selectbox("기간",["1시간", "24시간", "48시간", "7일", "전체"])

    max_news = st.slider("최대 뉴스 개수", 10, 100, 30)

    search = st.button("🔍 검색", use_container_width=True)

    if search:
        st.session_state.run_search = True

manual_keywords = [k.strip()
    for k in keywords_input.split("\n")
    if k.strip()]

keywords = list(set(manual_keywords + st.session_state.selected_keywords))

now = datetime.now()

if period == "1시간":
    limit = now - timedelta(hours=1)

elif period == "24시간":
    limit = now - timedelta(hours=24)

elif period == "48시간":
    limit = now - timedelta(hours=48)

elif period == "7일":
    limit = now - timedelta(days=7)

else:
    limit = None

BREAK = ["속보","긴급","breaking","Breaking"]

@st.cache_data(ttl=300)
def fetch_feed(keyword):

    url = ("https://news.google.com/rss/search?q="
        f"{urllib.parse.quote(keyword)}"
        "&hl=ko&gl=KR&ceid=KR:ko")

    return keyword, feedparser.parse(url)

if st.session_state.run_search:

    if not keywords:

        st.warning("키워드를 입력하세요")
        st.stop()

    data = []
    seen = set()

    with ThreadPoolExecutor(max_workers=5) as executor:

        results = executor.map(fetch_feed,keywords)

    for kw, feed in results:

        for n in feed.entries:

            title = n.title
            link = n.link

            if title in seen:
                continue

            seen.add(title)

            try:

                pub = parsedate_to_datetime(n.published)

                pub = pub.astimezone(ZoneInfo("Asia/Seoul"))

                pub = pub.replace(tzinfo=None)

            except:
                continue

            if limit and pub < limit:
                continue

            is_breaking = any( b.lower() in title.lower()for b in BREAK)

            data.append({"title": title, "link": link, "breaking": is_breaking, "keyword": kw, "date": pub })

    if not data:

        st.warning("뉴스가 없습니다")
        st.stop()

    data = sorted(data, key=lambda x: x["date"], reverse=True)

    data = data[:max_news]

    breaking_top = [d for d in data if d["breaking"]]

    if breaking_top:
        st.error("🚨 속보 뉴스")
        for n in breaking_top[:5]:
            st.markdown(
                f"""
### 🚨 [{n['title']}]({n['link']})
"""
            )

            st.caption(
                f"{n['keyword']} | "
                f"{n['date'].strftime('%Y-%m-%d %H:%M')}"
            )

    tab1, tab2 = st.tabs([
        "전체 뉴스",
        "속보 뉴스"
    ])

    with tab1:

        grouped = {}

        for item in data:

            kw = item["keyword"]

            if kw not in grouped:
                grouped[kw] = []

            grouped[kw].append(item)

        for kw, items in grouped.items():

            st.subheader(f"🔎 {kw}")

            st.write(f"총 {len(items)}건")

            for n in items:

                icon = (
                    "🚨 "
                    if n["breaking"]
                    else ""
                )

                st.markdown(
                    f"""
### {icon}[{n['title']}]({n['link']})
"""
                )

                st.caption(
                    n["date"].strftime(
                        "%Y-%m-%d %H:%M"
                    )
                )

            st.divider()

    with tab2:

        breaking = [
            d for d in data
            if d["breaking"]
        ]

        if not breaking:

            st.info("속보 뉴스가 없습니다")

        else:

            grouped_breaking = {}

            for item in breaking:

                kw = item["keyword"]

                if kw not in grouped_breaking:
                    grouped_breaking[kw] = []

                grouped_breaking[kw].append(item)

            for kw, items in grouped_breaking.items():

                st.subheader(f"🚨 {kw}")

                st.write(f"총 {len(items)}건")

                for n in items:

                    st.markdown(f"""### 🚨 [{n['title']}]({n['link']})""")

                    st.caption( n["date"].strftime( "%Y-%m-%d %H:%M" ))

                st.divider()
else:
    st.info("왼쪽에서 키워드 입력 후 검색하세요")
