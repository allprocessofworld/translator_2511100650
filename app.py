import streamlit as st
import googleapiclient.discovery
import deepl
import pysrt # .srt 파일을 위한 라이브러리
import io
import json

# [v6.2 수정] 언어를 '안정(Stable)'과 '베타(Beta)'로 분리합니다.
# 'beta: True'는 Pro 플랜과 enable_beta_languages=True 플래그가 필요합니다.
TARGET_LANGUAGES = {
    # --- Stable Languages (Free/Pro) ---
    '노르웨이어': {'code': 'NB', 'beta': False},
    '덴마크어': {'code': 'DA', 'beta': False},
    '독일어': {'code': 'DE', 'beta': False},
    '러시아어': {'code': 'RU', 'beta': False},
    '베트남어': {'code': 'VI', 'beta': False},
    '스페인어': {'code': 'ES', 'beta': False},
    '아랍어': {'code': 'AR', 'beta': False},
    '우크라이나어': {'code': 'UK', 'beta': False},
    '이탈리아어': {'code': 'IT', 'beta': False},
    '인도네시아어': {'code': 'ID', 'beta': False},
    '일본어': {'code': 'JA', 'beta': False},
    '중국어(간체)': {'code': 'ZH', 'beta': False},
    '중국어(번체)': {'code': 'ZH', 'beta': False}, # DeepL은 'ZH'로 통합
    '튀르키예어': {'code': 'TR', 'beta': False},
    '포르투갈어(브라질)': {'code': 'PT-BR', 'beta': False},
    '프랑스어': {'code': 'FR', 'beta': False},
    '한국어': {'code': 'KO', 'beta': False},
    
    # --- Beta Languages (Pro Only) ---
    '마라티어': {'code': 'MR', 'beta': True},
    '말레이어': {'code': 'MS', 'beta': True}, # MS도 Beta로 간주
    '벵골어': {'code': 'BN', 'beta': True},
    '우르두어': {'code': 'UR', 'beta': True},
    '타밀어': {'code': 'TA', 'beta': True},
    '태국어': {'code': 'TH', 'beta': True},
    '텔루구어': {'code': 'TE', 'beta': True},
    '힌디어': {'code': 'HI', 'beta': True},
}

# --- API 키 로드 및 클라이언트 초기화 ---
try:
    YOUTUBE_KEY = st.secrets["YOUTUBE_API_KEY"]
    DEEPL_KEY = st.secrets["DEEPL_API_KEY"]
    
    translator = deepl.Translator(DEEPL_KEY)
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
def translate_text(text_list, target_lang_code, is_beta=False):
    try:
        # [v6.2 수정] 'is_beta' 플래그에 따라 API 호출을 분리합니다.
        request_params = {
            "text": text_list,
            "target_lang": target_lang_code,
            "source_lang": "EN"
        }
        
        if is_beta:
            # 베타 언어는 이 플래그가 필요합니다.
            request_params["enable_beta_languages"] = True
        
        results = translator.translate_text(**request_params)
        
        return [result.text for result in results], None
    except Exception as e:
        return None, f"DeepL 번역 오류 ({target_lang_code}): {str(e)}"

