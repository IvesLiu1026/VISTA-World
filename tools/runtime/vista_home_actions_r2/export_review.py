"""Create a VISTA review candidate and a separate, allowlisted model input.

This does not publish a benchmark row or call a model. Native event success is
privileged simulator evidence; it never substitutes for benchmark-lab review.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid


def fingerprint(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return dict(bytes=path.stat().st_size, sha256=h.hexdigest())


def normalize_dialogue(turns, duration):
    if not isinstance(turns, list) or not 1 <= len(turns) <= 100:
        raise ValueError('Provide 1–100 selected dialogue turns')
    result = []
    ids = set()
    for turn in turns:
        allowed = {'turn_id', 'speaker', 'text', 'start_sec', 'end_sec'}
        if not isinstance(turn, dict) or set(turn) - allowed or not {'speaker', 'text'} <= set(turn):
            raise ValueError('Dialogue accepts user-facing speech and optional timing only')
        if not all(isinstance(turn[k], str) and turn[k].strip() for k in ('speaker', 'text')):
            raise ValueError('Each turn needs a speaker and text')
        row = {'speaker': turn['speaker'], 'text': turn['text']}
        if 'turn_id' in turn:
            if not isinstance(turn['turn_id'], str) or turn['turn_id'] in ids:
                raise ValueError('Dialogue turn IDs must be unique strings')
            ids.add(turn['turn_id']); row['turn_id'] = turn['turn_id']
        if 'start_sec' in turn or 'end_sec' in turn:
            start, end = turn.get('start_sec'), turn.get('end_sec')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)):
                raise ValueError('Both dialogue times must be finite seconds')
            if not 0 <= start <= end <= duration:
                raise ValueError('Dialogue timing must lie inside the selected video')
            row.update(start_sec=start, end_sec=end)
        result.append(row)
    return result


def restricted_input(case_id, dialogue, *, timed=False):
    # Construct from an allowlist. No runtime state, source event ID, filenames
    # containing event names, seeds, review notes, labels or oracle are copied.
    allowed = {'speaker', 'text', 'turn_id'} | ({'start_sec', 'end_sec'} if timed else set())
    speech = []
    for turn in dialogue:
        row={k:v for k,v in turn.items() if k in allowed}
        # VISTA's current MllmEvalInputV1 deliberately types dialogue values as
        # strings. The selected review dialogue keeps numeric timing separately.
        for key in ('start_sec','end_sec'):
            if key in row:
                value=row[key]
                if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
                    raise ValueError('Visible dialogue timing must be finite seconds')
                row[key]=format(value,'.6g')
        speech.append(row)
    return {
        'schema_version': '1.0.0', 'case_id': case_id,
        'modality_condition': 'video_plus_external_text_dialogue',
        'allowed_information': {
            'can_use_video': True, 'can_use_dialogue': True,
            'can_use_seed_metadata': False, 'can_use_render_script': False,
            'can_use_oracle': False, 'can_use_validity_artifacts': False,
        },
        'source_paths': {'video': 'observation.mp4'}, 'dialogue': speech,
        'question': 'Watch the video and read the dialogue. Decide whether assistance is needed. '
                    'If needed, give concrete steps and support them with visible or spoken evidence. '
                    'State uncertainty when the evidence is insufficient.',
        'agent_response_schema': {
            'schema_version':'1.0.0','case_id':case_id,'model':'',
            'assistance_decision':'uncertain','confidence':None,'issue_summary':'','issue_type':'',
            'target_objects':[],'target_state':'','user_intent_or_next_action':'','evidence_citations':[],
            'urgency':'none','recommended_action':'','recommended_warning':'','what_to_check_next':'',
            'uncertainty':'','no_assistance_rationale':'','final_user_message':'','raw_response':'',
        },
        'restricted_context_policy': {'allowed_artifacts': ['observation.mp4', 'dialogue'], 'dialogue_timing_included': timed},
        'notes': [],
    }


def export(video, turns, bridge, output, capture, timed=False):
    video, bridge, output = Path(video), Path(bridge), Path(output)
    if output.exists():
        raise ValueError('Review exports are append-only; choose a fresh output')
    if video.suffix.lower() != '.mp4' or not video.is_file():
        raise ValueError('Select an existing MP4 capture')
    info = json.loads(subprocess.check_output(['/usr/bin/ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,avg_frame_rate:format=duration', '-of', 'json', str(video)], text=True))
    duration = float(info['format']['duration'])
    if not math.isfinite(duration) or duration <= 0 or not info['streams']:
        raise ValueError('Capture has no readable video stream')
    if capture.get('clean_observation') is not True or capture.get('video_sha256') != fingerprint(video)['sha256']:
        raise ValueError('Capture receipt must bind this video with scenario HUD hidden')
    dialogue = normalize_dialogue(turns, duration)
    session = json.loads((bridge/'session.json').read_text(encoding='utf-8-sig'))
    state = json.loads((bridge/'state.json').read_text(encoding='utf-8-sig'))
    if state['session_id'] != session['session_id'] or capture.get('session_id') != session['session_id']:
        raise ValueError('Capture and runtime session do not match')
    if capture.get('event_id') != state['event_id']:
        raise ValueError('Export the captured episode before selecting another event')
    if not capture.get('state_samples') or capture.get('capture_status')!='complete':
        raise ValueError('Capture needs continuous native state observations and a completed recording')
    case_id = uuid.uuid4().hex
    output.mkdir(parents=True); (output/'restricted').mkdir(); (output/'privileged').mkdir()
    shutil.copyfile(video, output/'restricted/observation.mp4')
    for name in ['session.json', 'state.json', 'receipts.jsonl']:
        if (bridge/name).is_file(): shutil.copyfile(bridge/name, output/'privileged'/name)
    write = lambda path, data: path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    write(output/'restricted/restricted_assist_step_input.json', restricted_input(case_id, dialogue, timed=timed))
    write(output/'privileged/selected_dialogue.json', {'turns': dialogue})
    write(output/'privileged/capture.json', capture)
    manifest = {
        'schema': 'vista.world-review-candidate/v1', 'case_id': case_id,
        'created_at': datetime.now(timezone.utc).isoformat(), 'source_kind': 'native_unreal_simulation',
        'video_attempt': dict(path='restricted/observation.mp4', duration_s=duration, **fingerprint(video)),
        'video_stream': info['streams'][0], 'dialogue_path': 'privileged/selected_dialogue.json',
        'review_decision': 'needs_review', 'review_source_of_truth': 'benchmark-lab',
        'release_readiness': 'review_only', 'final_category': None, 'oracle': None,
        'native_event_id': capture['event_id'], 'native_event_status': capture['state_samples'][-1]['event_status'],
        'restricted_input_path': 'restricted/restricted_assist_step_input.json',
        'privileged_evidence_dir': 'privileged',
    }
    write(output/'reviewed_case_candidate.json', manifest)
    return manifest


def main():
    p=argparse.ArgumentParser()
    for name in ['video','dialogue','bridge','out','capture_receipt']:p.add_argument('--'+name.replace('_','-'),required=True,type=Path)
    p.add_argument('--include-dialogue-timing',action='store_true');a=p.parse_args()
    result=export(a.video,json.loads(a.dialogue.read_text())['turns'],a.bridge,a.out,
                  json.loads(a.capture_receipt.read_text()),a.include_dialogue_timing)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
