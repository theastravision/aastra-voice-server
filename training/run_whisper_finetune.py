"""Fine-tune Whisper on manifest.tsv and export CTranslate2 for faster-whisper."""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    TRAINING_CHECKPOINTS_ROOT,
    TRAINING_DATA_ROOT,
    WHISPER_FINETUNE_BASE,
    WHISPER_FINETUNE_EPOCHS,
)
from engines.stt_model_registry import set_stt_model
from training.job_runner import TrainingJob, get_job, upsert_job

logger = logging.getLogger(__name__)

_VALID_LANGUAGES = frozenset({'en', 'hi', 'hinglish'})


def _resolve_job(job_id: str, language: str | None) -> TrainingJob:
    job = get_job(job_id)
    if job:
        return job
    if not language:
        raise ValueError(
            f'Unknown job {job_id}. Pass --language to register a CLI job, '
            'or create one via POST /api/v1/training/jobs / the training UI.'
        )
    if language not in _VALID_LANGUAGES:
        raise ValueError(f'language must be one of: {", ".join(sorted(_VALID_LANGUAGES))}')
    job = TrainingJob(id=job_id, language=language, status='queued')
    upsert_job(job)
    logger.info('Registered CLI training job %s (%s)', job_id, language)
    return job


def _load_manifest(language: str) -> list[tuple[str, str]]:
    manifest = Path(TRAINING_DATA_ROOT) / language / 'manifest.tsv'
    if not manifest.is_file():
        raise FileNotFoundError(f'Missing manifest: {manifest}')
    root = Path(TRAINING_DATA_ROOT).resolve()
    rows: list[tuple[str, str]] = []
    with manifest.open(encoding='utf-8') as f:
        for row in csv.reader(f, delimiter='\t'):
            if len(row) < 2:
                continue
            rel, text = row[0].strip(), row[1].strip()
            if not text:
                continue
            wav = (root / rel).resolve()
            if wav.is_file():
                rows.append((str(wav), text))
    if not rows:
        raise ValueError('Manifest has no valid rows')
    return rows


@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    """Pad variable-length mel features and token labels for Whisper batches."""

    processor: Any
    decoder_start_token_id: int

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        import torch

        input_name = self.processor.model_input_names[0]
        input_features = [{input_name: feat[input_name]} for feat in features]
        label_features = [{'input_ids': feat['labels']} for feat in features]

        batch = self.processor.feature_extractor.pad(input_features, return_tensors='pt')
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors='pt')
        labels = labels_batch['input_ids'].masked_fill(labels_batch.attention_mask.ne(1), -100)
        if (labels[:, 0] == self.decoder_start_token_id).all().cpu().item():
            labels = labels[:, 1:]
        batch['labels'] = labels
        return batch


def _finetune_hf(rows: list[tuple[str, str]], language: str, out_hf: Path) -> None:
    import torch
    from datasets import Dataset
    from transformers import (
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        WhisperForConditionalGeneration,
        WhisperProcessor,
    )

    processor = WhisperProcessor.from_pretrained(WHISPER_FINETUNE_BASE)
    model = WhisperForConditionalGeneration.from_pretrained(WHISPER_FINETUNE_BASE)
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []
    model.config.use_cache = False

    max_audio_samples = 16000 * 30
    max_label_length = 448

    def _prepare(example: dict[str, str]) -> dict[str, Any]:
        import librosa

        audio, _ = librosa.load(example['audio'], sr=16000, mono=True)
        audio = audio[:max_audio_samples]
        example['input_features'] = processor(
            audio, sampling_rate=16000, return_tensors='pt'
        ).input_features[0]
        example['labels'] = processor.tokenizer(
            example['text'],
            truncation=True,
            max_length=max_label_length,
        ).input_ids
        return example

    ds = Dataset.from_dict({'audio': [r[0] for r in rows], 'text': [r[1] for r in rows]})
    ds = ds.map(_prepare, remove_columns=ds.column_names)

    data_collator = DataCollatorSpeechSeq2SeqWithPadding(
        processor=processor,
        decoder_start_token_id=model.config.decoder_start_token_id,
    )

    args = Seq2SeqTrainingArguments(
        output_dir=str(out_hf),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=WHISPER_FINETUNE_EPOCHS,
        learning_rate=1e-5,
        fp16=torch.cuda.is_available(),
        save_strategy='epoch',
        logging_steps=10,
        remove_unused_columns=False,
        label_names=['labels'],
        report_to=[],
        predict_with_generate=False,
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=args,
        train_dataset=ds,
        data_collator=data_collator,
        processing_class=processor,
    )
    trainer.train()
    model.save_pretrained(out_hf)
    processor.save_pretrained(out_hf)


def _export_ct2(hf_dir: Path, ct2_dir: Path) -> None:
    ct2_dir.mkdir(parents=True, exist_ok=True)
    try:
        from ctranslate2.converters import TransformersConverter

        TransformersConverter(str(hf_dir)).convert(
            str(ct2_dir),
            quantization='float16',
            force=True,
        )
    except Exception as exc:
        logger.warning('CT2 export failed (%s); copying HF weights only', exc)
        import shutil

        if ct2_dir.exists():
            shutil.rmtree(ct2_dir)
        shutil.copytree(hf_dir, ct2_dir)


def run_job(job_id: str, *, language: str | None = None) -> None:
    job = _resolve_job(job_id, language)
    language = job.language
    job.status = 'preprocessing'
    upsert_job(job)

    rows = _load_manifest(language)
    job.sample_count = len(rows)
    job.hours = round(sum(Path(p).stat().st_size for p, _ in rows) / (16000 * 2 * 3600), 3)
    job.status = 'training'
    upsert_job(job)

    ckpt_root = Path(TRAINING_CHECKPOINTS_ROOT) / language
    hf_dir = ckpt_root / 'hf'
    ct2_dir = ckpt_root / 'ct2'
    hf_dir.mkdir(parents=True, exist_ok=True)

    _finetune_hf(rows, language, hf_dir)
    _export_ct2(hf_dir, ct2_dir)

    rel_ct2 = str(ct2_dir.relative_to(Path(__file__).resolve().parents[1]))
    set_stt_model(
        language,
        whisper_path=rel_ct2.replace('\\', '/'),
        job_id=job_id,
        ready=True,
        sample_count=job.sample_count,
        hours=job.hours,
    )
    job.status = 'ready'
    job.whisper_path = rel_ct2
    upsert_job(job)
    logger.info('Training job %s ready at %s', job_id, ct2_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--language', default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        run_job(args.job_id, language=args.language)
    except Exception as exc:
        job = get_job(args.job_id)
        if job:
            job.status = 'failed'
            job.error = str(exc)[:2000]
            upsert_job(job)
        raise


if __name__ == '__main__':
    main()
