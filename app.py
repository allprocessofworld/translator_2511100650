import streamlit as st
import deepl
from googleapiclient.discovery import build
import pysrt
import io
import zipfile
import pandas as pd
import json
from collections import OrderedDict

# --- DeepL 지원 언어 목록 (v7.0) ---
TARGET_LANGUAGES = OrderedDict({
    # --- Standard Languages ---
    "no": {"name": "노르웨이어 (no)", "code": "NB", "is_beta": False},
    "da": {"name": "덴마크어 (da)", "code": "DA", "is_beta": False},
    "de": {"name": "독일어 (de)", "code": "DE", "is_beta": False},
    "ru": {"name": "러시아어 (ru)", "code": "RU", "is_beta": False},
    "es": {"name": "스페인어 (es)", "code": "ES", "is_beta": False},
    "ar": {"name": "아랍어 (ar)", "code": "AR", "is_beta": False},
    "uk": {"name": "우크라이나어 (uk)", "code": "UK", "is_beta": False},
    "it": {"name": "이탈리아어 (it)", "code": "IT", "is_beta": False},
    "id": {"name": "인도네시아어 (id)", "code": "ID", "is_beta": False},
    "ja": {"name": "일본어 (ja)", "code": "JA", "is_beta": False},
    "zh-CN": {"name": "중국어(간체) (zh-CN)", "code": "ZH", "is_beta": False},
    "zh-TW": {"name": "중국어(번체) (zh-TW)", "code": "zh-TW", "is_beta": False},
    "tr": {"name": "튀르키예어 (tr)", "code": "TR", "is_beta": False},
    "pt": {"name": "포르투갈어 (pt)", "code": "PT-PT", "is_beta": False},
    "fr": {"name": "프랑스어 (fr)", "code": "FR", "is_beta": False},
    "ko": {"name": "한국어 (ko)", "code": "KO", "is_beta": False},
    
    # --- Beta Languages (Pro Key & Flag Required) ---
    "mr": {"name": "마라티어 (mr)", "code": "MR", "is_beta": True},
    "ms": {"name": "말레이어 (ms)", "code": "MS", "is_beta": True},
    "vi": {"name": "베트남어 (vi)", "code": "VI", "is_beta": True},
    "bn": {"name": "벵골어 (bn)", "code": "BN", "is_beta": True},
    "ur": {"name": "우르두어 (ur)", "code": "UR", "is_beta": True},
    "ta": {"name": "타밀어 (ta)", "code": "TA", "is_beta": True},
    "th": {"name": "태국어 (th)", "code": "TH", "is_beta": True},
    "te": {"name": "텔루구어 (te)", "code": "TE", "is_beta": True},
    "hi": {"name": "힌디어 (hi)", "code": "HI", "is_beta": True},
})

# --- API 함수 ---

@st.cache_data(show_spinner=False)
def get_video_details(api_key, video_id):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(
            part="snippet",
            id=video_id
        )
        response = request.execute()
        if not response.get('items'):
            return None, "YouTube API 오류: 해당 ID의 영상을 찾을 수 없습니다."
        
        snippet = response['items'][0]['snippet']
        return snippet, None
    except Exception as e:
        return None, f"YouTube API 오류: {str(e)}"

@st.cache_data(show_spinner=False)
def translate_deepl(_translator, text, target_lang_code, is_beta=False):
    try:
        if is_beta:
            result = _translator.translate_text(
                text, target_lang=target_lang_code, enable_beta_languages=True
            )
        else:
            result = _translator.translate_text(
                text, target_lang=target_lang_code
            )
        return result.text, None
    except Exception as e:
        return None, f"DeepL 실패: {str(e)}"

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, text, target_lang_code_ui):
    try:
        result = _google_translator.translations().list(
            q=text,
            target=target_lang_code_ui,
            source='en'
        ).execute()
        
        if isinstance(text, list):
             return [item['translatedText'] for item in result['translations']], None
        else:
             return result['translations'][0]['translatedText'], None
            
    except Exception as e:
        return None, f"Google 실패: {str(e)}"

@st.cache_data(show_spinner=False)
def parse_srt(file_content):
    try:
        subs = pysrt.from_string(file_content)
        return subs, None
    except Exception as e:
        return None, f"SRT 파싱 오류: {str(e)}"

# --- Streamlit UI ---

st.set_page_config(layout="wide")
st.title("YouTube 자동 번역기 (v7.0 - Fallback & Table)")
st.write("DeepL API 실패 시 Google Translation API로 자동 대체 (Fallback)합니다.")

