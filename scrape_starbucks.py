import io
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="전국 스타벅스 매장 현황",
    page_icon="☕",
    layout="wide",
)

STORE_API_URL = "https://www.starbucks.co.kr/store/getStore.do"

# 스타벅스 공식 매장찾기에서 사용하는 시도 코드
SIDO_CODES = {
    "서울": "01",
    "경기": "08",
    "광주": "02",
    "대구": "03",
    "대전": "04",
    "부산": "05",
    "울산": "06",
    "인천": "07",
    "강원": "09",
    "경남": "10",
    "경북": "11",
    "전남": "12",
    "전북": "13",
    "충남": "14",
    "충북": "15",
    "제주": "16",
    "세종": "17",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.starbucks.co.kr/store/store_map.do",
    "Origin": "https://www.starbucks.co.kr",
    "X-Requested-With": "XMLHttpRequest",
}


# ------------------------------------------------------------
# 보조 함수
# ------------------------------------------------------------
def clean_text(value) -> str:
    """결측치와 공백을 정리한다."""
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {"none", "nan", "null"}:
        return ""

    return " ".join(text.split())


def safe_float(value):
    """문자열 좌표를 실수로 변환한다."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_sigungu(address: str) -> str:
    """
    주소에서 시군구를 추출한다.

    예:
    서울특별시 강남구 테헤란로 ... → 강남구
    경기도 수원시 영통구 ... → 수원시 영통구
    세종특별자치시 도움8로 ... → 세종시
    """
    address = clean_text(address)

    if not address:
        return ""

    parts = address.split()

    if not parts:
        return ""

    # 세종특별자치시는 기초자치단체가 따로 없음
    if "세종" in parts[0]:
        return "세종시"

    candidates = []

    # 광역자치단체명 다음에 나오는 행정구역을 탐색
    for part in parts[1:4]:
        if part.endswith(("시", "군", "구")):
            candidates.append(part)

    if not candidates:
        return ""

    # 수원시 영통구, 성남시 분당구처럼 시와 일반구가 함께 있는 경우
    if (
        len(candidates) >= 2
        and candidates[0].endswith("시")
        and candidates[1].endswith("구")
    ):
        return f"{candidates[0]} {candidates[1]}"

    return candidates[0]


def normalize_store(store: dict, sido_name: str) -> dict:
    """스타벅스 응답 한 건을 분석용 표준 형식으로 변환한다."""
    road_address = clean_text(
        store.get("addr")
        or store.get("addr2")
        or store.get("new_address")
    )

    old_address = clean_text(
        store.get("addr_old")
        or store.get("old_address")
    )

    address_for_region = road_address or old_address

    latitude = safe_float(
        store.get("lat")
        or store.get("latitude")
    )

    longitude = safe_float(
        store.get("lot")
        or store.get("lng")
        or store.get("longitude")
    )

    return {
        "매장코드": clean_text(
            store.get("s_code")
            or store.get("seq")
            or store.get("store_code")
        ),
        "매장명": clean_text(
            store.get("s_name")
            or store.get("store_nm")
            or store.get("name")
        ),
        "시도": sido_name,
        "시군구": extract_sigungu(address_for_region),
        "도로명주소": road_address,
        "지번주소": old_address,
        "전화번호": clean_text(
            store.get("tel")
            or store.get("store_tel")
        ),
        "위도": latitude,
        "경도": longitude,
        "매장유형": clean_text(
            store.get("store_type")
            or store.get("storeTypeName")
        ),
        "영업상태": clean_text(
            store.get("open_dt")
            or store.get("open_date")
        ),
    }


def extract_store_list(response_json) -> list:
    """
    응답 구조가 변경되더라도 가능한 범위에서 매장 목록을 찾는다.
    """
    if isinstance(response_json, list):
        return response_json

    if not isinstance(response_json, dict):
        return []

    possible_keys = [
        "list",
        "storeList",
        "stores",
        "result",
        "data",
    ]

    for key in possible_keys:
        value = response_json.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in possible_keys:
                nested_value = value.get(nested_key)
                if isinstance(nested_value, list):
                    return nested_value

    return []


def request_region_stores(
    session: requests.Session,
    sido_name: str,
    sido_code: str,
) -> list:
    """특정 시도의 스타벅스 매장 정보를 요청한다."""
    payload = {
        "ins_lat": "37.56682",
        "ins_lng": "126.97865",
        "p_sido_cd": sido_code,
        "p_gugun_cd": "",
        "in_biz_cd": "",
        "set_date": "",
        "iend": "5000",
        "search_text": "",
        "all_store": "0",
        "T03": "0",
        "T01": "0",
        "T12": "0",
        "T09": "0",
        "T30": "0",
        "T05": "0",
        "T22": "0",
        "T21": "0",
        "T10": "0",
        "T36": "0",
        "P10": "0",
        "P50": "0",
        "P20": "0",
        "P60": "0",
        "P30": "0",
        "P70": "0",
        "P40": "0",
        "P80": "0",
        "whcroad_yn": "0",
        "P90": "0",
        "new_bool": "0",
    }

    response = session.post(
        STORE_API_URL,
        data=payload,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    try:
        response_json = response.json()
    except requests.exceptions.JSONDecodeError as error:
        raise RuntimeError(
            f"{sido_name} 응답이 JSON 형식이 아닙니다. "
            "스타벅스 사이트의 데이터 구조가 변경되었을 수 있습니다."
        ) from error

    store_list = extract_store_list(response_json)

    return [
        normalize_store(store, sido_name)
        for store in store_list
        if isinstance(store, dict)
    ]


@st.cache_data(ttl=3600, show_spinner=False)
def collect_all_stores():
    """
    전국 매장 데이터를 수집한다.

    반환값:
    1. 매장 데이터프레임
    2. 시도별 수집 결과 데이터프레임
    3. 수집 시각
    """
    stores = []
    collection_log = []

    with requests.Session() as session:
        # 세션 쿠키 생성을 위해 매장찾기 페이지에 먼저 접속
        try:
            session.get(
                "https://www.starbucks.co.kr/store/store_map.do",
                headers=HEADERS,
                timeout=20,
            )
        except requests.RequestException:
            # 초기 페이지 접속 실패가 실제 API 요청 실패를 뜻하지는 않으므로 계속 진행
            pass

        for sido_name, sido_code in SIDO_CODES.items():
            try:
                region_stores = request_region_stores(
                    session=session,
                    sido_name=sido_name,
                    sido_code=sido_code,
                )

                stores.extend(region_stores)

                collection_log.append(
                    {
                        "시도": sido_name,
                        "수집상태": "성공",
                        "매장수": len(region_stores),
                        "오류내용": "",
                    }
                )

            except Exception as error:
                collection_log.append(
                    {
                        "시도": sido_name,
                        "수집상태": "실패",
                        "매장수": 0,
                        "오류내용": str(error),
                    }
                )

            # 서버에 지나치게 빠르게 요청하지 않도록 잠시 대기
            time.sleep(0.25)

    collected_at = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).strftime("%Y-%m-%d %H:%M:%S")

    store_df = pd.DataFrame(stores)
    log_df = pd.DataFrame(collection_log)

    if not store_df.empty:
        # 중복 매장 제거
        if "매장코드" in store_df.columns:
            has_code = store_df["매장코드"].ne("")

            coded = store_df.loc[has_code].drop_duplicates(
                subset=["매장코드"],
                keep="first",
            )

            uncoded = store_df.loc[~has_code].drop_duplicates(
                subset=["매장명", "도로명주소"],
                keep="first",
            )

            store_df = pd.concat(
                [coded, uncoded],
                ignore_index=True,
            )
        else:
            store_df = store_df.drop_duplicates(
                subset=["매장명", "도로명주소"],
                keep="first",
            )

        store_df = store_df.sort_values(
            by=["시도", "시군구", "매장명"],
            na_position="last",
        ).reset_index(drop=True)

        store_df.insert(0, "연번", range(1, len(store_df) + 1))
        store_df["수집시각"] = collected_at

    return store_df, log_df, collected_at


def dataframe_to_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    """
    엑셀에서 한글이 깨지지 않도록 UTF-8 BOM 형식의 CSV를 만든다.
    """
    return dataframe.to_csv(
        index=False,
        encoding="utf-8-sig",
    ).encode("utf-8-sig")


# ------------------------------------------------------------
# 화면 구성
# ------------------------------------------------------------
st.title("전국 스타벅스 매장 현황")
st.caption(
    "스타벅스 코리아 공식 매장찾기 정보를 수집하여 "
    "지역별 매장 분포를 보여주는 Streamlit 앱입니다."
)

with st.expander("사용 방법과 주의사항"):
    st.markdown(
        """
        1. 아래의 **전국 매장 데이터 수집** 버튼을 누릅니다.
        2. 수집이 끝나면 시도와 시군구를 선택해 결과를 확인합니다.
        3. 필요한 경우 전체 데이터 또는 지역별 요약 데이터를 CSV로 내려받습니다.

        **주의사항**

        - 이 앱은 스타벅스의 공식 공개 API가 아니라 공식 매장찾기 페이지가
          사용하는 데이터 요청 방식을 이용합니다.
        - 스타벅스 홈페이지 구조가 변경되면 수집 기능이 작동하지 않을 수 있습니다.
        - 반복적으로 버튼을 누르지 않도록 수집 결과를 1시간 동안 임시 저장합니다.
        - 연구에 사용할 때는 데이터 수집일을 반드시 기록하는 것이 좋습니다.
        """
    )

collect_button = st.button(
    "전국 매장 데이터 수집",
    type="primary",
    use_container_width=True,
)

if not collect_button:
    st.info(
        "버튼을 누르면 전국 스타벅스 매장 정보를 수집합니다."
    )
    st.stop()

with st.spinner("전국 매장 정보를 수집하고 있습니다."):
    try:
        store_df, log_df, collected_at = collect_all_stores()
    except Exception as error:
        st.error(f"데이터 수집 중 오류가 발생했습니다: {error}")
        st.stop()

if store_df.empty:
    st.error(
        "수집된 매장 데이터가 없습니다. "
        "스타벅스 사이트의 응답 구조가 변경되었거나 "
        "일시적으로 요청이 차단되었을 수 있습니다."
    )

    if not log_df.empty:
        st.subheader("지역별 수집 결과")
        st.dataframe(
            log_df,
            use_container_width=True,
            hide_index=True,
        )

    st.stop()


# ------------------------------------------------------------
# 전체 현황
# ------------------------------------------------------------
st.success(
    f"{len(store_df):,}개 매장을 수집했습니다. "
    f"수집 시각: {collected_at}"
)

sido_summary = (
    store_df.groupby("시도", as_index=False)
    .size()
    .rename(columns={"size": "매장수"})
    .sort_values("매장수", ascending=False)
)

sigungu_summary = (
    store_df.groupby(
        ["시도", "시군구"],
        as_index=False,
        dropna=False,
    )
    .size()
    .rename(columns={"size": "매장수"})
    .sort_values(
        ["매장수", "시도", "시군구"],
        ascending=[False, True, True],
    )
)

col1, col2, col3 = st.columns(3)

col1.metric(
    "전국 매장 수",
    f"{len(store_df):,}개",
)

col2.metric(
    "매장이 있는 시도",
    f"{store_df['시도'].nunique():,}개",
)

col3.metric(
    "매장이 있는 시군구",
    f"{store_df['시군구'].replace('', pd.NA).nunique():,}개",
)

st.divider()


# ------------------------------------------------------------
# 지역 필터
# ------------------------------------------------------------
st.subheader("지역별 매장 검색")

filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])

sido_options = ["전체"] + sorted(
    store_df["시도"].dropna().unique().tolist()
)

selected_sido = filter_col1.selectbox(
    "시도",
    sido_options,
)

if selected_sido == "전체":
    sigungu_options = ["전체"]
else:
    sigungu_options = ["전체"] + sorted(
        store_df.loc[
            store_df["시도"] == selected_sido,
            "시군구",
        ]
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )

selected_sigungu = filter_col2.selectbox(
    "시군구",
    sigungu_options,
)

search_word = filter_col3.text_input(
    "매장명 또는 주소 검색",
    placeholder="예: 강남, 대학로, 제주",
)

filtered_df = store_df.copy()

if selected_sido != "전체":
    filtered_df = filtered_df[
        filtered_df["시도"] == selected_sido
    ]

if selected_sigungu != "전체":
    filtered_df = filtered_df[
        filtered_df["시군구"] == selected_sigungu
    ]

if search_word.strip():
    keyword = search_word.strip()

    search_mask = (
        filtered_df["매장명"]
        .fillna("")
        .str.contains(keyword, case=False, regex=False)
        |
        filtered_df["도로명주소"]
        .fillna("")
        .str.contains(keyword, case=False, regex=False)
    )

    filtered_df = filtered_df[search_mask]

st.write(f"검색 결과: **{len(filtered_df):,}개 매장**")

display_columns = [
    "매장명",
    "시도",
    "시군구",
    "도로명주소",
    "전화번호",
    "위도",
    "경도",
]

st.dataframe(
    filtered_df[display_columns],
    use_container_width=True,
    hide_index=True,
    height=500,
)


# ------------------------------------------------------------
# 지도
# ------------------------------------------------------------
map_df = filtered_df[
    ["위도", "경도", "매장명"]
].dropna(subset=["위도", "경도"]).copy()

map_df = map_df.rename(
    columns={
        "위도": "lat",
        "경도": "lon",
    }
)

if not map_df.empty:
    st.subheader("매장 위치")
    st.map(
        map_df,
        latitude="lat",
        longitude="lon",
        size=20,
    )


# ------------------------------------------------------------
# 지역별 집계
# ------------------------------------------------------------
st.divider()
st.subheader("지역별 매장 수")

summary_tab1, summary_tab2, summary_tab3 = st.tabs(
    ["시도별", "시군구별", "수집 점검"]
)

with summary_tab1:
    st.bar_chart(
        sido_summary.set_index("시도")["매장수"],
        horizontal=True,
    )

    st.dataframe(
        sido_summary,
        use_container_width=True,
        hide_index=True,
    )

with summary_tab2:
    st.dataframe(
        sigungu_summary,
        use_container_width=True,
        hide_index=True,
        height=600,
    )

with summary_tab3:
    st.dataframe(
        log_df,
        use_container_width=True,
        hide_index=True,
    )

    failed_regions = log_df[
        log_df["수집상태"] == "실패"
    ]

    if failed_regions.empty:
        st.success("모든 시도의 데이터 수집에 성공했습니다.")
    else:
        st.warning(
            f"{len(failed_regions)}개 시도에서 수집 오류가 발생했습니다."
        )


# ------------------------------------------------------------
# CSV 내려받기
# ------------------------------------------------------------
st.divider()
st.subheader("데이터 내려받기")

download_col1, download_col2, download_col3 = st.columns(3)

date_text = datetime.now(
    ZoneInfo("Asia/Seoul")
).strftime("%Y%m%d")

download_col1.download_button(
    label="전체 매장 CSV",
    data=dataframe_to_csv_bytes(store_df),
    file_name=f"starbucks_korea_stores_{date_text}.csv",
    mime="text/csv",
    use_container_width=True,
)

download_col2.download_button(
    label="시도별 요약 CSV",
    data=dataframe_to_csv_bytes(sido_summary),
    file_name=f"starbucks_sido_summary_{date_text}.csv",
    mime="text/csv",
    use_container_width=True,
)

download_col3.download_button(
    label="시군구별 요약 CSV",
    data=dataframe_to_csv_bytes(sigungu_summary),
    file_name=f"starbucks_sigungu_summary_{date_text}.csv",
    mime="text/csv",
    use_container_width=True,
)

st.caption(
    "자료 출처: 스타벅스 코리아 공식 매장찾기 · "
    f"데이터 수집 시각: {collected_at}"
)
