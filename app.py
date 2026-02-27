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
# 요청하신 순수 '영어' (en) 옵션을 포함한 최적화 리스트
TARGET_LANGUAGES = OrderedDict({
    "ko": {"name": "한국어", "code": "KO", "use_google": False},
    "en": {"name": "영어", "code": "EN-US", "use_google": False}, # 순수 영어 추가
    "el": {"name": "그리스어", "code": "EL", "use_google": True},
    "nl": {"name": "네덜란드어", "code": "NL", "use_google": False},
    "no": {"name": "노르웨이어", "code": "NB", "use_google": False},
    "da": {"name": "덴마크어", "code": "DA", "use_google": False},
    "de": {"name": "독일어", "code": "DE", "use_google": False},
    "ru": {"name": "러시아어", "code": "RU", "use_google": True},
    "mr": {"name": "마라티어", "code": "MR", "use_google": True},
    "ms": {"name": "말레이어", "code": "MS", "use_google": True},
    "vi": {"name": "베트남어", "code": "VI", "use_google": False},
    "bn": {"name": "벵골어", "code": "BN", "use_google": True},
    "sv": {"name": "스웨덴어", "code": "SV", "use_google": False},
    "es": {"name": "스페인어", "code": "ES", "use_google": False},
    "sk": {"name": "슬로바키아어", "code": "SK", "use_google": True},
    "ar": {"name": "아랍어", "code": "AR", "use_google": True},
    "en-GB": {"name": "영어 (영국)", "code": "EN-GB", "use_google": False},
    "en-AU": {"name": "영어 (오스트레일리아)", "code": "EN-AU", "use_google": False},
    "en-CA": {"name": "영어 (캐나다)", "code": "EN-CA", "use_google": False},
    "ur": {"name": "우르두어", "code": "UR", "use_google": True},
    "uk": {"name": "우크라이나어", "code": "UK", "use_google": True},
    "it": {"name": "이탈리아어", "code": "IT", "use_google": True},
    "id": {"name": "인도네시아어", "code": "ID", "use_google": False},
    "ja": {"name": "일본어", "code": "JA", "use_google": False},
    "zh-CN": {"name": "중국어(간체)", "code": "ZH", "use_google": True},
    "zh-TW": {"name": "중국어(번체)", "code": "zh-TW", "use_google": True},
    "cs": {"name": "체코어", "code": "CS", "use_google": True},
    "ta": {"name": "타밀어", "code": "TA", "use_google": True},
    "th": {"name": "태국어", "code": "TH", "use_google": True},
    "te": {"name": "텔루구어", "code": "TE", "use_google": True},
    "tr": {"name": "튀르키예어", "code": "TR", "use_google": True},
    "pa": {"name": "펀잡어", "code": "PA", "use_google": True},
    "pt": {"name": "포르투갈어", "code": "PT-PT", "use_google": False},
    "pl": {"name": "폴란드어", "code": "PL", "use_google": True},
    "fr": {"name": "프랑스어", "code": "FR", "use_google": False},
    "fi": {"name": "핀란드어", "code": "FI", "use_google": True},
    "fil": {"name": "필리핀어", "code": "FIL", "use_google": False},
    "hu": {"name": "헝가리어", "code": "HU", "use_google": True},
    "hi": {"name": "힌디어", "code": "HI", "use_google": False},
})

CHUNK_SIZE = 40 

# --- [유틸리티 함수] ---
def extract_video_id(url_or_id):
    video_id_regex = r'(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(video_id_regex, url_or_id)
    return match.group(1) if match else url_or_id.strip()

def copy_to_clipboard(text):
    escaped_text = json.dumps(str(text or ""))
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

# --- [처음 방식 그대로! 단순한 JSON 생성 로직] ---
def generate_youtube_localizations_json(video_id, translations):
    localizations = {}
    for res in translations:
        ui_key = res['ui_key']
        # 사용자가 수정한 값을 세션에서 가져옴 (t1_ prefix 유지)
        final_title = st.session_state.get(f"t1_title_{ui_key}", res['title']) or ""
        final_desc = st.session_state.get(f"t1_desc_{ui_key}", res['desc']) or ""
        
        lang_code = ui_key
        if lang_code == 'fil': lang_code = 'tl'
        
        localizations[lang_code] = { "title": final_title, "description": final_desc }
        
    # 처음 잘 작동하던 그 구조: id와 localizations만 포함
    request_body = { "id": video_id, "localizations": localizations }
    return json.dumps(request_body, indent=2, ensure_ascii=False)

