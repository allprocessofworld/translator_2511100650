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
import asyncio
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
    "en-US": {"name": "영어 (미국)", "code": "EN-US"},
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

# --- 영어 압축 시스템 프롬프트 ---
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
"""

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
        
    # [핵심 로직] 현재 오디오 길이가 허용된 최대 길이(target_duration_ms)를 초과할 경우에만 배속 처리
    if current_duration_ms > target_duration_ms:
        speed_factor = current_duration_ms / target_duration_ms
        try:
            # 자연스러운 배속 처리를 위해 chunk_size와 crossfade 파라미터 최적화
            refined_audio = speedup(audio_segment, playback_speed=speed_factor, chunk_size=30, crossfade=15)
        except Exception:
            refined_audio = audio_segment
            
        # 배속 처리 후에도 길이가 미세하게 길다면 강제 커팅하여 절대 침범 불가 상태로 만듦
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

# --- Gemini API 비동기(Async) 번역 로직 ---
async def translate_gemini_async(text_data, target_lang_name, is_title=False, semaphore=None):
    if semaphore:
        async with semaphore:
            return await _call_gemini_async(text_data, target_lang_name, is_title)
    return await _call_gemini_async(text_data, target_lang_name, is_title)

async def _call_gemini_async(text_data, target_lang_name, is_title):
    is_list = isinstance(text_data, list)
    
    if is_title:
        director_guidelines = """
        ROLE: You are an Expert Literal Translator for documentary titles. Your singular goal is absolute fidelity to the source text without any creative adaptation.
        
        CRITICAL TITLE TRANSLATION RULES:
        1. Fidelity First (원문 충실도 최우선): Translate the exact words and structural meaning present in the source. Do NOT add missing adjectives, do NOT exaggerate meanings, and do NOT creatively rewrite (e.g., do not change "Motorcycle Tires" to "Colossal Manufacturing").
        2. Preserve Structure (문장 구조 보존): Maintain the original word order, phrase boundaries, and punctuation (especially the pipe separator '|'). 
           - Always translate "How..." structures into the target language's equivalent of "How [subject] [verb]" (e.g., "어떻게 ~하는지", "Πώς...").
           - Always translate idiomatic tags like "Start to Finish" literally (e.g., "처음부터 끝까지", "Από την αρχή έως το τέλος").
        3. Strict Consistency (일관된 번역 원칙 적용): Apply this exact mechanical, literal translation approach uniformly across all target languages. Do not try to make it sound like a local marketing headline.

        EXAMPLES OF EXPECTED TRANSLATION STYLE (Strictly Follow This Pattern):
        [Source English] How a Factory Mass Produces Motorcycle Tires from Raw Rubber | Start to Finish
        [Target Greek] Πώς ένα εργοστάσιο μαζικής παραγωγής ελαστικών μοτοσικλέτας από ακατέργαστο καουτσούκ | Από την αρχή έως το τέλος
        [Target Korean] 공장에서 원료 고무로 오토바이 타이어를 대량 생산하는 과정 | 처음부터 끝까지
        [Target Hindi] कैसे एक फैक्ट्री कच्चे रबर से मोटरसाइकिल टायर बड़े पैमाने पर बनाती है | शुरू से आखिर तक
        [Target Indonesian] Bagaimana Sebuah Pabrik Memproduksi Ban Motor Secara Massal dari Karet Mentah | Dari Awal Hingga Akhir
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
        prompt = f"""{director_guidelines}\nTASK: Translate the following JSON array of strings into {target_lang_name} applying the CRITICAL TRANSLATION RULES.\nSTRICT FORMATTING RULES:\n1. Return ONLY a valid JSON array of strings. No explanations, no markdown.\n2. The output array MUST have exactly {len(text_data)} items. Do not merge or split the array items themselves.\n3. Do NOT translate HTML tags.\nInput JSON:\n{json_payload}"""
    else:
        prompt = f"""{director_guidelines}\nTASK: Translate the following text into {target_lang_name} applying the CRITICAL TRANSLATION RULES.\nSTRICT FORMATTING RULES:\n1. Preserve ALL original line breaks (newlines), empty lines, and formatting EXACTLY as they are. Do NOT combine separate lines.\n2. Do NOT translate timestamps (e.g., 00:00) or email addresses.\n3. Return ONLY the translated text without any markdown wrappers.\nInput text:\n{text_data}"""

    max_retries = 5
    base_delay = 2
    for attempt in range(max_retries):
        try:
            response = await gemini_model.generate_content_async(prompt)
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
            if "429" in str(e) or attempt < max_retries - 1:
                await asyncio.sleep(base_delay ** attempt) 
                continue
            return None, f"Gemini 비동기 번역 실패: {str(e)}"

