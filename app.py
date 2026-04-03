import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from googleapiclient.discovery import build
import pysrt
import io
import zipfile
import pandas as pd
import json
import re 
import html 
from collections import OrderedDict
import time
import copy
import math
import requests
from pydub import AudioSegment
from pydub.effects import speedup

# --- Streamlit UI 설정 (페이지 탭 이름 변경) ---
st.set_page_config(page_title="허슬플레이 AI 번역 및 더빙 웹앱", layout="wide")

# --- 전역 세션 상태 (이어받기 캐시) 초기화 ---
if 'cache_multi_sbv' not in st.session_state: st.session_state.cache_multi_sbv = {}
if 'cache_multi_srt' not in st.session_state: st.session_state.cache_multi_srt = {}
if 'last_sbv_name' not in st.session_state: st.session_state.last_sbv_name = ""
if 'last_srt_name' not in st.session_state: st.session_state.last_srt_name = ""
if 'multi_sbv_zip' not in st.session_state: st.session_state.multi_sbv_zip = None
if 'multi_srt_zip' not in st.session_state: st.session_state.multi_srt_zip = None

# --- 지원 언어 목록 ---
TARGET_LANGUAGES = OrderedDict({
    "el": {"name": "그리스어", "code": "EL"},
    "nl": {"name": "네덜란드어", "code": "NL"},
    "no": {"name": "노르웨이어", "code": "NB"},
    "da": {"name": "덴마크어", "code": "DA"},
    "de": {"name": "독일어", "code": "DE"},
    "ru": {"name": "러시아어", "code": "RU"},
    "mr": {"name": "마라티어", "code": "MR"},
    "ms": {"name": "말레이어", "code": "MS"},
    "vi": {"name": "베트남어", "code": "VI"},
    "bn": {"name": "벵골어", "code": "BN"},
    "sv": {"name": "스웨덴어", "code": "SV"},
    "es": {"name": "스페인어", "code": "ES"},
    "sk": {"name": "슬로바키아어", "code": "SK"},
    "ar": {"name": "아랍어", "code": "AR"},
    "en-IE": {"name": "영어 (아일랜드)", "code": "EN-GB"}, 
    "en-GB": {"name": "영어 (영국)", "code": "EN-GB"},
    "en-AU": {"name": "영어 (호주)", "code": "EN-AU"},   
    "en-IN": {"name": "영어 (인도)", "code": "EN-GB"},   
    "en-CA": {"name": "영어 (캐나다)", "code": "EN-CA"},
    "ur": {"name": "우르두어", "code": "UR"},
    "uk": {"name": "우크라이나어", "code": "UK"},
    "it": {"name": "이탈리아어", "code": "IT"},
    "id": {"name": "인도네시아어", "code": "ID"},
    "ja": {"name": "일본어", "code": "JA"},
    "zh-CN": {"name": "중국어(간체)", "code": "ZH"},
    "zh-TW": {"name": "중국어(번체)", "code": "zh-TW"},
    "cs": {"name": "체코어", "code": "CS"},
    "ta": {"name": "타밀어", "code": "TA"},
    "th": {"name": "태국어", "code": "TH"},
    "te": {"name": "텔루구어", "code": "TE"},
    "tr": {"name": "튀르키예어", "code": "TR"},
    "pa": {"name": "펀잡어", "code": "PA"},
    "pt": {"name": "포르투갈어", "code": "PT-PT"},
    "pl": {"name": "폴란드어", "code": "PL"},
    "fr": {"name": "프랑스어", "code": "FR"},
    "fi": {"name": "핀란드어", "code": "FI"},
    "fil": {"name": "필리핀어", "code": "FIL"},
    "ko": {"name": "한국어", "code": "KO"},
    "hu": {"name": "헝가리어", "code": "HU"},
    "hi": {"name": "힌디어", "code": "HI"},
})

CHUNK_SIZE = 40

# --- ElevenLabs Voice ID 목록 ---
VOICE_OPTIONS = {
    "한국어(세모과)": "ruSJRhA64v8HAqiqKXVw",
    "영어(세모과)": "EkK5I93UQWFDigLMpZcX",
    "덴마크어, 네덜란드어, 스웨덴어, 독일어(세모과)": "ygiXC2Oa1BiHksD3WkJZ",
    "포르투갈어, 스페인어(세모과)": "4za2kOXGgUd57HRSQ1fn"
}

