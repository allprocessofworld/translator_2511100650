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

CHUNK_SIZE = 40 

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

# --- [YouTube API용 JSON 생성] ---

def generate_youtube_localizations_json(video_id, translations):
    localizations = {}
    for res in translations:
        ui_key = res['ui_key']
        # 사용자가 화면에서 수정한 값을 세션에서 가져옴
        final_title = st.session_state.get(f"title_{ui_key}", res['title']) or ""
        final_desc = st.session_state.get(f"desc_{ui_key}", res['desc']) or ""
        
        # YouTube API 필드 매핑
        lang_code = ui_key
        if lang_code == 'fil': lang_code = 'tl'
        
        localizations[lang_code] = {
            "title": final_title,
            "description": final_desc
        }
        
    request_body = {
        "id": video_id,
        "localizations": localizations
    }
    return json.dumps(request_body, indent=2, ensure_ascii=False)

# --- [핵심 번역 로직: 문맥 유지형] ---

@st.cache_data(show_spinner=False)
def translate_deepl(_translator, texts, target_lang):
    try:
        if isinstance(texts, list):
            # 문맥 보존을 위해 개행문자로 합쳐서 번역
            combined_text = "\n".join([str(t) for t in texts])
            res = _translator.translate_text(combined_text, target_lang=target_lang, split_sentences='off', tag_handling='html')
            translated_list = res.text.split('\n')
            if len(translated_list) != len(texts):
                # 줄 수가 맞지 않으면 안전을 위해 개별 번역 시도
                res_fallback = _translator.translate_text(texts, target_lang=target_lang, split_sentences='off', tag_handling='html')
                return [r.text for r in res_fallback], None
            return translated_list, None
        else:
            res = _translator.translate_text(texts, target_lang=target_lang, split_sentences='off', tag_handling='html')
            return res.text, None
    except Exception as e: return "", str(e)

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, texts, target_lang, source_lang='en'):
    try:
        target = 'tl' if target_lang == 'fil' else target_lang
        if isinstance(texts, list):
            combined_text = "\n".join([str(t) for t in texts])
            res = _google_translator.translations().list(q=combined_text, target=target, source=source_lang, format='text').execute()
            translated_text = html.unescape(res['translations'][0]['translatedText'])
            translated_list = translated_text.split('\n')
            if len(translated_list) != len(texts):
                res_fallback = _google_translator.translations().list(q=texts, target=target, source=source_lang, format='text').execute()
                return [html.unescape(item['translatedText']) for item in res_fallback['translations']], None
            return translated_list, None
        else:
            res = _google_translator.translations().list(q=texts, target=target, source=source_lang, format='text').execute()
            return html.unescape(res['translations'][0]['translatedText']), None
    except Exception as e: return "", str(e)

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

# --- [자막 직렬화 보정] ---

def to_sbv_format(subrip_file):
    output = []
    for sub in subrip_file:
        start = f"{sub.start.hours:01d}:{sub.start.minutes:02d}:{sub.start.seconds:02d}.{sub.start.milliseconds:03d}"
        end = f"{sub.end.hours:01d}:{sub.end.minutes:02d}:{sub.end.seconds:02d}.{sub.end.milliseconds:03d}"
        output.append(f"{start},{end}\n{sub.text}")
    return "\n\n".join(output)

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

# --- [다국어 자막 생성 로직] ---

def process_subtitle_translation(subs, file_type="srt"):
    zip_buffer = io.BytesIO()
    # 텍스트 내 불필요한 개행 제거 후 문맥 번역 준비
    original_texts = [s.text.replace('\n', ' ') for s in subs]
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        progress_text = st.empty()
        sub_progress = st.progress(0)
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            progress_text.text(f"🌐 문맥 파악 번역 중: {lang_name} ({i+1}/{len(TARGET_LANGUAGES)})")
            
            translated_lines = []
            error_occured = False
            
            for j in range(0, len(original_texts), CHUNK_SIZE):
                chunk = original_texts[j:j+CHUNK_SIZE]
                if lang_data["use_google"]:
                    res, err = translate_google(translator_google, chunk, ui_key)
                else:
                    res, err = translate_deepl(translator_deepl, chunk, lang_data["code"])
                
                if err:
                    st.error(f"❌ {lang_name} 번역 실패: {err}")
                    error_occured = True
                    break
                # 번역 결과가 문자열로 오면 리스트화 (안전장치)
                if isinstance(res, str): res = [res]
                translated_lines.extend(res)
            
            if not error_occured:
                temp_subs = pysrt.SubRipFile()
                for idx, t_text in enumerate(translated_lines):
                    if idx >= len(subs): break
                    new_item = pysrt.SubRipItem(
                        index=idx + 1, 
                        start=subs[idx].start, 
                        end=subs[idx].end, 
                        text=str(t_text).strip()
                    )
                    temp_subs.append(new_item)
                
                file_ext = "sbv" if file_type == "sbv" else "srt"
                filename = f"{lang_name} 자막.{file_ext}" # 한글 파일명 적용
                
                # 표준 규격 조립: 블록 간 빈 줄(\n\n) 유지
                if file_type == "sbv":
                    content = to_sbv_format(temp_subs)
                else:
                    # str(item)은 pysrt에서 index\nTime\nText\n 형태를 반환함
                    content = "\n".join([str(item) for item in temp_subs])
                
                zip_file.writestr(filename, content)
            
            sub_progress.progress((i + 1) / len(TARGET_LANGUAGES))
            
        progress_text.success("✅ 모든 언어 번역 완료!")
    return zip_buffer.getvalue()

