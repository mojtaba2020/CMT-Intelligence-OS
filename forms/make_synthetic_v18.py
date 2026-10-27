"""Generate ONLY synthetic input envelopes based on the old synthetic dataset."""
from pathlib import Path
import json

ROOT=Path(__file__).parent
old=json.loads((ROOT/'examples/SYNTHETIC_PACKET.json').read_text(encoding='utf-8'))

def make(*, pending=True):
    docs=[]
    for form in old['forms']:
        fid=form['form_id']; typ=form['form_type']
        def field(k,v,anchor,reviewed=True):
            return {'key':k,'value':str(v),'origin':'model' if k.endswith('percent') or k=='field_wet_density_pcf' else 'manual',
                    'confidence':0.97 if reviewed else 0.62,
                    'evidence_ref':f'{fid}#{anchor}',
                    'reviewed':reviewed,'reviewer_ref':'SYN-REVIEWER-01' if reviewed else ''}
        header=[];rows=[]
        excluded={'form_id','form_type','human_verified','rows','cylinders','observations'}
        for key,value in form.items():
            if key not in excluded and value is not None and key!='notes':
                outkey={'reported_concrete_cylinders_cast':'cylinders_cast','reported_concrete_cylinders_picked_up':'cylinders_picked_up'}.get(key,key)
                # Intentional pending AI guess, no auto-promotion
                reviewed=not (pending and fid=='DEMO-DENSITY-P2' and key=='page_count')
                header.append(field(outkey,value,'header.'+outkey,reviewed))
        source_rows=form.get('rows',form.get('cylinders',form.get('observations',[])))
        for i,r in enumerate(source_rows):
            rows.append({'row_id':f'R{i+1:03}',
                         'fields':[field(key,value,f'row.{i+1}.{key}') for key,value in r.items() if value is not None]})
        docs.append({'source_id':fid,'form_type':typ,'fields':header,'rows':rows})
    return {'schema':'cmt-capture-v1.8','data_mode':'synthetic','authorization_attested':False,
            'project_key':old['project_key'],'work_date':old['work_date'],'documents':docs}

if __name__=='__main__':
    dst=ROOT/'examples'
    for name,pending in [('SYNTHETIC_CAPTURE_PENDING_V18.json',True),('SYNTHETIC_CAPTURE_REVIEWED_V18.json',False)]:
        (dst/name).write_text(json.dumps(make(pending=pending),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
