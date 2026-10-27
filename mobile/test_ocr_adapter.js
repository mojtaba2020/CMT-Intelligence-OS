const assert=require('node:assert/strict'); const c=require('./ocr_adapter.js');
const basic={schema:'cmt-capture-v1.8',data_mode:'synthetic',project_key:'SYN-1',work_date:'2026-10-26',documents:[{form_type:'concrete_strength',source_id:'demo1',fields:[{key:'slump_in',value:'4.5',reviewed:false},{key:'air_percent',value:'5.2',reviewed:false}],rows:[]}]};
const r=c.importDraft(basic);assert.equal(r[0].values.slump,'4.5');assert.equal(r[0].values.air,'5.2');assert.deepEqual(r[0].checked,{});assert.equal(r[0].type,'concrete');
assert.throws(()=>c.importDraft({...basic,data_mode:'authorized'}),/Authorization/);
assert.throws(()=>c.importDraft({...basic,documents:[{form_type:'alien',fields:[],rows:[]}]}),/Unknown form/);
console.log('3 OCR adapter checks passed');
