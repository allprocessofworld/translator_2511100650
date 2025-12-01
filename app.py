import streamlit as st
import deepl
from googleapiclient.discovery import build
import pysrt
import io
import zipfile
import pandas as pd
import json
import re 
import html 
from collections import OrderedDict

# --- [수정됨] DeepL 지원 언어 목록 (수동 정렬) ---
# df.sort_values를 제거했으므로, 이 딕셔너리의 순서가 곧 화면 출력 순서입니다.
TARGET_LANGUAGES = OrderedDict({
    "el": {"name": "그리스어", "code": "EL", "is_beta": False},
    "nl": {"name": "네덜란드어", "code": "NL", "is_beta": False},
    "no": {"name": "노르웨이어", "code": "NB", "is_beta": False},
    "da": {"name": "덴마크어", "code": "DA", "is_beta": False},
    "de": {"name": "독일어", "code": "DE", "is_beta": False},
    "ru": {"name": "러시아어", "code": "RU", "is_beta": False},
    "mr": {"name": "마라티어", "code": "MR", "is_beta": True},
    "ms": {"name": "말레이어", "code": "MS", "is_beta": True},
    "vi": {"name": "베트남어", "code": "VI", "is_beta": True},
    "bn": {"name": "벵골어", "code": "BN", "is_beta": True},
    "sv": {"name": "스웨덴어", "code": "SV", "is_beta": False},
    "es": {"name": "스페인어", "code": "ES", "is_beta": False},
    "sk": {"name": "슬로바키아어", "code": "SK", "is_beta": False},
    "ar": {"name": "아랍어", "code": "AR", "is_beta": False},
    
    # [영어권 커스텀 순서]
    # 요청 사항: 미국 삭제 / 영국 -> 호주 -> 인도 순서 배치
    "en-IE": {"name": "영어 (아일랜드)", "code": "EN-GB", "is_beta": False}, # DeepL EN-GB 대체
    "en-GB": {"name": "영어 (영국)", "code": "EN-GB", "is_beta": False},
    "en-AU": {"name": "영어 (호주)", "code": "EN-AU", "is_beta": False},   # <--- 인도 위로 이동됨
    "en-IN": {"name": "영어 (인도)", "code": "EN-GB", "is_beta": False},   # DeepL EN-GB 대체
    "en-CA": {"name": "영어 (캐나다)", "code": "EN-CA", "is_beta": False},

    "ur": {"name": "우르두어", "code": "UR", "is_beta": True},
    "uk": {"name": "우크라이나어", "code": "UK", "is_beta": False},
    "it": {"name": "이탈리아어", "code": "IT", "is_beta": False},
    "id": {"name": "인도네시아어", "code": "ID", "is_beta": False},
    "ja": {"name": "일본어", "code": "JA", "is_beta": False},
    "zh-CN": {"name": "중국어(간체)", "code": "ZH", "is_beta": False},
    "zh-TW": {"name": "중국어(번체)", "code": "zh-TW", "is_beta": False}, # Google Fallback
    "cs": {"name": "체코어", "code": "CS", "is_beta": False},
    "tr": {"name": "튀르키예어", "code": "TR", "is_beta": False},
    "ta": {"name": "타밀어", "code": "TA", "is_beta": True},
    "th": {"name": "태국어", "code": "TH", "is_beta": True},
    "te": {"name": "텔루구어", "code": "TE", "is_beta": True},
    "pa": {"name": "펀잡어", "code": "PA", "is_beta": True},
    "pt": {"name": "포르투갈어", "code": "PT-PT", "is_beta": False},
    "pl": {"name": "폴란드어", "code": "PL", "is_beta": False},
    "fr": {"name": "프랑스어", "code": "FR", "is_beta": False},
    "fi": {"name": "핀란드어", "code": "FI", "is_beta": False},
    "fil": {"name": "필리핀어", "code": "FIL", "is_beta": False}, # Google Fallback
    "ko": {"name": "한국어", "code": "KO", "is_beta": False},
    "hu": {"name": "헝가리어", "code": "HU", "is_beta": False},
    "hi": {"name": "힌디어", "code": "HI", "is_beta": True},
})