# --- UI (Streamlit) ---
st.set_page_config(layout="wide")
st.title("Master's 하이브리드 번역기 (v6.2 - Beta Fix)")
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

    st.session_state.video_details["title"] = st.text_input(
        "원본 제목 (자동 입력됨)", 
        value=st.session_state.video_details["title"]
    )
    st.session_state.video_details["desc"] = st.text_area(
        "원본 설명 (자동 입력됨)", 
        value=st.session_state.video_details["desc"], 
        height=150
    )

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

                # [v6.2 수정] 분리된 언어 정보를 사용
                for lang_name, lang_info in TARGET_LANGUAGES.items():
                    lang_code = lang_info['code']
                    is_beta = lang_info['beta']
                    
                    translated_list, error = translate_text(texts_to_translate, lang_code, is_beta)
                    
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
                    for e in st.session_state.translation_errors:
                        st.write(e)

    st.subheader("3. 검수 및 다운로드")
    st.write("기계 번역 결과입니다. **직접 검수하고 수정한 뒤**, 아래 버튼으로 JSON 파일을 다운로드하십시오.")

    if st.session_state.translations:
        # [v6.2 수정] lang_code가 중복될 수 있으므로 (ZH) 키를 고유하게 만듭니다.
        corrected_translations = {}
        idx = 0
        for lang_name, lang_info in TARGET_LANGUAGES.items():
            lang_code = lang_info['code']
            # 번역에 성공한 경우에만 UI 표시
            if lang_code in st.session_state.translations or (lang_code == 'ZH' and 'ZH' in st.session_state.translations):
                
                # '중국어(간체)'와 '중국어(번체)'는 DeepL에서 'ZH' 코드를 공유합니다.
                # st.session_state.translations 에는 'ZH' 키가 하나만 있습니다.
                # UI에서는 두 개로 분리하여 보여주기 위해 lang_name을 고유 키로 사용합니다.
                
                data_key = lang_code
                ui_key = f"{lang_code}_{idx}" # 고유한 UI 키 (예: ZH_1, ZH_2)
                
                # 'ZH'가 아닌 경우, 또는 'ZH'이면서 lang_name이 간체/번체 중 하나일 때
                if lang_code != 'ZH' or (lang_code == 'ZH' and lang_name in ['중국어(간체)', '중국어(번체)']):
                    # 번역 데이터 가져오기. 'ZH'는 공통 데이터를 사용합니다.
                    data = st.session_state.translations.get(data_key)
                    if not data:
                        # 'ZH' 키에 데이터가 없는 경우 (오류)
                        continue

                    with st.expander(f"✅ {lang_name} ({lang_code})"):
                        corrected_title = st.text_area(
                            "수정된 제목", 
                            value=data["title"], 
                            key=f"title_{ui_key}"
                        )
                        corrected_desc = st.text_area(
                            "수정된 설명", 
                            value=data["desc"], 
                            key=f"desc_{ui_key}", 
                            height=150
                        )
                        
                        corrected_translations[lang_name] = { # 키를 lang_code 대신 lang_name으로 저장
                            "lang_name": lang_name,
                            "title": corrected_title,
                            "desc": corrected_desc
                        }
            idx += 1
        
        if not corrected_translations:
            st.info("먼저 번역을 실행하세요.")
        else:
            final_json_data = {}
            # 다운로드 버튼 로직: st.session_state에서 최신 값을 읽어옵니다.
            idx = 0
            for lang_name, lang_info in TARGET_LANGUAGES.items():
                lang_code = lang_info['code']
                ui_key = f"{lang_code}_{idx}"
                data_key = lang_code
                
                # 번역된 데이터가 있는지 확인
                if st.session_state.translations.get(data_key):
                    if lang_code != 'ZH' or (lang_code == 'ZH' and lang_name in ['중국어(간체)', '중국어(번체)']):
                        # st.session_state에서 직접 검수된 값을 가져옵니다.
                        final_json_data[lang_name] = {
                            "lang_name": lang_name,
                            "title": st.session_state.get(f"title_{ui_key}", st.session_state.translations[data_key]["title"]), 
                            "desc": st.session_state.get(f"desc_{ui_key}", st.session_state.translations[data_key]["desc"])
                        }
                idx += 1

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
        try:
            srt_content_bytes = uploaded_file.getvalue()
            srt_content_str = srt_content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                srt_content_str = srt_content_bytes.decode('latin-1')
            except Exception as e:
                st.error(f"파일 디코딩 오류: {e}. (UTF-8로 인코딩된 .srt 파일이 필요합니다)")
                st.stop()
        
        st.text_area("원본 .srt 파일 내용 (앞 500자)", srt_content_str[:500] + "...")

        if st.button("3. 자막 파일 번역 실행 (모든 언어)"):
            try:
                subs = pysrt.from_string(srt_content_str)
                st.session_state.parsed_subs = subs
                st.session_state.translated_srts = {} 
                
                texts_to_translate = [sub.text for sub in subs]

                with st.spinner(f"{len(TARGET_LANGUAGES)}개 언어로 자막 번역 중... (매우 오래 걸릴 수 있습니다)"):
                    errors = []
                    chunk_size = 50 
                    translated_texts_all_langs = {}
                    
                    for i in range(0, len(texts_to_translate), chunk_size):
                        chunk = texts_to_translate[i:i+chunk_size]
                        
                        # [v6.2 수정] 분리된 언어 정보를 사용
                        for lang_name, lang_info in TARGET_LANGUAGES.items():
                            if lang_name not in translated_texts_all_langs:
                                translated_texts_all_langs[lang_name] = []
                            
                            lang_code = lang_info['code']
                            is_beta = lang_info['beta']

                            try:
                                translated_chunk, error = translate_text(chunk, lang_code, is_beta)
                                
                                if error:
                                    errors.append(f"자막 번역 오류 ({lang_name}): {error}")
                                    translated_texts_all_langs[lang_name].extend(chunk)
                                else:
                                    translated_texts_all_langs[lang_name].extend(translated_chunk)
                                
                            except Exception as e:
                                errors.append(f"자막 청크 처리 오류 ({lang_name}): {str(e)}")
                                translated_texts_all_langs[lang_name].extend(chunk)
                        
                        current_progress = (i + chunk_size) / len(texts_to_translate)
                        if current_progress > 1: current_progress = 1.0
                        st.progress(current_progress)

                    # 번역된 텍스트로 srt 파일 재조립
                    for lang_name, translated_texts in translated_texts_all_langs.items():
                        new_subs = pysrt.from_string(srt_content_str) 
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
                        # 고유한 오류 메시지만 표시
                        for e in sorted(list(set(errors))):
                            st.write(e)

            except Exception as e:
                st.error(f"SRT 파싱 또는 번역 중 심각한 오류: {e}")

        if st.session_state.translated_srts:
            st.subheader("4. 번역된 .srt 파일 다운로드")
            st.write("각 언어별로 생성된 .srt 파일을 다운로드하여 YouTube 스튜디오에 '수동으로' 업로드하십시오.")
            
            cols = st.columns(5) 
            col_index = 0
            
            # [v6.2 수정] TARGET_LANGUAGES 순서대로 버튼 생성
            for lang_name, lang_info in TARGET_LANGUAGES.items():
                lang_code = lang_info['code']
                srt_data = st.session_state.translated_srts.get(lang_name)
                
                if srt_data: 
                    cols[col_index].download_button(
                        label=f"다운로드 ({lang_name})",
                        data=srt_data,
                        file_name=f"{uploaded_file.name.split('.')[0]}_{lang_code}.srt",
                        mime="text/plain",
                        key=f"srt_dl_{lang_name}"
                    )
                    col_index = (col_index + 1) % 5
