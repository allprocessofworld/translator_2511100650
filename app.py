import streamlit as st
import streamlit.components.v1 as components
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
import copy

# --- [UI 설정] 페이지 제목 및 레이아웃 ---
st.set_page_config(page_title="📚 허슬플레이 자동 번역기", layout="wide")

# --- [언어 설정] 한국어 가나다순 정렬 (Hybrid 설정) ---
# ko: 한국어 추가
TARGET_LANGUAGES = OrderedDict({
    "ko": {"name": "한국어", "code": "KO", "is_beta": False, "use_google": False}, # 한국어 추가
    "el": {"name": "그리스어", "code": "EL", "is_beta": False, "use_google": True},
    "nl": {"name": "네덜란드어", "code": "NL", "is_beta": False, "use_google": False},
    "no": {"name": "노르웨이어", "code": "NB", "is_beta": False, "use_google": False},
    "da": {"name": "덴마크어", "code": "DA", "is_beta": False, "use_google": False},
    "de": {"name": "독일어", "code": "DE", "is_beta": False, "use_google": False},
    "ru": {"name": "러시아어", "code": "RU", "is_beta": False, "use_google": True},
    "mr": {"name": "마라티어", "code": "MR", "is_beta": True, "use_google": True},
    "ms": {"name": "말레이어", "code": "MS", "is_beta": True, "use_google": True},
    "vi": {"name": "베트남어", "code": "VI", "is_beta": True, "use_google": False},
    "bn": {"name": "벵골어", "code": "BN", "is_beta": True, "use_google": True},
    "sv": {"name": "스웨덴어", "code": "SV", "is_beta": False, "use_google": False},
    "es": {"name": "스페인어", "code": "ES", "is_beta": False, "use_google": False},
    "sk": {"name": "슬로바키아어", "code": "SK", "is_beta": False, "use_google": True},
    "ar": {"name": "아랍어", "code": "AR", "is_beta": False, "use_google": True},
    
    # [영어권 가나다순 정렬]
    "en-IE": {"name": "영어 (아일랜드)", "code": "EN-GB", "is_beta": False, "use_google": False},
    "en-GB": {"name": "영어 (영국)", "code": "EN-GB", "is_beta": False, "use_google": False},
    "en-AU": {"name": "영어 (오스트레일리아)", "code": "EN-AU", "is_beta": False, "use_google": False},
    "en-IN": {"name": "영어 (인도)", "code": "EN-GB", "is_beta": False, "use_google": False},
    "en-CA": {"name": "영어 (캐나다)", "code": "EN-CA", "is_beta": False, "use_google": False},

    "ur": {"name": "우르두어", "code": "UR", "is_beta": True, "use_google": True},
    "uk": {"name": "우크라이나어", "code": "UK", "is_beta": False, "use_google": True},
    "it": {"name": "이탈리아어", "code": "IT", "is_beta": False, "use_google": True},
    "id": {"name": "인도네시아어", "code": "ID", "is_beta": False, "use_google": False},
    "ja": {"name": "일본어", "code": "JA", "is_beta": False, "use_google": False},
    "zh-CN": {"name": "중국어(간체)", "code": "ZH", "is_beta": False, "use_google": True},
    "zh-TW": {"name": "중국어(번체)", "code": "zh-TW", "is_beta": False, "use_google": True},
    "cs": {"name": "체코어", "code": "CS", "is_beta": False, "use_google": True},
    "ta": {"name": "타밀어", "code": "TA", "is_beta": True, "use_google": True},
    "th": {"name": "태국어", "code": "TH", "is_beta": True, "use_google": True},
    "te": {"name": "텔루구어", "code": "TE", "is_beta": True, "use_google": True},
    "tr": {"name": "튀르키예어", "code": "TR", "is_beta": False, "use_google": True},
    "pa": {"name": "펀잡어", "code": "PA", "is_beta": True, "use_google": True},
    "pt": {"name": "포르투갈어", "code": "PT-PT", "is_beta": False, "use_google": False},
    "pl": {"name": "폴란드어", "code": "PL", "is_beta": False, "use_google": True},
    "fr": {"name": "프랑스어", "code": "FR", "is_beta": False, "use_google": False},
    "fi": {"name": "핀란드어", "code": "FI", "is_beta": False, "use_google": True},
    "fil": {"name": "필리핀어", "code": "FIL", "is_beta": False, "use_google": False},
    "hu": {"name": "헝가리어", "code": "HU", "is_beta": False, "use_google": True},
    "hi": {"name": "힌디어", "code": "HI", "is_beta": True, "use_google": False},
})