st.header("1. API 키 설정")
st.write("Streamlit Cloud의 'Secrets'에 API 키가 안전하게 저장되어 있어야 합니다.")

try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"] 
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
    st.success("✅ YouTube 및 DeepL API 키가 'Secrets'에서 성공적으로 로드되었습니다.")
    st.info("💡 **참고:** Google 번역 대체를 사용하려면, YouTube API 키를 발급한 GCP 프로젝트에서 **'Cloud Translation API'**를 **'사용 설정'**해야 합니다.")
except KeyError:
    st.error("❌ Streamlit Cloud의 'Secrets'에 YOUTUBE_API_KEY 또는 DEEPL_API_KEY가 설정되지 않았습니다.")
    st.info("앱 설정(Settings) > Secrets에 다음 2줄을 추가하세요:\n\nYOUTUBE_API_KEY = \"AIza...\"\nDEEPL_API_KEY = \"your_key...\"")
    st.stop()

st.header("Task 1: 영상 제목 및 설명 번역")
video_id_input = st.text_input("YouTube 영상 ID 입력 (예: dQw4w9WgXcQ)")

if 'video_details' not in st.session_state:
    st.session_state.video_details = None
if 'translation_results' not in st.session_state:
    st.session_state.translation_results = []

if st.button("1. 영상 정보 가져오기"):
    if video_id_input:
        with st.spinner("YouTube API에서 영상 정보를 가져오는 중..."):
            snippet, error = get_video_details(YOUTUBE_API_KEY, video_id_input)
            if error:
                st.error(error)
                st.session_state.video_details = None
            else:
                st.session_state.video_details = snippet
                st.session_state.translation_results = []
                st.success(f"영상 정보 로드 성공: \"{snippet['title']}\"")
    else:
        st.warning("영상 ID를 입력하세요.")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목 (영어)", snippet['title'], height=50, disabled=True)
    st.text_area("원본 설명 (영어)", snippet['description'], height=150, disabled=True)

    if st.button("2. 전체 언어 번역 실행 (Task 1)"):
        st.session_state.translation_results = []
        progress_bar = st.progress(0, text="전체 번역 진행 중...")
        total_langs = len(TARGET_LANGUAGES)
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            deepl_code = lang_data["code"]
            is_beta = lang_data["is_beta"]
            google_code = ui_key
            
            progress_bar.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
            
            result_data = {
                "lang_name": lang_name,
                "ui_key": ui_key,
                "api": None,
                "status": "실패",
                "title": "",
                "desc": ""
            }

            title_text, title_err = translate_deepl(translator_deepl, snippet['title'], deepl_code, is_beta)
            desc_text, desc_err = translate_deepl(translator_deepl, snippet['description'], deepl_code, is_beta)

            if title_err or desc_err:
                st.warning(f"DeepL 실패 ({lang_name}). Google 번역으로 대체합니다. (오류: {title_err or desc_err})")
                title_text_g, title_err_g = translate_google(translator_google, snippet['title'], google_code)
                desc_text_g, desc_err_g = translate_google(translator_google, snippet['description'], google_code)

                if title_err_g or desc_err_g:
                    result_data["api"] = "Google"
                    result_data["status"] = "실패"
                    result_data["title"] = f"Google 번역 오류: {title_err_g}"
                    result_data["desc"] = f"Google 번역 오류: {desc_err_g}"
                else:
                    result_data["api"] = "Google"
                    result_data["status"] = "성공"
                    result_data["title"] = title_text_g
                    result_data["desc"] = desc_text_g
            else:
                result_data["api"] = "DeepL"
                result_data["status"] = "성공"
                result_data["title"] = title_text
                result_data["desc"] = desc_text

            st.session_state.translation_results.append(result_data)

        st.success("모든 언어 번역/대체 작업 완료!")
        progress_bar.empty()

    if st.session_state.translation_results:
        st.subheader("3. 번역 결과 요약표 (한눈에 보기)")
        df_data = []
        for res in st.session_state.translation_results:
            df_data.append({
                "언어": res["lang_name"],
                "엔진": res["api"],
                "상태": res["status"],
                "번역된 제목": res["title"]
            })
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True)

        st.subheader("4. 번역 결과 검수 및 다운로드 (Task 1)")
        json_output = {}
        cols = st.columns(5)
        col_index = 0
        
        for result_data in st.session_state.translation_results:
            ui_key = result_data["ui_key"]
            lang_name = result_data["lang_name"]
            api_used = result_data["api"]
            status = result_data["status"]
            
            with cols[col_index]:
                with st.expander(f"**{lang_name}** (검수)", expanded=False):
                    if status == "성공":
                        st.caption(f"번역 엔진: {api_used}")
                    else:
                        st.caption(f"번역 엔진: {api_used} (실패)")
                    original_title = result_data["title"]
                    original_desc = result_data["desc"]
                    corrected_title = st.text_area(f"제목 ({ui_key})", original_title, height=50)
                    corrected_desc = st.text_area(f"설명 ({ui_key})", original_desc, height=150)
                    json_output[ui_key] = {
                        "title": corrected_title,
                        "description": corrected_desc
                    }
            col_index = (col_index + 1) % 5
        
        st.download_button(
            label="✅ 검수 완료된 제목/설명 다운로드 (JSON)",
            data=json.dumps(json_output, indent=2, ensure_ascii=False),
            file_name=f"{video_id_input}_translations.json",
            mime="application/json"
        )

