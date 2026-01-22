import streamlit as st
import re
from datetime import datetime, timedelta
import requests
import io
import gc
import zipfile
import concurrent.futures 
from pydub import AudioSegment

# --- 1. 기본 설정 및 함수 정의 ---

def parse_srt_time(time_str):
    """SRT 시간 문자열(00:00:00,000)을 밀리초(ms)로 변환"""
    time_str = time_str.replace(',', '.')
    t = datetime.strptime(time_str, "%H:%M:%S.%f")
    delta = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second, microseconds=t.microsecond)
    return delta.total_seconds() * 1000

def parse_srt(srt_content):
    """SRT 내용을 파싱하여 리스트로 반환"""
    srt_content = srt_content.replace("\r\n", "\n") 
    
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:(?!\d+\n).)*)', re.DOTALL)
    matches = pattern.findall(srt_content)
    
    parsed_data = []
    for idx, start, end, text in matches:
        start_ms = parse_srt_time(start)
        end_ms = parse_srt_time(end)
        duration_ms = end_ms - start_ms
        clean_text = text.strip().replace('\n', ' ')
        parsed_data.append({
            'index': int(idx),
            'start_ms': start_ms,
            'end_ms': end_ms,
            'duration_ms': duration_ms,
            'text': clean_text
        })
    return parsed_data

def generate_audio_task(params):
    """병렬 처리를 위한 개별 작업 함수 (API 호출)"""
    text, voice_id, api_key, segment_idx = params
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        if response.status_code == 200:
            return (segment_idx, response.content)
        else:
            return (segment_idx, None)
    except Exception as e:
        return (segment_idx, None)

def remove_silence(audio_segment, silence_thresh=-50.0):
    """오디오 앞뒤 무음 제거"""
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
    """오디오 싱크 맞추기"""
    if len(audio_segment) > 0:
        audio_segment = remove_silence(audio_segment)

    current_duration_ms = len(audio_segment)
    if current_duration_ms == 0:
        return AudioSegment.silent(duration=int(target_duration_ms))

    if current_duration_ms > target_duration_ms:
        speed_factor = current_duration_ms / target_duration_ms
        try:
            refined_audio = audio_segment.speedup(playback_speed=speed_factor)
        except Exception:
            refined_audio = audio_segment
        if len(refined_audio) > target_duration_ms:
            refined_audio = refined_audio[:int(target_duration_ms)]
    else:
        silence_duration = target_duration_ms - current_duration_ms
        silence = AudioSegment.silent(duration=int(silence_duration))
        refined_audio = audio_segment + silence
        
    return refined_audio

# --- 2. Streamlit 웹 앱 UI 구성 ---

st.set_page_config(page_title="장편 다큐용 일레븐랩스 (스마트 분할)", page_icon="⚡")
st.title("⚡ 장편 다큐용 일레븐랩스 (스마트 분할)")

st.warning("⚠ **고속 모드:** 처리 속도가 3~4배 빠릅니다. 반드시 **SRT 파일을 1개씩만** 업로드하세요.")
st.warning("⚠ 더빙 생성을 신중하게 결정하세요. (버튼을 누르면 즉시 비용이 차감됩니다.)")

with st.sidebar:
    st.header("설정 (Settings)")
    st.markdown("### 더빙 캐릭터의 Voice ID 입력")
    voice_id = st.text_input("voice_id_label", value="", label_visibility="collapsed")
    st.error("⚠ 목소리 캐릭터를 신중하게 입력하세요.")
    st.info("💡 Tip: 영어 원문을 20% 정도 짧게 압축해야 자연스럽습니다.")
    max_workers = st.slider("동시 처리 개수 (속도 조절)", min_value=1, max_value=5, value=4)
    st.caption("권장: 4")
    st.divider() 
    if "ELEVENLABS_API_KEY" in st.secrets:
        api_key = st.secrets["ELEVENLABS_API_KEY"]
        st.success("✅ API Key가 안전하게 로드되었습니다.")
    else:
        api_key = st.text_input("ElevenLabs API Key", type="password")
        st.warning("Secrets에 키를 등록하면 매번 입력하지 않아도 됩니다.")

st.info("ℹ️ 10분 단위로 문장이 끊기지 않게 **스마트 분할**되어 ZIP 파일로 저장됩니다.")
st.warning("SRT 파일을 업로드하세요. 반드시 '완료' 문구가 뜰 때까지 기다리세요.")

uploaded_files = st.file_uploader("SRT 파일을 1개만 업로드하세요", type=["srt"], accept_multiple_files=True)

if 'generated_zips' not in st.session_state:
    st.session_state.generated_zips = []

