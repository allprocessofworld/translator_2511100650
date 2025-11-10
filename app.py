import streamlit as st
import deepl
from googleapiclient.discovery import build
import pysrt
import io
import zipfile
from collections import OrderedDict

# --- DeepL 지원 언어 목록 (v6.8) ---
# v6.8: 'enable_beta_languages' (가짜 파라미터) 관련 로직 전부 삭제
# v6.8: DeepL 공식 API 문서를 기반으로 모든 언어 코드를 수정
# 'no' -> 'NB', 'pt' -> 'PT-PT', 'zh-CN' -> 'ZH'
# 'zh-TW' (번체)는 DeepL API가 'target_lang'으로 지원하지 않아 목록에서 제거

TARGET_LANGUAGES = OrderedDict({
    # --- Standard Languages (v6.8 수정) ---
    "no": {"name": "노르웨이어 (no)", "code": "NB"},
    "da": {"name": "덴마크어 (da)", "code": "DA"},
    "de": {"name": "독일어 (de)", "code": "DE"},
    "ru": {"name": "러시아어 (ru)", "code": "RU"},
    "es": {"name": "스페인어 (es)", "code": "ES"},
    "ar": {"name": "아랍어 (ar)", "code": "AR"},
    "uk": {"name": "우크라이나어 (uk)", "code": "UK"},
    "it": {"name": "이탈리아어 (it)", "code": "IT"},
    "id": {"name": "인도네시아어 (id)", "code": "ID"},
    "ja": {"name": "일본어 (ja)", "code": "JA"},
    "zh-CN": {"name": "중국어(간체) (zh-CN)", "code": "ZH"},
    # "zh-TW": {"name": "중국어(번체) (zh-TW)", "code": "zh-TW"}, # DeepL API 미지원
    "tr": {"name": "튀르키예어 (tr)", "code": "TR"},
    "pt": {"name": "포르투갈어 (pt)", "code": "PT-PT"}, # PT는 폐기됨
    "fr": {"name": "프랑스어 (fr)", "code": "FR"},
    "ko": {"name": "한국어 (ko)", "code": "KO"},
    
    # --- Beta Languages (Pro Key Required) ---
    "mr": {"name": "마라티어 (mr)", "code": "MR"},
    "ms": {"name": "말레이어 (ms)", "code": "MS"},
    "vi": {"name": "베트남어 (vi)", "code": "VI"},
    "bn": {"name": "벵골어 (bn)", "code": "BN"},
    "ur": {"name": "우르두어 (ur)", "code": "UR"},
    "ta": {"name": "타밀어 (ta)", "code": "TA"},
    "th": {"name": "태국어 (th)", "code": "TH"},
    "te": {"name": "텔루구어 (te)", "code": "TE"},
    "hi": {"name": "힌디어 (hi)", "code": "HI"},
})

# --- API 함수 ---

@st.cache_data(show_spinner=False)
def get_video_details(api_key, video_id):
    """YouTube Data API를 호출하여 영상 제목과 설명을 가져옵니다."""
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
def translate_text(_translator, text, target_lang_code):
    """DeepL API를 호출하여 텍스트를 번역합니다."""
    # v6.8: 'enable_beta_languages' (가짜 파라미터) 완전 삭제
    try:
        result = _translator.translate_text(
            text,
            target_lang=target_lang_code
        )
        return result.text, None
    except Exception as e:
        return None, f"DeepL 번역 오류 ({target_lang_code}): {str(e)}"

@st.cache_data(show_spinner=False)
def parse_srt(file_content):
    """SRT 파일 내용을 파싱합니다."""
    try:
        subs = pysrt.from_string(file_content)
        return subs, None
    except Exception as e:
        return None, f"SRT 파싱 오류: {str(e)}"

# --- Streamlit UI ---

st.set_page_config(layout="wide")
st.title("YouTube 자동 번역기 (v6.8 - 최종 수정)")
st.write("`v6.5` `requirements.txt`와 함께 작동하는 최종 수정 버전입니다.")

# --- 1. API 키 입력 (Secrets) ---
st.header("1. API 키 설정")
st.write("Streamlit Cloud의 'Secrets'에 API 키가 안전하게 저장되어 있어야 합니다.")

