/* Synthetic training data ONLY. Not an engineering record or ASTM acceptance test. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.CMTDemoSeed=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const DATE='2026-10-28';
function build(makeId){
 const newId=makeId || (()=>crypto.randomUUID());
 const tests=[
  ['TEST-001','10+00','132','10','120','125','96'],
  ['TEST-002','10+50','128.52','8','119','125','95.2'],
  ['TEST-003','11+00','133.1','10','121','125','96.8'],
  ['TEST-004','11+50','129.8','10','118','125','94.4'],
  ['TEST-005','12+00','134.2','10','122','125','97.6']
 ];
 const results=tests.map(([testId,station,wet,moisture,dry,mdd,percent])=>({
  client_id:newId(),category:'density',test_date:DATE,project_id:null,
  values:{location:'DEMO Site A',soilDescription:'Sandy Clay',proctorNumber:'TEST-P01',remarks:'SYNTHETIC TRAINING DATA ONLY — NOT A FIELD RESULT'},
  rows:[{testId,station,lift:'1',wet,moisture,dry,mdd,percent,proctorRef:'TEST-P01'}]
 }));
 for(const [id,time,slump,temperature] of [['SL-001','09:10','4.0','76'],['SL-002','09:35','5.0','78'],['SL-003','10:05','4.5','77']]){
  results.push({client_id:newId(),category:'concrete',test_date:DATE,project_id:null,
   values:{supplier:'DEMO Concrete',samplingLocation:'Slab A',slump,temperature,mixDesign:'DEMO-M1',remarks:'SYNTHETIC SLUMP DATA ONLY — NOT A FIELD RESULT'},
   rows:[{sampleId:id,time,location:'Slab A',slump,temperature,notes:'SYNTHETIC DEMO'}]});
 }
 for(const [id,time,air,temperature] of [['AIR-001','10:30','5.2','77'],['AIR-002','11:00','5.5','79']]){
  results.push({client_id:newId(),category:'concrete',test_date:DATE,project_id:null,
   values:{supplier:'DEMO Concrete',samplingLocation:'Slab B',air,temperature,mixDesign:'DEMO-M1',remarks:'SYNTHETIC AIR DATA ONLY — NOT A FIELD RESULT'},
   rows:[{sampleId:id,time,location:'Slab B',air,temperature,notes:'SYNTHETIC DEMO'}]});
 }
 return results;
}
function identity(d){const row=d&&Array.isArray(d.rows)?d.rows[0]:null;if(!row)return null;
 const id=d.category==='density'?row.testId:d.category==='concrete'?row.sampleId:null;
 return id?d.category+':'+String(id).trim().toUpperCase():null;
}
return {build,identity,DATE};
});
