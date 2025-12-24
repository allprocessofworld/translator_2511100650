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
# use_google: True -> Google 강제 사용 (그룹 4)
# use_google: False -> DeepL 우선 사용 (그룹 1~3, 영어)
TARGET_LANGUAGES = OrderedDict({
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
    """
    pysrt 객체를 복사하지 않고, 원본 타임코드와 번역된 텍스트를 사용하여
    새로운 SRT 포맷의 문자열을 직접 생성합니다. (데이터 오염 원천 차단)
    """
    output = []
    for index, (sub, text) in enumerate(zip(original_subs, translated_texts)):
        # 1. Index
        output.append(str(index + 1))
        # 2. Time (pysrt time object to string)
        # pysrt uses comma for milliseconds in output usually
        start = str(sub.start).replace('.', ',') 
        end = str(sub.end).replace('.', ',')
        output.append(f"{start} --> {end}")
        # 3. Text
        output.append(text)
        # 4. Empty line
        output.append("")
    
    return "\n".join(output)

# --- API 함수 ---
@st.cache_data(show_spinner=False)
def get_video_details(api_key, video_id):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        if not response.get('items'): return None, "YouTube API 오류: 해당 ID의 영상을 찾을 수 없습니다."
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

def to_text_docx_substitute(data_list, original_desc_input, video_id):
    output = io.StringIO()
    output.write("==================================================\n")
    output.write(f"YouTube 영상 제목 및 설명 번역 보고서\n")
    output.write(f"영상 ID: {video_id}\n")
    output.write(f"생성 날짜: {pd.to_datetime('today').strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write("==================================================\n\n")
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
st.title("허슬플레이 자동 번역기 (Vr.251210-FIX)")

st.info("❗ 그룹 1~3 (주요 언어)는 DeepL을 사용하고, 그룹 4 (기타 언어)는 Google 번역을 사용하여 비용을 절감합니다.")
st.info("⚠️ 최종적으로 유튜브 스튜디오에는 총 41개 언어가 업로드되어야 합니다.")

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
video_id_input = st.text_input("YouTube 동영상 ID 입력")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []

if st.button("1. 영상 정보 가져오기"):
    if video_id_input:
        with st.spinner("YouTube API 연결 중..."):
            snippet, error = get_video_details(YOUTUBE_API_KEY, video_id_input)
            if error:
                st.error(error)
                st.session_state.video_details = None
            else:
                st.session_state.video_details = snippet
                st.session_state.translation_results = []
                st.success(f"영상 정보 로드: {snippet['title']}")
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
            use_google = lang_data["use_google"] # DeepL 사용 여부 확인
            google_code = ui_key
            
            # 진행상황 표시에 엔진 정보 추가
            engine_label = "Google" if use_google else "DeepL"
            progress_bar.progress((i + 1) / total_langs, text=f"번역 중 ({engine_label}): {lang_name}")
            
            result_data = {
                "lang_name": lang_name, "ui_key": ui_key, "is_beta": is_beta,
                "api": None, "status": "실패", "title": "", "desc": ""
            }

            title_text = desc_text = None
            title_err = desc_err = None
            used_api = ""

            # --- 로직 분기: Google 강제 그룹 vs DeepL 그룹 ---
            if use_google:
                # [그룹 4] Google 바로 실행
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
                # [그룹 1~3] DeepL 우선 -> 실패 시 Google
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

                # DeepL 실패 시 Google Fallback
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

            # 결과 저장
            if title_err or desc_err:
                result_data["api"] = used_api
                result_data["status"] = "실패"
                result_data["title"] = f"Error: {title_err}"; result_data["desc"] = f"Error: {desc_err}"
            else:
                result_data["api"] = used_api
                result_data["status"] = "성공"
                result_data["title"] = title_text; result_data["desc"] = desc_text

            st.session_state.translation_results.append(result_data)

        st.success("작업 완료!")
        progress_bar.empty()

    if st.session_state.translation_results:
        st.subheader("번역 결과 (자동 펼침 및 복사)")
        
        # [UI 개선] 각 언어별로 박스 형태로 표시 및 복사 버튼 추가
        for res in st.session_state.translation_results:
            st.markdown(f"### **{res['lang_name']}** <small>({res['api']})</small>", unsafe_allow_html=True)
            
            # 1. 제목 섹션 (입력창 + 복사버튼)
            c1, c2 = st.columns([8, 1])
            with c1:
                # session_state key를 활용하여 수정된 값 유지
                new_title = st.text_input("제목", res['title'], key=f"t1_title_{res['ui_key']}", label_visibility="collapsed")
                
                # --- [수정: 핵심 기능] 제목 길이 유효성 검사 ---
                title_len = len(new_title)
                if title_len > 100:
                    st.error(f"🚨 [오류] 제목 길이 초과: {title_len}/100자 (YouTube 제한 100자를 넘었습니다. 줄여주세요!)")
                elif title_len >= 95:
                    st.warning(f"⚠️ [주의] 제목 길이가 제한에 근접합니다: {title_len}/100자")
                # ---------------------------------------------

            with c2:
                copy_to_clipboard(new_title)
            
            # 2. 설명 섹션 (입력창 + 복사버튼)
            c3, c4 = st.columns([8, 1])
            with c3:
                new_desc = st.text_area("설명", res['desc'], key=f"t1_desc_{res['ui_key']}", height=150, label_visibility="collapsed")
            with c4:
                copy_to_clipboard(new_desc)
                
            st.divider()

        # JSON 생성 및 안내 섹션
        st.header("3. YouTube 일괄 업로드 (JSON)")
        if st.button("JSON 생성"):
            # --- [수정: 핵심 기능] JSON 생성 전 전체 검증 ---
            has_length_error = False
            error_langs = []
            
            for res in st.session_state.translation_results:
                # 현재 session state에 있는(사용자가 수정한) 값 가져오기
                t_key = f"t1_title_{res['ui_key']}"
                curr_title = st.session_state.get(t_key, res['title'])
                
                if len(curr_title) > 100:
                    has_length_error = True
                    error_langs.append(f"{res['lang_name']} ({len(curr_title)}자)")
            
            if has_length_error:
                st.error("❌ [생성 불가] 다음 언어의 제목이 100자를 초과했습니다. 수정 후 다시 시도하세요.")
                st.error(", ".join(error_langs))
            else:
                json_body = generate_youtube_localizations_json(video_id_input, st.session_state.translation_results)
                st.code(json_body, language="json")
                
                col_json_btn, col_json_info = st.columns([2, 8])
                with col_json_btn:
                    copy_to_clipboard(json_body)
                
                # [안내 문구 추가]
                st.markdown("""
                ---
                ### **🚀 40개 언어 1초 만에 업데이트하는 방법**
                1. 위 **JSON 코드**를 복사하세요 ('Copy' 버튼 클릭).
                2. **👉 [Google YouTube API Explorer (videos.update) 바로가기](https://developers.google.com/youtube/v3/docs/videos/update?apix=true)** 를 클릭하세요.
                3. 이동한 페이지에서 **Execute** 버튼 위에 있는 입력창을 찾으세요:
                   - **`part`**: 입력창에 `localizations` 라고 적으세요.
                   - **`Request body`**: 복사한 JSON 코드를 **전체 붙여넣기** 하세요.
                4. 하단의 **Execute** 버튼을 누르고, Google 계정 권한을 허용하세요.
                5. 초록색 **200 OK** 응답이 뜨면 성공입니다! (YouTube 스튜디오에서 새로고침 확인)
                """)

# --- Task 2: 한국어 SBV -> 영어 번역 (High Quality) ---
st.header("2. 한국어 SBV ▶ 영어 번역 (High Quality)")
uploaded_sbv_ko_file = st.file_uploader("한국어 .sbv 파일", type=['sbv'], key="sbv_uploader_ko")

if uploaded_sbv_ko_file:
    try:
        sbv_ko_content = uploaded_sbv_ko_file.getvalue().decode("utf-8")
        subs_ko, parse_ko_err = parse_sbv(sbv_ko_content)
        if parse_ko_err: st.error(parse_ko_err)
        else:
            if st.button("한국어 SBV ▶ 영어 번역 실행"):
                with st.spinner("DeepL(KO->EN) 번역 중..."):
                    texts_to_translate_ko = [sub.text for sub in subs_ko]
                    translated_texts_ko = []
                    try:
                        # 1. DeepL 우선 번역
                        for i in range(0, len(texts_to_translate_ko), CHUNK_SIZE):
                            chunk = texts_to_translate_ko[i:i + CHUNK_SIZE]
                            translated_chunk, translate_err = translate_deepl(translator_deepl, chunk, "EN-US", is_beta=False) 
                            
                            # 2. 실패 시 Google 대체
                            if translate_err:
                                translated_chunk, translate_err = translate_google(translator_google, chunk, "en", source_lang='ko')
                                if translate_err: raise Exception(translate_err)
                            translated_texts_ko.extend(translated_chunk) 
                        
                        # 3. 결과 조합 및 저장
                        translated_subs_ko = copy.deepcopy(subs_ko)
                        if isinstance(translated_texts_ko, list):
                            for j, sub in enumerate(translated_subs_ko): sub.text = translated_texts_ko[j]
                        else: translated_subs_ko[0].text = translated_texts_ko[0]
                        
                        # session_state에 결과 저장 (버튼 밖에서 쓰기 위함)
                        st.session_state.sbv_ko_result = to_sbv_format(translated_subs_ko)
                        st.success("작업이 완료되었습니다! 아래 다운로드 버튼을 확인하세요.")
                        
                    except Exception as e: st.error(str(e))
            
            # [수정] 버튼 밖에서 결과 렌더링 (지속성 유지)
            if 'sbv_ko_result' in st.session_state and st.session_state.sbv_ko_result:
                st.divider()
                st.download_button(
                    label="📥 영어 SBV 다운로드", 
                    data=st.session_state.sbv_ko_result.encode('utf-8'), 
                    file_name="translated_en.sbv",
                    mime="text/plain"
                )

    except Exception as e: st.error(str(e))

# --- Task 3: 한국어 SRT -> 영어 번역 (High Quality) ---
st.header("3. 한국어 SRT ▶ 영어 번역 (High Quality)")
uploaded_srt_ko_file = st.file_uploader("한국어 .srt 파일", type=['srt'], key="srt_uploader_ko")

if uploaded_srt_ko_file:
    try:
        # 인코딩 자동 감지
        try: srt_ko_content = uploaded_srt_ko_file.getvalue().decode("utf-8")
        except: srt_ko_content = uploaded_srt_ko_file.getvalue().decode("cp949")

        subs_ko, parse_ko_err = parse_srt_native(srt_ko_content)
        if parse_ko_err: st.error(parse_ko_err)
        else:
            if st.button("한국어 SRT ▶ 영어 번역 실행"):
                with st.spinner("DeepL(KO->EN) 번역 중..."):
                    texts_to_translate_ko = [sub.text for sub in subs_ko]
                    translated_texts_ko = []
                    try:
                        # 1. DeepL 우선 번역
                        for i in range(0, len(texts_to_translate_ko), CHUNK_SIZE):
                            chunk = texts_to_translate_ko[i:i + CHUNK_SIZE]
                            translated_chunk, translate_err = translate_deepl(translator_deepl, chunk, "EN-US", is_beta=False) 
                            
                            # 2. 실패 시 Google 대체
                            if translate_err:
                                translated_chunk, translate_err = translate_google(translator_google, chunk, "en", source_lang='ko')
                                if translate_err: raise Exception(translate_err)
                            translated_texts_ko.extend(translated_chunk) 
                        
                        # 3. 결과 조합 및 저장 (안전한 재조립 함수 사용)
                        st.session_state.srt_ko_result = reconstruct_srt_content(subs_ko, translated_texts_ko)
                        st.success("작업이 완료되었습니다! 아래 다운로드 버튼을 확인하세요.")

                    except Exception as e: st.error(str(e))

            # [수정] 버튼 밖에서 결과 렌더링 (지속성 유지)
            if 'srt_ko_result' in st.session_state and st.session_state.srt_ko_result:
                st.divider()
                st.download_button(
                    label="📥 영어 SRT 다운로드", 
                    data=st.session_state.srt_ko_result.encode('utf-8'), 
                    file_name="translated_en.srt",
                    mime="text/plain"
                )

    except Exception as e: st.error(str(e))

# --- Task 4: 영어 SBV -> 다국어 번역 (Hybrid) ---
st.header("4. 영어 SBV ▶ 다국어 번역 (Hybrid)")
uploaded_sbv_file = st.file_uploader("영어 .sbv 파일", type=['sbv'], key="sbv_uploader")

if uploaded_sbv_file:
    try:
        sbv_content = uploaded_sbv_file.getvalue().decode("utf-8")
        subs, parse_err = parse_sbv(sbv_content)
        if parse_err: st.error(parse_err)
        else:
            if st.button("SBV 다국어 번역 실행"):
                st.session_state.sbv_translations = {}
                st.session_state.sbv_errors = []
                
                # [수정] 영어권 국가 제외 필터링
                target_langs_subs = OrderedDict(
                    (k, v) for k, v in TARGET_LANGUAGES.items() if not k.startswith("en-")
                )
                
                progress = st.progress(0)
                original_texts = [sub.text for sub in subs]
                total_langs = len(target_langs_subs)
                
                for i, (ui_key, lang_data) in enumerate(target_langs_subs.items()):
                    lang_name = lang_data["name"]; deepl_code = lang_data["code"]
                    use_google = lang_data["use_google"]
                    progress.progress((i + 1) / total_langs, text=f"번역: {lang_name}")

                    try:
                        translated_texts_list = []
                        if use_google:
                            # Group 4: Google Only
                            for chunk_i in range(0, len(original_texts), CHUNK_SIZE):
                                chunk = original_texts[chunk_i:chunk_i + CHUNK_SIZE]
                                translated_chunk, err = translate_google(translator_google, chunk, ui_key)
                                if err: raise Exception(err)
                                translated_texts_list.extend(translated_chunk)
                        else:
                            # Group 1-3: DeepL First
                            for chunk_i in range(0, len(original_texts), CHUNK_SIZE):
                                chunk = original_texts[chunk_i:chunk_i + CHUNK_SIZE]
                                translated_chunk, err = translate_deepl(translator_deepl, chunk, deepl_code, lang_data["is_beta"])
                                if err:
                                    translated_chunk, err = translate_google(translator_google, chunk, ui_key)
                                    if err: raise Exception(err)
                                translated_texts_list.extend(translated_chunk)

                        translated_subs = copy.deepcopy(subs)
                        if isinstance(translated_texts_list, list):
                            for j, sub in enumerate(translated_subs): sub.text = translated_texts_list[j]
                        else: translated_subs[0].text = translated_texts_list[0]
                        st.session_state.sbv_translations[ui_key] = to_sbv_format(translated_subs)

                    except Exception as e: st.session_state.sbv_errors.append(f"{lang_name}: {str(e)}")
                
                st.success("작업이 완료되었습니다! 아래 버튼을 확인하세요.")
            
            # [수정] 버튼 클릭 블록 밖에서 결과 렌더링 (지속성 유지)
            if 'sbv_translations' in st.session_state and st.session_state.sbv_translations:
                st.divider()
                st.subheader("📥 번역 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.sbv_translations.items():
                        # 파일명 공백 처리
                        safe_name = TARGET_LANGUAGES[ui_key]['name'].replace(" ", "_")
                        zip_file.writestr(f"{safe_name}_{ui_key}.sbv", content.encode('utf-8'))
                
                st.download_button(
                    label="✅ 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="sbv_subs.zip",
                    mime="application/zip"
                )
            
            # [수정] 오류 로그 출력
            if 'sbv_errors' in st.session_state and st.session_state.sbv_errors:
                st.error(f"총 {len(st.session_state.sbv_errors)}건의 번역 실패가 있습니다.")
                for err in st.session_state.sbv_errors:
                    st.warning(err)

    except Exception as e: st.error(str(e))

# --- Task 5: 영어 SRT -> 다국어 번역 (Hybrid) ---
st.header("5. 영어 SRT ▶ 다국어 번역 (Hybrid)")
uploaded_srt_file = st.file_uploader("영어 .srt 파일", type=['srt'], key="srt_uploader")

if uploaded_srt_file:
    try:
        try: srt_content = uploaded_srt_file.getvalue().decode("utf-8")
        except: srt_content = uploaded_srt_file.getvalue().decode("cp949")
        
        subs, parse_err = parse_srt_native(srt_content)
        if parse_err: st.error(parse_err)
        else:
            if st.button("SRT 다국어 번역 실행"):
                st.session_state.srt_translations = {}
                st.session_state.srt_errors = []
                
                # [수정] 영어권 국가 제외 필터링
                target_langs_subs = OrderedDict(
                    (k, v) for k, v in TARGET_LANGUAGES.items() if not k.startswith("en-")
                )
                
                progress = st.progress(0)
                original_texts = [sub.text for sub in subs]
                total_langs = len(target_langs_subs)
                
                for i, (ui_key, lang_data) in enumerate(target_langs_subs.items()):
                    lang_name = lang_data["name"]; deepl_code = lang_data["code"]
                    use_google = lang_data["use_google"]
                    progress.progress((i + 1) / total_langs, text=f"번역: {lang_name}")
                    
                    try:
                        translated_texts_list = []
                        if use_google:
                            # Group 4: Google Only
                            for chunk_i in range(0, len(original_texts), CHUNK_SIZE):
                                chunk = original_texts[chunk_i:chunk_i + CHUNK_SIZE]
                                translated_chunk, err = translate_google(translator_google, chunk, ui_key)
                                if err: raise Exception(err)
                                translated_texts_list.extend(translated_chunk)
                        else:
                            # Group 1-3: DeepL First
                            for chunk_i in range(0, len(original_texts), CHUNK_SIZE):
                                chunk = original_texts[chunk_i:chunk_i + CHUNK_SIZE]
                                translated_chunk, err = translate_deepl(translator_deepl, chunk, deepl_code, lang_data["is_beta"])
                                if err:
                                    translated_chunk, err = translate_google(translator_google, chunk, ui_key)
                                    if err: raise Exception(err)
                                translated_texts_list.extend(translated_chunk)

                        # [핵심 수정] 안전한 텍스트 재조립 함수 사용 (객체 오염 및 속성 오류 방지)
                        st.session_state.srt_translations[ui_key] = reconstruct_srt_content(subs, translated_texts_list)

                    except Exception as e: st.session_state.srt_errors.append(f"{lang_name}: {str(e)}")
                
                st.success("작업이 완료되었습니다! 아래 버튼을 확인하세요.")

            # [수정] 버튼 클릭 블록 밖에서 결과 렌더링 (지속성 유지)
            if 'srt_translations' in st.session_state and st.session_state.srt_translations:
                st.divider()
                st.subheader("📥 번역 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.srt_translations.items():
                        safe_name = TARGET_LANGUAGES[ui_key]['name'].replace(" ", "_")
                        zip_file.writestr(f"{safe_name}_{ui_key}.srt", content.encode('utf-8'))
                
                st.download_button(
                    label="✅ 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="srt_subs.zip",
                    mime="application/zip"
                )
            
            # [수정] 오류 로그 출력
            if 'srt_errors' in st.session_state and st.session_state.srt_errors:
                st.error(f"총 {len(st.session_state.srt_errors)}건의 번역 실패가 있습니다.")
                for err in st.session_state.srt_errors:
                    st.warning(err)

    except Exception as e: st.error(str(e))
