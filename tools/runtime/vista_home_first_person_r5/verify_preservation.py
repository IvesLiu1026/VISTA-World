"""Verify retained demo identity and byte-identical inherited content."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    for key in ['demo-lock','source','candidate','out']:
        parser.add_argument('--'+key,type=Path,required=True)
    a=parser.parse_args()
    if a.out.exists():raise RuntimeError('Retain earlier preservation receipts')
    lock=json.loads(a.demo_lock.read_text());live=Path(lock['live_project']).parent
    backup=a.demo_lock.parent/'project';failures=[]
    for row in lock['files']:
        for label,root in [('live',live),('backup',backup)]:
            p=root/row['file']
            if not p.is_file() or sha(p)!=row['sha256']:failures.append(label+'/'+row['file'])
    inherited=[]
    for path in sorted((a.source/'Content').rglob('*')):
        if not path.is_file():continue
        name=path.relative_to(a.source);candidate=a.candidate/name
        if not candidate.is_file() or sha(candidate)!=sha(path):failures.append('content/'+str(name))
        inherited.append(str(name))
    candidate_content={str(path.relative_to(a.candidate)) for path in (a.candidate/'Content').rglob('*') if path.is_file()}
    if candidate_content!=set(inherited):failures.append('content/file set changed')
    for path in (a.source/'Config').rglob('*'):
        if not path.is_file():continue
        name=path.relative_to(a.source);candidate=a.candidate/name
        same=candidate.read_bytes().startswith(path.read_bytes()) if path.name=='DefaultEngine.ini' else sha(candidate)==sha(path)
        if not same:failures.append('config/'+str(name))
    if sha(a.source/'PhotorealHome.uproject')!=sha(a.candidate/'PhotorealHome.uproject'):failures.append('project descriptor')
    apps_sha=sha(Path('/home/yhliu/.config/sunshine/apps.json'))
    if apps_sha!=lock['apps_sha256']:failures.append('Sunshine apps')
    services={}
    for name,expected in lock['services'].items():
        current=subprocess.check_output(['systemctl','--user','show',name,'--property=MainPID,ExecMainStartTimestamp,ActiveState'],text=True).strip()
        parse=lambda text:dict(line.split('=',1) for line in text.splitlines())
        same=parse(current)==parse(expected);services[name]={'unchanged':same,'current':current}
        if not same:failures.append('service/'+name)
    plugin=Path(__file__).resolve().parents[3]/'unreal_plugins/VistaPhotorealReview/Source'
    plugin_files=0
    for path in plugin.rglob('*'):
        if not path.is_file():continue
        copied=a.candidate/'Plugins/VistaPhotorealReview/Source'/path.relative_to(plugin)
        if not copied.is_file() or sha(copied)!=sha(path):failures.append('compiled plugin source/'+str(path.relative_to(plugin)))
        plugin_files+=1
    report={'schema':'vista.home-first-person-preservation/v1','status':'failed' if failures else 'passed',
        'demo_files_checked':len(lock['files']),'inherited_content_files':len(inherited),'inherited_content_byte_identical':not any(x.startswith('content/') for x in failures),
        'compiled_plugin_source_files':plugin_files,'apps_sha256':apps_sha,'services':services,'failures':failures,
        'candidate':str(a.candidate.resolve()),'source':str(a.source.resolve())}
    a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