# --- 영어 압축 시스템 프롬프트 (마크다운 충돌 방지를 위해 백틱 대체) ---
COMPRESSION_PROMPT = """
### Role & Context
You are the **Chief Script Editor** for the 3-million-subscriber industrial documentary channel 'All process of world'.
Your mission is to optimize English subtitles for **Multi-Language Dubbing (German, French, etc.)**.

Target languages (like German) naturally expand in length by ~30%. Therefore, you must slightly tighten the English text to create "breathing room" for translators.
**HOWEVER**, you must strictly preserve the **documentary's narrative tone, descriptive richness, and audio density**.

### **CORE GOAL: "Smart Dubbing Optimization" (더빙 최적화)**
Do not strip the script to its bare bones. Instead, **"tighten the bolts."**
Your goal is to reduce the character count by **10% to 20%** (Smart Trim), NOT 50% (Hard Cut).
* **Avoid:** Creating "dead air" where the text becomes too short for the timestamp duration.
* **Aim for:** A smooth, professional flow that retains the original meaning and imagery but uses fewer syllables.

### **CRITICAL RULES (Strict Adherence)**

**1. STRICT TIMELINE INTEGRITY**
* **ONE-TO-ONE MAPPING:** Output the **EXACT SAME number of lines** as the input.
* **NO DELETION:** Never delete a subtitle block.
* **NO MERGING:** Keep original timestamps 100% intact.

**2. DURATION AWARENESS (Prevent Dead Air)**
* **Check the Duration:** Calculate the time difference (`End Time` - `Start Time`) for each line.
* **If a segment is LONG (e.g., > 4 seconds):**
    * **DO NOT SHORTEN AGGRESSIVELY.** The narrator needs enough text to fill the audio time naturally.
    * **Keep Adjectives:** Retain words like "kiln-fired," "guarding," "colossal" to maintain atmosphere.
* **If a segment is SHORT (e.g., < 2 seconds) and text is long:**
    * **SHORTEN AGGRESSIVELY.** This is where you need to create space.

**3. STRUCTURAL COMPRESSION (Priority Strategy)**
Use this order to shorten text instead of deleting words randomly:
* **Priority 1: Grammar Shift (A of B → B A)**
    * *Ex:* "The frames of wooden houses" → "The wooden frames" (Saves syllables, keeps meaning).
    * *Ex:* "Production of the factory" → "Factory production".
* **Priority 2: Trim "Functional" Fillers Only**
    * Remove: "basically," "actually," "in order to," "is designed to."
    * *Ex:* "It is designed to be used for cutting" → "It cuts".
* **Priority 3: Flavor Preservation**
    * **KEEP:** Adjectives that describe texture, mood, or quality.
    * **REMOVE:** Only if the sentence is *critically* too long for the timestamp.

### **Output Rules**

You must provide **TWO separate Code Blocks**.

**[Output 1: Master Subtitle File (For Sync)]**
* **Format:** Code Block (identifier: `srt` or `sbv`).
* **Content:** The optimized English text with **EXACT** original timestamps.

**[Output 2: Readable Script (For Review)]**
* **Format:** Plaintext Code Block (identifier: `txt`).
* **Content:** The optimized text merged into continuous sentences.

### **Comparison Example (Calibration)**

**[Input Raw]**
'''srt
115
00:08:51,597 --> 00:08:57,436
From kiln-fired bricks

116
00:08:57,436 --> 00:09:02,875
to concrete walls guarding the earth…

117
00:09:02,875 --> 00:09:06,712
…and the breathing frames of wooden houses.
'''

**[BAD Output (Over-Compressed - Do NOT do this)]**
'''srt
From bricks to concrete walls… …and wooden frames.
'''

**[GOOD Output (Target Standard)]**
'''srt
115
00:08:51,597 --> 00:08:57,436
From kiln-fired bricks

116
00:08:57,436 --> 00:09:02,875
to concrete walls guarding the earth…

117
00:09:02,875 --> 00:09:06,712
…and the breathing wooden frames.
'''
""".replace("'''", "`" * 3)

# --- 유틸리티: 복사 버튼 생성 컴포넌트 ---
def create_copy_button(text_to_copy, button_id):
    safe_id = re.sub(r'\W+', '_', button_id)
    escaped_text = json.dumps(text_to_copy or "")
    
    html_code = f"""
    <script>
    function copyText_{safe_id}() {{
        navigator.clipboard.writeText({escaped_text}).then(function() {{
            var btn = document.getElementById('btn_{safe_id}');
            btn.innerText = '✅ 복사완료';
            btn.style.backgroundColor = '#d4edda';
            setTimeout(() => {{
                btn.innerText = '📄 복사';
                btn.style.backgroundColor = '#f9f9f9';
            }}, 2000);
        }});
    }}
    </script>
    <button id="btn_{safe_id}" onclick="copyText_{safe_id}()" 
        style="width: 100%; height: 100%; cursor: pointer; padding: 10px; border-radius: 6px; 
               border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold; font-size: 14px;
               transition: all 0.2s;">📄 복사</button>
    """
    components.html(html_code, height=50)

# --- 오디오 프로세싱 함수 ---
def remove_silence(audio_segment, silence_thresh=-50.0):
    if len(audio_segment) == 0: return audio_segment
    start_trim = 0
    end_trim = len(audio_segment)
    for i in range(0, len(audio_segment), 10):
        if audio_segment[i:i+10].dBFS > silence_thresh:
            start_trim = i
            break
    for i in range(len(audio_segment)-10, 0, -10):
        if audio_segment[i:i+10].dBFS > silence_thresh:
            end_trim = i + 10
            break
    if start_trim >= end_trim: return audio_segment
    return audio_segment[start_trim:end_trim]

