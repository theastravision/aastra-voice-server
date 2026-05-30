"""
Kokoro TTS Dataset Preparation Script (Windows Safe)

This script automates the tedious process of building a TTS dataset from raw, 
hour-long MP3 files. It will:
1. Split long MP3s on silences into 2-10 second chunks.
2. Convert chunks to 24000Hz WAV (required by Kokoro).
3. Auto-transcribe the audio using Whisper (distil-large-v3).
4. Phonemize the Hinglish text into IPA tokens using misaki.
5. Output a fully ready metadata.csv file.
"""

import os
import argparse
import csv
from pathlib import Path
from tqdm import tqdm

def process_dataset(input_dir: str, output_dir: str):
    print("Initializing models (Whisper + Misaki)...")
    
    try:
        from pydub import AudioSegment
        from pydub.silence import split_on_silence
    except ImportError:
        print("ERROR: pydub is required. Run: pip install pydub")
        return

    try:
        from faster_whisper import WhisperModel
        # Use a highly accurate model for dataset creation
        whisper = WhisperModel("large-v3", device="cuda", compute_type="float16")
    except ImportError:
        print("ERROR: faster-whisper is required.")
        return
        
    try:
        from misaki import hi
        phonemizer = hi.G2P()
    except ImportError:
        print("ERROR: misaki is required. Run: pip install misaki[hi]>=0.4.2")
        return

    in_path = Path(input_dir)
    out_path = Path(output_dir)
    wav_dir = out_path / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)
    
    metadata_file = out_path / "metadata.csv"
    
    mp3_files = list(in_path.glob("*.mp3")) + list(in_path.glob("*.wav"))
    if not mp3_files:
        print(f"No audio files found in {input_dir}")
        return
        
    print(f"Found {len(mp3_files)} files to process.")
    
    chunk_index = 0
    total_duration_sec = 0
    
    with open(metadata_file, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile, delimiter="|")
        
        for file in mp3_files:
            print(f"\nProcessing {file.name}...")
            audio = AudioSegment.from_file(str(file))
            
            # 1. Split on silences
            print("  Splitting on silence (this may take a minute for long files)...")
            chunks = split_on_silence(
                audio,
                min_silence_len=500,     # 500ms silence threshold
                silence_thresh=audio.dBFS - 14, # relative to average volume
                keep_silence=250         # leave 250ms silence at ends
            )
            
            for chunk in tqdm(chunks, desc="  Transcribing chunks"):
                # Discard chunks that are too short (< 1s) or too long (> 15s)
                dur = len(chunk)
                if dur < 1000 or dur > 15000:
                    continue
                    
                # 2. Convert to 24kHz mono WAV for Kokoro
                chunk = chunk.set_frame_rate(24000).set_channels(1)
                wav_filename = f"chunk_{chunk_index:06d}.wav"
                chunk_path = wav_dir / wav_filename
                chunk.export(str(chunk_path), format="wav")
                
                # 3. Transcribe with Whisper
                segments, _ = whisper.transcribe(str(chunk_path), language="hi", condition_on_previous_text=False)
                text = " ".join(seg.text for seg in segments).strip()
                
                # Discard empty transcripts
                if len(text) < 2:
                    chunk_path.unlink()
                    continue
                    
                # 4. Phonemize to IPA
                phonemes, _ = phonemizer(text)
                
                if not phonemes:
                    chunk_path.unlink()
                    continue
                    
                # 5. Save to metadata
                writer.writerow([wav_filename, text, phonemes])
                
                chunk_index += 1
                total_duration_sec += dur / 1000.0

    print(f"\nDone! Created dataset with {chunk_index} audio clips.")
    print(f"Total usable audio duration: {total_duration_sec / 3600:.2f} hours.")
    print(f"Dataset saved to: {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-prepare Kokoro TTS Dataset")
    parser.add_argument("--input", type=str, required=True, help="Path to raw mp3 folder")
    parser.add_argument("--output", type=str, required=True, help="Path to save processed dataset")
    args = parser.parse_args()
    
    process_dataset(args.input, args.output)
