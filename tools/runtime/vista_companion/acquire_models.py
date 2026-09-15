"""Fetch pinned public model files into an explicitly scoped local service root."""
import argparse
import hashlib
import json
import os
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--service', type=Path, required=True)
a = p.parse_args()
root = a.service.resolve(strict=True)
os.environ['HF_HOME'] = str(root / 'model-cache')
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
from huggingface_hub import snapshot_download

models = [
    ('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', '29e01c4e8d000f4bcd70751be16fa94bf3d85a18',
     root / 'CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B',
     ['cosyvoice3.yaml', 'config.json', 'configuration.json', 'campplus.onnx',
      'speech_tokenizer_v3.onnx', 'llm.pt', 'flow.pt', 'hift.pt', 'CosyVoice-BlankEN/*', 'LICENSE*', 'README*']),
    ('Qwen/Qwen3-4B-Instruct-2507', 'cdbee75f17c01a7cc42f958dc650907174af0554', root / 'models/Qwen3-4B-Instruct-2507',
     ['*.safetensors', '*.json', '*.txt', '*.tiktoken', 'LICENSE*', 'README*']),
]
receipts = []
for repo, revision, target, patterns in models:
    print('MODEL_DOWNLOAD', repo, revision, flush=True)
    snapshot_download(repo_id=repo, revision=revision, local_dir=target,
                      allow_patterns=patterns, token=False, max_workers=3)
    rows = []
    for f in sorted(target.rglob('*')):
        if f.is_file() and '.cache' not in f.relative_to(target).parts:
            digest=hashlib.sha256()
            with f.open('rb') as stream:
                for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
            rows.append(dict(path=f.relative_to(target).as_posix(), bytes=f.stat().st_size,sha256=digest.hexdigest()))
    receipts.append(dict(repository=repo, revision=revision, path=str(target), files=rows))
    (root / 'models.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print('MODEL_READY', repo, len(rows), flush=True)