# --- [Main UI] ---

try:
    if "YOUTUBE_API_KEY" in st.secrets and "DEEPL_API_KEY" in st.secrets:
        YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
        DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
        translator_deepl = deepl.Translator(DEEPL_API_KEY)
        translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
        st.sidebar.success("✅ API 인증 성공")
    else:
        st.error("❌ Streamlit Cloud의 Secrets 설정이 필요합니다.")
        st.stop()
except Exception as e:
    st.error(f"❌ 초기화 오류: {e}")
    st.stop()

st.title("📚 허슬플레이 자동 번역기 (Vr.260226-PRO)")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []
if 'clean_id' not in st.session_state: st.session_state.clean_id = ""

# Task 1: 영상 정보 번역
st.header("1. 영상 제목 및 설명란 번역")
v_input = st.text_input("YouTube ID 또는 URL", key="yt_url_input", placeholder="ID를 입력하거나 URL을 붙여넣으세요.")

if st.button("1. 정보 가져오기"):
    if v_input:
        with st.spinner("YouTube 서버에서 정보를 가져오는 중..."):
            snippet, err = get_video_details(YOUTUBE_API_KEY, v_input)
            if err:
                st.error(f"데이터 로드 실패: {err}")
            else:
                st.session_state.video_details = snippet
                st.session_state.clean_id = extract_video_id(v_input)
                st.success("영상 정보 로드 완료")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.subheader("원본 데이터 확인")
    st.text_area("원본 제목", snippet['title'], height=70, disabled=True)
    st.text_area("원본 설명", snippet.get('description', ''), height=200, disabled=True)
    
    if st.button("2. 다국어 번역 실행 (Hybrid)"):
        st.session_state.translation_results = []
        progress_bar = st.progress(0)
        lines = snippet.get('description', '').split('\n')
        
        for idx, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            if lang_data["use_google"]:
                t_title, _ = translate_google(translator_google, snippet['title'], ui_key)
                t_desc_list, _ = translate_google(translator_google, lines, ui_key)
            else:
                t_title, _ = translate_deepl(translator_deepl, snippet['title'], lang_data["code"])
                t_desc_list, _ = translate_deepl(translator_deepl, lines, lang_data["code"])
            
            st.session_state.translation_results.append({
                "lang_name": lang_data["name"],
                "ui_key": ui_key,
                "title": t_title or "",
                "desc": "\n".join(t_desc_list) if t_desc_list else ""
            })
            progress_bar.progress((idx + 1) / len(TARGET_LANGUAGES))
        st.success("전체 언어 번역이 완료되었습니다!")

    if st.session_state.translation_results:
        st.subheader("번역 결과 및 수동 보정")
        for res in st.session_state.translation_results:
            with st.expander(f"📍 {res['lang_name']}"):
                col_t1, col_t2 = st.columns([8, 1])
                with col_t1: 
                    new_title = st.text_input("번역된 제목", res['title'], key=f"title_{res['ui_key']}")
                    t_len = len(new_title) # TypeError 해결: 초기값 보장
                    if t_len > 100: st.error(f"❌ 제목 길이 초과: {t_len}/100자")
                    elif t_len >= 95: st.warning(f"⚠️ 제한 임박: {t_len}/100자")
                with col_t2: copy_to_clipboard(new_title)
                
                col_d1, col_d2 = st.columns([8, 1])
                with col_d1: st.text_area("번역된 설명", res['desc'], key=f"desc_{res['ui_key']}", height=150)
                with col_d2: copy_to_clipboard(res['desc'])
        
        # --- [복구된 섹션] YouTube 일괄 업로드 (JSON) ---
        st.divider()
        st.header("3. YouTube 일괄 업로드 (JSON)")
        if st.button("🚀 업로드용 JSON 생성"):
            error_langs = []
            for res in st.session_state.translation_results:
                curr_title = st.session_state.get(f"title_{res['ui_key']}", res['title'])
                if len(curr_title) > 100:
                    error_langs.append(f"{res['lang_name']} ({len(curr_title)}자)")
            
            if error_langs:
                st.error("❌ 제목이 100자를 초과하는 언어가 있어 JSON을 생성할 수 없습니다.")
                st.write(", ".join(error_langs))
            else:
                json_body = generate_youtube_localizations_json(st.session_state.clean_id, st.session_state.translation_results)
                st.code(json_body, language="json")
                col_j1, col_j2 = st.columns([2, 8])
                with col_j1: copy_to_clipboard(json_body)
                with col_j2: st.info("복사한 JSON 코드를 YouTube API Explorer의 Request Body에 붙여넣으세요.")
                
                st.markdown("""
                ### **💡 일괄 업데이트 팁**
                1. 생성된 JSON 코드를 **Copy** 합니다.
                2. **[Google YouTube API Explorer](https://developers.google.com/youtube/v3/docs/videos/update?apix=true)** 페이지로 이동합니다.
                3. `part` 파라미터에 `localizations`를 입력합니다.
                4. `Request body` 칸에 복사한 코드를 붙여넣고 **Execute**를 실행하세요!
                """)