if uploaded_files and api_key:
    if st.button(f"고속 변환 시작 ({len(uploaded_files)}개 파일)"):
        if not voice_id.strip():
            st.error("🚨 Voice ID를 입력하세요!"); st.stop()
        if len(uploaded_files) > 1:
            st.error("🚨 메모리 보호를 위해 **한 번에 1개씩만** 작업해주세요."); st.stop()

        st.session_state.generated_zips = []
        main_progress = st.progress(0)
        status_text = st.empty()

        for file_idx, uploaded_file in enumerate(uploaded_files):
            file_name = uploaded_file.name
            status_text.markdown(f"### 🚀 처리 중: **{file_name}**...")
            srt_content = uploaded_file.getvalue().decode("utf-8")
            parsed_segments = parse_srt(srt_content)
            
            if not parsed_segments:
                st.error(f"⚠️ {file_name}: 내용을 읽을 수 없습니다.")
                continue
            
            # --- [스마트 분할 로직] ---
            chunk_limit_ms = 10 * 60 * 1000  # 10분
            current_chunk_audio = AudioSegment.empty()
            parts_buffer = [] 
            
            last_segment_end_ms = 0 
            part_number = 1
            
            sub_progress = st.progress(0)
            
            batch_size = max_workers
            total_segments = len(parsed_segments)
            
            for i in range(0, total_segments, batch_size):
                batch_segments = parsed_segments[i : i + batch_size]
                
                tasks = []
                for seg in batch_segments:
                    tasks.append((seg['text'], voice_id, api_key, seg['index']))
                
                batch_results = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for result in executor.map(generate_audio_task, tasks):
                        idx, audio_bytes = result
                        batch_results[idx] = audio_bytes
                
                for seg in batch_segments:
                    audio_data = batch_results.get(seg['index'])
                    if not audio_data: continue

                    # 공백 계산
                    silence_gap = seg['start_ms'] - last_segment_end_ms
                    if silence_gap < 0: silence_gap = 0
                    
                    segment_audio = AudioSegment.from_file(io.BytesIO(audio_data), format="mp3")
                    synced_audio = match_target_duration(segment_audio, seg['duration_ms'])
                    
                    # [핵심] 스마트 분할: 이 문장을 더했을 때 10분을 넘으면, 미리 끊는다.
                    # (단, 현재 청크가 비어있지 않을 때만)
                    added_duration = int(silence_gap) + len(synced_audio)
                    
                    if (len(current_chunk_audio) + added_duration > chunk_limit_ms) and (len(current_chunk_audio) > 0):
                        # 1. 현재까지의 파일 저장
                        part_filename = f"{file_name.replace('.srt', '')}_Part_{part_number:02d}.mp3"
                        part_buffer = io.BytesIO()
                        current_chunk_audio.export(part_buffer, format="mp3")
                        parts_buffer.append((part_filename, part_buffer))
                        
                        # 2. 초기화 및 다음 파일 번호로 이동
                        current_chunk_audio = AudioSegment.empty()
                        part_number += 1
                        gc.collect()
                        
                        # 중요: 새 파일의 시작점에서도 공백(silence_gap)은 유지되어야 
                        # 편집기 타임라인 상에서 위치가 맞습니다.
                    
                    # 오디오 추가
                    current_chunk_audio += AudioSegment.silent(duration=int(silence_gap))
                    current_chunk_audio += synced_audio
                    
                    last_segment_end_ms = seg['end_ms']
                    del audio_data, segment_audio, synced_audio
                
                current_progress = min((i + batch_size) / total_segments, 1.0)
                sub_progress.progress(current_progress)
            
            if len(current_chunk_audio) > 0:
                part_filename = f"{file_name.replace('.srt', '')}_Part_{part_number:02d}.mp3"
                part_buffer = io.BytesIO()
                current_chunk_audio.export(part_buffer, format="mp3")
                parts_buffer.append((part_filename, part_buffer))
                del current_chunk_audio
                gc.collect()

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                for fname, fbtn in parts_buffer:
                    zip_file.writestr(fname, fbtn.getvalue())
            
            zip_filename = file_name.replace(".srt", "_Full_Parts.zip")
            
            st.session_state.generated_zips.append({
                "filename": zip_filename,
                "data": zip_buffer.getvalue()
            })
            
            st.divider()
            main_progress.progress((file_idx + 1) / len(uploaded_files))

        status_text.success("🎉 고속 장편 변환 완료! ZIP 파일을 다운로드하세요.")

if st.session_state.generated_zips:
    st.markdown("### 📥 완료된 파일 다운로드 (ZIP)")
    for result in st.session_state.generated_zips:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"🗂️ {result['filename']} (스마트 분할 완료)")
        with col2:
            st.download_button(
                label="📥 ZIP 다운로드",
                data=result["data"],
                file_name=result["filename"],
                mime="application/zip",
                use_container_width=True 
            )
        st.divider()

elif not api_key:
    st.warning("왼쪽 사이드바에 API Key를 입력하거나 Secrets에 등록해주세요.")
