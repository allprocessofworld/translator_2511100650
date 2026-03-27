# --- Gemini API 번역 로직 (다큐멘터리 마스터 디렉터 프롬프트 적용) ---
@st.cache_data(show_spinner=False)
def translate_gemini(text_data, target_lang_name):
    is_list = isinstance(text_data, list)
    
    # 공통 다큐멘터리 디렉팅 가이드라인
    director_guidelines = """
        ROLE: You are a Master Voice Director and Expert Script Translator for high-end, philosophical documentaries (think Morgan Freeman's narration style).
        
        CRITICAL TRANSLATION RULES:
        1. Gravitas & Vocabulary: Do not use dry, literal words (e.g., use 'Founder/Master' instead of 'CEO', 'Ritual' instead of 'Process'). The tone must be profound, weighty, and poetic.
        2. Pacing & Breathing: Break down overly long technical sentences into shorter, rhythmic phrases suitable for a voice actor's natural breathing.
        3. Pauses for Emphasis: Naturally structure sentences so that technical terms (e.g., Slip, Casting) have slight rhythmic pauses before or after them.
        4. Emotional Crescendo: Escalate the energy and impact of the vocabulary towards the climax of the narrative (e.g., intense heat, ultimate creation).
        5. Phonetic Resonance: Where natural in the target language, construct the end of sentences with words that carry long vowel sounds (e.g., Ocean, Infinite) to leave a lingering auditory resonance.
    """
    
    if is_list:
        json_payload = json.dumps(text_data, ensure_ascii=False)
        prompt = f"""{director_guidelines}
        
        TASK: Translate the following JSON array of strings into {target_lang_name} applying the CRITICAL TRANSLATION RULES.
        
        STRICT FORMATTING RULES:
        1. Return ONLY a valid JSON array of strings. No explanations, no markdown.
        2. The output array MUST have exactly {len(text_data)} items. Do not merge or split the array items themselves, but you may alter the internal pacing of the text within each item.
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
                    raise Exception("JSON 배열 기호 '[' 또는 ']'를 찾을 수 없습니다.")
                    
                translated_list = json.loads(res_text)
                if len(translated_list) != len(text_data):
                    raise Exception(f"배열 길이 불일치 (원본 {len(text_data)}개 vs 번역 {len(translated_list)}개)")
                return translated_list, None
            else:
                return res_text, None
                
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt) 
                continue
            return None, f"Gemini 번역 실패 (재시도 초과): {str(e)}"