# --- 동기 번역 래퍼 (기존 코드 호환 유지용) ---
@st.cache_data(show_spinner=False)
def translate_gemini(text_data, target_lang_name, is_title=False):
    return asyncio.run(_call_gemini_async(text_data, target_lang_name, is_title))


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


st.title("허슬플레이 AI 번역 및 더빙 웹앱 v.260520")

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
        progress_bar = st.progress(0, text="전체 번역 진행 중... (병렬 처리)")
        
        async def run_task1():
            semaphore = asyncio.Semaphore(5) # API Rate Limit 방어를 위해 동시 실행 5개로 제한
            results = []
            completed = 0
            
            async def process_lang(ui_key, lang_name):
                if lang_name.startswith("영어"):
                    return {"lang_name": lang_name, "ui_key": ui_key, "api": "Gemini", "status": "성공", "title": snippet['title'], "desc": original_desc_input, "order": list(TARGET_LANGUAGES.keys()).index(ui_key)}
                
                title_text, title_err = await translate_gemini_async(snippet['title'], lang_name, is_title=True, semaphore=semaphore)
                desc_text, desc_err = await translate_gemini_async(original_desc_input, lang_name, is_title=False, semaphore=semaphore)
                
                if title_text:
                    title_text = title_text.replace('\n', ' ').replace('\r', '').strip()

                status = "실패" if (title_err or desc_err) else "성공"
                return {
                    "lang_name": lang_name, "ui_key": ui_key, "api": "Gemini", "status": status,
                    "title": title_text if status=="성공" else f"오류: {title_err}",
                    "desc": desc_text if status=="성공" else f"오류: {desc_err}",
                    "order": list(TARGET_LANGUAGES.keys()).index(ui_key)
                }

            tasks = [process_lang(ui_key, lang_data["name"]) for ui_key, lang_data in TARGET_LANGUAGES.items()]
            
            for f in asyncio.as_completed(tasks):
                res = await f
                results.append(res)
                completed += 1
                progress_bar.progress(completed / len(TARGET_LANGUAGES), text=f"번역 진행 중: {completed}/{len(TARGET_LANGUAGES)} 완료")
            
            # 원래 UI Key 순서대로 정렬
            return sorted(results, key=lambda x: x["order"])

        with st.spinner("🚀 비동기 병렬 번역을 실행합니다. 잠시만 기다려주세요..."):
            sorted_results = asyncio.run(run_task1())
            
            # order 키 제거 및 상태 저장
            for res in sorted_results:
                del res["order"]
                st.session_state.translation_results.append(res)
                
        st.success("모든 언어 번역 완료! (비동기 병렬 처리 적용됨)")
        progress_bar.empty()

    if st.session_state.translation_results:
        st.subheader("번역 결과 검수 및 다운로드")
        excel_data_list = []
        for result_data in st.session_state.translation_results:
            ui_key, lang_name, status = result_data["ui_key"], result_data["lang_name"], result_data["status"]
            final_data_entry = {"Language": lang_name, "UI_Key": ui_key, "Engine": result_data["api"], "Status": status}
            
            # 3. 아코디언이 기본적으로 항상 펼쳐져 있도록 설정 (expanded=True)
            with st.expander(f"**{lang_name}** ({status})", expanded=True):
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
                
                # --- 복구된 안내 가이드 ---
                st.markdown("""
                ### **🚀 일괄 업데이트 적용 가이드 (방법 1)**
                *채널 소유자에게 '편집자' 권한을 부여받은 후 아래 절차를 진행하십시오.*
                
                1. 위 생성된 JSON 코드를 **복사**합니다.
                2. **👉 [Google YouTube API Explorer (클릭 시 새 창 이동)](https://developers.google.com/youtube/v3/docs/videos/update?apix=true)** 에 접속합니다.
                3. 우측 탭의 **`part`** 입력란에 **`localizations`** 라고 적습니다.
                4. **`Request body`** 영역 안쪽을 클릭하고, 복사한 JSON 코드를 그대로 붙여넣습니다.
                5. 하단의 파란색 **[Execute]** 버튼을 클릭하면 수십 개국 다국어 데이터가 즉시 덮어씌워집니다!
                """)


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
        if st.button("SBV 다국어 번역 시작 (비동기 병렬 처리)"):
            try:
                subs, err = parse_sbv(up_en_sbv.getvalue().decode("utf-8"))
                if err: st.error(err)
                else:
                    texts = [s.text for s in subs]
                    total_chunks = math.ceil(len(texts) / CHUNK_SIZE)
                    prog = st.progress(len(st.session_state.cache_multi_sbv) / len(TARGET_LANGUAGES))
                    status_msg = st.empty()
                    
                    async def run_task4_sbv():
                        semaphore = asyncio.Semaphore(5)
                        completed = len(st.session_state.cache_multi_sbv)
                        
                        async def process_lang(lang_name):
                            if lang_name in st.session_state.cache_multi_sbv:
                                return lang_name, None
                            trans = []
                            for j in range(0, len(texts), CHUNK_SIZE):
                                chunk, e = await translate_gemini_async(texts[j:j+CHUNK_SIZE], lang_name, is_title=False, semaphore=semaphore)
                                if e: 
                                    trans.extend(["오류"]*len(texts[j:j+CHUNK_SIZE]))
                                else: 
                                    trans.extend(chunk)
                                await asyncio.sleep(0.5) 
                            
                            ts = copy.deepcopy(subs)
                            for k, s in enumerate(ts): s.text = trans[k].strip() if k < len(trans) else s.text.strip()
                            return lang_name, to_sbv_format(ts).encode('utf-8')

                        tasks = [process_lang(ld['name']) for uk, ld in TARGET_LANGUAGES.items()]
                        
                        for f in asyncio.as_completed(tasks):
                            lang_name, encoded_content = await f
                            if encoded_content:
                                st.session_state.cache_multi_sbv[lang_name] = encoded_content
                                completed += 1
                                prog.progress(completed / len(TARGET_LANGUAGES), text=f"전체 진행률: {completed}/{len(TARGET_LANGUAGES)} 언어 완료 ({lang_name})")
                                
                    status_msg.info("⏳ 비동기 병렬 번역 진행 중... (43개 언어를 동시에 처리합니다)")
                    asyncio.run(run_task4_sbv())
                    
                    status_msg.info("📦 결과물 압축 파일을 생성하고 있습니다...")
                    zb = io.BytesIO()
                    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED, False) as zf:
                        for lname, lcontent in st.session_state.cache_multi_sbv.items(): zf.writestr(f"{lname}.sbv", lcontent)
                    status_msg.empty(); prog.empty()
                    st.session_state.multi_sbv_zip = zb.getvalue()
                    st.success("🎉 다국어 병렬 번역 완료! 아래 버튼을 눌러 다운로드하세요.")
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
        if st.button("SRT 다국어 번역 시작 (비동기 병렬 처리)"):
            try:
                subs, err = parse_srt_native(up_en_srt.getvalue().decode("utf-8"))
                if err: st.error(err)
                else:
                    texts = [s.text for s in subs]
                    total_chunks = math.ceil(len(texts) / CHUNK_SIZE)
                    prog = st.progress(len(st.session_state.cache_multi_srt) / len(TARGET_LANGUAGES))
                    status_msg = st.empty()

                    async def run_task4_srt():
                        semaphore = asyncio.Semaphore(5)
                        completed = len(st.session_state.cache_multi_srt)
                        
                        async def process_lang(lang_name):
                            if lang_name in st.session_state.cache_multi_srt:
                                return lang_name, None
                            trans = []
                            for j in range(0, len(texts), CHUNK_SIZE):
                                chunk, e = await translate_gemini_async(texts[j:j+CHUNK_SIZE], lang_name, is_title=False, semaphore=semaphore)
                                if e: 
                                    trans.extend(["오류"]*len(texts[j:j+CHUNK_SIZE]))
                                else: 
                                    trans.extend(chunk)
                                await asyncio.sleep(0.5)
                            
                            ts = copy.deepcopy(subs)
                            for k, s in enumerate(ts): s.text = trans[k].strip() if k < len(trans) else s.text.strip()
                            return lang_name, to_srt_format_native(ts).encode('utf-8')

                        tasks = [process_lang(ld['name']) for uk, ld in TARGET_LANGUAGES.items()]
                        
                        for f in asyncio.as_completed(tasks):
                            lang_name, encoded_content = await f
                            if encoded_content:
                                st.session_state.cache_multi_srt[lang_name] = encoded_content
                                completed += 1
                                prog.progress(completed / len(TARGET_LANGUAGES), text=f"전체 진행률: {completed}/{len(TARGET_LANGUAGES)} 언어 완료 ({lang_name})")

                    status_msg.info("⏳ 비동기 병렬 번역 진행 중... (43개 언어를 동시에 처리합니다)")
                    asyncio.run(run_task4_srt())
                    
                    status_msg.info("📦 결과물 압축 파일을 생성하고 있습니다...")
                    zb = io.BytesIO()
                    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED, False) as zf:
                        for lname, lcontent in st.session_state.cache_multi_srt.items(): zf.writestr(f"{lname}.srt", lcontent)
                    status_msg.empty(); prog.empty()
                    st.session_state.multi_srt_zip = zb.getvalue()
                    st.success("🎉 다국어 병렬 번역 완료! 아래 버튼을 눌러 다운로드하세요.")
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
    selected_voice_id = st.text_input("🎙️ AI 성우 (Voice ID) 입력", placeholder="예: ruSJRhA64v8HAqiqKXVw")

    if not elevenlabs_api_key:
        elevenlabs_api_key = st.text_input("🔑 ElevenLabs API Key 입력", type="password")
        st.caption("Secrets에 키가 등록되어 있지 않아 수동 입력이 필요합니다.")