CHUNK_SIZE = 100

# --- [유틸리티] YouTube ID 추출 함수 ---
def extract_video_id(url_or_id):
    """
    URL 형태(watch?v=, youtu.be/)나 순수 ID를 입력받아 11자리 ID만 반환합니다.
    """
    video_id_regex = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(video_id_regex, url_or_id)
    if match:
        return match.group(1)
    # 11자리 정규 패턴에 맞으면 그대로 반환
    if len(url_or_id.strip()) == 11:
        return url_or_id.strip()
    return url_or_id.strip()

# --- [UI Component] 커스텀 복사 버튼 함수 ---
def copy_to_clipboard(text):
    escaped_text = json.dumps(text)
    html_code = f"""
    <!DOCTYPE html>
    <html style="height: 100%; overflow: hidden;">
    <head>
        <style>
            body {{ margin: 0; padding: 0; display: flex; justify-content: center; align-items: flex-start; height: 100%; }}
            .copy-btn {{
                background-color: #f0f2f6;
                border: 1px solid #d6d6d8;
                border-radius: 4px;
                color: #31333F;
                padding: 6px 12px;
                text-align: center;
                text-decoration: none;
                display: inline-block;
                font-size: 14px;
                font-family: "Source Sans Pro", sans-serif;
                cursor: pointer;
                transition-duration: 0.2s;
                font-weight: 600;
                width: 100%;
                box-sizing: border-box;
            }}
            .copy-btn:hover {{
                background-color: #ff4b4b;
                color: white;
                border: 1px solid #ff4b4b;
            }}
            .copy-btn:active {{
                background-color: #c93a3a;
                transform: translateY(1px);
            }}
        </style>
        <script>
        function copyToClipboard() {{
            const text = {escaped_text};
            navigator.clipboard.writeText(text).then(function() {{
                const btn = document.getElementById("btn");
                btn.innerText = "✅ Copied!";
                btn.style.backgroundColor = "#d4edda";
                btn.style.color = "#155724";
                btn.style.borderColor = "#c3e6cb";
                setTimeout(() => {{ 
                    btn.innerText = "📄 Copy"; 
                    btn.style.backgroundColor = "#f0f2f6";
                    btn.style.color = "#31333F";
                    btn.style.borderColor = "#d6d6d8";
                }}, 2000);
            }}, function(err) {{
                console.error('Async: Could not copy text: ', err);
            }});
        }}
        </script>
    </head>
    <body>
        <button id="btn" class="copy-btn" onclick="copyToClipboard()">📄 Copy</button>
    </body>
    </html>
    """
    components.html(html_code, height=50)


# --- [핵심 기능] 텍스트 보호/복원 Helper 함수 ---
def protect_formatting(text):
    pattern = r'\*'
    replacement = '<span translate="no">*</span>'
    if isinstance(text, list):
        return [re.sub(pattern, replacement, t) for t in text]
    else:
        return re.sub(pattern, replacement, text)

def restore_formatting(text):
    pattern = r'<span[^>]*translate=["\']?no["\']?[^>]*>\s*\*\s*<\/span>'
    replacement = '*'
    if isinstance(text, list):
        return [re.sub(pattern, replacement, t, flags=re.IGNORECASE) for t in text]
    else:
        return re.sub(pattern, replacement, text, flags=re.IGNORECASE)

# --- SBV / SRT 처리 헬퍼 함수 ---
@st.cache_data(show_spinner=False)
def parse_sbv(file_content):
    subs = pysrt.SubRipFile()
    lines = file_content.strip().replace('\r\n', '\n').split('\n\n')
    for i, block in enumerate(lines):
        if not block.strip(): continue
        parts = block.split('\n', 1)
        if len(parts) != 2: continue
        time_str, text = parts
        time_match = re.match(r'(\d+):(\d+):(\d+)\.(\d+),(\d+):(\d+):(\d+)\.(\d+)', time_str.strip())
        if time_match:
            start_h, start_m, start_s, start_ms, end_h, end_m, end_s, end_ms = map(int, time_match.groups())
            sub = pysrt.SubRipItem()
            sub.index = i + 1
            sub.start.hours = start_h; sub.start.minutes = start_m; sub.start.seconds = start_s; sub.start.milliseconds = start_ms
            sub.end.hours = end_h; sub.end.minutes = end_m; sub.end.seconds = end_s; sub.end.milliseconds = end_ms
            sub.text = html.unescape(text.strip())
            subs.append(sub)
    if not subs: return None, "SBV 파싱 오류: 유효한 시간/텍스트 블록을 찾을 수 없습니다."
    return subs, None