# --- [핵심 번역 로직: 문맥 유지형] ---
@st.cache_data(show_spinner=False)
def translate_deepl(_translator, texts, target_lang):
    try:
        if isinstance(texts, list):
            combined_text = "\n".join([str(t).strip() for t in texts])
            res = _translator.translate_text(combined_text, target_lang=target_lang, split_sentences='off', tag_handling='html')
            return res.text.split('\n'), None
        res = _translator.translate_text(texts, target_lang=target_lang, split_sentences='off', tag_handling='html')
        return res.text, None
    except Exception as e: return "", str(e)

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, texts, target_lang, source_lang='en'):
    try:
        target = 'tl' if target_lang == 'fil' else target_lang
        if isinstance(texts, list):
            combined_text = "\n".join([str(t).strip() for t in texts])
            res = _google_translator.translations().list(q=combined_text, target=target, source=source_lang, format='text').execute()
            translated_text = html.unescape(res['translations'][0]['translatedText'])
            return translated_text.split('\n'), None
        res = _google_translator.translations().list(q=texts, target=target, source=source_lang, format='text').execute()
        return html.unescape(res['translations'][0]['translatedText']), None
    except Exception as e: return "", str(e)

# --- [자막 포맷팅: 표준 규격 및 줄바꿈 보장] ---
def srt_serialise(index, start, end, text):
    """자막 번호, 타임코드, 텍스트 후 명확한 더블 엔터(\n\n) 추가"""
    def fmt_t(ts): return f"{ts.hours:02d}:{ts.minutes:02d}:{ts.seconds:02d},{ts.milliseconds:03d}"
    return f"{index}\n{fmt_t(start)} --> {fmt_t(end)}\n{text}\n\n"

def sbv_serialise(start, end, text):
    """SBV 고유 양식 보장"""
    def fmt_t(ts): return f"{ts.hours:01d}:{ts.minutes:02d}:{ts.seconds:02d}.{ts.milliseconds:03d}"
    return f"{fmt_t(start)},{fmt_t(end)}\n{text}\n\n"

# --- [Main UI] ---
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
except Exception as e:
    st.error(f"API 키 로드 실패: {e}")
    st.stop()

st.title("📚 허슬플레이 자동 번역기 (Vr.260227-Success)")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []
if 'clean_id' not in st.session_state: st.session_state.clean_id = ""

# Task 1: 영상 정보 번역
st.header("1. 영상 제목 및 설명란 번역")
v_input = st.text_input("YouTube ID 또는 URL", key="yt_input_v3")

if st.button("1. 정보 가져오기"):
    if v_input:
        video_id = extract_video_id(v_input)
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        if response.get('items'):
            st.session_state.video_details = response['items'][0]['snippet']
            st.session_state.clean_id = video_id
            st.success("로드 완료 (제목 및 설명란 포함)")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목", snippet['title'], height=70, disabled=True)
    st.text_area("원본 설명", snippet.get('description', ''), height=200, disabled=True)
    
    if st.button("2. 다국어 번역 실행"):
        st.session_state.translation_results = []
        prog = st.progress(0)
        lines = snippet.get('description', '').split('\n')
        for idx, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            if lang_data["use_google"]:
                t_t, _ = translate_google(translator_google, snippet['title'], ui_key)
                t_d, _ = translate_google(translator_google, lines, ui_key)
            else:
                t_t, _ = translate_deepl(translator_deepl, snippet['title'], lang_data["code"])
                t_d, _ = translate_deepl(translator_deepl, lines, lang_data["code"])
            st.session_state.translation_results.append({
                "lang_name": lang_data["name"], "ui_key": ui_key,
                "title": t_t or "", "desc": "\n".join(t_d) if t_d else ""
            })
            prog.progress((idx+1)/len(TARGET_LANGUAGES))
        st.success("전체 번역 완료!")

    if st.session_state.translation_results:
        for res in st.session_state.translation_results:
            with st.expander(f"📍 {res['lang_name']}"):
                st.text_input("제목", res['title'], key=f"t1_title_{res['ui_key']}")
                st.text_area("설명", res['desc'], key=f"t1_desc_{res['ui_key']}", height=150)
        
        st.divider()
        st.header("3. YouTube 일괄 업로드 (JSON)")
        if st.button("🚀 JSON 생성"):
            # 예외 처리: 제목 100자 초과 체크
            error_langs = []
            for res in st.session_state.translation_results:
                curr_title = st.session_state.get(f"t1_title_{res['ui_key']}", res['title'])
                if len(str(curr_title or "")) > 100: error_langs.append(f"{res['lang_name']}")
            
            if error_langs:
                st.error(f"❌ 제목이 100자를 초과한 언어가 있습니다: {', '.join(error_langs)}")
            else:
                json_body = generate_youtube_localizations_json(st.session_state.clean_id, st.session_state.translation_results)
                st.code(json_body, language="json")
                copy_to_clipboard(json_body)
                st.markdown("""
                ### **🚀 업데이트 방법 (처음 성공했던 방식)**
                1. 위 코드를 **Copy** 하세요.
                2. **👉 [Google YouTube API Explorer 바로가기](https://developers.google.com/youtube/v3/docs/videos/update?apix=true)**
                3. **`part`**: 반드시 **`localizations`** 라고만 입력하세요.
                4. **`Request body`**: 복사한 JSON 코드를 붙여넣으세요.
                5. **Execute** 클릭!
                """)

