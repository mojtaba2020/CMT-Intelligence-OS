from pathlib import Path
import json
from server.reconcile_v15 import Case,reconcile
root=Path(__file__).resolve().parent
scenarios={}
for path in sorted((root/'examples'/'v15').glob('*.json')):
    data=json.loads(path.read_text(encoding='utf-8'))
    scenarios[path.stem]={'input':data,'report':reconcile(Case.model_validate(data))}
(root/'examples'/'v15'/'SYNTHETIC_RECONCILIATION_REPORTS.json').write_text(json.dumps({k:v['report'] for k,v in scenarios.items()},indent=2,ensure_ascii=False),encoding='utf-8')
template=(root/'examples'/'v15'/'demo_template.html').read_text(encoding='utf-8')
html=template.replace('/*__SCENARIOS__*/',json.dumps(scenarios,ensure_ascii=False).replace('</','<\\/'))
(root/'reconciliation_demo_v15.html').write_text(html,encoding='utf-8')
print('Demo created',len(html),'bytes')
