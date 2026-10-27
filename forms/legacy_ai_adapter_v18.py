"""Conservative bridge from existing local AI photo proposals into v1.8 review.

This does NOT run the AI model. All model values remain unverified. Missing fields
must NOT be inferred. Provenance anchors identify a source page, not a true OCR bbox.
"""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
import argparse
from forms.capture_v18 import VERSION

MAPPINGS={
 'density_sheet': {
    'project':('header','project_key'),
    'wet_density':('row','field_wet_density_pcf'),
    'moisture':('row','field_moisture_percent'),
    'max_dry_density':('row','max_dry_density_pcf'),
    'proctor':('header','proctor_reference'),
    'location':('row','location'),
 },
 'concrete_strength': {
    'project':('header','project_key'),
    'slump':('header','slump_in'),
    'air':('header','air_percent'),
    'temperature':('header','concrete_temp_f'),
    'location':('header','test_location'),
    'mix':('header','mix_design_ref'),
 }}


def adapt(proposal:dict, *, form_type:str, source_id:str, project_key:str, work_date:str,
          data_mode:str='synthetic',authorization_attested:bool=False) -> dict:
    if form_type not in MAPPINGS:raise ValueError('only supported legacy soil/concrete hints')
    if data_mode not in ('synthetic','authorized'):raise ValueError('explicit mode required')
    if data_mode=='authorized' and authorization_attested is not True:
        raise ValueError('authorized data require explicit permission')
    if not all(isinstance(v,str) and 0<len(v)<120 for v in [source_id,project_key,work_date]):
        raise ValueError('source/project/day must be provided by an operator')
    date.fromisoformat(work_date)
    if not isinstance(proposal,dict) or not isinstance(proposal.get('fields'),list):
        raise ValueError('legacy proposal must have fields array')
    header=[];rows=[];observed=set();mapping=MAPPINGS[form_type]
    def put(bucket,key,value,rawkey):
        if key in observed:raise ValueError('duplicate mapped field')
        observed.add(key)
        bucket.append({'key':key,'value':value,'origin':'model','confidence':None,
                       'evidence_ref':source_id+'#ai-candidate.'+rawkey,
                       'reviewed':False,'reviewer_ref':''})
    put(header,'work_date',work_date,'operator-day')
    # Intentionally NOT marking operator-provided project/day verified; human must check source.
    project_seen=False
    for pair in proposal['fields']:
        if not isinstance(pair,dict):raise ValueError('invalid candidate pair')
        key=pair.get('key');value=pair.get('value')
        if key not in mapping or not isinstance(value,str) or not value.strip() or len(value)>220:
            continue
        bucket, dest=mapping[key]
        if dest=='project_key':project_seen=True
        put(header if bucket=='header' else rows,dest,value.strip(),key)
    if not project_seen:put(header,'project_key',project_key,'operator-project')
    row_items=[{'row_id':'PROPOSED-ROW-1','fields':rows}] if rows else []
    return {'schema':VERSION,'data_mode':data_mode,'authorization_attested':authorization_attested,
            'project_key':project_key,'work_date':work_date,
            'documents':[{'source_id':source_id,'form_type':form_type,'fields':header,'rows':row_items}]}


def main():
    p=argparse.ArgumentParser(description='Legacy AI candidate -> unverified field review envelope')
    p.add_argument('proposal',type=Path);p.add_argument('--type',required=True,choices=tuple(MAPPINGS))
    p.add_argument('--source-id',required=True);p.add_argument('--project-key',required=True);p.add_argument('--work-date',required=True)
    p.add_argument('--output',required=True,type=Path)
    # CLI intentionally synthetic-only; the python API has separate explicit attestation.
    a=p.parse_args();raw=json.loads(a.proposal.read_text('utf8'))
    packet=adapt(raw,form_type=a.type,source_id=a.source_id,project_key=a.project_key,work_date=a.work_date)
    a.output.write_text(json.dumps(packet,indent=2,ensure_ascii=False)+'\n',encoding='utf8')

if __name__=='__main__':main()