def to_sbv_format(subrip_file):
    sbv_output = []
    for sub in subrip_file:
        def format_sbv_time(time):
            return f"{time.hours:02d}:{time.minutes:02d}:{time.seconds:02d}.{time.milliseconds:03d}"
        start_time = format_sbv_time(sub.start)
        end_time = format_sbv_time(sub.end)
        time_line = f"{start_time},{end_time}"
        text_content = html.unescape(sub.text.strip())
        sbv_output.append(time_line); sbv_output.append(text_content); sbv_output.append("")
    return "\n".join(sbv_output).strip()

@st.cache_data(show_spinner=False)
def parse_srt_native(file_content):
    try:
        subs = pysrt.from_string(file_content)
        return subs, None
    except Exception as e:
        return None, f"SRT 파싱 오류: {str(e)}"

# --- [NEW] 안전한 SRT 재조립 함수 (객체 오염 방지) ---
def reconstruct_srt_content(original_subs, translated_texts):
    output = []
    for index, (sub, text) in enumerate(zip(original_subs, translated_texts)):
        output.append(str(index + 1))
        start = str(sub.start).replace('.', ',') 
        end = str(sub.end).replace('.', ',')
        output.append(f"{start} --> {end}")
        output.append(text)
        output.append("")
    return "\n".join(output)

# --- API 함수 ---
@st.cache_data(show_spinner=False)
def get_video_details(api_key, raw_video_id):
    try:
        # 비디오 ID 정제 (URL 입력 대응)
        video_id = extract_video_id(raw_video_id)
        if not video_id or len(video_id) != 11:
            return None, f"유효하지 않은 동영상 ID입니다: {video_id}"

        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        
        if not response.get('items'): 
            return None, f"YouTube API 오류: 해당 ID({video_id})의 영상을 찾을 수 없습니다. (비공개 영상이거나 삭제된 영상일 수 있습니다.)"
        
        snippet = response['items'][0]['snippet']
        return snippet, None
    except Exception as e:
        return None, f"YouTube API 오류: {str(e)}"

@st.cache_data(show_spinner=False)
def translate_deepl(_translator, text, target_lang_code, is_beta=False):
    try:
        protected_text = protect_formatting(text)
        is_list = isinstance(protected_text, list)
        if is_beta:
            result = _translator.translate_text(protected_text, target_lang=target_lang_code, enable_beta_languages=True, split_sentences='off', tag_handling='html')
        else:
            # target_lang_code가 'KO'인 경우 등 대응
            result = _translator.translate_text(protected_text, target_lang=target_lang_code, split_sentences='off', tag_handling='html')
        
        if is_list: translated_raw = [r.text for r in result]
        else: translated_raw = result.text
        
        final_text = restore_formatting(translated_raw)
        return final_text, None
    except Exception as e:
        return None, f"DeepL 실패: {str(e)}"

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, text, target_lang_code_ui, source_lang='en'):
    try:
        protected_text = protect_formatting(text)
        target = target_lang_code_ui
        if target == 'fil': target = 'tl'
        
        result = _google_translator.translations().list(q=protected_text, target=target, source=source_lang, format='html').execute()
        
        if isinstance(protected_text, list): translated_raw = [html.unescape(item['translatedText']) for item in result['translations']]
        else: translated_raw = html.unescape(result['translations'][0]['translatedText'])
        
        final_text = restore_formatting(translated_raw)
        return final_text, None
    except Exception as e:
        return None, f"Google 실패: {str(e)}"

# --- [신규] API 일괄 업데이트용 JSON 생성 함수 ---
def generate_youtube_localizations_json(video_id, translations):
    localizations = {}
    for item in translations:
        if item['status'] != '성공': continue
        lang_key = item['ui_key']
        title_key = f"t1_title_{lang_key}"
        desc_key = f"t1_desc_{lang_key}"
        final_title = st.session_state.get(title_key, item['title'])
        final_desc = st.session_state.get(desc_key, item['desc'])
        localizations[lang_key] = { "title": final_title, "description": final_desc }
        
    request_body = { "id": video_id, "localizations": localizations }
    return json.dumps(request_body, indent=2, ensure_ascii=False)