try:
    # Streamlit Secrets에서 API 키 로드
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    
    # DeepL Translator 객체 초기화
    translator = deepl.Translator(DEEPL_API_KEY)
    
    st.success("✅ YouTube 및 DeepL API 키가 'Secrets'에서 성공적으로 로드되었습니다.")
except KeyError:
    st.error("❌ Streamlit Cloud의 'Secrets'에 YOUTUBE_API_KEY 또는 DEEPL_API_KEY가 설정되지 않았습니다.")
    st.info("앱 설정(Settings) > Secrets에 다음 2줄을 추가하세요:\n\nYOUTUBE_API_KEY = \"AIza...\"\nDEEPL_API_KEY = \"your_key...\"")
    st.stop() # API 키 없으면 앱 중단

# --- 2. Task 1: 제목 및 설명 번역 ---
st.header("Task 1: 영상 제목 및 설명 번역")

video_id_input = st.text_input("YouTube 영상 ID 입력 (예: dQw4w9WgXcQ)")

if 'video_details' not in st.session_state:
    st.session_state.video_details = None

if st.button("1. 영상 정보 가져오기"):
    if video_id_input:
        with st.spinner("YouTube API에서 영상 정보를 가져오는 중..."):
            snippet, error = get_video_details(YOUTUBE_API_KEY, video_id_input)
            if error:
                st.error(error)
                st.session_state.video_details = None
            else:
                st.session_state.video_details = snippet
                st.success(f"영상 정보 로드 성공: \"{snippet['title']}\"")
    else:
        st.warning("영상 ID를 입력하세요.")