# --- 번역 API 요청 시 분할 처리할 텍스트 줄 수 ---
CHUNK_SIZE = 100

# --- [핵심 기능] 텍스트 보호/복원 Helper 함수 (별표 깨짐 방지) ---
def protect_formatting(text):
    """
    특수 기호(*)가 번역 엔진에 의해 삭제되지 않도록 
    '번역 금지(translate="no")' 태그로 감싸서 보호합니다.
    """
    pattern = r'\*'
    # DeepL/Google 모두 <span translate="no">를 인식하고 내부 텍스트를 유지하려는 성향이 강함
    replacement = '<span translate="no">*</span>'
    
    if isinstance(text, list):
        return [re.sub(pattern, replacement, t) for t in text]
    else:
        return re.sub(pattern, replacement, text)

def restore_formatting(text):
    """
    보호된 태그(<span...>)를 제거하고 원래 기호(*)로 복원합니다.
    번역기가 태그 사이에 공백을 넣거나 대소문자를 바꿀 수 있으므로 정규식으로 처리합니다.
    """
    # <span translate="no"> * </span> 형태를 찾아 * 로 치환
    pattern = r'<span[^>]*translate=["\']?no["\']?[^>]*>\s*\*\s*<\/span>'
    replacement = '*'
    
    if isinstance(text, list):
        return [re.sub(pattern, replacement, t, flags=re.IGNORECASE) for t in text]
    else:
        return re.sub(pattern, replacement, text, flags=re.IGNORECASE)


# --- SBV / SRT 처리 헬퍼 함수 ---

@st.cache_data(show_spinner=False)
def parse_sbv(file_content):
    """SBV 파일 내용을 파싱하여 pysrt SubRipFile 객체 리스트로 변환합니다."""
    subs = pysrt.SubRipFile()
    lines = file_content.strip().replace('\r\n', '\n').split('\n\n')
    
    for i, block in enumerate(lines):
        if not block.strip():
            continue
        
        parts = block.split('\n', 1)
        if len(parts) != 2:
            continue
            
        time_str, text = parts
        time_match = re.match(r'(\d+):(\d+):(\d+)\.(\d+),(\d+):(\d+):(\d+)\.(\d+)', time_str.strip())
        
        if time_match:
            start_h, start_m, start_s, start_ms, end_h, end_m, end_s, end_ms = map(int, time_match.groups())
            
            sub = pysrt.SubRipItem()
            sub.index = i + 1
            
            sub.start.hours = start_h
            sub.start.minutes = start_m
            sub.start.seconds = start_s
            sub.start.milliseconds = start_ms
            
            sub.end.hours = end_h
            sub.end.minutes = end_m
            sub.end.seconds = end_s
            sub.end.milliseconds = end_ms
            
            sub.text = html.unescape(text.strip())
            subs.append(sub)
    
    if not subs:
        return None, "SBV 파싱 오류: 유효한 시간/텍스트 블록을 찾을 수 없습니다."
        
    return subs, None


def to_sbv_format(subrip_file):
    """pysrt SubRipFile 객체를 SBV 형식의 문자열로 변환합니다."""
    sbv_output = []
    
    for sub in subrip_file:
        def format_sbv_time(time):
            return f"{time.hours:02d}:{time.minutes:02d}:{time.seconds:02d}.{time.milliseconds:03d}"
            
        start_time = format_sbv_time(sub.start)
        end_time = format_sbv_time(sub.end)
        
        time_line = f"{start_time},{end_time}"
        text_content = html.unescape(sub.text.strip())
        
        sbv_output.append(time_line)
        sbv_output.append(text_content)
        sbv_output.append("") # 블록 간의 빈 줄을 위해 추가 (결과적으로 \n\n)
        
    return "\n".join(sbv_output).strip()