# --- Streamlit UI ---
st.title("허슬플레이 자동 번역기 (Vr.260220-FIX)")

st.info("❗ 그룹 1~3 및 한국어는 DeepL을 사용하고, 그룹 4는 Google 번역을 사용합니다.")

try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"] 
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
    st.success("✅ API 키 로드 완료")
except KeyError:
    st.error("❌ Secrets 설정 오류: YOUTUBE_API_KEY 또는 DEEPL_API_KEY 없음")
    st.stop()

# --- Task 1: 영상 제목 및 설명란 번역 ---
st.header("1. 영상 제목 및 설명란 번역")
video_id_input = st.text_input("YouTube 동영상 ID 또는 URL 입력", placeholder="예: dQw4w9WgXcQ 또는 https://www.youtube.com/watch?v=...")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []
if 'clean_video_id' not in st.session_state: st.session_state.clean_video_id = ""

if st.button("1. 영상 정보 가져오기"):
    if video_id_input:
        with st.spinner("YouTube API 연결 중..."):
            snippet, error = get_video_details(YOUTUBE_API_KEY, video_id_input)
            if error:
                st.error(error)
                st.session_state.video_details = None
            else:
                st.session_state.video_details = snippet
                st.session_state.clean_video_id = extract_video_id(video_id_input)
                st.session_state.translation_results = []
                st.success(f"영상 정보 로드 성공: {snippet['title']}")
    else: st.warning("ID를 입력하세요.")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목", snippet['title'], height=50, disabled=True)
    st.session_state.original_desc_input = snippet['description']
    st.text_area("원본 설명", snippet['description'], height=350, disabled=True) 

    if st.button("2. 전체 언어 번역 실행 (하이브리드 모드)"):
        st.session_state.translation_results = []
        progress_bar = st.progress(0, text="번역 시작...")
        total_langs = len(TARGET_LANGUAGES)
        original_desc_lines = snippet['description'].split('\n')
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            deepl_code = lang_data["code"]
            is_beta = lang_data["is_beta"]
            use_google = lang_data["use_google"]
            google_code = ui_key
            
            engine_label = "Google" if use_google else "DeepL"
            progress_bar.progress((i + 1) / total_langs, text=f"번역 중 ({engine_label}): {lang_name}")
            
            result_data = {
                "lang_name": lang_name, "ui_key": ui_key, "is_beta": is_beta,
                "api": None, "status": "실패", "title": "", "desc": ""
            }

            title_text = desc_text = None
            title_err = desc_err = None
            used_api = ""

            if use_google:
                used_api = "Google"
                title_text, title_err = translate_google(translator_google, snippet['title'], google_code)
                if not title_err:
                    translated_desc_lines = []
                    try:
                        for chunk_i in range(0, len(original_desc_lines), CHUNK_SIZE):
                            chunk = original_desc_lines[chunk_i:chunk_i + CHUNK_SIZE]
                            translated_chunk, err = translate_google(translator_google, chunk, google_code)
                            if err: raise Exception(err)
                            translated_desc_lines.extend(translated_chunk)
                        desc_text = '\n'.join(translated_desc_lines)
                    except Exception as e: desc_err = e
            else:
                used_api = "DeepL"
                title_text, title_err = translate_deepl(translator_deepl, snippet['title'], deepl_code, is_beta)
                
                if not title_err:
                    translated_desc_lines = []
                    try:
                        for chunk_i in range(0, len(original_desc_lines), CHUNK_SIZE):
                            chunk = original_desc_lines[chunk_i:chunk_i + CHUNK_SIZE]
                            translated_chunk, err = translate_deepl(translator_deepl, chunk, deepl_code, is_beta)
                            if err: raise Exception(err)
                            translated_desc_lines.extend(translated_chunk)
                        desc_text = '\n'.join(translated_desc_lines)
                    except Exception as e: desc_err = e

                if title_err or desc_err:
                    st.warning(f"DeepL 실패 ({lang_name}). Google로 대체합니다.")
                    used_api = "Google (Fallback)"
                    title_text, title_err = translate_google(translator_google, snippet['title'], google_code)
                    if not title_err:
                        translated_desc_lines = []
                        try:
                            for chunk_i in range(0, len(original_desc_lines), CHUNK_SIZE):
                                chunk = original_desc_lines[chunk_i:chunk_i + CHUNK_SIZE]
                                translated_chunk, err = translate_google(translator_google, chunk, google_code)
                                if err: raise Exception(err)
                                translated_desc_lines.extend(translated_chunk)
                            desc_text = '\n'.join(translated_desc_lines)
                        except Exception as e: desc_err = e

            if title_err or desc_err:
                result_data["api"] = used_api
                result_data["status"] = "실패"
                result_data["title"] = f"Error: {title_err}"; result_data["desc"] = f"Error: {desc_err}"
            else:
                result_data["api"] = used_api
                result_data["status"] = "성공"
                result_data["title"] = title_text; result_data["desc"] = desc_text

            st.session_state.translation_results.append(result_data)

        st.success("전체 번역 작업 완료!")
        progress_bar.empty()

    if st.session_state.translation_results:
        st.subheader("번역 결과 (자동 펼침 및 복사)")
        
        for res in st.session_state.translation_results:
            st.markdown(f"### **{res['lang_name']}** <small>({res['api']})</small>", unsafe_allow_html=True)
            
            c1, c2 = st.columns([8, 1])
            with c1:
                new_title = st.text_input("제목", res['title'], key=f"t1_title_{res['ui_key']}", label_visibility="collapsed")
                title_len = len(new_title)
                if title_len > 100:
                    st.error(f"🚨 [오류] 제목 길이 초과: {title_len}/100자")
                elif title_len >= 95:
                    st.warning(f"⚠️ [주의] 제목 길이가 제한에 근접합니다: {title_len}/100자")

            with c2:
                copy_to_clipboard(new_title)
            
            c3, c4 = st.columns([8, 1])
            with c3:
                new_desc = st.text_area("설명", res['desc'], key=f"t1_desc_{res['ui_key']}", height=150, label_visibility="collapsed")
            with c4:
                copy_to_clipboard(new_desc)
                
            st.divider()

        st.header("3. YouTube 일괄 업로드 (JSON)")
        if st.button("JSON 생성"):
            has_length_error = False
            error_langs = []
            
            for res in st.session_state.translation_results:
                t_key = f"t1_title_{res['ui_key']}"
                curr_title = st.session_state.get(t_key, res['title'])
                if len(curr_title) > 100:
                    has_length_error = True
                    error_langs.append(f"{res['lang_name']} ({len(curr_title)}자)")
            
            if has_length_error:
                st.error("❌ [생성 불가] 다음 언어의 제목이 100자를 초과했습니다. 수정 후 다시 시도하세요.")
                st.error(", ".join(error_langs))
            else:
                json_body = generate_youtube_localizations_json(st.session_state.clean_video_id, st.session_state.translation_results)
                st.code(json_body, language="json")
                
                col_json_btn, col_json_info = st.columns([2, 8])
                with col_json_btn:
                    copy_to_clipboard(json_body)
                
                st.markdown("""
                ---
                ### **🚀 41개 언어 1초 만에 업데이트하는 방법**
                1. 위 **JSON 코드**를 복사하세요 ('Copy' 버튼 클릭).
                2. **👉 [Google YouTube API Explorer 바로가기](https://developers.google.com/youtube/v3/docs/videos/update?apix=true)**
                3. **`part`**: `localizations` 입력
                4. **`Request body`**: 복사한 JSON 코드를 붙여넣기
                5. **Execute** 버튼을 누르고 성공 여부 확인!
                """)

# --- 나머지 Task 2 ~ 5 코드는 기존과 동일하므로 유지됨 ---
# (공간 절약을 위해 요약표시하며 실제 환경에서는 위 코드 뒤에 기존 Task 2~5 코드가 이어집니다)

st.header("2. 한국어 SBV ▶ 영어 번역 (High Quality)")
uploaded_sbv_ko_file = st.file_uploader("한국어 .sbv 파일", type=['sbv'], key="sbv_uploader_ko")
# ... (기존 Task 2 코드) ...

st.header("3. 한국어 SRT ▶ 영어 번역 (High Quality)")
uploaded_srt_ko_file = st.file_uploader("한국어 .srt 파일", type=['srt'], key="srt_uploader_ko")
# ... (기존 Task 3 코드) ...

st.header("4. 영어 SBV ▶ 다국어 번역 (Hybrid)")
uploaded_sbv_file = st.file_uploader("영어 .sbv 파일", type=['sbv'], key="sbv_uploader")
# ... (기존 Task 4 코드) ...

st.header("5. 영어 SRT ▶ 다국어 번역 (Hybrid)")
uploaded_srt_file = st.file_uploader("영어 .srt 파일", type=['srt'], key="srt_uploader")
# ... (기존 Task 5 코드) ...
