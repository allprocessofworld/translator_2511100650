import streamlit as st
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

# --- 지원 언어 목록 (Gemini 프롬프트에 전달하기 위해 언어명을 활용합니다) ---
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
    "tr": {"name": "튀르키예어", "code": "TR"},
    "ta": {"name": "타밀어", "code": "TA"},
    "th": {"name": "태국어", "code": "TH"},
    "te": {"name": "텔루구어", "code": "TE"},
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

# --- 번역 API 요청 시 분할 처리할 텍스트 줄 수 (Gemini 한도 고려) ---
CHUNK_SIZE = 40

# --- SBV / SRT 처리 헬퍼 함수 ---
@st.cache_data(show_spinner=False)
def parse_sbv(file_content):
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
            sub.start.hours, sub.start.minutes, sub.start.seconds, sub.start.milliseconds = start_h, start_m, start_s, start_ms
            sub.end.hours, sub.end.minutes, sub.end.seconds, sub.end.milliseconds = end_h, end_m, end_s, end_ms
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
        
        sbv_output.append(time_line)
        sbv_output.append(text_content)
        sbv_output.append("")
        
    return "\n".join(sbv_output).strip()

@st.cache_data(show_spinner=False)
def parse_srt_native(file_content):
    try:
        subs = pysrt.from_string(file_content)
        return subs, None
    except Exception as e:
        return None, f"SRT 파싱 오류: {str(e)}"

def to_srt_format_native(subrip_file):
    return subrip_file.to_string(encoding='utf-8')

# --- YouTube API ---
@st.cache_data(show_spinner=False)
def get_video_details(api_key, video_id):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        if not response.get('items'):
            return None, "YouTube API 오류: 해당 ID의 영상을 찾을 수 없습니다."
        return response['items'][0]['snippet'], None
    except Exception as e:
        return None, f"YouTube API 오류: {str(e)}"

# --- Gemini API Translation ---
@st.cache_data(show_spinner=False)
def translate_gemini(text_data, target_lang_name):
    """Gemini API를 활용한 범용 번역 함수 (List 1:1 매핑 보장)"""
    try:
        is_list = isinstance(text_data, list)
        
        if is_list:
            json_payload = json.dumps(text_data, ensure_ascii=False)
            prompt = f"""
            You are a professional translator. Translate the following JSON array of strings into {target_lang_name}.
            CRITICAL RULES:
            1. Maintain the EXACT SAME array length. Do not merge or split items.
            2. Do NOT translate HTML tags (like <i>, <b>) or formatting.
            3. Return ONLY a valid JSON array of strings. No markdown formatting like ```json, no explanations.
            
            Input JSON:
            {json_payload}
            """
        else:
            prompt = f"Translate the following text into {target_lang_name}. Do NOT translate HTML tags. Return ONLY the translated text.\n\n{text_data}"

        # Gemini API 호출
        response = gemini_model.generate_content(prompt)
        res_text = response.text.strip()

        if is_list:
            # LLM의 불필요한 마크다운 태그 제거
            res_text = res_text.removeprefix('```json').removesuffix('```').removeprefix('```').strip()
            translated_list = json.loads(res_text)
            
            if len(translated_list) != len(text_data):
                raise Exception(f"싱크 오류: 원본 {len(text_data)}줄 -> 번역 {len(translated_list)}줄 (Gemini가 배열 길이를 훼손함)")
            return translated_list, None
        else:
            return res_text, None
            
    except Exception as e:
        return None, f"Gemini 번역 실패: {str(e)}"

# --- DOCX 포맷팅 ---
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
        output.write(item['Description'])
        output.write("\n\n")
    return output.getvalue().encode('utf-8')


# --- Streamlit UI 설정 ---
st.set_page_config(layout="wide")
st.title("허슬플레이 자동 번역기 (Gemini AI 적용)")

st.info("❗ 사용 중, 오류 또는 개선 사항은 즉시 보고하세요.")
st.warning("⚠️ 현재 앱은 Gemini AI Studio 기반으로 작동합니다. 할당량 초과 시 일시적인 오류가 발생할 수 있습니다.")
st.info("⚠️ 최종적으로 유튜브 스튜디오에는 총 41개 언어가 업로드되어야 합니다.")

# --- API 키 로드 ---
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"] 
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    
    # Gemini API 초기화
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    
    youtube_client = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    st.success("✅ API 키가 성공적으로 로드되었습니다. (Gemini API 활성화 완료)")
except KeyError:
    st.error("❌ 'Secrets'에 YOUTUBE_API_KEY 또는 GEMINI_API_KEY가 설정되지 않았습니다.")
    st.stop()


