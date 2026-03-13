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
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

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

CHUNK_SIZE = 40

# --- 유틸리티: 복사 버튼 생성 컴포넌트 ---
def create_copy_button(text_to_copy, button_id):
    escaped_text = json.dumps(text_to_copy or "")
    html_code = f"""
    <script>
    function copyText_{button_id}() {{
        navigator.clipboard.writeText({escaped_text}).then(function() {{
            var btn = document.getElementById('btn_{button_id}');
            btn.innerText = '✅ 복사완료';
            btn.style.backgroundColor = '#d4edda';
            setTimeout(() => {{
                btn.innerText = '📄 복사';
                btn.style.backgroundColor = '#f9f9f9';
            }}, 2000);
        }});
    }}
    </script>
    <button id="btn_{button_id}" onclick="copyText_{button_id}()" 
        style="width: 100%; height: 100%; cursor: pointer; padding: 10px; border-radius: 6px; 
               border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold; font-size: 14px;
               transition: all 0.2s;">📄 복사</button>
    """
    components.html(html_code, height=50)

# --- SBV / SRT 파싱 함수 ---
@st.cache_data(show_spinner=False)
def parse_sbv(file_content):
    subs = pysrt.SubRipFile()
    lines = file_content.strip().replace('\r\n', '\n').split('\n\n')
    for i, block in enumerate(lines):
        if not block.strip(): continue
        parts = block.split('\n', 1)
        if len(parts) != 2: continue
        time_match = re.match(r'(\d+):(\d+):(\d+)\.(\d+),(\d+):(\d+):(\d+)\.(\d+)', time_str.strip() if (time_str := parts[0]) else "")
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
    return subrip_file.to_string(encoding='utf-8')

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

# --- Gemini API 번역 로직 개선 (Single String / Array 분기 처리) ---
@st.cache_data(show_spinner=False)
def translate_gemini(text_data, target_lang_name):
    try:
        is_list = isinstance(text_data, list)
        if is_list:
            json_payload = json.dumps(text_data, ensure_ascii=False)
            prompt = f"""
            You are a professional translator. Translate the following JSON array of strings into {target_lang_name}.
            CRITICAL RULES:
            1. Maintain the EXACT SAME array length.
            2. Do NOT translate HTML tags.
            3. Return ONLY a valid JSON array of strings.
            Input JSON: {json_payload}
            """
        else:
            # 설명란처럼 전체 통문자열이 들어올 때 줄바꿈 유지 강제 프롬프트
            prompt = f"""You are a professional translator. Translate the following text into {target_lang_name}.
            CRITICAL RULES:
            1. Preserve ALL original line breaks (newlines), empty lines, and formatting EXACTLY as they are. Do NOT combine lines.
            2. Do NOT translate timestamps (e.g., 00:00) or email addresses.
            3. Return ONLY the translated text without any markdown wrappers.
            
            Input text:
            {text_data}
            """

        response = gemini_model.generate_content(prompt)
        res_text = response.text.strip()

        if is_list:
            res_text = res_text.removeprefix('```json').removesuffix('```').removeprefix('```').strip()
            translated_list = json.loads(res_text)
            if len(translated_list) != len(text_data):
                raise Exception(f"싱크 오류: 배열 길이 불일치")
            return translated_list, None
        else:
            return res_text, None
            
    except Exception as e:
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


# --- Streamlit UI 설정 ---
st.set_page_config(layout="wide")
st.title("허슬플레이 자동 번역기 (Gemini AI + UI 개선)")

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
video_id_input = st.text_input("YouTube 동영상 URL의 동영상 ID 입력")

if 'video_details' not in st.session_state: st.session_state.video_details = None
if 'translation_results' not in st.session_state: st.session_state.translation_results = []

