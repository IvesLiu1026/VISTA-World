"""Assemble an offline review from complete, matching native runs; never edit pixels."""
import argparse
import base64
import hashlib
import json
from pathlib import Path


ROOMS = [('entry_hall', '玄關'), ('living_room', '客廳'), ('kitchen_dining', '廚房／餐廳'),
         ('bedroom', '臥室'), ('office', '書房'), ('bathroom_laundry', '浴室／洗衣')]
EXPECTED = dict(actions=26, details=34, sequences=21, protocol=14, tour=6, input=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--background-cleanup', type=Path)
    args = parser.parse_args()
    cleanup, allowed = None, {}
    if args.background_cleanup:
        cleanup = json.loads(args.background_cleanup.read_text())
        assert cleanup['schema'] == 'vista.six-spaces-background-only/v1'
        folder = args.background_cleanup.parent
        before = json.loads((folder/'contract-before.json').read_text())
        after = json.loads((folder/'contract-after.json').read_text())
        source_map, target_map = before.pop('scene_map'), after.pop('scene_map')
        assert before.pop('revision') == cleanup['source_revision']
        assert after.pop('revision') == cleanup['target_revision']
        assert before == after, 'Background cleanup changed the functional contract'
        before_bindings = json.loads((folder/'bindings-before.json').read_text())
        after_bindings = json.loads((folder/'bindings-after.json').read_text())
        assert len(before_bindings) == 43 and before_bindings == after_bindings
        allowed = cleanup['allowed_input_versions']
        for path, versions in allowed.items():
            assert len(versions) == 2
            current = Path(path).read_bytes()
            assert hashlib.sha256(current).hexdigest() == versions[1]
            if Path(path).name == 'DefaultEngine.ini':
                assert hashlib.sha256(current.replace(target_map.encode(), source_map.encode())).hexdigest() == versions[0]
            else:
                assert Path(path).name == 'VistaHomeActions.json'
                for name, version in zip(['contract-before.json', 'contract-after.json'], versions):
                    assert hashlib.sha256((folder/name).read_bytes()).hexdigest() == version
    runs, pins, artifacts, cases_by_suite, attempts = {}, {}, {}, {}, []
    for directory in args.runs:
        directory = directory.resolve(strict=True)
        result = json.loads((directory/'process.json').read_text())
        suite = result['suite']
        assert suite in EXPECTED
        assert result['completed'] and not result.get('error')
        assert result['crash_reporter_start_disabled_verified']
        assert result['shared_runtime_changed'] is False
        for path, digest in result['input_sha256'].items():
            # A failed navigation probe may be retried with a corrected route.
            # Keep both driver digests; the native map, plugin and contracts must match.
            if Path(path).name == 'run_native.py':
                continue
            if path in allowed:
                assert digest in allowed[path]
            else:
                assert path not in pins or pins[path] == digest, 'Mixed native inputs: '+path
            pins[path] = digest
        checks = json.loads((directory/'checks/results.json').read_text())
        cases = checks.get('cases', [])
        if suite == 'protocol':
            cases = [dict(name=c['name'], status='passed' if c['passed'] else 'failed') for c in checks['checks']]
        merged = cases_by_suite.setdefault(suite, {})
        for case in cases:
            merged[case.get('name', case.get('target'))] = dict(status=case['status'], run=str(directory))
        attempts.append(dict(path=str(directory), suite=suite, passed=result['passed_cases'],
                             failed=result['failed_cases'], input_sha256=result['input_sha256']))
        row = runs.setdefault(suite, dict(paths=[], revisions=[], elapsed_s=0))
        if result['initial_state']['revision'] not in row['revisions']:
            row['revisions'].append(result['initial_state']['revision'])
        row['paths'].append(str(directory))
        row['elapsed_s'] += result['elapsed_s']
        for path in [directory/'process.json', directory/'checks/results.json',
                     *sorted((directory/'checks').glob('*.png'))]:
            artifacts[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert set(runs) == set(EXPECTED), 'All six suites are required'
    for suite, count in EXPECTED.items():
        assert len(cases_by_suite[suite]) == count
        assert all(c['status'] == 'passed' for c in cases_by_suite[suite].values())
        runs[suite]['passed'] = count
    revisions = {revision for row in runs.values() for revision in row['revisions']}
    if cleanup:
        assert revisions == {cleanup['source_revision'], cleanup['target_revision']}
        assert runs['tour']['revisions'] == [cleanup['target_revision']]
        assert cleanup['target_revision'] in runs['sequences']['revisions']
        assert cleanup['target_revision'] in runs['actions']['revisions']
    else:
        assert len(revisions) == 1
    for path, digest in pins.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, 'Inputs changed since validation: '+path
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema='vista.six-spaces-review/v1', native_checks=sum(EXPECTED.values()),
                  runs=runs, attempts=attempts, cases=cases_by_suite, input_sha256=pins, artifact_sha256=artifacts,
                  background_cleanup=cleanup,
                  model_evaluation=False, client_streaming_verified=False,
                  tour_is_fixture_only=True, screenshots_modified=False)
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    title = 'Villa 六空間還原：原生驗證與畫面'
    intro = ('六個空間、43 個具名互動物件與七個既有事件已接回 Villa。'
             '以下是私人測試專案的 UE 原生截圖；空間取景使用空手定位，'
             '鑰匙／手機搬運另以實際 WASD、碰撞及持物約束驗證。')
    if cleanup:
        intro += ('功能基準為 R4；R5 清除了合併欄杆模型中的舊水龍頭，43 個互動綁定與功能契約逐項相同。'
                  'R5 另補驗跨樓層搬運、廚房操作及六空間畫面；下表合併各案例最新的通過紀錄，並非宣稱全部案例皆在 R5 重跑。')
    boundary = ('這是工程驗證，尚未進行模型評測或 Windows／Mac 串流驗收。'
                '液體仍是容量與狀態模型；人物與布料細節留待後續改進。'
                '共享 Sunshine 尚未切換至此私人版本。')
    incident = ('早期測試 native-f 曾發生引擎當機，UE 自動向 Epic 傳送 35,709 位元組診斷回報。'
                '已告知使用者並停用私人專案的回報程序；此處六組最終驗證均確認停用設定生效。'
                '原先 Nanite 啟動當機原因尚未確定，失敗紀錄保留。')
    markdown = [f'# {title}', '', intro, '', boundary, '', '| 驗證 | 通過 |', '| --- | --- |']
    names = dict(actions='單項互動', details='互動循環', sequences='事件／完整流程及逾時',
                 protocol='命令、取消與回復', tour='六空間取景', input='手動鍵盤操作')
    for suite, count in EXPECTED.items():
        markdown.append(f'| {names[suite]} | {count}/{count} |')
    html = [f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>{title}</title>',
            '<style>body{font:18px/1.7 system-ui;background:#151919;color:#eee;max-width:1440px;margin:auto;padding:32px}'
            'img{width:100%;display:block}section{margin:42px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}'
            'figure{margin:0}a{color:#b5dace}p{max-width:1000px}@media(max-width:800px){.pair{grid-template-columns:1fr}}</style>',
            f'<h1>{title}</h1><p>{intro}</p><p>{boundary}</p>',
            '<p>'+'；'.join(f'{names[k]} {v}/{v}' for k, v in EXPECTED.items())+'</p>']
    for key, name in ROOMS:
        markdown += ['', f'## {name}', '']
        html += [f'<section><h2>{name}</h2><div class="pair">']
        for view, label in [('first', '第一人稱'), ('third', '第三人稱')]:
            path = Path(cases_by_suite['tour'][key]['run'])/'checks'/f'{key}-{view}.png'
            assert path.is_file()
            markdown.append(f'![{name}・{label}]({path})')
            encoded = base64.b64encode(path.read_bytes()).decode('ascii')
            html.append(f'<figure><img src="data:image/png;base64,{encoded}" loading="lazy"><figcaption>{label}</figcaption></figure>')
        html += ['</div></section>']
    markdown += ['', '## 診斷紀錄', '', incident, '', '[驗證索引]('+str(out/'summary.json')+')', '']
    encoded_summary = base64.b64encode((out/'summary.json').read_bytes()).decode('ascii')
    html += [f'<p>{incident}</p><p><a download="summary.json" href="data:application/json;base64,{encoded_summary}">驗證索引與 SHA-256</a></p></html>']
    (out/'REVIEW.zh-TW.md').write_text('\n'.join(markdown))
    (out/'index.html').write_text('\n'.join(html))


if __name__ == '__main__':
    main()