def match_target_duration(audio_segment, target_duration_ms):
    if len(audio_segment) > 0:
        audio_segment = remove_silence(audio_segment)
    
    current_duration_ms = len(audio_segment)
    if current_duration_ms == 0:
        return AudioSegment.silent(duration=int(target_duration_ms))
        
    if current_duration_ms > target_duration_ms:
        speed_factor = current_duration_ms / target_duration_ms
        try:
            refined_audio = speedup(audio_segment, playback_speed=speed_factor)
        except Exception:
            refined_audio = audio_segment
            
        if len(refined_audio) > target_duration_ms:
            refined_audio = refined_audio[:int(target_duration_ms)]
    else:
        refined_audio = audio_segment
        
    return refined_audio

# --- 문장 병합(Sentence Merging) 로직 ---
def merge_pysrt_items(subs):
    merged = []
    if not subs: return merged
    current_seg = None
    for sub in subs:
        start_ms = sub.start.ordinal
        end_ms = sub.end.ordinal
        text = sub.text.strip().replace('\n', ' ')
        
        if current_seg is None:
            current_seg = {'start_ms': start_ms, 'end_ms': end_ms, 'text': text}
        else:
            current_seg['text'] += " " + text
            current_seg['end_ms'] = end_ms
            
        if re.search(r'[.?!’”"]\s*$', current_seg['text']) or current_seg['text'].endswith('...'):
            merged.append(current_seg)
            current_seg = None
            
    if current_seg is not None:
        merged.append(current_seg)
    return merged

# --- SBV / SRT 파싱 함수 ---
@st.cache_data(show_spinner=False)
def parse_sbv(file_content):
    subs = pysrt.SubRipFile()
    lines = file_content.strip().replace('\r\n', '\n').split('\n\n')
    for i, block in enumerate(lines):
        if not block.strip(): continue
        parts = block.split('\n', 1)
        if len(parts) != 2: continue
        time_match = re.match(r'(\d+):(\d+):(\d+)\.(\d+),(\d+):(\d+):(\d+)\.(\d+)', parts[0].strip())
        if time_match:
            start_h, start_m, start_s, start_ms, end_h, end_m, end_s, end_ms = map(int, time_match.groups())
            sub = pysrt.SubRipItem()
            sub.index = i + 1
            sub.start.hours, sub.start.minutes, sub.start.seconds, sub.start.milliseconds = start_h, start_m, start_s, start_ms
            sub.end.hours, sub.end.minutes, sub.end.seconds, sub.end.milliseconds = end_h, end_m, end_s, end_ms
            sub.text = html.unescape(parts[1].strip())
            subs.append(sub)
    if not subs: return None, "SBV 파싱 오류: 유효한 시간/텍스트 블록을 찾을 수 없습니다."
    return subs, None

def to_sbv_format(subrip_file):
    sbv_output = []
    for sub in subrip_file:
        start_time = f"{sub.start.hours:02d}:{sub.start.minutes:02d}:{sub.start.seconds:02d}.{sub.start.milliseconds:03d}"
        end_time = f"{sub.end.hours:02d}:{sub.end.minutes:02d}:{sub.end.seconds:02d}.{sub.end.milliseconds:03d}"
        sbv_output.extend([f"{start_time},{end_time}", html.unescape(sub.text.strip()), ""])
    return "\n".join(sbv_output).strip()

@st.cache_data(show_spinner=False)
def parse_srt_native(file_content):
    try: return pysrt.from_string(file_content), None
    except Exception as e: return None, f"SRT 파싱 오류: {str(e)}"

def to_srt_format_native(subrip_file):
    for sub in subrip_file:
        sub.text = sub.text.strip()
    return "\n\n".join(str(sub).strip() for sub in subrip_file).strip()

@st.cache_data(show_spinner=False)
def get_video_details(api_key, video_id):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        if not response.get('items'): return None, "YouTube API 오류: 해당 ID의 영상을 찾을 수 없습니다."
        return response['items'][0]['snippet'], None
    except Exception as e:
        return None, f"YouTube API 오류: {str(e)}"

