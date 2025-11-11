import streamlit as st
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

# --- DeepL 지원 언어 목록 (v7.0 유지) ---
TARGET_LANGUAGES = OrderedDict({
    # --- Standard Languages ---
    "no": {"name": "노르웨이어", "code": "NB", "is_beta": False},
    "da": {"name": "덴마크어", "code": "DA", "is_beta": False},
    "de": {"name": "독일어", "code": "DE", "is_beta": False},
    "ru": {"name": "러시아어", "code": "RU", "is_beta": False},
    "es": {"name": "스페인어", "code": "ES", "is_beta": False},
    "ar": {"name": "아랍어", "code": "AR", "is_beta": False},
    "uk": {"name": "우크라이나어", "code": "UK", "is_beta": False},
    "it": {"name": "이탈리아어", "code": "IT", "is_beta": False},
    "id": {"name": "인도네시아어", "code": "ID", "is_beta": False},
    "ja": {"name": "일본어", "code": "JA", "is_beta": False},
    "zh-CN": {"name": "중국어(간체)", "code": "ZH", "is_beta": False},
    "zh-TW": {"name": "중국어(번체)", "code": "zh-TW", "is_beta": False},
    "tr": {"name": "튀르키예어", "code": "TR", "is_beta": False},
    "pt": {"name": "포르투갈어", "code": "PT-PT", "is_beta": False},
    "fr": {"name": "프랑스어", "code": "FR", "is_beta": False},
    "ko": {"name": "한국어", "code": "KO", "is_beta": False},
    
    # --- Beta Languages (Pro Key & Flag Required) ---
    "mr": {"name": "마라티어", "code": "MR", "is_beta": True},
    "ms": {"name": "말레이어", "code": "MS", "is_beta": True},
    "vi": {"name": "베트남어", "code": "VI", "is_beta": True},
    "bn": {"name": "벵골어", "code": "BN", "is_beta": True},
    "ur": {"name": "우르두어", "code": "UR", "is_beta": True},
    "ta": {"name": "타밀어", "code": "TA", "is_beta": True},
    "th": {"name": "태국어", "code": "TH", "is_beta": True},
    "te": {"name": "텔루구어", "code": "TE", "is_beta": True},
    "hi": {"name": "힌디어", "code": "HI", "is_beta": True},
})

# --- SBV / SRT 처리 헬퍼 함수 (v7.5 유지) ---

@st.cache_data(show_spinner=False)
def translate_google(_google_translator, text, target_lang_code_ui, source_lang='en'):
    """Google Cloud Translation API를 호출하여 텍스트를 번역합니다."""
    try:
        result = _google_translator.translations().list(
            q=text,
            target=target_lang_code_ui,
            source=source_lang
        ).execute()
        
        if isinstance(text, list):
             return [html.unescape(item['translatedText']) for item in result['translations']], None
        else:
             return html.unescape(result['translations'][0]['translatedText']), None
            
    except Exception as e:
        return None, f"Google 실패: {str(e)}"