st.divider()

# Task 2 & 3: 한국어 -> 영어 번역
st.header("2. 한국어 자막 ▶ 영어 번역 (High Quality)")
col_a, col_b = st.columns(2)
with col_a: up_sbv_ko = st.file_uploader("한국어 .sbv 파일 업로드", type=['sbv'], key="ko_sbv_up")
with col_b: up_srt_ko = st.file_uploader("한국어 .srt 파일 업로드", type=['srt'], key="ko_srt_up")

if up_sbv_ko or up_srt_ko:
    if st.button("🇺🇸 고품질 영어 번역 시작"):
        f = up_sbv_ko if up_sbv_ko else up_srt_ko
        is_sbv = up_sbv_ko is not None
        content = f.read().decode("utf-8")
        subs = parse_sbv(content) if is_sbv else pysrt.from_string(content)
        
        with st.spinner("DeepL 문맥 분석 중..."):
            texts = [s.text for s in subs]
            translated, _ = translate_deepl(translator_deepl, texts, "EN-US")
            
            temp_subs = pysrt.SubRipFile()
            for i, t in enumerate(translated):
                new_item = pysrt.SubRipItem(index=i+1, start=subs[i].start, end=subs[i].end, text=str(t).strip())
                temp_subs.append(new_item)
            
            final_content = to_sbv_format(temp_subs) if is_sbv else "\n".join([str(s) for s in temp_subs])
            st.download_button("📥 영어 번역본 다운로드", final_content, file_name=f"영어 자막.{('sbv' if is_sbv else 'srt')}")

st.divider()

# Task 4 & 5: 영어 -> 다국어 번역 (Hybrid)
st.header("4. 영어 자막 ▶ 다국어 번역 (Hybrid)")
c1, c2 = st.columns(2)
with c1: up_sbv_multi = st.file_uploader("영어 .sbv 업로드", type=['sbv'], key="multi_sbv")
with c2: up_srt_multi = st.file_uploader("영어 .srt 업로드", type=['srt'], key="multi_srt")

if up_sbv_multi:
    if st.button("🚀 다국어 SBV 번역 및 ZIP 생성"):
        content = up_sbv_multi.read().decode("utf-8")
        subs = parse_sbv(content)
        if subs:
            zip_data = process_subtitle_translation(subs, file_type="sbv")
            st.download_button("📂 번역된 SBV ZIP 다운로드", zip_data, "다국어_SBV_자막.zip")

if up_srt_multi:
    if st.button("🚀 다국어 SRT 번역 및 ZIP 생성"):
        content = up_srt_multi.read().decode("utf-8")
        try:
            subs = pysrt.from_string(content)
            zip_data = process_subtitle_translation(subs, file_type="srt")
            st.download_button("📂 번역된 SRT ZIP 다운로드", zip_data, "다국어_SRT_자막.zip")
        except Exception as e: st.error(f"파일 처리 중 오류: {e}")