# --- Gemini API 번역 로직 (제목 번역 및 자막 번역 분리) ---
@st.cache_data(show_spinner=False)
def translate_gemini(text_data, target_lang_name, is_title=False):
    is_list = isinstance(text_data, list)
    
    if is_title:
        director_guidelines = """
        ROLE: You are an Expert Title Translator for high-end industrial, manufacturing, and cultural documentaries (e.g., BBC, National Geographic).
        
        CRITICAL TITLE TRANSLATION RULES:
        1. Contextual Analysis: Identify the specific industry/topic. ALWAYS prioritize authentic 'Industry Jargon' over literal words (e.g., instead of literally translating 'massive', use industry-appropriate nuances like 'colossal scale' or 'gigantic process').
        2. Meaning-Based & No Literal Translation: Translate the *core purpose* and *context*, not the dictionary definition (e.g., 'Junkyard' translates to the professional equivalent of 'Car Dismantling Facility' in the target language). Ensure zero "Translation-ese".
        3. Amplify Adjectives: Replace bland adjectives with the most powerful, impactful expressions available in the target language to highlight scale, speed, or rarity.
        4. Headline Impact & Conciseness: Eliminate unnecessary conjunctions and prepositions. Deliver a concise, striking headline.
        5. Tone of Formal Expertise: Avoid cheap clickbait. Maintain a tone of professional awe and trustworthiness, exactly as a major documentary broadcaster would format a title in the target country.
        """
    else:
        director_guidelines = """
        ROLE: You are an Expert Script Translator for professional industrial and craftsmanship documentaries (similar to the style of "How It's Made").
        
        CRITICAL TRANSLATION RULES:
        1. Factual & Professional: Translate with accurate, professional terminology. STRICTLY AVOID overly dramatic, poetic, or flowery language (e.g., do not use words like "Sacred Ritual" or "Alchemy"). Maintain the exact original meaning of the text without exaggeration.
        2. Natural Documentary Tone: Ensure the English sounds completely natural for a native-speaking audience watching a factual documentary. Use clear subject-verb structures, prefer active voice, and avoid convoluted relative clauses.
        3. NO Special Characters: STRICTLY PROHIBITED to use slashes (/), brackets ([ ]), or ellipses (...) to indicate pauses, pacing, or formatting. Use only standard, minimal grammatical punctuation (like periods and necessary commas).
        4. Technical Accuracy: Use correct industry terms naturally within the context (e.g., slip, bisque firing, casting, parting line). Translate '대표' as 'Founder' or 'Head' rather than a sterile 'CEO' in the context of craftsmanship, but keep the overall tone grounded and factual.
        """
    
    if is_list:
        json_payload = json.dumps(text_data, ensure_ascii=False)
        prompt = f"""{director_guidelines}
        TASK: Translate the following JSON array of strings into {target_lang_name} applying the CRITICAL TRANSLATION RULES.
        STRICT FORMATTING RULES:
        1. Return ONLY a valid JSON array of strings. No explanations, no markdown.
        2. The output array MUST have exactly {len(text_data)} items. Do not merge or split the array items themselves.
        3. Do NOT translate HTML tags.
        Input JSON:
        {json_payload}"""
    else:
        prompt = f"""{director_guidelines}
        TASK: Translate the following text into {target_lang_name} applying the CRITICAL TRANSLATION RULES.
        STRICT FORMATTING RULES:
        1. Preserve ALL original line breaks (newlines), empty lines, and formatting EXACTLY as they are. Do NOT combine separate lines.
        2. Do NOT translate timestamps (e.g., 00:00) or email addresses.
        3. Return ONLY the translated text without any markdown wrappers.
        Input text:
        {text_data}"""

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = gemini_model.generate_content(prompt)
            res_text = response.text.strip()
            if is_list:
                start_idx = res_text.find('[')
                end_idx = res_text.rfind(']')
                if start_idx != -1 and end_idx != -1:
                    res_text = res_text[start_idx:end_idx+1]
                else:
                    raise Exception("JSON 배열 기호를 찾을 수 없습니다.")
                translated_list = json.loads(res_text)
                if len(translated_list) != len(text_data):
                    raise Exception("배열 길이 불일치")
                return translated_list, None
            else:
                return res_text, None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt) 
                continue
            return None, f"Gemini 번역 실패: {str(e)}"

