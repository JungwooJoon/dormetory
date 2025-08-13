import streamlit as st
import pandas as pd
import numpy as np
import requests
from haversine import haversine
from io import BytesIO

# --- Streamlit 페이지 설정 ---
st.set_page_config(page_title="기숙사 거리 계산기", page_icon="📏")

# --- 핵심 로직 함수 (이전과 동일) ---
@st.cache_data
def get_lat_lon_from_address(address, rest_api_key):
    """주소를 위도, 경도로 변환하는 함수"""
    url = f"https://dapi.kakao.com/v2/local/search/address.json?query={address}"
    headers = {"Authorization": f"KakaoAK {rest_api_key}"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        json_result = response.json()
        if json_result.get('documents'):
            address_info = json_result['documents'][0]['address']
            return float(address_info['y']), float(address_info['x']), None
        else:
            return None, None, "주소를 찾을 수 없음"
    except requests.exceptions.RequestException as e:
        return None, None, f"API 요청 실패: {e}"
    except (KeyError, IndexError, TypeError):
        return None, None, "잘못된 API 응답 형식"

def calculate_distance_from_school(lat_lon):
    """학교 좌표로부터의 거리를 계산하는 함수"""
    school_coords = (37.4973462, 126.8640144)
    if lat_lon and all(lat_lon):
        return haversine(school_coords, lat_lon, unit='km')
    return None

def assign_score(distance):
    """거리에 따라 배점을 부여하는 함수"""
    if pd.isna(distance):
        return 0
    if distance >= 400:
        return 70
    elif distance >= 300:
        return 50
    elif distance >= 200:
        return 30
    elif distance >= 100:
        return 10
    else:
        return 0

# --- Streamlit UI 구성 ---
st.title("📏 기숙사 거리 자동 계산기")
st.info("엑셀 파일을 업로드하면 '집주소'가 포함된 컬럼을 기준으로 거리를 계산합니다.")

rest_api_key = st.text_input("카카오(Kakao) REST API 키를 입력하세요", type="password")
uploaded_file = st.file_uploader("거리 계산이 필요한 엑셀 파일을 업로드하세요", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        
        # --- [수정됨] '집주소'를 포함하는 컬럼 자동 찾기 ---
        address_columns = [col for col in df.columns if '집주소' in str(col)]
        selected_address_column = None

        if len(address_columns) == 0:
            st.error("업로드한 엑셀 파일에서 '집주소'를 포함하는 컬럼을 찾을 수 없습니다.")
        elif len(address_columns) == 1:
            selected_address_column = address_columns[0]
            st.info(f"주소 컬럼으로 **'{selected_address_column}'** 을 사용합니다.")
        else:
            # '집주소' 컬럼이 여러 개 발견되면 사용자에게 선택하도록 함
            st.warning(f"'집주소'를 포함하는 컬럼이 여러 개({len(address_columns)}개) 발견되었습니다.")
            selected_address_column = st.selectbox(
                "거리 계산에 사용할 주소 컬럼을 선택하세요.",
                options=address_columns
            )
        # --- [수정 완료] ---

        # 주소 컬럼이 성공적으로 선택된 경우에만 실행 버튼 표시
        if selected_address_column:
            if st.button("거리 계산 실행하기"):
                if not rest_api_key:
                    st.error("API 키를 먼저 입력해야 합니다.")
                else:
                    with st.spinner('주소를 좌표로 변환하고 거리를 계산하는 중입니다...'):
                        total_rows = len(df)
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        df['위도'] = pd.NA
                        df['경도'] = pd.NA
                        df['계산된 거리 (km)'] = pd.NA
                        df['오류 메시지'] = ''

                        for i, row in df.iterrows():
                            # 선택된 주소 컬럼에서 값을 가져옴
                            original_address = str(row.get(selected_address_column, ''))
                            address_to_search = original_address.split(',')[0].strip()
                            
                            if address_to_search:
                                lat, lon, error_message = get_lat_lon_from_address(address_to_search, rest_api_key)
                                if error_message:
                                    df.at[i, '오류 메시지'] = error_message
                                else:
                                    df.at[i, '위도'] = lat
                                    df.at[i, '경도'] = lon
                                    df.at[i, '계산된 거리 (km)'] = calculate_distance_from_school((lat, lon))
                            else:
                                df.at[i, '오류 메시지'] = "주소 정보 없음"

                            progress = (i + 1) / total_rows
                            progress_bar.progress(progress)
                            status_text.text(f"처리 중: {i + 1}/{total_rows} 완료")
                        
                        status_text.text("배점을 계산 중입니다...")
                        df['배점'] = df['계산된 거리 (km)'].apply(assign_score)
                        
                        progress_bar.empty()
                        status_text.empty()

                    st.success("모든 계산이 완료되었습니다!")
                    
                    numeric_cols = ['위도', '경도', '계산된 거리 (km)']
                    for col in numeric_cols:
                        df[col] = pd.to_numeric(df[col], errors='coerce').round(4)
                    
                    st.dataframe(df)

                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='거리계산결과')
                    
                    processed_data = output.getvalue()
                    original_filename = uploaded_file.name.rsplit('.', 1)[0]
                    st.download_button(
                        label="📥 결과 파일 다운로드 (.xlsx)",
                        data=processed_data,
                        file_name=f"{original_filename}_결과.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    except Exception as e:
        st.error(f"파일 처리 중 예상치 못한 오류가 발생했습니다: {e}")