st.divider()
# Task 4 & 5: 자막 번역 (줄바꿈 및 문맥 최적화)
st.header("4. 영어 자막 ▶ 다국어 번역 (Hybrid)")
c1, c2 = st.columns(2)
with c1: up_sbv = st.file_uploader("영어 .sbv 업로드", type=['sbv'], key="up_sbv_final")
with c2: up_srt = st.file_uploader("영어 .srt 업로드", type=['srt'], key="up_srt_final")

def process_subs(subs, file_type):
    zip_buf = io.BytesIO()
    original_texts = [s.text.replace('\n', ' ') for s in subs]
    with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zf:
        p_text = st.empty()
        for i, (uk, ld) in enumerate(TARGET_LANGUAGES.items()):
            p_text.text(f"번역 중: {ld['name']}")
            t_l = []
            for j in range(0, len(original_texts), CHUNK_SIZE):
                chunk = original_texts[j:j+CHUNK_SIZE]
                res, _ = translate_google(translator_google, chunk, uk) if ld["use_google"] else translate_deepl(translator_deepl, chunk, ld["code"])
                t_l.extend(res if isinstance(res, list) else [res])
            
            content = []
            for idx, txt in enumerate(t_l):
                if idx >= len(subs): break
                if file_type == "sbv": content.append(sbv_serialise(subs[idx].start, subs[idx].end, str(txt).strip()))
                else: content.append(srt_serialise(idx+1, subs[idx].start, subs[idx].end, str(txt).strip()))
            zf.writestr(f"{ld['name']} 자막.{file_type}", "".join(content))
        p_text.success("전체 다국어 번역 완료!")
    return zip_buf.getvalue()

if up_sbv and st.button("🚀 SBV 다국어 번역 시작"):
    from pysrt import SubRipFile, SubRipItem
    content = up_sbv.read().decode("utf-8")
    subs = SubRipFile()
    blocks = content.strip().replace('\r\n', '\n').split('\n\n')
    for block in blocks:
        parts = block.split('\n', 1)
        if len(parts) == 2:
            tm = re.match(r'(\d+):(\d+):(\d+)\.(\d+),(\d+):(\d+):(\d+)\.(\d+)', parts[0].strip())
            if tm:
                g = list(map(int, tm.groups()))
                sub = SubRipItem(); sub.text = html.unescape(parts[1].strip())
                sub.start.hours, sub.start.minutes, sub.start.seconds, sub.start.milliseconds = g[0], g[1], g[2], g[3]
                sub.end.hours, sub.end.minutes, sub.end.seconds, sub.end.milliseconds = g[4], g[5], g[6], g[7]
                subs.append(sub)
    st.download_button("📂 번역된 SBV ZIP 다운로드", process_subs(subs, "sbv"), "multilingual_sbv.zip")

if up_srt and st.button("🚀 SRT 다국어 번역 시작"):
    content = up_srt.read().decode("utf-8")
    subs = pysrt.from_string(content)
    st.download_button("📂 번역된 SRT ZIP 다운로드", process_subs(subs, "srt"), "multilingual_srt.zip")