if st.button("1. 영상 정보 가져오기"):
    if video_id_input:
        with st.spinner("가져오는 중..."):
            snippet, error = get_video_details(YOUTUBE_API_KEY, video_id_input)
            if error: st.error(error)
            else:
                st.session_state.video_details = snippet
                st.session_state.translation_results = []
                st.success(f"성공: \"{snippet['title']}\"")
    else: st.warning("ID를 입력하세요.")

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
            
            # [핵심 변경] 설명란을 리스트로 쪼개지 않고 통째로 넘겨서 줄바꿈 강제 유지
            title_text, title_err = translate_gemini(snippet['title'], lang_name)
            desc_text, desc_err = translate_gemini(original_desc_input, lang_name)
            time.sleep(1.5) # API 429 에러 방지용

            status = "실패" if (title_err or desc_err) else "성공"
            st.session_state.translation_results.append({
                "lang_name": lang_name, "ui_key": ui_key, "api": "Gemini", "status": status,
                "title": title_text if status=="성공" else f"오류: {title_err}",
                "desc": desc_text if status=="성공" else f"오류: {desc_err}"
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
                
                # [핵심 변경] 원클릭 복사 버튼 배치
                c1, c2 = st.columns([9, 1])
                with c1:
                    corrected_title = st.text_area(f"제목", result_data["title"], height=68, key=f"t1_title_{ui_key}")
                with c2:
                    st.write(" ") # 수직 여백
                    create_copy_button(corrected_title, f"title_{ui_key}")
                
                c3, c4 = st.columns([9, 1])
                with c3:
                    corrected_desc = st.text_area(f"설명", result_data["desc"], height=250, key=f"t1_desc_{ui_key}")
                with c4:
                    st.write(" ") # 수직 여백
                    st.write(" ")
                    st.write(" ")
                    create_copy_button(corrected_desc, f"desc_{ui_key}")
                
                final_data_entry["Title"] = corrected_title
                final_data_entry["Description"] = corrected_desc
            
            excel_data_list.append(final_data_entry)

        if excel_data_list:
            docx_sub_bytes = to_text_docx_substitute(excel_data_list, st.session_state.original_desc_input, video_id_input)
            st.download_button("✅ 전체 결과 다운로드 (Word 보고서)", data=docx_sub_bytes, file_name=f"{video_id_input}_translations.docx")

            # YouTube 자동 업로드 로직 유지
            st.markdown("---")
            if st.button("🚀 YouTube API로 자동 업로드 실행"):
                try:
                    with st.spinner("OAuth 2.0 인증 및 YouTube 업데이트 진행 중..."):
                        SCOPES = ['[https://www.googleapis.com/auth/youtube.force-ssl](https://www.googleapis.com/auth/youtube.force-ssl)']
                        creds = None
                        if os.path.exists('token.json'): creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                        if not creds or not creds.valid:
                            if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
                            else:
                                if not os.path.exists('client_secrets.json'):
                                    st.error("❌ 'client_secrets.json' 파일이 없습니다.")
                                    st.stop()
                                flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
                                creds = flow.run_local_server(port=0)
                            with open('token.json', 'w') as token: token.write(creds.to_json())

                        youtube_auth = build('youtube', 'v3', credentials=creds)
                        localizations = {}
                        for res in excel_data_list: 
                            if res['Status'] == '성공':
                                api_lang_code = 'tl' if res['UI_Key'] == 'fil' else res['UI_Key']
                                localizations[api_lang_code] = {"title": res['Title'], "description": res['Description']}

                        video_response = youtube_auth.videos().list(part='snippet,localizations', id=video_id_input).execute()
                        if not video_response['items']: st.error("❌ 영상을 찾을 수 없습니다.")
                        else:
                            video_data = video_response['items'][0]
                            existing_localizations = video_data.get('localizations', {})
                            existing_localizations.update(localizations)
                            youtube_auth.videos().update(
                                part='snippet,localizations',
                                body={"id": video_id_input, "snippet": video_data['snippet'], "localizations": existing_localizations}
                            ).execute()
                            st.success("🎉 성공적으로 자동 업데이트되었습니다!")
                except Exception as e: st.error(f"API 업데이트 실패: {str(e)}")

# ==========================================================
# Task 3/4/5: 자막 파일 번역 (유지됨)
# ==========================================================
st.header("자막 파일 번역 (SBV / SRT)")
c1, c2, c3 = st.columns(3)

with c1:
    up_ko_sbv = st.file_uploader("한국어 SBV ▶ 영어 번역", type=['sbv'])
    if up_ko_sbv and st.button("KO ➡ EN 시작"):
        try:
            subs_ko, err = parse_sbv(up_ko_sbv.getvalue().decode("utf-8"))
            if err: st.error(err)
            else:
                texts, trans = [s.text for s in subs_ko], []
                for i in range(0, len(texts), CHUNK_SIZE):
                    chunk, trans_err = translate_gemini(texts[i:i+CHUNK_SIZE], "English (US)")
                    if trans_err: raise Exception(trans_err)
                    trans.extend(chunk); time.sleep(1)
                for j, s in enumerate(subs_ko): s.text = trans[j]
                st.download_button("✅ 영어 SBV 다운로드", to_sbv_format(subs_ko).encode('utf-8'), "translated_en.sbv")
        except Exception as e: st.error(str(e))

with c2:
    up_en_sbv = st.file_uploader("영어 SBV ▶ 다국어 번역", type=['sbv'])
    if up_en_sbv and st.button("SBV 다국어 번역 시작"):
        try:
            subs, err = parse_sbv(up_en_sbv.getvalue().decode("utf-8"))
            if err: st.error(err)
            else:
                zb, prog = io.BytesIO(), st.progress(0)
                texts = [s.text for s in subs]
                with zipfile.ZipFile(zb, "a", zipfile.ZIP_DEFLATED, False) as zf:
                    for i, (uk, ld) in enumerate(TARGET_LANGUAGES.items()):
                        prog.progress((i+1)/len(TARGET_LANGUAGES), text=f"번역 중: {ld['name']}")
                        trans = []
                        for j in range(0, len(texts), CHUNK_SIZE):
                            chunk, e = translate_gemini(texts[j:j+CHUNK_SIZE], ld["name"])
                            if e: trans.extend(["오류"]*len(texts[j:j+CHUNK_SIZE]))
                            else: trans.extend(chunk)
                            time.sleep(1)
                        ts = subs[:]
                        for k, s in enumerate(ts): s.text = trans[k] if k < len(trans) else s.text
                        zf.writestr(f"{ld['name']}_{uk}.sbv", to_sbv_format(ts).encode('utf-8'))
                prog.empty()
                st.download_button("✅ 다국어 SBV 다운로드 (ZIP)", zb.getvalue(), "all_sbv.zip", "application/zip")
        except Exception as e: st.error(str(e))

with c3:
    up_en_srt = st.file_uploader("영어 SRT ▶ 다국어 번역", type=['srt'])
    if up_en_srt and st.button("SRT 다국어 번역 시작"):
        try:
            subs, err = parse_srt_native(up_en_srt.getvalue().decode("utf-8"))
            if err: st.error(err)
            else:
                zb, prog = io.BytesIO(), st.progress(0)
                texts = [s.text for s in subs]
                with zipfile.ZipFile(zb, "a", zipfile.ZIP_DEFLATED, False) as zf:
                    for i, (uk, ld) in enumerate(TARGET_LANGUAGES.items()):
                        prog.progress((i+1)/len(TARGET_LANGUAGES), text=f"번역 중: {ld['name']}")
                        trans = []
                        for j in range(0, len(texts), CHUNK_SIZE):
                            chunk, e = translate_gemini(texts[j:j+CHUNK_SIZE], ld["name"])
                            if e: trans.extend(["오류"]*len(texts[j:j+CHUNK_SIZE]))
                            else: trans.extend(chunk)
                            time.sleep(1)
                        ts = subs[:]
                        for k, s in enumerate(ts): s.text = trans[k] if k < len(trans) else s.text
                        zf.writestr(f"{ld['name']}_{uk}.srt", to_srt_format_native(ts).encode('utf-8'))
                prog.empty()
                st.download_button("✅ 다국어 SRT 다운로드 (ZIP)", zb.getvalue(), "all_srt.zip", "application/zip")
        except Exception as e: st.error(str(e))