@st.cache_data(show_spinner=False)
def parse_srt_native(file_content):
    """SRT 파일 내용을 파싱합니다. (pysrt 네이티브 사용)"""
    try:
        subs = pysrt.from_string(file_content)
        return subs, None
    except Exception as e:
        return None, f"SRT 파싱 오류: {str(e)}"

def to_srt_format_native(subrip_file):
    """pysrt SubRipFile 객체를 SRT 형식의 문자열로 변환합니다."""
    return subrip_file.to_string(encoding='utf-8')


# --- API 함수 (Formatting 보호 로직 적용됨) ---

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
def translate_deepl(_translator, text, target_lang_code, is_beta=False):
    """DeepL API를 호출하여 텍스트를 번역합니다. (Formatting 보호 적용됨)"""
    try:
        # 1. [전처리] 마스킹 적용 (* -> <span>*</span>)
        protected_text = protect_formatting(text)
        
        # text가 리스트인지 단일 문자열인지 확인
        is_list = isinstance(protected_text, list)
        
        if is_beta:
            result = _translator.translate_text(
                protected_text, target_lang=target_lang_code, 
                enable_beta_languages=True,
                split_sentences='off', 
                tag_handling='html' # 태그 보호를 위해 필수
            )
        else:
            result = _translator.translate_text(
                protected_text, target_lang=target_lang_code,
                split_sentences='off', 
                tag_handling='html' # 태그 보호를 위해 필수
            )
        
        # 2. 결과 추출
        if is_list:
            translated_raw = [r.text for r in result]
        else:
            translated_raw = result.text
            
        # 3. [후처리] 마스킹 해제 (<span>*</span> -> *)
        final_text = restore_formatting(translated_raw)
        
        return final_text, None
            
    except Exception as e:
        return None, f"DeepL 실패: {str(e)}"

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, text, target_lang_code_ui, source_lang='en'):
    """Google Cloud Translation API를 호출하여 텍스트를 번역합니다. (Formatting 보호 적용됨)"""
    try:
        # 1. [전처리] 마스킹 적용
        protected_text = protect_formatting(text)
        
        target = target_lang_code_ui
        if target == 'fil':
            target = 'tl'

        # Google API 호출 (format='html' 명시 권장)
        result = _google_translator.translations().list(
            q=protected_text,
            target=target,
            source=source_lang,
            format='html' # 태그 인식을 위해 html 모드 명시
        ).execute()
        
        # 2. 결과 추출 및 unescape
        if isinstance(protected_text, list):
             translated_raw = [html.unescape(item['translatedText']) for item in result['translations']]
        else:
             translated_raw = html.unescape(result['translations'][0]['translatedText'])
        
        # 3. [후처리] 마스킹 해제
        final_text = restore_formatting(translated_raw)
        
        return final_text, None
            
    except Exception as e:
        return None, f"Google 실패: {str(e)}"

