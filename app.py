import streamlit as st
import googleapiclient.discovery
import deepl
import pysrt # .srt 파일을 위한 라이브러리
import io
import json

# [v6] DeepL Free/Pro API가 지원하는 언어 코드 기준
# 참고: DeepL은 'zh' 하나로 간체/번체를 처리합니다.
# 요청하신 25개 언어에 최대한 맞춘 리스트입니다. (일부 Pro 필요)
TARGET_LANGUAGES = {
    '노르웨이어': 'NB', '덴마크어': 'DA', '독일어': 'DE', '러시아어': 'RU',
    '마라티어': 'MR', '말레이어': 'MS', '베트남어': 'VI', '벵골어': 'BN',
    '스페인어': 'ES', '아랍어': 'AR', '우르두어': 'UR', '우크라이나어': 'UK',
    '이탈리아어': 'IT', '인도네시아어': 'ID', '일본어': 'JA',
    '중국어(간체)': 'ZH', '중국어(번체)': 'ZH', # DeepL은 'ZH'로 통합
    '타밀어': 'TA', '태국어': 'TH', '텔루구어': 'TE', '튀르키예어': 'TR',
    '포르투갈어(브라질)': 'PT-BR', # 'PT'도 가능하나 'PT-BR'이 명시적
    '프랑스어': 'FR', '한국어': 'KO', '힌디어': 'HI',
}

# --- API 키 로드 및 클라이언트 초기화 ---
try:
    # Streamlit 배포 환경에서는 st.secrets에서, 로컬에서는 secrets.toml에서 읽어옵니다.
    YOUTUBE_KEY = st.secrets["YOUTUBE_API_KEY"]
    DEEPL_KEY = st.secrets["DEEPL_API_KEY"]
    
    # DeepL 번역기 초기화
    translator = deepl.Translator(DEEPL_KEY)
    
    # YouTube API 클라이언트 초기화
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_KEY)

except FileNotFoundError:
    st.error("오류: `.streamlit/secrets.toml` 파일을 찾을 수 없습니다. (2단계 5항 확인)")
    st.stop()
except KeyError:
    st.error("오류: Streamlit Secrets에 API 키가 설정되지 않았습니다. (4단계 2항 확인)")
    st.stop()
except Exception as e:
    st.error(f"API 클라이언트 초기화 실패: {e}")
    st.stop()


# --- 핵심 기능 함수 ---

# 1. 유튜브 API로 영상 정보 가져오기
def get_video_details(video_id):
    try:
        request = youtube.videos().list(
            part="snippet",
            id=video_id
        )
        response = request.execute()
        if not response.get("items"):
            return None, None, "ID 오류: 영상을 찾을 수 없습니다."
        
        snippet = response["items"][0]["snippet"]
        return snippet["title"], snippet["description"], None
    except Exception as e:
        return None, None, f"YouTube API 오류: {str(e)}"

# 2. DeepL API로 텍스트 번역하기
def translate_text(text_list, target_lang_code):
    try:
        # DeepL은 텍스트 '리스트'를 받아 한 번에 번역할 수 있습니다. (효율적)
        results = translator.translate_text(text_list, target_lang=target_lang_code, source_lang="EN")
        return [result.text for result in results], None
    except Exception as e:
        return None, f"DeepL 번역 오류 ({target_lang_code}): {str(e)}"

# --- UI (Streamlit) ---
st.set_page_config(layout="wide")
st.title("Master's 하이브리드 번역기 (v6)")
st.info("이 앱은 '제목/설명'은 YouTube API로 자동화하고, '자막'은 수동으로 업로드하여 번역합니다.")

# --- 세션 상태 초기화 ---
if "video_details" not in st.session_state:
    st.session_state.video_details = {"title": "", "desc": ""}
if "translations" not in st.session_state:
    st.session_state.translations = {}
if "translation_errors" not in st.session_state:
    st.session_state.translation_errors = []
if "translated_srts" not in st.session_state:
    st.session_state.translated_srts = {}


# --- 탭 구분 ---
tab1, tab2 = st.tabs(["[Task 1] 제목/설명 번역", "[Task 2] 자막 (.srt) 번역"])