st.header("Task 2: '영어' 자막 파일 번역 (.srt)")
uploaded_file = st.file_uploader("번역할 원본 '영어' .srt 파일을 업로드하세요.", type=['srt'])

if uploaded_file:
    try:
        srt_content = uploaded_file.getvalue().decode("utf-8")
        subs, parse_err = parse_srt(srt_content)
        
        if parse_err:
            st.error(parse_err)
        else:
            st.success(f"✅ .srt 파일 로드 성공! (총 {len(subs)}개의 자막 감지)")
            
            if st.button("3. .srt 파일 번역 실행 (Task 2)"):
                st.session_state.srt_translations = {}
                st.session_state.srt_errors = []
                srt_progress = st.progress(0, text="SRT 번역 진행 중...")
                total_langs = len(TARGET_LANGUAGES)
                texts_to_translate = [sub.text for sub in subs]
                
                for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
                    lang_name = lang_data["name"]
                    deepl_code = lang_data["code"]
                    is_beta = lang_data["is_beta"]
                    google_code = ui_key
                    
                    srt_progress.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
                    
                    try:
                        translated_texts = None
                        translate_err = "Init Fail"
                        translated_texts, translate_err = translate_deepl(translator_deepl, texts_to_translate, deepl_code, is_beta)
                        
                        if translate_err:
                            st.warning(f"SRT DeepL 실패 ({lang_name}). Google로 대체합니다.")
                            translated_texts, translate_err = translate_google(translator_google, texts_to_translate, google_code)
                            if translate_err:
                                raise Exception(f"Google마저 실패: {translate_err}")

                        translated_subs = subs[:]
                        if isinstance(translated_texts, list):
                            for j, sub in enumerate(translated_subs):
                                sub.text = translated_texts[j]
                        else:
                            translated_subs[0].text = translated_texts
                        st.session_state.srt_translations[ui_key] = translated_subs.to_string(encoding='utf-8')
                        
                    except Exception as e:
                        st.session_state.srt_errors.append(f"SRT 생성 실패 ({lang_name}): {str(e)}")
                
                st.success("SRT 파일 번역 완료!")
                srt_progress.empty()
                if st.session_state.srt_errors:
                    st.error("일부 SRT 번역 실패:")
                    for err in st.session_state.srt_errors:
                        st.warning(err)

            if 'srt_translations' in st.session_state and st.session_state.srt_translations:
                st.subheader("4. 번역된 .srt 파일 다운로드 (Task 2)")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.srt_translations.items():
                        lang_code = TARGET_LANGUAGES[ui_key]["code"]
                        file_name = f"subtitles_{ui_key}.srt"
                        zip_file.writestr(file_name, content)
                
                st.download_button(
                    label="✅ 번역된 .srt 파일 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="all_subtitles.zip",
                    mime="application/zip"
                )
                st.markdown("---")
                cols = st.columns(5)
                col_index = 0
                for ui_key, lang_data in TARGET_LANGUAGES.items():
                    if ui_key in st.session_state.srt_translations:
                        lang_name = lang_data["name"]
                        with cols[col_index]:
                            st.download_button(
                                label=f"{lang_name} (.srt)",
                                data=st.session_state.srt_translations[ui_key],
                                file_name=f"subtitles_{ui_key}.srt",
                                mime="text/plain"
                            )
                        col_index = (col_index + 1) % 5

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .srt 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")
