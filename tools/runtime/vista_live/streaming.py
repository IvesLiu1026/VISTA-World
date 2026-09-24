"""Bounded transport parsing and speculative speech preparation, never execution."""
import json
import re
import time


def speech_chunks(text):
    """Keep complete sentences and original words; avoid a content-free first clip."""
    boundaries = list(re.finditer(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])', text))
    result, start = [], 0
    for match in boundaries:
        piece = text[start:match.start()]
        last = piece.split()[-1] if piece.split() else ''
        if len(piece.split()) >= 4 and last not in ('Dr.', 'Mr.', 'Mrs.', 'Ms.', 'Prof.', 'St.'):
            result.append(piece)
            start = match.end()
            if len(result) == 2:
                break
    if text[start:]:
        result.append(text[start:])
    return result


def speech_preview(document):
    """Read only a finished top-level speech string from incomplete JSON.

    A preview can warm local TTS. It NEVER authorizes speech or an action; the
    final complete document must still pass the existing closed-schema validator.
    """
    source = document.lstrip()
    # Match the final parser's supported entire JSON fence, for preparation
    # only. Extra prose or a different fence still produces no preview.
    if source.startswith('```json\n'):
        source = source[8:].lstrip()
    if not source.startswith('{'):
        return None
    decoder = json.JSONDecoder()
    i, seen = 1, set()
    try:
        while i < len(source):
            while i < len(source) and source[i].isspace(): i += 1
            key, i = decoder.raw_decode(source, i)
            if not isinstance(key, str) or key in seen:
                return None
            seen.add(key)
            while i < len(source) and source[i].isspace(): i += 1
            if source[i] != ':': return None
            i += 1
            while i < len(source) and source[i].isspace(): i += 1
            value, i = decoder.raw_decode(source, i)
            if key == 'speech':
                if isinstance(value, str) and 0 < len(value) <= 240 and len(value.split()) <= 32 and all(32 <= ord(c) <= 126 for c in value):
                    return value
                return None
            while i < len(source) and source[i].isspace(): i += 1
            if source[i] != ',': return None
            i += 1
    except (ValueError, IndexError):
        return None
    return None


def read_completion(stream, on_preview=None, clock=time.monotonic, started=None):
    """Collect one SSE completion, retaining terminal/error/accounting evidence."""
    started = clock() if started is None else started
    content, data = '', []
    count, finished, terminal, previewed = 0, False, None, False
    meta, timing = {}, {}
    for raw in stream:
        count += len(raw)
        if count > 2_880_000 or len(raw) > 262144:
            raise ValueError('Oversized model stream')
        line = raw.decode('utf-8').rstrip('\r\n')
        if line.startswith(':'):
            continue
        if line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
            continue
        if line:
            continue  # SSE event/id/retry fields carry no completion data.
        if not data:
            continue
        value = '\n'.join(data)
        data.clear()
        if value == '[DONE]':
            finished = True
            break
        item = json.loads(value)
        if item.get('error'):
            raise ValueError('Upstream streaming error: ' + str(item['error'])[:240])
        for key in ('model', 'id', 'provider'):
            if item.get(key):
                if key in meta and meta[key] != item[key]:
                    raise ValueError('Model stream identity changed')
                meta[key] = item[key]
        if item.get('usage') is not None:
            meta['usage'] = item['usage']
        choices = item.get('choices', [])
        if len(choices) > 1:
            raise ValueError('Expected one completion')
        for choice in choices:
            if choice.get('index', 0) != 0:
                raise ValueError('Unexpected completion index')
            delta = choice.get('delta') or {}
            if delta.get('tool_calls') or delta.get('refusal'):
                raise ValueError('Unexpected tool call or refusal')
            fragment = delta.get('content') or ''
            if not isinstance(fragment, str):
                raise ValueError('Expected text delta')
            if fragment:
                if terminal is not None:
                    raise ValueError('Content after completion end')
                timing.setdefault('first_content_ms', round((clock()-started)*1000, 2))
                content += fragment
                if not previewed:
                    preview = speech_preview(content)
                    if preview:
                        previewed = True
                        timing['speech_preview_ms'] = round((clock()-started)*1000, 2)
                        if on_preview:
                            on_preview(preview)
            reason = choice.get('finish_reason')
            if reason:
                if reason != 'stop' or (terminal is not None and terminal != reason):
                    raise ValueError('Incomplete model stream: ' + str(reason))
                terminal = reason  # OpenRouter repeats this on the usage chunk.
    if not finished or terminal != 'stop' or not content:
        raise ValueError('Model stream ended without a complete response')
    return {**meta, 'choices': [{'message': {'content': content}, 'finish_reason': terminal}]}, timing