def to_text_docx_substitute(data_list, original_desc_input, video_id):
    output = io.StringIO()
    output.write("==================================================\n")
    output.write(f"YouTube 영상 제목 및 설명 번역 보고서\n영상 ID: {video_id}\n")
    output.write(f"생성 날짜: {pd.to_datetime('today').strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write("==================================================\n\n")
    for item in data_list:
        output.write("**************************************************\n")
        output.write(f"언어: {item['Language']} ({item['UI_Key']}) | 상태: {item['Status']}\n")
        output.write("**************************************************\n\n[ 제목 ]\n")
        output.write(f"{item['Title']}\n\n[ 설명 ]\n")
        output.write(item['Description'])
        output.write("\n\n")
    return output.getvalue().encode('utf-8')


st.title("허슬플레이 AI 번역 및 더빙 웹앱 v.260403")

try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"] 
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    youtube_client = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    st.success("✅ API 키 로드 완료. (Gemini API)")
except KeyError:
    st.error("❌ 'Secrets'에 YOUTUBE_API_KEY 또는 GEMINI_API_KEY가 없습니다.")
    st.stop()


# ==========================================================
# Task 1: 영상 제목 및 설명란 번역
# ==========================================================
st.header("영상 제목 및 설명란 번역")

def extract_video_id(url_or_id):
    url_or_id = url_or_id.strip()
    if len(url_or_id) == 11 and not url_or_id.startswith("http"): return url_or_id
    pattern = r'(?:v=|\/shorts\/|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url_or_id)
    if match: return match.group(1)
    fallback = r'(?:\/)([a-zA-Z0-9_-]{11})(?:[?&/]|$)'
    match_fb = re.search(fallback, url_or_id)
    return match_fb.group(1) if match_fb else url_or_id

video_id_input_raw = st.text_input("YouTube 동영상 URL 또는 동영상 ID 입력")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []
if 'clean_id' not in st.session_state: st.session_state.clean_id = ""

if st.button("1. 영상 정보 가져오기"):
    if video_id_input_raw:
        video_id = extract_video_id(video_id_input_raw)
        st.session_state.clean_id = video_id
        with st.spinner("가져오는 중..."):
            snippet, error = get_video_details(YOUTUBE_API_KEY, video_id)
            if error: st.error(error)
            else:
                st.session_state.video_details = snippet
                st.session_state.translation_results = []
                st.success(f"성공: \"{snippet['title']}\"")
    else: st.warning("ID 또는 URL을 입력하세요.")

if st.session_state.video_details:
    snippet = st.session_state.video_details
    st.text_area("원본 제목 (영어)", snippet['title'], height=50, disabled=True)
    original_desc_input = snippet['description']
    st.session_state.original_desc_input = original_desc_input 
    st.text_area("원본 설명 (영어)", original_desc_input, height=350, disabled=True) 

    if st.button("2. 전체 언어 번역 실행"):
        st.session_state.translation_results = []
        progress_bar = st.progress(0, text="전체 번역 진행 중...")
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            progress_bar.progress((i + 1) / len(TARGET_LANGUAGES), text=f"번역 중: {lang_name}")
            try:
                # 제목은 is_title=True 파라미터를 주입하여 '제목 전문 번역 가이드' 적용
                title_text, title_err = translate_gemini(snippet['title'], lang_name, is_title=True)
                # 설명란은 기존 다큐멘터리 스크립트 가이드 유지
                desc_text, desc_err = translate_gemini(original_desc_input, lang_name, is_title=False)
                time.sleep(1.5) 
                status = "실패" if (title_err or desc_err) else "성공"
                st.session_state.translation_results.append({
                    "lang_name": lang_name, "ui_key": ui_key, "api": "Gemini", "status": status,
                    "title": title_text if status=="성공" else f"오류: {title_err}",
                    "desc": desc_text if status=="성공" else f"오류: {desc_err}"
                })
            except Exception as e:
                st.session_state.translation_results.append({
                    "lang_name": lang_name, "ui_key": ui_key, "api": "Gemini", "status": "실패",
                    "title": f"시스템 오류: {str(e)}", "desc": f"시스템 오류: {str(e)}"
                })
        st.success("모든 언어 번역 완료! (줄바꿈 포맷 완벽 보존)")
        progress_bar.empty()

    if st.session_state.translation_results:
        st.subheader("번역 결과 검수 및 다운로드")
        excel_data_list = []
        for result_data in st.session_state.translation_results:
            ui_key, lang_name, status = result_data["ui_key"], result_data["lang_name"], result_data["status"]
            final_data_entry = {"Language": lang_name, "UI_Key": ui_key, "Engine": result_data["api"], "Status": status}
            with st.expander(f"**{lang_name}** ({status})", expanded=False):
                st.caption(f"언어코드: {ui_key}")
                c1, c2 = st.columns([9, 1])
                with c1:
                    corrected_title = st.text_area(f"제목", result_data["title"], height=68, key=f"t1_title_{ui_key}")
                    if len(corrected_title) > 100: st.error(f"⚠️ 경고: 제목 길이가 100자를 초과했습니다. (현재 {len(corrected_title)}자)")
                with c2:
                    st.write(" "); create_copy_button(corrected_title, f"title_{ui_key}")
                c3, c4 = st.columns([9, 1])
                with c3: corrected_desc = st.text_area(f"설명", result_data["desc"], height=250, key=f"t1_desc_{ui_key}")
                with c4:
                    st.write(" "); st.write(" "); st.write(" "); create_copy_button(corrected_desc, f"desc_{ui_key}")
                final_data_entry["Title"] = corrected_title; final_data_entry["Description"] = corrected_desc
            excel_data_list.append(final_data_entry)

        if excel_data_list:
            docx_sub_bytes = to_text_docx_substitute(excel_data_list, st.session_state.original_desc_input, st.session_state.clean_id)
            st.download_button("✅ 전체 결과 다운로드 (Word 보고서)", data=docx_sub_bytes, file_name=f"{st.session_state.clean_id}_translations.docx")
            st.markdown("---")
            st.subheader("🚀 YouTube 일괄 업로드 (JSON)")
            if st.button("🚀 JSON 데이터 생성"):
                localizations = {}
                for res in excel_data_list: 
                    if res['Status'] == '성공':
                        api_lang_code = 'tl' if res['UI_Key'] == 'fil' else res['UI_Key']
                        localizations[api_lang_code] = {"title": res['Title'], "description": res['Description']}
                json_body = json.dumps({"id": st.session_state.clean_id, "localizations": localizations}, indent=2, ensure_ascii=False)
                st.code(json_body, language="json")
                st.info("💡 위 코드 블록 우측 상단의 '복사' 아이콘을 클릭하여 전체 코드를 복사하세요.")


# ==========================================================
# Task 2: 영어 자막 번역
# ==========================================================
st.markdown("---")
st.header("영어 자막 번역")

c1, c2 = st.columns(2)

with c1:
    up_ko_sbv = st.file_uploader("한국어 SBV ▶ 영어 번역", type=['sbv'])
    if up_ko_sbv and st.button("KO SBV ➡ EN 시작"):
        try:
            subs_ko, err = parse_sbv(up_ko_sbv.getvalue().decode("utf-8"))
            if err: st.error(err)
            else:
                status_msg = st.empty()
                texts, trans = [s.text for s in subs_ko], []
                total_chunks = math.ceil(len(texts) / CHUNK_SIZE)
                for chunk_idx, i in enumerate(range(0, len(texts), CHUNK_SIZE)):
                    status_msg.info(f"⏳ 영어 번역 진행 중... (조각 {chunk_idx + 1}/{total_chunks})")
                    chunk, trans_err = translate_gemini(texts[i:i+CHUNK_SIZE], "English (US)")
                    if trans_err: raise Exception(trans_err)
                    trans.extend(chunk); time.sleep(1.5) 
                status_msg.empty()
                ts = copy.deepcopy(subs_ko)
                for j, s in enumerate(ts): s.text = trans[j].strip()
                st.download_button("✅ 영어 SBV 다운로드", to_sbv_format(ts).encode('utf-8'), "영어.sbv")
        except Exception as e: st.error(str(e))

with c2:
    up_ko_srt = st.file_uploader("한국어 SRT ▶ 영어 번역", type=['srt'])
    if up_ko_srt and st.button("KO SRT ➡ EN 시작"):
        try:
            subs_ko, err = parse_srt_native(up_ko_srt.getvalue().decode("utf-8"))
            if err: st.error(err)
            else:
                status_msg = st.empty()
                texts, trans = [s.text for s in subs_ko], []
                total_chunks = math.ceil(len(texts) / CHUNK_SIZE)
                for chunk_idx, i in enumerate(range(0, len(texts), CHUNK_SIZE)):
                    status_msg.info(f"⏳ 영어 번역 진행 중... (조각 {chunk_idx + 1}/{total_chunks})")
                    chunk, trans_err = translate_gemini(texts[i:i+CHUNK_SIZE], "English (US)")
                    if trans_err: raise Exception(trans_err)
                    trans.extend(chunk); time.sleep(1.5)
                status_msg.empty()
                ts = copy.deepcopy(subs_ko)
                for j, s in enumerate(ts): s.text = trans[j].strip()
                st.download_button("✅ 영어 SRT 다운로드", to_srt_format_native(ts).encode('utf-8'), "영어.srt")
        except Exception as e: st.error(str(e))


# ==========================================================
# Task 3: 영어 자막 압축
# ==========================================================
st.markdown("---")
st.header("영어 자막 압축")
st.info("💡 독일어, 프랑스어 등 길이가 길어지는 다국어 더빙을 위해 영어 자막의 길이를 원본 대비 10~20% 타이트하게 압축합니다.")

up_compress_file = st.file_uploader("압축할 영어 자막 파일 업로드 (SRT / SBV)", type=['srt', 'sbv'], key='compress_uploader')
if up_compress_file and st.button("🚀 영어 자막 압축 시작"):
    content = up_compress_file.getvalue().decode("utf-8")
    ext = up_compress_file.name.split('.')[-1].lower()
    
    with st.spinner("AI가 자막을 분석하고 최적화하는 중입니다... (약 1~2분 소요)"):
        try:
            bt = "`" * 3
            prompt = COMPRESSION_PROMPT + f"\n\n[Input Raw]\n{bt}{ext}\n{content}\n{bt}"
            
            response = gemini_model.generate_content(prompt)
            res_text = response.text
            
            srt_sbv_match = re.search(bt + r'(?:srt|sbv)\n(.*?)\n' + bt, res_text, re.DOTALL | re.IGNORECASE)
            txt_match = re.search(bt + r'txt\n(.*?)\n' + bt, res_text, re.DOTALL | re.IGNORECASE)
            
            compressed_sub = srt_sbv_match.group(1).strip() if srt_sbv_match else "⚠️ 오류: 자막 코드 블록 파싱 실패. 원본 응답을 확인하세요.\n\n" + res_text
            readable_script = txt_match.group(1).strip() if txt_match else "⚠️ 오류: 스크립트 텍스트 블록 파싱 실패."
            
            st.success("✅ 영어 자막 압축 및 읽기용 스크립트 생성이 완료되었습니다.")
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("압축된 자막 (For Sync)")
                st.text_area("결과", compressed_sub, height=300)
                st.download_button("📥 압축 자막 다운로드", compressed_sub.encode('utf-8'), up_compress_file.name.replace(f".{ext}", f"_compressed.{ext}"))
            with c2:
                st.subheader("읽기용 스크립트 (For Review)")
                st.text_area("결과", readable_script, height=300)
                st.download_button("📥 스크립트 다운로드", readable_script.encode('utf-8'), up_compress_file.name.replace(f".{ext}", "_script.txt"))
                
        except Exception as e:
            st.error(f"압축 처리 중 오류가 발생했습니다: {str(e)}")


# ==========================================================
# Task 4: 다국어 번역
# ==========================================================
st.markdown("---")
st.header("다국어 번역")

c1, c2 = st.columns(2)

with c1:
    up_en_sbv = st.file_uploader("영어 SBV ▶ 다국어 번역", type=['sbv'])
    if up_en_sbv:
        if st.session_state.last_sbv_name != up_en_sbv.name:
            st.session_state.cache_multi_sbv = {}; st.session_state.multi_sbv_zip = None; st.session_state.last_sbv_name = up_en_sbv.name
        if st.button("SBV 다국어 번역 시작 (중단 시 다시 누르면 이어서 진행)"):
            try:
                subs, err = parse_sbv(up_en_sbv.getvalue().decode("utf-8"))
                if err: st.error(err)
                else:
                    status_msg = st.empty()
                    texts = [s.text for s in subs]
                    total_chunks = math.ceil(len(texts) / CHUNK_SIZE)
                    prog = st.progress(len(st.session_state.cache_multi_sbv) / len(TARGET_LANGUAGES))
                    for i, (uk, ld) in enumerate(TARGET_LANGUAGES.items()):
                        lang_name = ld['name']
                        if lang_name in st.session_state.cache_multi_sbv:
                            prog.progress((i+1)/len(TARGET_LANGUAGES), text=f"전체 진행률: {i+1}/{len(TARGET_LANGUAGES)} (패스: {lang_name} 완료됨)"); continue
                        prog.progress((i+1)/len(TARGET_LANGUAGES), text=f"전체 진행률: {i+1}/{len(TARGET_LANGUAGES)} 언어 (현재: {lang_name})")
                        trans = []
                        try:
                            for chunk_idx, j in enumerate(range(0, len(texts), CHUNK_SIZE)):
                                status_msg.info(f"⏳ {lang_name} 번역 중... (조각 {chunk_idx + 1}/{total_chunks})")
                                chunk, e = translate_gemini(texts[j:j+CHUNK_SIZE], lang_name)
                                if e: trans.extend(["오류"]*len(texts[j:j+CHUNK_SIZE])); st.toast(f"{lang_name} 일부 구간 오류 발생", icon="⚠️")
                                else: trans.extend(chunk)
                                time.sleep(1.5)
                            ts = copy.deepcopy(subs)
                            for k, s in enumerate(ts): s.text = trans[k].strip() if k < len(trans) else s.text.strip()
                            st.session_state.cache_multi_sbv[lang_name] = to_sbv_format(ts).encode('utf-8')
                        except Exception as lang_err: st.warning(f"{lang_name} 예외 발생: {str(lang_err)}"); continue
                    
                    status_msg.info("📦 결과물 압축 파일을 생성하고 있습니다...")
                    zb = io.BytesIO()
                    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED, False) as zf:
                        for lname, lcontent in st.session_state.cache_multi_sbv.items(): zf.writestr(f"{lname}.sbv", lcontent)
                    status_msg.empty(); prog.empty()
                    st.session_state.multi_sbv_zip = zb.getvalue()
                    st.success("🎉 다국어 번역 완료! 아래 버튼을 눌러 다운로드하세요.")
            except Exception as e: st.error(str(e))
        if st.session_state.multi_sbv_zip:
            st.download_button("✅ 다국어 SBV 다운로드 (ZIP)", st.session_state.multi_sbv_zip, "all_sbv.zip", "application/zip", key="dl_multi_sbv")
        elif st.session_state.cache_multi_sbv:
            zb_temp = io.BytesIO()
            with zipfile.ZipFile(zb_temp, "w", zipfile.ZIP_DEFLATED, False) as zf:
                for lname, lcontent in st.session_state.cache_multi_sbv.items(): zf.writestr(f"{lname}.sbv", lcontent)
            st.download_button(f"⚠️ 중간 저장본 다운로드 ({len(st.session_state.cache_multi_sbv)}개 언어)", zb_temp.getvalue(), "partial_sbv.zip", "application/zip", key="dl_partial_sbv")

