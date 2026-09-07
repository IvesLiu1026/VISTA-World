"""Validate exports against the user's checked-out VISTA contracts, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--vista-root',type=Path,required=True)
    p.add_argument('--input',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    source=a.vista_root/'benchmarks/vista_mm_dialogue_exp/src'
    contract=source/'mm_dialogue_benchmark/contracts/downstream.py'
    if not contract.is_file():raise SystemExit('Current VISTA downstream contract was not found')
    if a.out.exists():raise SystemExit('Use a fresh verification receipt')
    sys.path.insert(0,str(source))
    from mm_dialogue_benchmark.contracts.downstream import MllmEvalInputV1,AgentAssistanceResponse
    from export_review import restricted_input
    if a.input:
        rows=[json.loads(a.input.read_text())]
        video=a.input.parent/rows[0]['source_paths']['video']
        if not video.is_file() or video.resolve().parent!=a.input.parent.resolve():raise ValueError('Video must stay inside the restricted bundle')
    else:
        turns=[{'turn_id':'1','speaker':'user','text':'I am heading out.','start_sec':0,'end_sec':2}]
        rows=[restricted_input('contract-check',turns,timed=t) for t in [False,True]]
    for data in rows:
        input_model=MllmEvalInputV1.model_validate(data)
        response=AgentAssistanceResponse.model_validate(data['agent_response_schema'])
        if response.model_dump(mode='json')!=data['agent_response_schema']:raise ValueError('Assistant response schema lost fields in VISTA')
        if input_model.allowed_information.can_use_oracle:raise ValueError('Privileged input was enabled')
    receipt={'schema':'vista.home-contract-compatibility/v1','status':'passed',
        'vista_contract':str(contract.resolve()),'vista_contract_sha256':hashlib.sha256(contract.read_bytes()).hexdigest(),
        'input_contract':'MllmEvalInputV1','response_contract':'AgentAssistanceResponse','cases':len(rows),
        'input':str(a.input.resolve()) if a.input else None,'model_calls':0}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
