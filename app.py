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

# --- [언어 설정] (사용자 요청 반영) ---
# is_original: 번역하지 않고 원본 영어를 그대로 사용할 언어들
TARGET_LANGUAGES = OrderedDict({
    "ko": {"name": "한국어", "code": "KO", "use_google": False},
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
    
    "en-US": {"name": "영어 (미국)", "code": "en", "use_google": False, "is_original": True},
    "en-IE": {"name": "영어 (아일랜드)", "code": "en", "use_google": False, "is_original": True},
    "en-GB": {"name": "영어 (영국)", "code": "en", "use_google": False, "is_original": True},
    "en-AU": {"name": "영어 (오스트레일리아)", "code": "en", "use_google": False, "is_original": True},
    "en-IN": {"name": "영어 (인도)", "code": "en", "use_google": False, "is_original": True},
    "en-CA": {"name": "영어 (캐나다)", "code": "en", "use_google": False, "is_original": True},

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
    "fil": {"name": "필리핀어", "code": "tl", "use_google": True}, 
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

def generate_youtube_localizations_json(video_id, translations):
    localizations = {}
    for res in translations:
        ui_key = res['ui_key']
        final_title = st.session_state.get(f"t1_title_{ui_key}", res['title']) or ""
        final_desc = st.session_state.get(f"t1_desc_{ui_key}", res['desc']) or ""
        api_key = 'tl' if ui_key == 'fil' else ui_key
        localizations[api_key] = { "title": final_title, "description": final_desc }
        
    request_body = { "id": video_id, "localizations": localizations }
    return json.dumps(request_body, indent=2, ensure_ascii=False)

# --- [핵심 번역 로직 개선] ---
# [완벽 해결] 리스트를 조인하지 않고 그대로 전달하여 1:1 강제 매핑
@st.cache_data(show_spinner=False)
def translate_deepl(_translator, texts, target_lang):
    try:
        # texts가 리스트면 리스트 그대로 DeepL에 전달하여 1:1 개수 일치 보장
        res = _translator.translate_text(texts, target_lang=target_lang, split_sentences='off', tag_handling='html')
        if isinstance(texts, list):
            return [r.text for r in res], None
        return res.text, None
    except Exception as e: return "", str(e)

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, texts, target_lang, source_lang='en'):
    try:
        target = 'tl' if target_lang == 'fil' or target_lang == 'tl' else target_lang
        # Google API의 'q' 파라미터에 리스트를 그대로 전달하여 1:1 배열 번역 보장
        res = _google_translator.translations().list(q=texts, target=target, source=source_lang, format='text').execute()
        if isinstance(texts, list):
            return [html.unescape(item['translatedText']) for item in res['translations']], None
        return html.unescape(res['translations'][0]['translatedText']), None
    except Exception as e: return "", str(e)

# --- [자막 포맷팅] ---
def srt_serialise(index, start, end, text):
    def fmt_t(ts): return f"{ts.hours:02d}:{ts.minutes:02d}:{ts.seconds:02d},{ts.milliseconds:03d}"
    return f"{index}\n{fmt_t(start)} --> {fmt_t(end)}\n{text}\n\n"

def sbv_serialise(start, end, text):
    def fmt_t(ts): return f"{ts.hours:01d}:{ts.minutes:02d}:{ts.seconds:02d}.{ts.milliseconds:03d}"
    return f"{fmt_t(start)},{fmt_t(end)}\n{text}\n\n"

def parse_subs_from_content(content, file_type):
    from pysrt import SubRipFile, SubRipItem
    if file_type == "srt":
        return pysrt.from_string(content)
    else:
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
        return subs

# --- [Main UI] ---
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
except Exception as e:
    st.error(f"Secrets 로드 실패: {e}")
    st.stop()

st.title("📚 허슬플레이 자동 번역기 (자막 싱크 어긋남 완벽 해결판)")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []

# Task 1: 영상 정보 번역
st.header("1. 영상 제목 및 설명란 번역")
v_input = st.text_input("YouTube ID 또는 URL", key="yt_input_main")

if st.button("1. 정보 가져오기"):
    if v_input:
        video_id = extract_video_id(v_input)
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        if response.get('items'):
            st.session_state.video_details = response['items'][0]['snippet']
            st.session_state.clean_id = video_id
            st.success("영상 정보를 성공적으로 로드했습니다.")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목", snippet['title'], height=70, disabled=True)
    st.text_area("원본 설명", snippet.get('description', ''), height=150, disabled=True)
    
    if st.button("2. 다국어 번역 실행"):
        st.session_state.translation_results = []
        prog = st.progress(0)
        lines = snippet.get('description', '').split('\n')
        
        for idx, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            if ui_key == "en": continue
            
            if lang_data.get("is_original"):
                t_t = snippet['title']
                t_d = snippet.get('description', '')
            else:
                if lang_data["use_google"]:
                    t_t, _ = translate_google(translator_google, snippet['title'], ui_key)
                    t_d_list, _ = translate_google(translator_google, lines, ui_key)
                    t_d = "\n".join(t_d_list) if t_d_list else ""
                else:
                    t_t, _ = translate_deepl(translator_deepl, snippet['title'], lang_data["code"])
                    t_d_list, _ = translate_deepl(translator_deepl, lines, lang_data["code"])
                    t_d = "\n".join(t_d_list) if t_d_list else ""
            
            st.session_state.translation_results.append({
                "lang_name": lang_data["name"], "ui_key": ui_key,
                "title": t_t or "", "desc": t_d or ""
            })
            prog.progress((idx+1)/len(TARGET_LANGUAGES))
        st.success("전체 다국어 번역이 완료되었습니다!")

    if st.session_state.translation_results:
        for res in st.session_state.translation_results:
            with st.expander(f"📍 {res['lang_name']}", expanded=True):
                st.text_input("제목", res['title'], key=f"t1_title_{res['ui_key']}")
                st.text_area("설명", res['desc'], key=f"t1_desc_{res['ui_key']}", height=100)
        
        st.divider()
        st.header("YouTube 일괄 업로드 (JSON)")
        if st.button("🚀 JSON 생성"):
            error_langs = []
            for res in st.session_state.translation_results:
                curr_title = st.session_state.get(f"t1_title_{res['ui_key']}", res['title'])
                if len(str(curr_title or "")) > 100: error_langs.append(f"{res['lang_name']}")
            
            if error_langs:
                st.error(f"❌ 제목 100자 초과 언어: {', '.join(error_langs)}")
            else:
                json_body = generate_youtube_localizations_json(st.session_state.clean_id, st.session_state.translation_results)
                st.code(json_body, language="json")
                copy_to_clipboard(json_body)
                st.markdown("""
                ### **🚀 업데이트 가이드**
                1. 위 코드를 **Copy** 하세요.
                2. **👉 [Google YouTube API Explorer](https://developers.google.com/youtube/v3/docs/videos/update?apix=true)** 접속
                3. **`part`**: **`localizations`** 라고 입력
                4. **`Request body`**: 복사한 JSON 붙여넣기
                5. **Execute** 클릭!
                """)

st.divider()

# 3. 한국어 ▶ 영어 번역 (Deepl)
st.header("3. 한국어 ▶ 영어 번역 (Deepl)")
ck1, ck2 = st.columns(2)
with ck1: up_ko_sbv = st.file_uploader("한국어 .sbv 업로드", type=['sbv'], key="up_ko_sbv")
with ck2: up_ko_srt = st.file_uploader("한국어 .srt 업로드", type=['srt'], key="up_ko_srt")

if (up_ko_sbv or up_ko_srt) and st.button("🇺🇸 한국어 ▶ 영어 번역 시작"):
    target_up = up_ko_sbv if up_ko_sbv else up_ko_srt
    f_type = "sbv" if up_ko_sbv else "srt"
    content = target_up.read().decode("utf-8")
    subs = parse_subs_from_content(content, f_type)
    
    with st.spinner("DeepL 영어 번역 중..."):
        texts = [s.text.replace('\n', ' ') for s in subs]
        translated = []
        
        # [안정성 보완] 한국어 번역도 CHUNK_SIZE로 쪼개서 서버 무리를 방지
        for j in range(0, len(texts), CHUNK_SIZE):
            chunk = texts[j:j+CHUNK_SIZE]
            res, _ = translate_deepl(translator_deepl, chunk, "EN-US")
            translated.extend(res if isinstance(res, list) else [res])
        
        final_content = []
        for idx, txt in enumerate(translated):
            if idx >= len(subs): break
            if f_type == "sbv":
                final_content.append(sbv_serialise(subs[idx].start, subs[idx].end, str(txt).strip()))
            else:
                final_content.append(srt_serialise(idx+1, subs[idx].start, subs[idx].end, str(txt).strip()))
        
        st.download_button(f"📥 영어 번역된 {f_type.upper()} 다운로드", "".join(final_content), file_name=f"Translated_EN.{f_type}")

st.divider()

# Task 4 & 5: 영어 자막 다국어 번역 (Hybrid)
st.header("4. 영어 자막 ▶ 다국어 번역 (Hybrid)")
c1, c2 = st.columns(2)
with c1: up_multi_sbv = st.file_uploader("영어 .sbv", type=['sbv'], key="up_multi_sbv")
with c2: up_multi_srt = st.file_uploader("영어 .srt", type=['srt'], key="up_multi_srt")

def process_subs_hybrid(subs, file_type):
    zip_buf = io.BytesIO()
    original_texts = [s.text.replace('\n', ' ') for s in subs]
    with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zf:
        p_text = st.empty()
        for i, (uk, ld) in enumerate(TARGET_LANGUAGES.items()):
            p_text.text(f"번역 중: {ld['name']}")
            t_l = []
            for j in range(0, len(original_texts), CHUNK_SIZE):
                chunk = original_texts[j:j+CHUNK_SIZE]
                if ld.get("is_original"):
                    res = chunk # 영어권은 번역 없이 원본 그대로
                else:
                    # 1:1 매핑을 완벽 보장하는 개선된 번역 함수 사용
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

if up_multi_sbv and st.button("🚀 SBV 다국어 번역 시작"):
    content = up_multi_sbv.read().decode("utf-8")
    subs = parse_subs_from_content(content, "sbv")
    st.download_button("📂 번역된 SBV ZIP 다운로드", process_subs_hybrid(subs, "sbv"), "multilingual_sbv.zip")

if up_multi_srt and st.button("🚀 SRT 다국어 번역 시작"):
    content = up_multi_srt.read().decode("utf-8")
    subs = parse_subs_from_content(content, "srt")
    st.download_button("📂 번역된 SRT ZIP 다운로드", process_subs_hybrid(subs, "srt"), "multilingual_srt.zip")
