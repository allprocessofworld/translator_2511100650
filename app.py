import streamlit as st
import streamlit.components.v1 as components
import deepl
from googleapiclient.discovery import build
import pysrt
import io
import zipfile
import json
import re
import html
from collections import OrderedDict

# --- [UI 설정] 페이지 제목 및 레이아웃 ---
st.set_page_config(page_title="📚 허슬플레이 자동 번역기", layout="wide")

# --- [언어 설정] ---
TARGET_LANGUAGES = OrderedDict({
    "ko": {"name": "한국어", "code": "KO", "is_beta": False, "use_google": False},
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
    "en-GB": {"name": "영어 (영국)", "code": "EN-GB", "is_beta": False, "use_google": False},
    "en-AU": {"name": "영어 (오스트레일리아)", "code": "EN-AU", "is_beta": False, "use_google": False},
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

CHUNK_SIZE = 50

# --- [유틸리티 함수] ---

def extract_video_id(url_or_id):
    video_id_regex = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(video_id_regex, url_or_id)
    if match: return match.group(1)
    if len(url_or_id.strip()) == 11: return url_or_id.strip()
    return url_or_id.strip()

def copy_to_clipboard(text):
    escaped_text = json.dumps(text)
    html_code = f"""
    <script>
    function copyToClipboard() {{
        const text = {escaped_text};
        const el = document.createElement('textarea');
        el.value = text;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
    }}
    </script>
    <button onclick="copyToClipboard()" style="cursor:pointer; padding:5px 10px; border-radius:4px; border:1px solid #ddd; background:#f9f9f9; font-weight:600;">📄 Copy</button>
    """
    components.html(html_code, height=45)

def protect_formatting(text):
    pattern = r'\*'
    replacement = '<span translate="no">*</span>'
    if isinstance(text, list): return [re.sub(pattern, replacement, t) for t in text]
    return re.sub(pattern, replacement, text)

def restore_formatting(text):
    pattern = r'<span[^>]*translate=["\']?no["\']?[^>]*>\s*\*\s*<\/span>'
    replacement = '*'
    if isinstance(text, list): return [re.sub(pattern, replacement, t, flags=re.IGNORECASE) for t in text]
    return re.sub(pattern, replacement, text, flags=re.IGNORECASE)

# --- [자막 파싱 및 변환] ---

@st.cache_data(show_spinner=False)
def parse_sbv(file_content):
    subs = pysrt.SubRipFile()
    blocks = file_content.strip().replace('\r\n', '\n').split('\n\n')
    for i, block in enumerate(blocks):
        if not block.strip(): continue
        parts = block.split('\n', 1)
        if len(parts) != 2: continue
        time_str, text = parts
        time_match = re.match(r'(\d+):(\d+):(\d+)\.(\d+),(\d+):(\d+):(\d+)\.(\d+)', time_str.strip())
        if time_match:
            g = list(map(int, time_match.groups()))
            sub = pysrt.SubRipItem(index=i+1)
            sub.start.hours, sub.start.minutes, sub.start.seconds, sub.start.milliseconds = g[0], g[1], g[2], g[3]
            sub.end.hours, sub.end.minutes, sub.end.seconds, sub.end.milliseconds = g[4], g[5], g[6], g[7]
            sub.text = html.unescape(text.strip())
            subs.append(sub)
    return subs if subs else None

def to_sbv_format(subrip_file):
    output = []
    for sub in subrip_file:
        start = f"{sub.start.hours:01d}:{sub.start.minutes:02d}:{sub.start.seconds:02d}.{sub.start.milliseconds:03d}"
        end = f"{sub.end.hours:01d}:{sub.end.minutes:02d}:{sub.end.seconds:02d}.{sub.end.milliseconds:03d}"
        output.append(f"{start},{end}\n{sub.text}\n")
    return "\n".join(output)

# --- [API 통신 함수] ---

@st.cache_data(show_spinner=False)
def translate_deepl(_translator, texts, target_lang, is_beta=False):
    """
    is_beta 인자는 무시하도록 수정하여 API 호환성 문제를 해결함.
    """
    try:
        protected = protect_formatting(texts)
        # enable_beta_languages 인자를 제거하여 에러 방지
        res = _translator.translate_text(
            protected, 
            target_lang=target_lang, 
            split_sentences='off', 
            tag_handling='html'
        )
        raw = [r.text for r in res] if isinstance(texts, list) else res.text
        return restore_formatting(raw), None
    except Exception as e: return None, str(e)

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, texts, target_lang, source_lang='en'):
    try:
        protected = protect_formatting(texts)
        target = 'tl' if target_lang == 'fil' else target_lang
        res = _google_translator.translations().list(q=protected, target=target, source=source_lang, format='html').execute()
        raw = [html.unescape(item['translatedText']) for item in res['translations']] if isinstance(texts, list) else html.unescape(res['translations'][0]['translatedText'])
        return restore_formatting(raw), None
    except Exception as e: return None, str(e)

@st.cache_data(show_spinner=False)
def get_video_details(api_key, raw_video_id):
    try:
        video_id = extract_video_id(raw_video_id)
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        if not response.get('items'): return None, "영상을 찾을 수 없습니다."
        return response['items'][0]['snippet'], None
    except Exception as e: return None, str(e)

# --- [자막 다국어 처리 로직] ---

def process_subtitle_translation(subs, file_type="srt"):
    zip_buffer = io.BytesIO()
    original_texts = [s.text for s in subs]
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        progress_text = st.empty()
        sub_progress = st.progress(0)
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            progress_text.text(f"🌐 번역 중: {lang_name} ({i+1}/{len(TARGET_LANGUAGES)})")
            
            translated_lines = []
            error_occured = False
            
            for j in range(0, len(original_texts), CHUNK_SIZE):
                chunk = original_texts[j:j+CHUNK_SIZE]
                if lang_data["use_google"]:
                    res, err = translate_google(translator_google, chunk, ui_key)
                else:
                    res, err = translate_deepl(translator_deepl, chunk, lang_data["code"], lang_data["is_beta"])
                
                if err:
                    st.error(f"❌ {lang_name} 번역 실패: {err}")
                    error_occured = True
                    break
                translated_lines.extend(res)
            
            if not error_occured:
                temp_subs = pysrt.SubRipFile()
                for idx, t_text in enumerate(translated_lines):
                    new_item = pysrt.SubRipItem(index=idx+1, start=subs[idx].start, end=subs[idx].end, text=t_text)
                    temp_subs.append(new_item)
                
                file_ext = "sbv" if file_type == "sbv" else "srt"
                content = to_sbv_format(temp_subs) if file_type == "sbv" else temp_subs.text
                zip_file.writestr(f"translated_{ui_key}.{file_ext}", content)
            
            sub_progress.progress((i + 1) / len(TARGET_LANGUAGES))
            
        progress_text.success("✅ 모든 언어 번역 완료!")
    return zip_buffer.getvalue()

# --- [Streamlit UI Main] ---

st.title("📚 허슬플레이 자동 번역기 (Vr.260220-FIXED)")

try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
    st.sidebar.success("✅ API 연결 성공")
except Exception as e:
    st.error(f"❌ API 키 설정 오류: {e}")
    st.stop()

# --- Task 1: 영상 제목 및 설명란 번역 ---
st.header("1. 영상 제목 및 설명란 번역")
v_input = st.text_input("YouTube 동영상 ID 또는 URL", placeholder="예: dQw4w9WgXcQ")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []

if st.button("1. 정보 가져오기"):
    if v_input:
        snippet, err = get_video_details(YOUTUBE_API_KEY, v_input)
        if err: st.error(err)
        else:
            st.session_state.video_details = snippet
            st.session_state.clean_id = extract_video_id(v_input)
            st.success(f"영상 로드 완료: {snippet['title']}")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목", snippet['title'], height=50, disabled=True)
    
    if st.button("2. 다국어 번역 실행 (Hybrid)"):
        st.session_state.translation_results = []
        prog = st.progress(0)
        lines = snippet['description'].split('\n')
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            res_data = {"lang_name": lang_data["name"], "ui_key": ui_key, "api": "DeepL" if not lang_data["use_google"] else "Google"}
            
            if lang_data["use_google"]:
                t_title, _ = translate_google(translator_google, snippet['title'], ui_key)
                t_desc_list, _ = translate_google(translator_google, lines, ui_key)
                t_desc = "\n".join(t_desc_list)
            else:
                t_title, _ = translate_deepl(translator_deepl, snippet['title'], lang_data["code"], lang_data["is_beta"])
                t_desc_list, _ = translate_deepl(translator_deepl, lines, lang_data["code"], lang_data["is_beta"])
                t_desc = "\n".join(t_desc_list)
            
            res_data.update({"title": t_title, "desc": t_desc})
            st.session_state.translation_results.append(res_data)
            prog.progress((i+1)/len(TARGET_LANGUAGES))
        st.success("번역 완료!")

    if st.session_state.translation_results:
        for res in st.session_state.translation_results:
            with st.expander(f"📍 {res['lang_name']} ({res['api']})"):
                st.text_input("제목", res['title'], key=f"t1_t_{res['ui_key']}")
                copy_to_clipboard(res['title'])
                st.text_area("설명", res['desc'], key=f"t1_d_{res['ui_key']}", height=150)
                copy_to_clipboard(res['desc'])

st.divider()

# --- Task 2 & 3: 한국어 -> 영어 고품질 번역 ---
st.header("2. 한국어 자막 ▶ 영어 번역 (High Quality)")
col_a, col_b = st.columns(2)
with col_a:
    up_sbv_ko = st.file_uploader("한국어 .sbv 파일", type=['sbv'], key="ko_sbv")
with col_b:
    up_srt_ko = st.file_uploader("한국어 .srt 파일", type=['srt'], key="ko_srt")

if up_sbv_ko or up_srt_ko:
    if st.button("🇺🇸 영어로 번역 시작"):
        f = up_sbv_ko if up_sbv_ko else up_srt_ko
        is_sbv = up_sbv_ko is not None
        content = f.read().decode("utf-8")
        subs = parse_sbv(content) if is_sbv else pysrt.from_string(content)
        
        with st.spinner("DeepL 번역 중..."):
            texts = [s.text for s in subs]
            translated, _ = translate_deepl(translator_deepl, texts, "EN-US")
            for i, t in enumerate(translated): subs[i].text = t
            
            final_content = to_sbv_format(subs) if is_sbv else subs.text
            st.download_button("📥 번역된 파일 다운로드", final_content, file_name=f"EN_{f.name}")

st.divider()

# --- Task 4: 영어 SBV ▶ 다국어 번역 (Hybrid) ---
st.header("4. 영어 SBV ▶ 다국어 번역 (Hybrid)")
up_sbv_multi = st.file_uploader("영어 .sbv 파일 업로드", type=['sbv'], key="task4")
if up_sbv_multi:
    content = up_sbv_multi.read().decode("utf-8")
    subs = parse_sbv(content)
    if subs and st.button("🚀 SBV 다국어 번역 시작"):
        zip_data = process_subtitle_translation(subs, file_type="sbv")
        st.download_button("📂 번역된 SBV ZIP 다운로드", zip_data, "multi_sbv.zip", "application/zip")

st.divider()

# --- Task 5: 영어 SRT ▶ 다국어 번역 (Hybrid) ---
st.header("5. 영어 SRT ▶ 다국어 번역 (Hybrid)")
up_srt_multi = st.file_uploader("영어 .srt 파일 업로드", type=['srt'], key="task5")
if up_srt_multi:
    content = up_srt_multi.read().decode("utf-8")
    try:
        subs = pysrt.from_string(content)
        if st.button("🚀 SRT 다국어 번역 시작"):
            zip_data = process_subtitle_translation(subs, file_type="srt")
            st.download_button("📂 번역된 SRT ZIP 다운로드", zip_data, "multi_srt.zip", "application/zip")
    except Exception as e: st.error(f"파일 오류: {e}")
