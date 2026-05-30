import numpy as np
from faster_whisper import WhisperModel
import logging

logger = logging.getLogger("astra_stt")

class STTService:
    def __init__(self):
        # Using large-v3 for accurate multilingual compliance
        self.model = WhisperModel("large-v3", device="cuda", compute_type="float16")

    def transcribe_chunk(self, audio_bytes: bytes, target_language: str) -> str:
        """
        Transcribes audio chunks using exact language constraints to stop cross-language hallucinations.
        target_language map: 'en' for English, 'hi' for Hindi
        """
        try:
            # Convert raw PCM/WAV bytes to float32 numpy array
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # CRITICAL FIX: Explicitly set language, beam size, and VAD filters to ignore echo
            segments, info = self.model.transcribe(
                audio_data,
                language=target_language,
                beam_size=5,
                vad_filter=True, 
                vad_parameters=dict(
                    min_speech_duration_ms=300,  # Suppress tiny background hums
                    max_speech_duration_s=30,
                    speech_pad_ms=400
                )
            )
            
            text_segments = [segment.text for segment in segments]
            full_text = " ".join(text_segments).strip()
            return full_text
            
        except Exception as e:
            logger.error(f"STT Error: {str(e)}")
            return ""