# ==========================================================
# Task 1: 영상 제목 및 설명란 번역
# ==========================================================
st.header("영상 제목 및 설명란 번역")
video_id_input = st.text_input("YouTube 동영상 URL의 동영상 ID 입력")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []

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
        
        original_desc_lines = snippet['description'].split('\n')
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            progress_bar.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
            
            result_data = {
                "lang_name": lang_name, "ui_key": ui_key, 
                "api": "Gemini", "status": "실패", "title": "", "desc": ""
            }

            # 제목 번역
            title_text, title_err = translate_gemini(snippet['title'], lang_name)
            
            # 설명란 분할 번역
            translated_desc_lines = []
            desc_err = None
            try:
                for chunk_i in range(0, len(original_desc_lines), CHUNK_SIZE):
                    chunk = original_desc_lines[chunk_i:chunk_i + CHUNK_SIZE]
                    translated_chunk, err = translate_gemini(chunk, lang_name)
                    if err: raise Exception(err)
                    translated_desc_lines.extend(translated_chunk)
                    time.sleep(1) # API Rate Limit 방어용
                desc_text = '\n'.join(translated_desc_lines)
            except Exception as e:
                desc_err = e
                desc_text = None

            # 결과 저장
            if title_err or desc_err:
                result_data["status"] = "실패"
                result_data["title"] = f"오류: {title_err}"
                result_data["desc"] = f"오류: {desc_err}"
            else:
                result_data["status"] = "성공"
                result_data["title"] = title_text
                result_data["desc"] = desc_text

            st.session_state.translation_results.append(result_data)

        st.success("모든 언어 번역/대체 작업 완료!")
        progress_bar.empty()

    if st.session_state.translation_results:
        st.subheader("번역 결과")
        
        df_data = []
        for res in st.session_state.translation_results:
            df_data.append({
                "언어": res["lang_name"],
                "번역된 제목": res["title"],
                "번역된 설명": res["desc"],
                "엔진": res["api"],
                "상태": res["status"]
            })
        
        df = pd.DataFrame(df_data)
        
        styled_df = df.style.set_properties(
            subset=['번역된 설명', '번역된 제목'],
            **{'white-space': 'pre-wrap', 'min-width': '200px', 'text-align': 'left'}
        )

        st.dataframe(styled_df, column_order=["언어", "번역된 제목", "번역된 설명", "엔진", "상태"], use_container_width=True, height=900)

        st.subheader("번역 결과 검수 및 다운로드")
        excel_data_list = []
        cols = st.columns(5)
        col_index = 0
        
        for result_data in st.session_state.translation_results:
            ui_key, lang_name, status = result_data["ui_key"], result_data["lang_name"], result_data["status"]
            final_data_entry = {"Language": lang_name, "UI_Key": ui_key, "Engine": result_data["api"], "Status": status}

            with cols[col_index]:
                with st.expander(f"**{lang_name}** (검수)", expanded=False):
                    st.caption(f"상태: {status}")
                    corrected_title = st.text_area(f"제목 ({ui_key})", result_data["title"], height=50, key=f"t1_title_{ui_key}")
                    corrected_desc = st.text_area(f"설명 ({ui_key})", result_data["desc"], height=150, key=f"t1_desc_{ui_key}")
                    final_data_entry["Title"] = corrected_title
                    final_data_entry["Description"] = corrected_desc
            
            col_index = (col_index + 1) % 5
            excel_data_list.append(final_data_entry)

        if excel_data_list:
            docx_sub_bytes = to_text_docx_substitute(excel_data_list, st.session_state.original_desc_input, video_id_input)
            st.download_button(
                label="✅ 검수 완료된 제목/설명 다운로드 (Word 문서 형식)",
                data=docx_sub_bytes, file_name=f"{video_id_input}_translations_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )


# ==========================================================
# Task 3: 한국어 SBV 자막 파일 ▶ 영어 번역
# ==========================================================
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
                with st.spinner("한국어 ➡ 영어 번역 진행 중..."):
                    texts_to_translate_ko = [sub.text for sub in subs_ko]
                    translated_texts_ko = []
                    
                    try:
                        for i in range(0, len(texts_to_translate_ko), CHUNK_SIZE):
                            chunk = texts_to_translate_ko[i:i + CHUNK_SIZE]
                            translated_chunk, translate_err = translate_gemini(chunk, "English (US)")
                            
                            if translate_err: raise Exception(f"번역 실패: {translate_err}")
                            translated_texts_ko.extend(translated_chunk)
                            time.sleep(1) # API Rate Limit 방어용

                        translated_subs_ko = subs_ko[:]
                        for j, sub in enumerate(translated_subs_ko):
                            sub.text = translated_texts_ko[j]
                        
                        st.session_state.sbv_ko_to_en_result = to_sbv_format(translated_subs_ko)
                        st.success("✅ 한국어 ▶ 영어 번역 완료!")
                        
                    except Exception as e:
                        st.error(f"KO->EN SBV 생성 실패: {str(e)}")

    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")

if 'sbv_ko_to_en_result' in st.session_state and st.session_state.sbv_ko_to_en_result:
    st.download_button("✅ 번역된 영어 .sbv 파일 다운로드", data=st.session_state.sbv_ko_to_en_result.encode('utf-8'), file_name="translated_en.sbv", mime="text/plain")


# ==========================================================
# Task 4: 영어 SBV 자막 파일 ▶ 다국어 번역
# ==========================================================
st.header("영어 SBV 자막 파일 ▶ 다국어 번역")
uploaded_sbv_file = st.file_uploader("영어 .sbv 파일 업로드", type=['sbv'], key="sbv_uploader")

if uploaded_sbv_file:
    try:
        sbv_content = uploaded_sbv_file.getvalue().decode("utf-8")
        subs, parse_err = parse_sbv(sbv_content)
        
        if parse_err: st.error(parse_err)
        else:
            st.success(f"✅ .sbv 파일 로드 성공! (총 {len(subs)}개의 자막 감지)")
            
            if st.button("SBV 파일 번역 실행"):
                st.session_state.sbv_translations = {}
                st.session_state.sbv_errors = []
                srt_progress = st.progress(0, text="SBV 다국어 번역 진행 중...")
                texts_to_translate = [sub.text for sub in subs]
                
                for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
                    lang_name = lang_data["name"]
                    srt_progress.progress((i + 1) / len(TARGET_LANGUAGES), text=f"번역 중: {lang_name}")
                    
                    try:
                        translated_texts_list = []
                        for chunk_i in range(0, len(texts_to_translate), CHUNK_SIZE):
                            chunk = texts_to_translate[chunk_i:chunk_i + CHUNK_SIZE]
                            translated_chunk, translate_err = translate_gemini(chunk, lang_name)
                            if translate_err: raise Exception(translate_err)
                            translated_texts_list.extend(translated_chunk)
                            time.sleep(1)

                        translated_subs = subs[:]
                        for j, sub in enumerate(translated_subs):
                            sub.text = translated_texts_list[j]
                        
                        st.session_state.sbv_translations[ui_key] = to_sbv_format(translated_subs)
                        
                    except Exception as e:
                        st.session_state.sbv_errors.append(f"{lang_name} 실패: {str(e)}")
                
                st.success("SBV 파일 번역 완료!")
                srt_progress.empty()
                if st.session_state.sbv_errors:
                    st.error("일부 SBV 번역 실패:")
                    for err in st.session_state.sbv_errors: st.warning(err)

            if 'sbv_translations' in st.session_state and st.session_state.sbv_translations:
                st.subheader("번역된 .sbv 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.sbv_translations.items():
                        lang_name = TARGET_LANGUAGES[ui_key]["name"]
                        zip_file.writestr(f"{lang_name}_{ui_key}.sbv", content.encode('utf-8'))
                
                st.download_button("✅ 번역된 .sbv 파일 전체 다운로드 (ZIP)", data=zip_buffer.getvalue(), file_name="all_sbv_subtitles.zip", mime="application/zip")


# ==========================================================
# Task 5: 영어 SRT 자막 파일 ▶ 다국어 번역
# ==========================================================
st.header("영어 SRT 자막 파일 ▶ 다국어 번역")
uploaded_srt_file = st.file_uploader("영어 .srt 파일 업로드", type=['srt'], key="srt_uploader")

if uploaded_srt_file:
    try:
        srt_content = uploaded_srt_file.getvalue().decode("utf-8")
        subs, parse_err = parse_srt_native(srt_content)
        
        if parse_err: st.error(parse_err)
        else:
            st.success(f"✅ .srt 파일 로드 성공! (총 {len(subs)}개의 자막 감지)")
            
            if st.button("SRT 파일 번역 실행"):
                st.session_state.srt_translations = {}
                st.session_state.srt_errors = []
                srt_progress = st.progress(0, text="SRT 다국어 번역 진행 중...")
                texts_to_translate = [sub.text for sub in subs]
                
                for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
                    lang_name = lang_data["name"]
                    srt_progress.progress((i + 1) / len(TARGET_LANGUAGES), text=f"번역 중: {lang_name}")
                    
                    try:
                        translated_texts_list = []
                        for chunk_i in range(0, len(texts_to_translate), CHUNK_SIZE):
                            chunk = texts_to_translate[chunk_i:chunk_i + CHUNK_SIZE]
                            translated_chunk, translate_err = translate_gemini(chunk, lang_name)
                            if translate_err: raise Exception(translate_err)
                            translated_texts_list.extend(translated_chunk)
                            time.sleep(1)

                        translated_subs = subs[:]
                        for j, sub in enumerate(translated_subs):
                            sub.text = translated_texts_list[j]
                        
                        st.session_state.srt_translations[ui_key] = to_srt_format_native(translated_subs)
                        
                    except Exception as e:
                        st.session_state.srt_errors.append(f"{lang_name} 실패: {str(e)}")
                
                st.success("SRT 파일 번역 완료!")
                srt_progress.empty()
                if st.session_state.srt_errors:
                    st.error("일부 SRT 번역 실패:")
                    for err in st.session_state.srt_errors: st.warning(err)

            if 'srt_translations' in st.session_state and st.session_state.srt_translations:
                st.subheader("번역된 .srt 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.srt_translations.items():
                        lang_name = TARGET_LANGUAGES[ui_key]["name"]
                        zip_file.writestr(f"{lang_name}_{ui_key}.srt", content.encode('utf-8'))
                
                st.download_button("✅ 번역된 .srt 파일 전체 다운로드 (ZIP)", data=zip_buffer.getvalue(), file_name="all_srt_subtitles.zip", mime="application/zip")

    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")
