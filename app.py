import streamlit as st
import pandas as pd
import urllib.parse
from datetime import datetime

# 페이지 설정
st.set_page_config(page_title="지은이랑 성우의 우당탕당 일본 여행", page_icon="✈️")

# 세션 상태(Session State)에 일정 데이터 저장용 데이터프레임 생성
if 'itinerary' not in st.session_state:
    st.session_state.itinerary = pd.DataFrame(columns=['일차', '시간', '장소명', '주소'])

st.title("🇯🇵 일본 여행 일정표 및 동선 생성기")

# --- [입력 섹션] ---
st.header("1. 일정 입력하기")
with st.form("input_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    # 1~4일차 선택
    day = col1.selectbox("몇 일차?", [1, 2, 3, 4])
    # 시간 입력
    time = col2.time_input("방문 시간", value=datetime.strptime('10:00', '%H:%M').time())
    
    # 가게 이름 및 주소 입력
    place = st.text_input("가게 또는 명소 이름 (예: 이치란 라멘 본점)")
    address = st.text_input("정확한 주소 (구글맵 검색용, 예: 일본 〒542-0084 Osaka, Chuo Ward, Souemoncho, 7−18 1F)")
    
    submitted = st.form_submit_button("일정 추가하기")

    if submitted:
        if place and address:
            # 새 일정 추가
            new_row = {
                '일차': day, 
                '시간': time.strftime('%H:%M'), 
                '장소명': place, 
                '주소': address
            }
            new_df = pd.DataFrame([new_row])
            st.session_state.itinerary = pd.concat([st.session_state.itinerary, new_df], ignore_index=True)
            st.success(f"{day}일차 일정에 '{place}'이(가) 추가되었습니다!")
        else:
            st.error("가게 이름과 주소를 모두 입력해주세요.")

# --- [일정표 확인 섹션] ---
st.header("2. 나의 여행 일정표")
# 일차별, 시간별로 정렬하여 보여주기
if not st.session_state.itinerary.empty:
    display_df = st.session_state.itinerary.sort_values(by=['일차', '시간']).reset_index(drop=True)
    st.dataframe(display_df, use_container_width=True)
else:
    st.info("아직 추가된 일정이 없습니다.")

# --- [구글맵 동선 생성 섹션] ---
st.header("3. 구글맵 동선 보기")
selected_day = st.selectbox("동선을 확인할 일차를 선택하세요", [1, 2, 3, 4], key='map_day')
travel_mode = st.radio("이동 수단", ["대중교통", "도보"], horizontal=True)

# 구글맵 길찾기 모드 영문 변환
mode_dict = {"대중교통": "transit", "도보": "walking"}

# 선택한 일차의 데이터만 필터링 후 시간순 정렬
day_data = st.session_state.itinerary[st.session_state.itinerary['일차'] == selected_day].sort_values(by='시간')

if len(day_data) >= 2:
    addresses = day_data['주소'].tolist()
    
    # 출발지, 도착지, 경유지(Waypoints) 분리 및 URL 인코딩 (한글/일본어 깨짐 방지)
    origin = urllib.parse.quote(addresses[0])
    destination = urllib.parse.quote(addresses[-1])
    
    maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&travelmode={mode_dict[travel_mode]}"
    
    # 장소가 3개 이상일 경우 중간 장소들을 경유지로 추가
    if len(addresses) > 2:
        waypoints = "|".join([urllib.parse.quote(addr) for addr in addresses[1:-1]])
        maps_url += f"&waypoints={waypoints}"

    st.markdown(f"### [🗺️ 클릭해서 {selected_day}일차 구글맵 동선 열기]({maps_url})")
    
elif len(day_data) == 1:
    st.warning("동선을 만들려면 해당 일차에 최소 2개 이상의 장소가 입력되어야 합니다.")
else:
    st.info(f"{selected_day}일차에 입력된 일정이 없습니다.")