with c2:
    up_en_srt = st.file_uploader("영어 SRT ▶ 다국어 번역", type=['srt'])
    if up_en_srt:
        if st.session_state.last_srt_name != up_en_srt.name:
            st.session_state.cache_multi_srt = {}; st.session_state.multi_srt_zip = None; st.session_state.last_srt_name = up_en_srt.name
        if st.button("SRT 다국어 번역 시작 (중단 시 다시 누르면 이어서 진행)"):
            try:
                subs, err = parse_srt_native(up_en_srt.getvalue().decode("utf-8"))
                if err: st.error(err)
                else:
                    status_msg = st.empty()
                    texts = [s.text for s in subs]
                    total_chunks = math.ceil(len(texts) / CHUNK_SIZE)
                    prog = st.progress(len(st.session_state.cache_multi_srt) / len(TARGET_LANGUAGES))
                    for i, (uk, ld) in enumerate(TARGET_LANGUAGES.items()):
                        lang_name = ld['name']
                        if lang_name in st.session_state.cache_multi_srt:
                            prog.progress((i+1)/len(TARGET_LANGUAGES), text=f"전체 진행률: {i+1}/{len(TARGET_LANGUAGES)} (패스: {lang_name} 완료됨)"); continue
                        prog.progress((i+1)/len(TARGET_LANGUAGES), text=f"전체 진행률: {i+1}/{len(TARGET_LANGUAGES)} 언어 (현재: {lang_name})")
                        trans = []
                        try:
                            for chunk_idx, j in enumerate(range(0, len(texts), CHUNK_SIZE)):
                                status_msg.info(f"⏳ {lang_name} 번역 중... (조각 {chunk_idx + 1}/{total_chunks})")
                                chunk, e = translate_gemini(texts[j:j+CHUNK_SIZE], lang_name)
                                if e: trans.extend(["오류"]*len(texts[j:j+CHUNK_SIZE])); st.toast(f"{lang_name} 일부 구간 오류 발생", icon="⚠️")
                                else: trans.extend(chunk)
                                time.sleep(1.5) 
                            ts = copy.deepcopy(subs)
                            for k, s in enumerate(ts): s.text = trans[k].strip() if k < len(trans) else s.text.strip()
                            st.session_state.cache_multi_srt[lang_name] = to_srt_format_native(ts).encode('utf-8')
                        except Exception as lang_err: st.warning(f"{lang_name} 예외 발생: {str(lang_err)}"); continue
                    
                    status_msg.info("📦 결과물 압축 파일을 생성하고 있습니다...")
                    zb = io.BytesIO()
                    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED, False) as zf:
                        for lname, lcontent in st.session_state.cache_multi_srt.items(): zf.writestr(f"{lname}.srt", lcontent)
                    status_msg.empty(); prog.empty()
                    st.session_state.multi_srt_zip = zb.getvalue()
                    st.success("🎉 다국어 번역 완료! 아래 버튼을 눌러 다운로드하세요.")
            except Exception as e: st.error(str(e))
        if st.session_state.multi_srt_zip:
            st.download_button("✅ 다국어 SRT 다운로드 (ZIP)", st.session_state.multi_srt_zip, "all_srt.zip", "application/zip", key="dl_multi_srt")
        elif st.session_state.cache_multi_srt:
            zb_temp = io.BytesIO()
            with zipfile.ZipFile(zb_temp, "w", zipfile.ZIP_DEFLATED, False) as zf:
                for lname, lcontent in st.session_state.cache_multi_srt.items(): zf.writestr(f"{lname}.srt", lcontent)
            st.download_button(f"⚠️ 중간 저장본 다운로드 ({len(st.session_state.cache_multi_srt)}개 언어)", zb_temp.getvalue(), "partial_srt.zip", "application/zip", key="dl_partial_srt")