# [v7.9 수정 2] Word 다운로드 함수를 재정의하고, 포맷팅 로직 추가
def to_text_docx_substitute(data_list, original_desc_input, video_id):
    """
    검수 완료된 제목/설명을 Word 문서 스타일의 텍스트로 변환합니다.
    [v7.10 수정]: 원본 설명의 줄바꿈 패턴을 번역된 설명에 적용합니다.
    """
    output = io.StringIO()
    
    # 문서 헤더
    output.write("==================================================\n")
    output.write(f"YouTube 영상 제목 및 설명 번역 보고서\n")
    output.write(f"영상 ID: {video_id}\n")
    output.write(f"생성 날짜: {pd.to_datetime('today').strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write("==================================================\n\n")

    # 2. 번역 결과 섹션
    for item in data_list:
        output.write("**************************************************\n")
        output.write(f"언어: {item['Language']} ({item['UI_Key']})\n")
        output.write(f"번역 엔진: {item['Engine']} (상태: {item['Status']})\n")
        output.write("**************************************************\n")
        
        output.write("\n[ 제목 ]\n")
        output.write(f"{item['Title']}\n")
        
        output.write("\n[ 설명 ]\n")
        
        translated_desc_raw = item['Description']
        
        # [v7.10 수정됨] 번역 프로세스(line-by-line)에서 원본 줄바꿈이 유지되었으므로,
        # 불필요한 re.sub 포맷팅 로직을 제거하고 원본(번역된) 텍스트를 그대로 씁니다.
        output.write(translated_desc_raw)
        
        output.write("\n\n")
        
    return output.getvalue().encode('utf-8')

# [v7.1 수정] Excel 파일 생성을 위한 헬퍼 함수
def to_excel(df_data):
    """DataFrame 데이터를 Excel 파일(bytes)로 변환합니다."""
    output_buffer = io.BytesIO()
    df = pd.DataFrame(df_data)
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Translations')
    
    return output_buffer.getvalue()


# --- Streamlit UI ---

st.set_page_config(layout="wide")
st.title("허슬플레이 자동 번역기 (Vr.251111)")

# [v7.9] 경고 블럭 추가
st.info("❗ 사용 중, 오류 또는 개선 사항은 즉시 보고하세요.")
# [v7.11 수정 1] 경고 문구를 블럭 스타일로 변경
st.info("⚠️ 디플 번역 실패 시, 구글 번역으로 자동 대체하며, 구글 번역으로 자동 대체된 언어는 반드시 다시 검수하세요.")


# --- API 키 로드 (UI 숨김) ---
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"] 
    DEEPL_API_KEY = st.secrets["DEEPL_API_KEY"]
    translator_deepl = deepl.Translator(DEEPL_API_KEY)
    translator_google = build('translate', 'v2', developerKey=YOUTUBE_API_KEY)
    st.success("✅ API 키가 'Secrets'에서 성공적으로 로드되었습니다.")
except KeyError:
    st.error("❌ 'Secrets'에 YOUTUBE_API_KEY 또는 DEEPL_API_KEY가 설정되지 않았습니다.")
    st.info("💡 앱 설정(Settings) > Secrets에 API 키를 설정해야 합니다.")
    st.stop()


# [v7.10 수정 2] Task 1 헤더 변경
st.header("영상 제목 및 설명란 번역")
video_id_input = st.text_input("YouTube 동영상 URL의 동영상 ID 입력 (예: URL - https://youtu.be/JsoPqXPIrI0 ▶ 동영상 ID - JsoPqXPIrI0)")

if 'video_details' not in st.session_state:
    st.session_state.video_details = None
if 'translation_results' not in st.session_state:
    st.session_state.translation_results = []

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
        
        # [개선 사항] 원본 설명을 줄바꿈 기준으로 미리 분리
        original_desc_lines = snippet['description'].split('\n')
        
        for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
            lang_name = lang_data["name"]
            deepl_code = lang_data["code"]
            is_beta = lang_data["is_beta"]
            google_code = ui_key
            
            progress_bar.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
            
            result_data = {
                "lang_name": lang_name,
                "ui_key": ui_key,
                "is_beta": is_beta,
                "api": None,
                "status": "실패",
                "title": "",
                "desc": ""
            }

            # 제목 번역 (단일 텍스트)
            title_text, title_err = translate_deepl(translator_deepl, snippet['title'], deepl_code, is_beta)
            
            # [개선 사항] 설명 번역 (줄바꿈 리스트로 요청)
            translated_desc_lines, desc_err = translate_deepl(translator_deepl, original_desc_lines, deepl_code, is_beta)
            desc_text = '\n'.join(translated_desc_lines) if not desc_err else None

            if title_err or desc_err:
                st.warning(f"DeepL 실패 ({lang_name}). Google 번역으로 대체합니다. (오류: {title_err or desc_err})")
                
                # Google 제목 번역
                title_text_g, title_err_g = translate_google(translator_google, snippet['title'], google_code)
                
                # [개선 사항] Google 설명 번역 (줄바꿈 리스트로 요청)
                translated_desc_lines_g, desc_err_g = translate_google(translator_google, original_desc_lines, google_code)
                desc_text_g = '\n'.join(translated_desc_lines_g) if not desc_err_g else None

                if title_err_g or desc_err_g:
                    result_data["api"] = "Google"
                    result_data["status"] = "실패"
                    result_data["title"] = f"Google 번역 오류: {title_err_g}"
                    result_data["desc"] = f"Google 번역 오류: {desc_err_g}"
                else:
                    result_data["api"] = "Google"
                    result_data["status"] = "성공"
                    result_data["title"] = title_text_g
                    result_data["desc"] = desc_text_g
            else:
                result_data["api"] = "DeepL"
                result_data["status"] = "성공"
                result_data["title"] = title_text
                result_data["desc"] = desc_text

            st.session_state.translation_results.append(result_data)

        st.success("모든 언어 번역/대체 작업 완료!")
        progress_bar.empty()

    if st.session_state.translation_results:
        st.subheader("번역 결과")
        
        def highlight_google_engine(s):
            is_google = s['엔진'] == 'Google'
            color = '#ffe0e0' if is_google else '' 
            text_color = '#c00000' if is_google else ''
            
            return [f'background-color: {color}; color: {text_color}' for _ in s]

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
        ).apply(highlight_google_engine, axis=1)

        st.dataframe(
            styled_df, 
            column_order=["언어", "번역된 제목", "번역된 설명", "엔진", "상태"],
            use_container_width=True,
            height=900 
        )

        st.subheader("번역 결과 검수 및 다운로드")
        
        excel_data_list = []
        cols = st.columns(5)
        col_index = 0
        
        for result_data in st.session_state.translation_results:
            ui_key = result_data["ui_key"]
            lang_name = result_data["lang_name"]
            is_beta = result_data["is_beta"]
            status = result_data["status"]
            
            final_data_entry = {
                "Language": lang_name,
                "UI_Key": ui_key,
                "Title": result_data["title"],
                "Description": result_data["desc"],
                "Engine": result_data["api"],
                "Status": status
            }

            with cols[col_index]:
                with st.expander(f"**{lang_name}** (검수)", expanded=False):
                    
                    if status == "성공":
                        st.caption(f"번역 엔진: {result_data['api']}")
                    else:
                        st.caption(f"번역 엔진: {result_data['api']} (실패)")

                    original_title = result_data["title"]
                    original_desc = result_data["desc"]

                    corrected_title = st.text_area(f"제목 ({ui_key})", original_title, height=50, key=f"t1_title_{ui_key}")
                    corrected_desc = st.text_area(f"설명 ({ui_key})", original_desc, height=150, key=f"t1_desc_{ui_key}")
                    
                    final_data_entry["Title"] = corrected_title
                    final_data_entry["Description"] = corrected_desc
            
            col_index = (col_index + 1) % 5
            
            excel_data_list.append(final_data_entry)

        if excel_data_list:
            docx_sub_bytes = to_text_docx_substitute(excel_data_list, st.session_state.original_desc_input, video_id_input)
            
            st.download_button(
                label="✅ 검수 완료된 제목/설명 다운로드 (Word 문서 형식)",
                data=docx_sub_bytes,
                file_name=f"{video_id_input}_translations_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

# --- 신규: 한국어 SBV -> 영어 SBV 번역 섹션 ---
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
                    st.session_state.sbv_ko_to_en_result = None
                    st.session_state.sbv_ko_to_en_error = None
                    
                    texts_to_translate_ko = [sub.text for sub in subs_ko]
                    
                    try:
                        # 1. Try DeepL (Target "EN")
                        translated_texts_ko, translate_err = translate_deepl(translator_deepl, texts_to_translate_ko, "EN", is_beta=False)
                        
                        if translate_err:
                            st.warning(f"KO->EN DeepL 실패. Google로 대체합니다. (오류: {translate_err})")
                            # 2. Try Google (Target "en", Source "ko")
                            translated_texts_ko, translate_err = translate_google(translator_google, texts_to_translate_ko, "en", source_lang='ko')
                            if translate_err:
                                raise Exception(f"Google마저 실패: {translate_err}")

                        # Build the translated SBV
                        translated_subs_ko = subs_ko[:]
                        if isinstance(translated_texts_ko, list):
                            for j, sub in enumerate(translated_subs_ko):
                                sub.text = translated_texts_ko[j]
                        else:
                            translated_subs_ko[0].text = translated_texts_ko
                        
                        sbv_output_content_ko_en = to_sbv_format(translated_subs_ko)
                        st.session_state.sbv_ko_to_en_result = sbv_output_content_ko_en
                        st.success("✅ 한국어 ▶ 영어 번역 완료!")
                        
                    except Exception as e:
                        st.session_state.sbv_ko_to_en_error = f"KO->EN SBV 생성 실패: {str(e)}"
                        st.error(st.session_state.sbv_ko_to_en_error)

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .sbv 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")

if 'sbv_ko_to_en_result' in st.session_state and st.session_state.sbv_ko_to_en_result:
    st.download_button(
        label="✅ 번역된 영어 .sbv 파일 다운로드",
        data=st.session_state.sbv_ko_to_en_result.encode('utf-8'),
        file_name="translated_en.sbv",
        mime="text/plain"
    )

# [v7.11 수정 2] SBV 파일 업로드 문구 수정
st.header("영어 SBV 자막 파일 ▶ 다국어 번역")
uploaded_sbv_file = st.file_uploader("영어 .sbv 파일 업로드", type=['sbv'], key="sbv_uploader")

if uploaded_sbv_file:
    try:
        sbv_content = uploaded_sbv_file.getvalue().decode("utf-8")
        subs, parse_err = parse_sbv(sbv_content)
        
        if parse_err:
            st.error(parse_err)
        else:
            st.success(f"✅ .sbv 파일 로드 성공! (총 {len(subs)}개의 자막 감지)")
            
            if st.button("SBV 파일 번역 실행"):
                st.session_state.sbv_translations = {}
                st.session_state.sbv_errors = []
                srt_progress = st.progress(0, text="SBV 번역 진행 중...")
                total_langs = len(TARGET_LANGUAGES)
                texts_to_translate = [sub.text for sub in subs]
                
                for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
                    lang_name = lang_data["name"]
                    deepl_code = lang_data["code"]
                    is_beta = lang_data["is_beta"]
                    google_code = ui_key
                    
                    srt_progress.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
                    
                    try:
                        translated_texts = None
                        translated_texts, translate_err = translate_deepl(translator_deepl, texts_to_translate, deepl_code, is_beta)
                        
                        if translate_err:
                            st.warning(f"SBV DeepL 실패 ({lang_name}). Google로 대체합니다.")
                            translated_texts, translate_err = translate_google(translator_google, texts_to_translate, google_code)
                            if translate_err:
                                raise Exception(f"Google마저 실패: {translate_err}")

                        translated_subs = subs[:]
                        if isinstance(translated_texts, list):
                            for j, sub in enumerate(translated_subs):
                                sub.text = translated_texts[j]
                        else:
                            translated_subs[0].text = translated_texts
                        
                        sbv_output_content = to_sbv_format(translated_subs)
                        st.session_state.sbv_translations[ui_key] = sbv_output_content
                        
                    except Exception as e:
                        st.session_state.sbv_errors.append(f"SBV 생성 실패 ({lang_name}): {str(e)}")
                
                st.success("SBV 파일 번역 완료!")
                srt_progress.empty()
                if st.session_state.sbv_errors:
                    st.error("일부 SBV 번역 실패:")
                    for err in st.session_state.sbv_errors:
                        st.warning(err)

            if 'sbv_translations' in st.session_state and st.session_state.sbv_translations:
                st.subheader("번역된 .sbv 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.sbv_translations.items():
                        lang_name = TARGET_LANGUAGES[ui_key]["name"]
                        file_name = f"{lang_name}_{ui_key}.sbv" 
                        zip_file.writestr(file_name, content.encode('utf-8'))
                
                st.download_button(
                    label="✅ 번역된 .sbv 파일 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="all_sbv_subtitles.zip",
                    mime="application/zip"
                )
                st.markdown("---")
                cols = st.columns(5)
                col_index = 0
                for ui_key, lang_data in TARGET_LANGUAGES.items():
                    if ui_key in st.session_state.sbv_translations:
                        lang_name = lang_data["name"]
                        with cols[col_index]:
                            st.download_button(
                                label=f"{lang_name} (.sbv)", 
                                data=st.session_state.sbv_translations[ui_key].encode('utf-8'),
                                file_name=f"{lang_name}_{ui_key}.sbv",
                                mime="text/plain"
                            )
                        col_index = (col_index + 1) % 5

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .sbv 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")


# [v7.11 수정 3] SRT 파일 업로드 문구 수정
st.header("영어 SRT 자막 파일 ▶ 다국어 번역")
uploaded_srt_file = st.file_uploader("영어 .srt 파일 업로드", type=['srt'], key="srt_uploader")

if uploaded_srt_file:
    try:
        srt_content = uploaded_srt_file.getvalue().decode("utf-8")
        subs, parse_err = parse_srt_native(srt_content)
        
        if parse_err:
            st.error(parse_err)
        else:
            st.success(f"✅ .srt 파일 로드 성공! (총 {len(subs)}개의 자막 감지)")
            
            if st.button("SRT 파일 번역 실행"):
                st.session_state.srt_translations = {}
                st.session_state.srt_errors = []
                srt_progress = st.progress(0, text="SRT 번역 진행 중...")
                total_langs = len(TARGET_LANGUAGES)
                texts_to_translate = [sub.text for sub in subs]
                
                for i, (ui_key, lang_data) in enumerate(TARGET_LANGUAGES.items()):
                    lang_name = lang_data["name"]
                    deepl_code = lang_data["code"]
                    is_beta = lang_data["is_beta"]
                    google_code = ui_key
                    
                    srt_progress.progress((i + 1) / total_langs, text=f"번역 중: {lang_name}")
                    
                    try:
                        translated_texts = None
                        translated_texts, translate_err = translate_deepl(translator_deepl, texts_to_translate, deepl_code, is_beta)
                        
                        if translate_err:
                            st.warning(f"SRT DeepL 실패 ({lang_name}). Google로 대체합니다.")
                            translated_texts, translate_err = translate_google(translator_google, texts_to_translate, google_code)
                            if translate_err:
                                raise Exception(f"Google마저 실패: {translate_err}")

                        translated_subs = subs[:]
                        if isinstance(translated_texts, list):
                            for j, sub in enumerate(translated_subs):
                                sub.text = translated_texts[j]
                        else:
                            translated_subs[0].text = translated_texts
                        
                        srt_output_content = to_srt_format_native(translated_subs)
                        st.session_state.srt_translations[ui_key] = srt_output_content
                        
                    except Exception as e:
                        st.session_state.srt_errors.append(f"SRT 생성 실패 ({lang_name}): {str(e)}")
                
                st.success("SRT 파일 번역 완료!")
                srt_progress.empty()
                if st.session_state.srt_errors:
                    st.error("일부 SRT 번역 실패:")
                    for err in st.session_state.srt_errors:
                        st.warning(err)

            if 'srt_translations' in st.session_state and st.session_state.srt_translations:
                st.subheader("4. 번역된 .srt 파일 다운로드")
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for ui_key, content in st.session_state.srt_translations.items():
                        lang_name = TARGET_LANGUAGES[ui_key]["name"]
                        file_name = f"{lang_name}_{ui_key}.srt"
                        zip_file.writestr(file_name, content.encode('utf-8'))
                
                st.download_button(
                    label="✅ 번역된 .srt 파일 전체 다운로드 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="all_srt_subtitles.zip",
                    mime="application/zip"
                )
                st.markdown("---")
                cols = st.columns(5)
                col_index = 0
                for ui_key, lang_data in TARGET_LANGUAGES.items():
                    if ui_key in st.session_state.srt_translations:
                        lang_name = lang_data["name"]
                        with cols[col_index]:
                            st.download_button(
                                label=f"{lang_name} (.srt)", 
                                data=st.session_state.srt_translations[ui_key].encode('utf-8'),
                                file_name=f"{lang_name}_{ui_key}.srt",
                                mime="text/plain"
                            )
                        col_index = (col_index + 1) % 5

    except UnicodeDecodeError:
        st.error("❌ 파일 업로드 오류: .srt 파일이 'UTF-8' 인코딩이 아닌 것 같습니다. 파일을 UTF-8로 저장한 후 다시 업로드하세요.")
    except Exception as e:
        st.error(f"알 수 없는 오류 발생: {str(e)}")