# --- [Task 1] 제목/설명 번역 탭 ---
with tab1:
    st.header("1. 영상 제목 및 설명 번역")
    video_id = st.text_input("유튜브 영상 ID를 입력하세요 (예: dQw4w9WgXcQ)")

    # [버튼 1] 영상 정보 가져오기
    if st.button("1. 원본 영상 정보 가져오기"):
        if not video_id:
            st.warning("유튜브 영상 ID를 입력하세요.")
        else:
            with st.spinner("YouTube API로 원본 영상 정보를 가져오는 중..."):
                title, desc, error = get_video_details(video_id)
                if error:
                    st.error(error)
                else:
                    st.session_state.video_details = {"title": title, "desc": desc}
                    st.success("원본 정보를 성공적으로 가져왔습니다.")

    # st.session_state를 사용하여 입력 필드 값을 유지합니다.
    st.session_state.video_details["title"] = st.text_input(
        "원본 제목 (자동 입력됨)", 
        value=st.session_state.video_details["title"]
    )
    st.session_state.video_details["desc"] = st.text_area(
        "원본 설명 (자동 입력됨)", 
        value=st.session_state.video_details["desc"], 
        height=150
    )

    # [버튼 2] 번역 실행
    if st.button("2. 모든 언어로 번역 실행 (DeepL API 사용)"):
        orig_title = st.session_state.video_details["title"]
        orig_desc = st.session_state.video_details["desc"]

        if not orig_title:
            st.warning("먼저 원본 제목을 가져오거나 입력하세요.")
        else:
            with st.spinner(f"{len(TARGET_LANGUAGES)}개 언어로 번역 중... (시간이 걸릴 수 있습니다)"):
                translations = {}
                errors = []
                
                texts_to_translate = [orig_title, orig_desc if orig_desc else " "]

                for lang_name, lang_code in TARGET_LANGUAGES.items():
                    # [v6 수정] 텍스트 리스트를 한 번에 번역
                    translated_list, error = translate_text(texts_to_translate, lang_code)
                    
                    if error:
                        errors.append(error)
                    else:
                        translations[lang_code] = {
                            "lang_name": lang_name,
                            "title": translated_list[0],
                            "desc": translated_list[1]
                        }

                st.session_state.translations = translations
                st.session_state.translation_errors = errors
                
                st.success(f"{len(translations)}개 언어 번역 완료!")
                if errors:
                    st.error("일부 언어 번역 실패:")
                    for e in errors:
                        st.write(e)

    # [결과 표시]
    st.subheader("3. 검수 및 다운로드")
    st.write("기계 번역 결과입니다. **직접 검수하고 수정한 뒤**, 아래 버튼으로 JSON 파일을 다운로드하십시오.")

    # 검수/수정을 위한 UI
    if st.session_state.translations:
        # 수정된 내용을 저장할 임시 딕셔너리
        corrected_translations = {}

        for lang_code, data in st.session_state.translations.items():
            lang_name = data["lang_name"]
            with st.expander(f"✅ {lang_name} ({lang_code})"):
                # st.text_area의 key를 이용해 Streamlit이 수정된 값을 기억하도록 함
                corrected_title = st.text_area(
                    "수정된 제목", 
                    value=data["title"], 
                    key=f"title_{lang_code}"
                )
                corrected_desc = st.text_area(
                    "수정된 설명", 
                    value=data["desc"], 
                    key=f"desc_{lang_code}", 
                    height=150
                )
                
                # 수정된 내용을 딕셔너리에 저장
                corrected_translations[lang_code] = {
                    "lang_name": lang_name,
                    "title": corrected_title,
                    "desc": corrected_desc
                }
        
        # [v6 신규] JSON 다운로드 버튼
        if not st.session_state.translations:
            st.info("먼저 번역을 실행하세요.")
        else:
            # JSON 파일로 변환
            # (주의: corrected_translations는 매 렌더링마다 생성되므로,
            # 실제로는 st.session_state에 저장된 key 값을 기반으로 JSON을 만들어야 함)
            
            final_json_data = {}
            for lang_code, data in st.session_state.translations.items():
                final_json_data[lang_code] = {
                    "lang_name": data["lang_name"],
                    "title": st.session_state[f"title_{lang_code}"], # key로 최신 값 접근
                    "desc": st.session_state[f"desc_{lang_code}"]  # key로 최신 값 접근
                }

            st.download_button(
                label="검수 완료된 제목/설명 다운로드 (JSON)",
                data=json.dumps(final_json_data, indent=2, ensure_ascii=False),
                file_name=f"{video_id or 'manual'}_translations.json",
                mime="application/json"
            )