with c2:
    up_dub_srt = st.file_uploader("더빙할 SRT 파일 업로드 (1개 한정)", type=['srt'], key='dub_srt')
    if up_dub_srt and st.button("🚀 AI 더빙 및 정밀 싱크 오디오 생성 시작 (WAV)"):
        if not elevenlabs_api_key:
            st.error("ElevenLabs API Key를 입력해주십시오.")
            st.stop()
        if not selected_voice_id.strip():
            st.error("Voice ID를 입력해주십시오.")
            st.stop()
            
        try:
            subs, err = parse_srt_native(up_dub_srt.getvalue().decode("utf-8"))
            if err: raise Exception(err)
            
            # [오류 해결 핵심] merge_pysrt_items() 사용 전면 중지!
            # 원본 SRT의 start_ms 타임코드를 1:1 절대 앵커(Anchor)로 보존하여 싱크 밀림 원천 차단
            merged_segments = []
            for sub in subs:
                merged_segments.append({
                    'start_ms': sub.start.ordinal,
                    'end_ms': sub.end.ordinal,
                    'text': sub.text.strip().replace('\n', ' ')
                })
                
            if not merged_segments:
                raise Exception("SRT에서 유효한 텍스트를 찾을 수 없습니다.")

            status_msg = st.empty()
            
            # --- 1단계: 타임코드 기반 대본 스마트 축약 (AI Script Optimization) ---
            status_msg.info("⏳ 1단계: 타임코드 밀도 분석 및 AI 대본 스마트 축약 진행 중...")
            
            sim_segs = []
            for i, s in enumerate(merged_segments):
                # 앞문장과 뒷문장 사이의 절대 허용 시간(max_duration_ms) 계산 (겹침 방지)
                if i < len(merged_segments) - 1:
                    max_duration_ms = merged_segments[i+1]['start_ms'] - s['start_ms'] - 50
                else:
                    max_duration_ms = s['end_ms'] - s['start_ms'] + 2000
                max_duration_ms = max(max_duration_ms, 500) # 최소 0.5초 보장
                s['max_duration_ms'] = max_duration_ms
                
                sim_segs.append({
                    "text": s['text'],
                    "max_sec": round(max_duration_ms / 1000.0, 1)
                })
            
            async def build_optimized_script():
                semaphore = asyncio.Semaphore(5)
                async def fetch_optimization(chunk, idx):
                    prompt = f"""
ROLE: Expert Audio Director & Script Editor
TASK: Review the following subtitle segments for a voiceover dubbing.
Each segment has a 'text' and a 'max_sec' (maximum allowed duration in seconds).
A professional voice actor speaks about 10~12 Korean characters per second.
If the text is too long for the given time limit, you MUST naturally condense and rewrite it while preserving the core meaning.
If the text easily fits within the time limit, KEEP IT EXACTLY as the original.
CRITICAL RULES:
1. Output ONLY a valid JSON array of strings containing the final text for each segment.
2. The output array MUST have exactly {len(chunk)} items.
3. DO NOT change the timestamp. Just provide the optimized string.

[EXAMPLE]
Input: [{{"text": "우리 돈으로 1조 원을 넘긴 것으로 알려졌죠.", "max_sec": 1.3}}, {{"text": "그 결혼식 한 번에 들어간 돈이", "max_sec": 2.5}}]
Output: ["1조 원을 넘겼습니다.", "그 결혼식 한 번에 들어간 돈이"]

INPUT (JSON): {json.dumps(chunk, ensure_ascii=False)}
"""
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            async with semaphore:
                                response = await gemini_model.generate_content_async(prompt)
                            res_text = response.text.strip()
                            start_idx = res_text.find('[')
                            end_idx = res_text.rfind(']')
                            if start_idx != -1 and end_idx != -1:
                                res_text = res_text[start_idx:end_idx+1]
                            arr = json.loads(res_text)
                            if len(arr) != len(chunk):
                                raise Exception("Array length mismatch")
                            return idx, arr
                        except Exception as e:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            return idx, [c['text'] for c in chunk] # 실패 시 안전하게 원문 유지

                tasks = []
                for i in range(0, len(sim_segs), CHUNK_SIZE):
                    tasks.append(fetch_optimization(sim_segs[i:i+CHUNK_SIZE], i))
                
                results = await asyncio.gather(*tasks)
                results.sort(key=lambda x: x[0])
                
                final_texts = []
                for r in results:
                    final_texts.extend(r[1])
                return final_texts

            # 비동기 LLM 대본 압축 실행
            optimized_texts = run_async_safely(build_optimized_script())
            
            # 원본 자막 객체(subs)와 병합 객체(merged_segments) 모두에 최적화된 텍스트 적용 (타임코드 유지)
            subs_optimized = copy.deepcopy(subs)
            for i, txt in enumerate(optimized_texts):
                merged_segments[i]['optimized_text'] = txt
                subs_optimized[i].text = txt
            
            st.success("✅ 타임코드 밀도 분석 및 대본 스마트 축약 완료!")
            with st.expander("📝 원본 대비 개선된 대본 비교 보기 (클릭하여 펼치기)", expanded=True):
                df_compare = pd.DataFrame({
                    "허용 시간(초)": [s['max_sec'] for s in sim_segs],
                    "원본 대본": [s['text'] for s in sim_segs],
                    "축약/개선된 대본": optimized_texts
                })
                st.dataframe(df_compare, use_container_width=True)


            # --- 2단계: API 통신 및 물리적 침범 방지(No Invasion) 싱크 적용 ---
            total_duration_ms = merged_segments[-1]['end_ms'] + 5000 
            final_audio = AudioSegment.silent(duration=total_duration_ms)
            
            prog = st.progress(0)
            
            for i, seg in enumerate(merged_segments):
                status_msg.info(f"⏳ 2단계: 오디오 생성 및 '침범 방지' 정밀 싱크 적용 중... ({i+1}/{len(merged_segments)})")
                
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{selected_voice_id}"
                headers = {
                    "xi-api-key": elevenlabs_api_key,
                    "Content-Type": "application/json"
                }
                data = {
                    # [핵심] 원문 대신 스마트 축약된 텍스트(optimized_text)를 API에 전달
                    "text": seg['optimized_text'], 
                    "model_id": "eleven_multilingual_v2",
                }
                
                res = requests.post(url, json=data, headers=headers)
                if res.status_code == 200:
                    seg_audio = AudioSegment.from_file(io.BytesIO(res.content), format="mp3")
                    seg_audio = remove_silence(seg_audio)
                    
                    max_duration = seg['max_duration_ms']
                        
                    # 생성된 오디오가 최대 허용 길이(max_duration)를 초과하면 match_target_duration 안에서 자동으로 'speedup' 물리적 강제 압축 실행 (최후의 보루)
                    seg_audio = match_target_duration(seg_audio, max_duration)
                    
                    # [수정 3] Pydub 합성 시 객체 누적 방지 및 메모리 강제 반환 (OOM 완전 차단)
                    temp_audio = final_audio 
                    final_audio = temp_audio.overlay(seg_audio, position=seg['start_ms'])
                    
                    # 메모리 해제
                    del temp_audio 
                    del seg_audio
                    gc.collect() 
                    
                else:
                    st.warning(f"API 호출 실패 (구간 {i+1}): {res.text}")
                    
                prog.progress((i+1)/len(merged_segments))
                
            status_msg.success("🎉 AI 더빙 오디오(WAV) 및 개선된 SRT 자막 파일 생성이 완료되었습니다!")
            prog.empty()
            
            wav_io = io.BytesIO()
            final_audio.export(wav_io, format="wav")
            wav_name = up_dub_srt.name.replace('.srt', '_dubbed_synced.wav')
            srt_name = up_dub_srt.name.replace('.srt', '_optimized.srt')
            
            # --- 다운로드 버튼 (2개의 산출물 제공) ---
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button("🎵 최종 더빙 오디오 다운로드 (WAV)", wav_io.getvalue(), wav_name, "audio/wav", use_container_width=True)
            with col_d2:
                # 타임코드는 원본(subs)과 동일하게 1:1 보존된 SRT 파일
                st.download_button("💬 축약/개선된 자막 다운로드 (SRT)", to_srt_format_native(subs_optimized).encode('utf-8'), srt_name, "text/plain", use_container_width=True)
            
        except Exception as e:
            st.error(f"오류 발생: {str(e)}")
