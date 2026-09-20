"""Bounded NL-to-catalog compiler. Not arbitrary scene generation or an LLM."""
import argparse
import hashlib
import json
from pathlib import Path
import re

DEFAULT_PROMPT='在六個室內空間中，我準備出門並找鑰匙，爐火還開著；接電話時浴缸持續放水。讓助手依輕重緩急提醒，處理後繼續找鑰匙。'
TOKENS={'stove':('爐火','瓦斯爐','stove'), 'bath':('浴缸','bath'),
        'keys':('鑰匙','keys'), 'phone':('電話','phone','call')}
def compile_prompt(prompt):
    if not isinstance(prompt,str) or not 12<=len(prompt)<=1600:raise ValueError('Expected a short scenario description')
    text=prompt.lower()
    if any(word in text for word in ('不要','不要有','without','no stove','no bath')):
        raise ValueError('Negation needs explicit structured authoring in this bounded compiler')
    missing=[name for name,words in TOKENS.items() if not any(word in text for word in words)]
    if missing:raise ValueError('This pilot supports stove + bath + keys + phone; missing: '+', '.join(missing))
    unsupported=[v for v in ('開車','騎車','開槍','driving','child','小孩','地震','earthquake') if v in text]
    if unsupported:raise ValueError('Unsupported assets/actions: '+', '.join(unsupported))
    return {'schema':'vista.concurrent-scenario/v1','authoring':'bounded_nl_catalog_match_not_llm',
            'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
            'scene':'six_room_anatomy_dev','episodes':['first','third'],
            'events':[{'template':'mmg_001','trigger':'initial_kitchen'},
                      {'template':'mmg_044','trigger':'initial_kitchen'},
                      {'template':'mmg_021','trigger':'phone_call_started'}],
            'human_controller':'scripted_reactive_to_assistant_notice',
            'assistant':'causal_rules_v1','language':'en','narrator':False,
            'provenance':{'stove':'VISTA multimodal-grounded safety 1',
                          'bath':'VISTA multimodal-grounded safety 21',
                          'keys':'VISTA multimodal-grounded non-safety 1',
                          'composition':'New authored concurrency; not an original VISTA episode'},
            'controls':['no_observed_hazard','already_resolved','ordinary_phone_call','offscreen_pending','priority_preemption']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prompt',default=DEFAULT_PROMPT)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with a.out.open('x') as f:json.dump(compile_prompt(a.prompt),f,ensure_ascii=False,indent=2)