# 영상 정보가 로드되었는지 확인
if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목 (영어)", snippet['title'], height=50, disabled=True)
    st.text_area("원본 설명 (영어)", snippet['description'], height=150, disabled=True)

    if st.button("2. 전체 언어 번역 실행 (Task 1)"):
        # 세션 상태 초기화
        st.session_state.title_translations = {}
        st.session_state.desc_translations = {}
        st.session_state.title_errors = []
        st.session_state.desc_errors = []
        
        title_progress = st.progress(0, text="제목 번역 진행 중...")
        desc_progress = st.progress(0, text="설명 번역 진행 중...")

        total_langs = len(TARGET_LANGUAGES)
        
        for i, (key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_code = lang_data["code"]
            lang_name = lang_data["name"]
            
            # --- 제목 번역 ---
            title_text, title_err = translate_text(translator, snippet['title'], lang_code)
            if title_err:
                st.session_state.title_errors.append(title_err)
            else:
                st.session_state.title_translations[key] = title_text # UI 키(예: 'zh-CN')로 저장
            
            title_progress.progress((i + 1) / total_langs, text=f"제목 번역: {lang_name}")
            
            # --- 설명 번역 ---
            desc_text, desc_err = translate_text(translator, snippet['description'], lang_code)
            if desc_err:
                st.session_state.desc_errors.append(desc_err)
            else:
                st.session_state.desc_translations[key] = desc_text # UI 키(예: 'zh-CN')로 저장
            
            desc_progress.progress((i + 1) / total_langs, text=f"설명 번역: {lang_name}")

        st.success("모든 언어 번역 완료!")
        title_progress.empty()
        desc_progress.empty()

        # 오류가 있다면 표시
        if st.session_state.title_errors or st.session_state.desc_errors:
            st.error("일부 언어 번역 실패:")
            for err in st.session_state.title_errors + st.session_state.desc_errors:
                st.warning(err)

    # 번역 결과가 세션에 있는지 확인 후 UI 생성
    if 'title_translations' in st.session_state and st.session_state.title_translations:
        st.subheader("3. 번역 결과 검수 및 다운로드 (Task 1)")
        
        json_output = {}
        cols = st.columns(5)
        col_index = 0
        
        for key, lang_data in TARGET_LANGUAGES.items():
            if key in st.session_state.title_translations and key in st.session_state.desc_translations:
                lang_code = lang_data["code"]
                lang_name = lang_data["name"]
                
                # 검수용 UI 생성
                with cols[col_index]:
                    with st.expander(f"**{lang_name}** (검수)", expanded=False):
                        st.write(f"API 코드: `{lang_code}`")
                        
                        # 원본 텍스트 (DeepL 번역 결과)
                        original_title = st.session_state.title_translations[key]
                        original_desc = st.session_state.desc_translations[key]

                        # 검수(수정) 가능한 텍스트 영역
                        corrected_title = st.text_area(f"제목 ({key})", original_title, height=50)
                        corrected_desc = st.text_area(f"설명 ({key})", original_desc, height=150)
                        
                        # 최종 JSON 객체에 검수된 내용 저장
                        json_output[key] = { # UI 키(예: 'zh-CN')로 저장
                            "title": corrected_title,
                            "description": corrected_desc
                        }
                
                col_index = (col_index + 1) % 5
        
        # 다운로드 버튼
        st.download_button(
            label="✅ 검수 완료된 제목/설명 다운로드 (JSON)",
            data=str(json_output),
            file_name=f"{video_id_input}_translations.json",
            mime="application/json"
        )

# --- 3. Task 2: 자막 파일 번역 (.srt) ---
st.header("Task 2: '영어' 자막 파일 번역 (.srt)")

uploaded_file = st.file_uploader("번역할 원본 '영어' .srt 파일을 업로드하세요.", type=['srt'])

if uploaded_file:
    try:
        # 파일 내용 읽기 (bytes -> string)
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
                
                # SRT 파일은 텍스트가 많으므로, 한 언어씩 순차적으로 처리
                for i, (key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
                    lang_code = lang_data["code"]
                    lang_name = lang_data["name"]
                    
                    srt_progress.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
                    
                    try:
                        # 원본 자막 객체 복사 (중요)
                        translated_subs = subs[:]
                        
                        # DeepL은 텍스트 '배열'을 받아 한 번에 번역할 수 있습니다.
                        texts_to_translate = [sub.text for sub in translated_subs]
                        
                        # v6.8 수정: 가짜 'is_beta' 플래그 삭제
                        translated_texts, translate_err = translate_text(translator, texts_to_translate, lang_code)
                        
                        if translate_err:
                            raise Exception(translate_err)
                        
                        # 번역된 텍스트로 자막 객체 업데이트
                        if isinstance(translated_texts, list):
                            for j, sub in enumerate(translated_subs):
                                sub.text = translated_texts[j]
                        else: # 단일 텍스트로 반환된 경우 (드물지만)
                            translated_subs[0].text = translated_texts

                        # 세션에 저장 (파일 내용 자체)
                        st.session_state.srt_translations[key] = translated_subs.to_string(encoding='utf-8')
                        
                    except Exception as e:
                        st.session_state.srt_errors.append(f"SRT 생성 실패 ({lang_name}): {str(e)}")
                
                st.success("SRT 파일 번역 완료!")
                srt_progress.empty()

                if st.session_state.srt_errors:
                    st.error("일부 SRT 번역 실패:")
                    for err in st.session_state.srt_errors:
                        st.warning(err)

            # SRT 번역 결과가 세션에 있으면 다운로드 UI 생성
            if 'srt_translations' in st.session_state and st.session_state.srt_translations:
                st.subheader("4. 번역된 .srt 파일 다운로드 (Task 2)")
                
                # ZIP 파일 일괄 다운로드
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for key, content in st.session_state.srt_translations.items():
                        lang_code = TARGET_LANGUAGES[key]["code"]
                        file_name = f"subtitles_{lang_code}.srt"
                        zip_file.writestr(file_name, content)
                
                st.download_button(
                    label="✅ 번역된 .srt 파일 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="all_subtitles.zip",
                    mime="application/zip"
                )
                
                st.markdown("---")
                
                # 개별 다운로드
                cols = st.columns(5)
                col_index = 0
                
                for key, lang_data in TARGET_LANGUAGES.items():
                    if key in st.session_state.srt_translations:
                        lang_name = lang_data["name"]
                        lang_code = lang_data["code"]
                        with cols[col_index]:
                            st.download_button(
                                label=f"{lang_name} (.srt)",
                                data=st.session_state.srt_translations[key],
                                file_name=f"subtitles_{lang_code}.srt",
                                mime="text/plain"
                            )
                        col_index = (col_index + 1) % 5

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .srt 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")