# --- [Task 2] 자막 (.srt) 번역 탭 ---
with tab2:
    st.header("2. SRT 자막 파일 번역")
    st.write("`영어`로 된 .srt 파일을 업로드하면 DeepL API를 통해 모든 언어로 자동 번역하고, 개별 파일로 다운로드할 수 있습니다.")

    uploaded_file = st.file_uploader("원본 .srt 자막 파일을 업로드하세요 (영어 권장)", type=["srt"])

    if uploaded_file is not None:
        # 파일 내용 읽기 (UTF-8)
        try:
            srt_content_bytes = uploaded_file.getvalue()
            srt_content_str = srt_content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                # UTF-8이 아니면 'latin-1' 시도
                srt_content_str = srt_content_bytes.decode('latin-1')
            except Exception as e:
                st.error(f"파일 디코딩 오류: {e}. (UTF-8로 인코딩된 .srt 파일이 필요합니다)")
                st.stop()
        
        st.text_area("원본 .srt 파일 내용 (앞 500자)", srt_content_str[:500] + "...")

        # [버튼 3] 자막 번역 실행
        if st.button("3. 자막 파일 번역 실행 (모든 언어)"):
            try:
                # pysrt로 srt 파싱
                subs = pysrt.from_string(srt_content_str)
                st.session_state.parsed_subs = subs
                st.session_state.translated_srts = {} # 초기화
                
                # 텍스트만 추출
                texts_to_translate = [sub.text for sub in subs]

                with st.spinner(f"{len(TARGET_LANGUAGES)}개 언어로 자막 번역 중... (매우 오래 걸릴 수 있습니다)"):
                    errors = []
                    
                    # 텍스트가 50개 이상일 경우 (DeepL Free API 제한) 분할 처리
                    chunk_size = 50
                    translated_texts_all_langs = {}
                    
                    for i in range(0, len(texts_to_translate), chunk_size):
                        chunk = texts_to_translate[i:i+chunk_size]
                        
                        for lang_name, lang_code in TARGET_LANGUAGES.items():
                            if lang_name not in translated_texts_all_langs:
                                translated_texts_all_langs[lang_name] = []
                            
                            try:
                                translated_chunk, error = translate_text(chunk, lang_code)
                                if error:
                                    errors.append(f"자막 번역 오류 ({lang_name}): {error}")
                                    # 오류 발생 시 원본 텍스트로 채움
                                    translated_texts_all_langs[lang_name].extend(chunk)
                                else:
                                    translated_texts_all_langs[lang_name].extend(translated_chunk)
                                
                            except Exception as e:
                                errors.append(f"자막 청크 처리 오류 ({lang_name}): {str(e)}")
                                translated_texts_all_langs[lang_name].extend(chunk)
                        
                        st.progress((i + chunk_size) / len(texts_to_translate)) # 진행률 표시

                    # 번역된 텍스트로 srt 파일 재조립
                    for lang_name, translated_texts in translated_texts_all_langs.items():
                        new_subs = pysrt.from_string(srt_content_str) # 원본 복사
                        if len(new_subs) == len(translated_texts):
                            for i, sub in enumerate(new_subs):
                                sub.text = translated_texts[i]
                            
                            output_stream = io.StringIO()
                            new_subs.save(output_stream, encoding='utf-8')
                            st.session_state.translated_srts[lang_name] = output_stream.getvalue()
                        else:
                            errors.append(f"자막 길이 불일치 ({lang_name})")

                    st.success("자막 파일 번역 완료!")
                    if errors:
                        st.error("일부 언어 자막 번역 실패:")
                        for e in errors:
                            st.write(e)

            except Exception as e:
                st.error(f"SRT 파싱 또는 번역 중 심각한 오류: {e}")

        # [결과 2] 다운로드 버튼 표시
        if st.session_state.translated_srts:
            st.subheader("4. 번역된 .srt 파일 다운로드")
            st.write("각 언어별로 생성된 .srt 파일을 다운로드하여 YouTube 스튜디오에 '수동으로' 업로드하십시오.")
            
            cols = st.columns(5) # 5열로 정렬
            col_index = 0
            
            for lang_name, srt_data in st.session_state.translated_srts.items():
                if srt_data: # 데이터가 있는 경우에만 버튼 생성
                    cols[col_index].download_button(
                        label=f"다운로드 ({lang_name})",
                        data=srt_data,
                        file_name=f"{uploaded_file.name.split('.')[0]}_{TARGET_LANGUAGES[lang_name]}.srt",
                        mime="text/plain",
                        key=f"srt_dl_{lang_name}"
                    )
                    col_index = (col_index + 1) % 5