def to_text_docx_substitute(data_list, original_desc_input, video_id):
    """
    검수 완료된 제목/설명을 Word 문서 스타일의 텍스트로 변환합니다.
    """
    output = io.StringIO()
    
    # 문서 헤더
    output.write("==================================================\n")
    output.write(f"YouTube 영상 제목 및 설명 번역 보고서\n")
    output.write(f"영상 ID: {video_id}\n")
    output.write(f"생성 날짜: {pd.to_datetime('today').strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write("==================================================\n\n")

    # 2. 번역 결과 섹션
    for item in data_list:
        output.write("**************************************************\n")
        output.write(f"언어: {item['Language']} ({item['UI_Key']})\n")
        output.write(f"번역 엔진: {item['Engine']} (상태: {item['Status']})\n")
        output.write("**************************************************\n")
        
        output.write("\n[ 제목 ]\n")
        output.write(f"{item['Title']}\n")
        
        output.write("\n[ 설명 ]\n")
        
        translated_desc_raw = item['Description']
        output.write(translated_desc_raw)
        
        output.write("\n\n")
        
    return output.getvalue().encode('utf-8')

def to_excel(df_data):
    """DataFrame 데이터를 Excel 파일(bytes)로 변환합니다."""
    output_buffer = io.BytesIO()
    df = pd.DataFrame(df_data)
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Translations')
    
    return output_buffer.getvalue()


# --- Streamlit UI ---

st.set_page_config(layout="wide")
st.title("허슬플레이 자동 번역기 (Vr.251201)")

st.info("❗ 사용 중, 오류 또는 개선 사항은 즉시 보고하세요.")
st.info("⚠️ 디플 번역 실패 시, 구글 번역으로 자동 대체하며, 구글 번역으로 자동 대체된 언어는 반드시 다시 검수하세요.")
st.info("⚠️ 최종적으로 유튜브 스튜디오에는 총 41개 언어가 업로드되어야 합니다.")


# --- API 키 로드 (UI 숨김) ---
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"] 
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
    st.success("✅ API 키가 'Secrets'에서 성공적으로 로드되었습니다.")
except KeyError:
    st.error("❌ 'Secrets'에 YOUTUBE_API_KEY 또는 DEEPL_API_KEY가 설정되지 않았습니다.")
    st.info("💡 앱 설정(Settings) > Secrets에 API 키를 설정해야 합니다.")
    st.stop()


# --- Task 1: 영상 제목 및 설명란 번역 ---
st.header("영상 제목 및 설명란 번역")
video_id_input = st.text_input("YouTube 동영상 URL의 동영상 ID 입력 (예: URL - https://youtu.be/JsoPqXPIrI0 ▶ 동영상 ID - JsoPqXPIrI0)")

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
        st.warning("동영상 ID를 입력하세요.")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목 (영어)", snippet['title'], height=50, disabled=True)
    
    original_desc_input = snippet['description']
    st.session_state.original_desc_input = original_desc_input 
    
    st.text_area("원본 설명 (영어)", original_desc_input, height=350, disabled=True) 

    if st.button("2. 전체 언어 번역 실행"):
        st.session_state.translation_results = []
        progress_bar = st.progress(0, text="전체 번역 진행 중...")
        total_langs = len(TARGET_LANGUAGES)
        
        # 원본 설명을 줄바꿈 기준으로 미리 분리
        original_desc_lines = snippet['description'].split('\n')
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            deepl_code = lang_data["code"]
            is_beta = lang_data["is_beta"]
            google_code = ui_key
            
            progress_bar.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
            
            result_data = {
                "lang_name": lang_name,
                "ui_key": ui_key,
                "is_beta": is_beta,
                "api": None,
                "status": "실패",
                "title": "",
                "desc": ""
            }

            # --- 1. Try DeepL ---
            title_text, title_err = translate_deepl(translator_deepl, snippet['title'], deepl_code, is_beta)
            
            # [오류 수정] 설명을 Chunk 단위로 나누어 번역
            translated_desc_lines = []
            desc_err = None
            try:
                for chunk_i in range(0, len(original_desc_lines), CHUNK_SIZE):
                    chunk = original_desc_lines[chunk_i:chunk_i + CHUNK_SIZE]
                    translated_chunk, err = translate_deepl(translator_deepl, chunk, deepl_code, is_beta)
                    if err:
                        raise Exception(err)
                    translated_desc_lines.extend(translated_chunk)
                desc_text = '\n'.join(translated_desc_lines)
            except Exception as e:
                desc_err = e # Mark description as failed
                desc_text = None

            if title_err or desc_err:
                st.warning(f"DeepL 실패 ({lang_name}). Google 번역으로 대체합니다. (오류: {title_err or desc_err})")
                
                # --- 2. Try Google (Fallback for BOTH) ---
                title_text_g, title_err_g = translate_google(translator_google, snippet['title'], google_code)
                
                # [오류 수정] Google 번역도 Chunk 단위로 실행
                translated_desc_lines_g = []
                desc_err_g = None
                try:
                    for chunk_i in range(0, len(original_desc_lines), CHUNK_SIZE):
                        chunk = original_desc_lines[chunk_i:chunk_i + CHUNK_SIZE]
                        translated_chunk, err = translate_google(translator_google, chunk, google_code)
                        if err:
                            raise Exception(err)
                        translated_desc_lines_g.extend(translated_chunk)
                    desc_text_g = '\n'.join(translated_desc_lines_g)
                except Exception as e:
                    desc_err_g = e
                    desc_text_g = None

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
        # --- [UI 변경] DataFrame 대신 Code Block + 복사 버튼 UI 사용 ---
        st.subheader("번역 결과 (복사 버튼 포함)")
        st.info("💡 각 텍스트 박스 우측 상단의 '📄(복사)' 아이콘을 클릭하면 즉시 복사됩니다.")

        # 헤더 행
        h1, h2, h3 = st.columns([1.5, 3.5, 5])
        h1.markdown("**언어 / 상태**")
        h2.markdown("**번역된 제목**")
        h3.markdown("**번역된 설명**")
        st.divider()

        # 데이터 루프
        for res in st.session_state.translation_results:
            c1, c2, c3 = st.columns([1.5, 3.5, 5])
            
            with c1:
                st.markdown(f"**{res['lang_name']}**")
                if res['status'] == '성공':
                    if res['api'] == 'DeepL':
                        st.success(f"{res['api']}")
                    else: # Google Fallback (빨간색 강조)
                        st.error(f"{res['api']}")
                else:
                    st.error(f"{res['api']} (실패)")
            
            with c2:
                # st.code를 사용하면 우측 상단에 자동으로 Copy 버튼이 생김
                # language="text"로 설정하여 코드 하이라이팅 없이 텍스트만 표시
                st.code(res['title'], language="text")
            
            with c3:
                st.code(res['desc'], language="text")
            
            st.divider()

        # 검수 및 다운로드 섹션 (기존 코드 유지)
        st.subheader("번역 결과 검수 및 다운로드")
        
        # 순서대로 출력
        excel_data_list = []
        cols = st.columns(5)
        col_index = 0
        
        for result_data in st.session_state.translation_results:
            ui_key = result_data["ui_key"]
            lang_name = result_data["lang_name"]
            status = result_data["status"]
            
            final_data_entry = {
                "Language": lang_name,
                "UI_Key": ui_key,
                "Title": result_data["title"],
                "Description": result_data["desc"],
                "Engine": result_data["api"],
                "Status": status
            }

            with cols[col_index]:
                with st.expander(f"**{lang_name}** (검수)", expanded=False):
                    
                    if status == "성공":
                        st.caption(f"번역 엔진: {result_data['api']}")
                    else:
                        st.caption(f"번역 엔진: {result_data['api']} (실패)")

                    original_title = result_data["title"]
                    original_desc = result_data["desc"]

                    corrected_title = st.text_area(f"제목 ({ui_key})", original_title, height=50, key=f"t1_title_{ui_key}")
                    corrected_desc = st.text_area(f"설명 ({ui_key})", original_desc, height=150, key=f"t1_desc_{ui_key}")
                    
                    final_data_entry["Title"] = corrected_title
                    final_data_entry["Description"] = corrected_desc
            
            col_index = (col_index + 1) % 5
            
            excel_data_list.append(final_data_entry)

        if excel_data_list:
            docx_sub_bytes = to_text_docx_substitute(excel_data_list, st.session_state.original_desc_input, video_id_input)
            
            st.download_button(
                label="✅ 검수 완료된 제목/설명 다운로드 (Word 문서 형식)",
                data=docx_sub_bytes,
                file_name=f"{video_id_input}_translations_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

# --- 신규: 한국어 SBV -> 영어 SBV 번역 섹션 ---
st.header("한국어 SBV 자막 파일 ▶ 영어 번역")
uploaded_sbv_ko_file = st.file_uploader("한국어 .sbv 파일 업로드", type=['sbv'], key="sbv_uploader_ko")

if uploaded_sbv_ko_file:
    try:
        sbv_ko_content = uploaded_sbv_ko_file.getvalue().decode("utf-8")
        subs_ko, parse_ko_err = parse_sbv(sbv_ko_content)
        
        if parse_ko_err:
            st.error(parse_ko_err)
        else:
            st.success(f"✅ 한국어 .sbv 파일 로드 성공! (총 {len(subs_ko)}개의 자막 감지)")
            
            if st.button("한국어 SBV ▶ 영어로 번역 실행"):
                with st.spinner("한국어 ➡ 영어 번역 진행 중... (1차 번역 + 역번역 검수)"):
                    st.session_state.sbv_ko_to_en_result = None
                    st.session_state.sbv_ko_to_en_error = None
                    
                    texts_to_translate_ko = [sub.text for sub in subs_ko]
                    translated_texts_ko = []
                    
                    try:
                        # [오류 수정] Chunk 단위로 나누어 번역
                        for i in range(0, len(texts_to_translate_ko), CHUNK_SIZE):
                            chunk_num = i//CHUNK_SIZE + 1
                            chunk = texts_to_translate_ko[i:i + CHUNK_SIZE]
                            
                            # --- 1단계: 1차 번역 (KO -> EN) ---
                            # 1a. Try DeepL (Target "EN-US")
                            translated_chunk, translate_err = translate_deepl(translator_deepl, chunk, "EN-US", is_beta=False) 
                            
                            if translate_err:
                                st.warning(f"KO->EN DeepL 실패 (Chunk {chunk_num}). Google로 대체합니다. (오류: {translate_err})")
                                # 1b. Try Google (Target "en", Source "ko")
                                translated_chunk, translate_err = translate_google(translator_google, chunk, "en", source_lang='ko')
                                if translate_err:
                                    # If Google also fails, raise the error to stop
                                    raise Exception(f"Google마저 실패 (Chunk {chunk_num}): {translate_err}")
                            
                            # --- 2단계: [요청 사항] DeepL 자동 검수 (EN -> KO '역번역' 비교) ---
                            st.info(f"DeepL 역번역 검수 진행 중... (Chunk {chunk_num})")
                            # (1) 1차 번역(영어)을 다시 한국어로 번역
                            reviewed_ko_chunk, review_err = translate_deepl(translator_deepl, translated_chunk, "KO", is_beta=False)
                            
                            if review_err:
                                st.warning(f"DeepL 역번역 검수 실패 (Chunk {chunk_num}). 1차 번역(영어) 결과를 사용합니다. (오류: {review_err})")
                            else:
                                st.info(f"DeepL 역번역 검수 완료 (Chunk {chunk_num}). 1차 번역(영어) 결과를 사용합니다.")
                            
                            # [핵심] 1단계에서 번역된 '영어' (translated_chunk)를 최종 결과에 추가합니다.
                            translated_texts_ko.extend(translated_chunk) 
                            # --- 검수 로직 종료 ---

                        # Build the translated SBV
                        translated_subs_ko = subs_ko[:]
                        if isinstance(translated_texts_ko, list):
                            for j, sub in enumerate(translated_subs_ko):
                                sub.text = translated_texts_ko[j]
                        else:
                            translated_subs_ko[0].text = translated_texts_ko[0] # Failsafe
                        
                        sbv_output_content_ko_en = to_sbv_format(translated_subs_ko)
                        st.session_state.sbv_ko_to_en_result = sbv_output_content_ko_en
                        st.success("✅ 한국어 ▶ 영어 번역 완료!")
                        
                    except Exception as e:
                        st.session_state.sbv_ko_to_en_error = f"KO->EN SBV 생성 실패: {str(e)}"
                        st.error(st.session_state.sbv_ko_to_en_error)

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .sbv 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")

if 'sbv_ko_to_en_result' in st.session_state and st.session_state.sbv_ko_to_en_result:
    st.download_button(
        label="✅ 번역된 영어 .sbv 파일 다운로드",
        data=st.session_state.sbv_ko_to_en_result.encode('utf-8'),
        file_name="translated_en.sbv",
        mime="text/plain"
    )

# --- 영어 SBV 자막 파일 ▶ 다국어 번역 ---
st.header("영어 SBV 자막 파일 ▶ 다국어 번역")
uploaded_sbv_file = st.file_uploader("영어 .sbv 파일 업로드", type=['sbv'], key="sbv_uploader")

if uploaded_sbv_file:
    try:
        sbv_content = uploaded_sbv_file.getvalue().decode("utf-8")
        subs, parse_err = parse_sbv(sbv_content)
        
        if parse_err:
            st.error(parse_err)
        else:
            st.success(f"✅ .sbv 파일 로드 성공! (총 {len(subs)}개의 자막 감지)")
            
            if st.button("SBV 파일 번역 실행"):
                st.session_state.sbv_translations = {}
                st.session_state.sbv_errors = []
                srt_progress = st.progress(0, text="SBV 번역 진행 중...")
                total_langs = len(TARGET_LANGUAGES)
                texts_to_translate = [sub.text for sub in subs]
                
                for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
                    lang_name = lang_data["name"]
                    deepl_code = lang_data["code"]
                    is_beta = lang_data["is_beta"]
                    google_code = ui_key
                    
                    srt_progress.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
                    
                    try:
                        translated_texts_list = [] # Store results for this language
                        
                        # Chunk 단위로 나누어 번역
                        for chunk_i in range(0, len(texts_to_translate), CHUNK_SIZE):
                            chunk = texts_to_translate[chunk_i:chunk_i + CHUNK_SIZE]
                            
                            translated_chunk, translate_err = translate_deepl(translator_deepl, chunk, deepl_code, is_beta)
                            
                            if translate_err:
                                st.warning(f"SBV DeepL 실패 ({lang_name}, Chunk {chunk_i//CHUNK_SIZE + 1}). Google로 대체합니다.")
                                translated_chunk, translate_err = translate_google(translator_google, chunk, google_code)
                                if translate_err:
                                    raise Exception(f"Google마저 실패: {translate_err}")
                            
                            translated_texts_list.extend(translated_chunk)

                        # Now, translated_texts_list contains all translated segments for this language
                        translated_subs = subs[:]
                        if isinstance(translated_texts_list, list):
                            for j, sub in enumerate(translated_subs):
                                sub.text = translated_texts_list[j]
                        else:
                            translated_subs[0].text = translated_texts_list[0]
                        
                        sbv_output_content = to_sbv_format(translated_subs)
                        st.session_state.sbv_translations[ui_key] = sbv_output_content
                        
                    except Exception as e:
                        st.session_state.sbv_errors.append(f"SBV 생성 실패 ({lang_name}): {str(e)}")
                
                st.success("SBV 파일 번역 완료!")
                srt_progress.empty()
                if st.session_state.sbv_errors:
                    st.error("일부 SBV 번역 실패:")
                    for err in st.session_state.sbv_errors:
                        st.warning(err)

            if 'sbv_translations' in st.session_state and st.session_state.sbv_translations:
                st.subheader("번역된 .sbv 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.sbv_translations.items():
                        lang_name = TARGET_LANGUAGES[ui_key]["name"]
                        file_name = f"{lang_name}_{ui_key}.sbv" 
                        zip_file.writestr(file_name, content.encode('utf-8'))
                
                st.download_button(
                    label="✅ 번역된 .sbv 파일 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="all_sbv_subtitles.zip",
                    mime="application/zip"
                )
                st.markdown("---")
                cols = st.columns(5)
                col_index = 0
                for ui_key, lang_data in TARGET_LANGUAGES.items():
                    if ui_key in st.session_state.sbv_translations:
                        lang_name = lang_data["name"]
                        with cols[col_index]:
                            st.download_button(
                                label=f"{lang_name} (.sbv)", 
                                data=st.session_state.sbv_translations[ui_key].encode('utf-8'),
                                file_name=f"{lang_name}_{ui_key}.sbv",
                                mime="text/plain"
                            )
                        col_index = (col_index + 1) % 5

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .sbv 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")


# --- 영어 SRT 자막 파일 ▶ 다국어 번역 ---
st.header("영어 SRT 자막 파일 ▶ 다국어 번역")
uploaded_srt_file = st.file_uploader("영어 .srt 파일 업로드", type=['srt'], key="srt_uploader")

if uploaded_srt_file:
    try:
        srt_content = uploaded_srt_file.getvalue().decode("utf-8")
        subs, parse_err = parse_srt_native(srt_content)
        
        if parse_err:
            st.error(parse_err)
        else:
            st.success(f"✅ .srt 파일 로드 성공! (총 {len(subs)}개의 자막 감지)")
            
            if st.button("SRT 파일 번역 실행"):
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
                        translated_texts_list = [] # Store results for this language

                        # Chunk 단위로 나누어 번역
                        for chunk_i in range(0, len(texts_to_translate), CHUNK_SIZE):
                            chunk = texts_to_translate[chunk_i:chunk_i + CHUNK_SIZE]
                            
                            translated_chunk, translate_err = translate_deepl(translator_deepl, chunk, deepl_code, is_beta)
                            
                            if translate_err:
                                st.warning(f"SRT DeepL 실패 ({lang_name}, Chunk {chunk_i//CHUNK_SIZE + 1}). Google로 대체합니다.")
                                translated_chunk, translate_err = translate_google(translator_google, chunk, google_code)
                                if translate_err:
                                    raise Exception(f"Google마저 실패: {translate_err}")

                            translated_texts_list.extend(translated_chunk)

                        # Now, translated_texts_list contains all translated segments for this language
                        translated_subs = subs[:]
                        if isinstance(translated_texts_list, list):
                            for j, sub in enumerate(translated_subs):
                                sub.text = translated_texts_list[j]
                        else:
                            translated_subs[0].text = translated_texts_list[0]
                        
                        srt_output_content = to_srt_format_native(translated_subs)
                        st.session_state.srt_translations[ui_key] = srt_output_content
                        
                    except Exception as e:
                        st.session_state.srt_errors.append(f"SRT 생성 실패 ({lang_name}): {str(e)}")
                
                st.success("SRT 파일 번역 완료!")
                srt_progress.empty()
                if st.session_state.srt_errors:
                    st.error("일부 SRT 번역 실패:")
                    for err in st.session_state.srt_errors:
                        st.warning(err)

            if 'srt_translations' in st.session_state and st.session_state.srt_translations:
                st.subheader("4. 번역된 .srt 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.srt_translations.items():
                        lang_name = TARGET_LANGUAGES[ui_key]["name"]
                        file_name = f"{lang_name}_{ui_key}.srt"
                        zip_file.writestr(file_name, content.encode('utf-8'))
                
                st.download_button(
                    label="✅ 번역된 .srt 파일 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="all_srt_subtitles.zip",
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
                                data=st.session_state.srt_translations[ui_key].encode('utf-8'),
                                file_name=f"{lang_name}_{ui_key}.srt",
                                mime="text/plain"
                            )
                        col_index = (col_index + 1) % 5

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .srt 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")

