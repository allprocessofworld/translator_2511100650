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

# --- [UI 설정] ---
st.set_page_config(page_title="📚 허슬플레이 자동 번역기", layout="wide")

# --- [언어 설정] ---
# 요청하신 순수 '영어' 옵션을 포함하고 번역 엔진 최적화
TARGET_LANGUAGES = OrderedDict({
    "en": {"name": "영어", "code": "EN-US", "use_google": False}, # 순수 영어(en) 최상단 배치
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

# --- [유틸리티] ---
def extract_video_id(url_or_id):
    regex = r'(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(regex, url_or_id)
    return match.group(1) if match else url_or_id.strip()

def copy_to_clipboard(text):
    escaped = json.dumps(str(text or ""))
    components.html(f"<script>function copy(){{const t={escaped};navigator.clipboard.writeText(t);}}</script><button onclick='copy()' style='cursor:pointer;padding:5px;border-radius:4px;border:1px solid #ddd;font-weight:bold;'>📄 Copy Code</button>", height=45)

# --- [YouTube API 상호작용] ---
def get_video_details(api_key, video_id):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        res = youtube.videos().list(part="snippet", id=video_id).execute()
        return res['items'][0]['snippet'] if res.get('items') else None
    except: return None

def generate_safe_youtube_json(video_id, translations, original_snippet, default_lang):
    """
    400 invalidVideoMetadata 오류를 차단하기 위해 Snippet을 미러링하고 중복 언어를 제거합니다.
    """
    localizations = {}
    for res in translations:
        lang_key = res['ui_key']
        # [해결책] 기본 언어(defaultLanguage)와 동일한 키가 localizations에 있으면 400 에러 발생
        if lang_key == default_lang: continue
        
        title = st.session_state.get(f"title_{lang_key}", res['title']) or ""
        desc = st.session_state.get(f"desc_{lang_key}", res['desc']) or ""
        
        api_lang = 'tl' if lang_key == 'fil' else lang_key
        localizations[api_lang] = {"title": str(title)[:100], "description": str(desc)}
    
    request_body = {
        "id": video_id,
        "snippet": {
            "title": original_snippet.get('title', ''),
            "description": original_snippet.get('description', ''),
            "categoryId": str(original_snippet.get('categoryId', '22')),
            "defaultLanguage": default_lang 
        },
        "localizations": localizations
    }
    return json.dumps(request_body, indent=2, ensure_ascii=False)

# --- [번역 엔진] ---
def translate_deepl(_translator, texts, target_lang):
    try:
        if isinstance(texts, list):
            comb = "\n".join([str(t).strip() for t in texts])
            res = _translator.translate_text(comb, target_lang=target_lang, split_sentences='off', tag_handling='html')
            return res.text.split('\n'), None
        res = _translator.translate_text(texts, target_lang=target_lang, split_sentences='off', tag_handling='html')
        return res.text, None
    except: return "", "Error"

def translate_google(_google, texts, target_lang):
    try:
        target = 'tl' if target_lang == 'fil' else target_lang
        if isinstance(texts, list):
            comb = "\n".join([str(t).strip() for t in texts])
            res = _google.translations().list(q=comb, target=target, format='text').execute()
            return html.unescape(res['translations'][0]['translatedText']).split('\n'), None
        res = _google.translations().list(q=texts, target=target, format='text').execute()
        return html.unescape(res['translations'][0]['translatedText']), None
    except: return "", "Error"

# --- [자막 포맷팅] ---
def srt_fmt(i, s, e, t):
    def f(ts): return f"{ts.hours:02d}:{ts.minutes:02d}:{ts.seconds:02d},{ts.milliseconds:03d}"
    return f"{i}\n{f(s)} --> {f(e)}\n{t}\n\n"

# --- [Main UI] ---
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
except:
    st.error("API 키 설정 확인 필요 (Secrets)")
    st.stop()

st.title("📚 허슬플레이 자동 번역기 (Vr.260226-Stable-System)")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []

# Section 1
st.header("1. 영상 제목 및 설명란 번역")
v_input = st.text_input("YouTube ID 또는 URL 입력", key="v_input_stable")

if st.button("1. 정보 가져오기"):
    if v_input:
        vid = extract_video_id(v_input)
        snippet = get_video_details(YOUTUBE_API_KEY, vid)
        if snippet:
            st.session_state.video_details = snippet
            st.session_state.clean_id = vid
            st.success(f"데이터 로드 성공: {snippet['title']}")
        else: st.error("정보를 찾을 수 없습니다. (비공개 영상 여부 확인)")

if st.session_state.video_details:
    snip = st.session_state.video_details
    st.info(f"📌 서버 감지 정보 - 카테고리ID: {snip.get('categoryId')}, 현재 기본언어: {snip.get('defaultLanguage', '미설정')}")
    st.text_area("원본 제목", snip['title'], height=70, disabled=True)
    st.text_area("원본 설명", snip.get('description', ''), height=150, disabled=True)
    
    if st.button("2. 다국어 번역 실행"):
        st.session_state.translation_results = []
        prog = st.progress(0)
        lines = snip.get('description', '').split('\n')
        for idx, (uk, ld) in enumerate(TARGET_LANGUAGES.items()):
            if ld["use_google"]:
                t_t, _ = translate_google(translator_google, snip['title'], uk)
                t_d_l, _ = translate_google(translator_google, lines, uk)
            else:
                t_t, _ = translate_deepl(translator_deepl, snip['title'], ld["code"])
                t_d_l, _ = translate_deepl(translator_deepl, lines, ld["code"])
            st.session_state.translation_results.append({
                "lang_name": ld["name"], "ui_key": uk,
                "title": t_t or "", "desc": "\n".join(t_d_l) if t_d_l else ""
            })
            prog.progress((idx+1)/len(TARGET_LANGUAGES))
        st.success("번역 완료!")

    if st.session_state.translation_results:
        for res in st.session_state.translation_results:
            with st.expander(f"📍 {res['lang_name']}"):
                st.text_input("제목", res['title'], key=f"title_{res['ui_key']}")
                st.text_area("설명", res['desc'], key=f"desc_{res['ui_key']}", height=100)
        
        st.divider()
        st.header("3. YouTube 일괄 업로드 (JSON)")
        
        # [해결책] 순수 '영어' 옵션을 선택하여 API 코드 불일치 해결
        def_lang = st.selectbox(
            "이 영상의 '원본 언어(기본 언어)'를 선택하세요. (해당 언어는 번역 목록에서 자동 제외됩니다)", 
            options=list(TARGET_LANGUAGES.keys()), 
            format_func=lambda x: TARGET_LANGUAGES[x]['name'],
            index=0 # 영어(en) 기본값
        )
        
        if st.button("🚀 JSON 생성"):
            json_body = generate_safe_youtube_json(st.session_state.clean_id, st.session_state.translation_results, snip, def_lang)
            st.code(json_body, language="json")
            copy_to_clipboard(json_body)
            
            st.markdown(f"""
            ### **🚀 일괄 업데이트 가이드 (복구 완료)**
            1. 위 JSON 코드를 **Copy** 하세요.
            2. **👉 [Google YouTube API Explorer 바로가기](https://developers.google.com/youtube/v3/docs/videos/update?apix=true)**
            3. **`part`**: 반드시 **`snippet,localizations`** 라고 입력하세요.
            4. **`Request body`**: 복사한 JSON 코드를 붙여넣으세요.
            5. **Execute** 클릭! (로그인 계정이 영상 소유주인지 확인 필수)
            """)

st.divider()
st.header("4. 자막 번역 (표준 규격 준수)")
up_srt = st.file_uploader("SRT 파일 업로드", type=['srt'], key="up_srt_stable")
if up_srt:
    if st.button("🚀 다국어 SRT 번역 시작"):
        content = up_srt.read().decode("utf-8")
        subs = pysrt.from_string(content)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zf:
            for uk, ld in TARGET_LANGUAGES.items():
                texts = [s.text.replace('\n', ' ') for s in subs]
                t_l, _ = translate_deepl(translator_deepl, texts, ld["code"]) if not ld["use_google"] else translate_google(translator_google, texts, uk)
                res_content = "".join([srt_fmt(j+1, subs[j].start, subs[j].end, str(t_l[j]).strip()) for j in range(len(subs))])
                zf.writestr(f"{ld['name']} 자막.srt", res_content)
        st.download_button("📂 ZIP 다운로드", zip_buf.getvalue(), "multilingual_srt.zip")