# ==========================================================
# Task 5: AI 더빙 생성 (ElevenLabs)
# ==========================================================
st.markdown("---")
st.header("AI 더빙 생성 (ElevenLabs)")

elevenlabs_api_key = st.secrets.get("ELEVENLABS_API_KEY", "")

c1, c2 = st.columns([1, 2])
with c1:
    selected_voice_label = st.selectbox("🎙️ AI 성우 (Voice ID) 선택", list(VOICE_OPTIONS.keys()))
    selected_voice_id = VOICE_OPTIONS[selected_voice_label]

    if not elevenlabs_api_key:
        elevenlabs_api_key = st.text_input("🔑 ElevenLabs API Key 입력", type="password")
        st.caption("Secrets에 키가 등록되어 있지 않아 수동 입력이 필요합니다.")

with c2:
    up_dub_srt = st.file_uploader("더빙할 SRT 파일 업로드 (1개 한정)", type=['srt'], key='dub_srt')
    if up_dub_srt and st.button("🚀 AI 더빙 오디오 생성 시작 (WAV)"):
        if not elevenlabs_api_key:
            st.error("ElevenLabs API Key를 입력해주십시오.")
            st.stop()
            
        try:
            subs, err = parse_srt_native(up_dub_srt.getvalue().decode("utf-8"))
            if err: raise Exception(err)
            
            merged_segments = merge_pysrt_items(subs)
            if not merged_segments:
                raise Exception("SRT에서 유효한 텍스트를 찾을 수 없습니다.")

            total_duration_ms = merged_segments[-1]['end_ms'] + 5000 
            final_audio = AudioSegment.silent(duration=total_duration_ms)
            
            status_msg = st.empty()
            prog = st.progress(0)
            
            for i, seg in enumerate(merged_segments):
                status_msg.info(f"⏳ 더빙 음성 생성 및 동기화 중... ({i+1}/{len(merged_segments)})")
                
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{selected_voice_id}"
                headers = {
                    "xi-api-key": elevenlabs_api_key,
                    "Content-Type": "application/json"
                }
                data = {
                    "text": seg['text'],
                    "model_id": "eleven_multilingual_v2",
                }
                
                res = requests.post(url, json=data, headers=headers)
                if res.status_code == 200:
                    seg_audio = AudioSegment.from_file(io.BytesIO(res.content), format="mp3")
                    seg_audio = remove_silence(seg_audio)
                    
                    target_duration = seg['end_ms'] - seg['start_ms']
                    seg_audio = match_target_duration(seg_audio, target_duration)
                    final_audio = final_audio.overlay(seg_audio, position=seg['start_ms'])
                else:
                    st.warning(f"API 호출 실패 (구간 {i+1}): {res.text}")
                    
                prog.progress((i+1)/len(merged_segments))
                
            status_msg.success("🎉 AI 더빙 오디오(WAV) 생성 및 싱크 조절이 완료되었습니다!")
            prog.empty()
            
            wav_io = io.BytesIO()
            final_audio.export(wav_io, format="wav")
            wav_name = up_dub_srt.name.replace('.srt', '_dubbed.wav')
            
            st.download_button("✅ 최종 더빙 오디오 다운로드 (WAV)", wav_io.getvalue(), wav_name, "audio/wav")
            
        except Exception as e:
            st.error(f"오류 발생: {str(e)}")
