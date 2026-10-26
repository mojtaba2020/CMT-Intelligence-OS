/* CMT Intelligence OS v0.8 — offline pilot measurement workbench.
   No engineering acceptance and no claims of standards conformance.
   This code is embedded in index.html for the standalone demo. */
const VALIDATION_KEY='cmt-intelligence-os-validation-v01';
const PILOT_FIELDS={
 wet:{label:'NDG wet density',kind:'number',critical:true,unit:'pcf'},
 dry:{label:'NDG dry density',kind:'number',critical:true,unit:'pcf'},
 moisture:{label:'NDG moisture content',kind:'number',critical:true,unit:'%'},
 mdd:{label:'Proctor MDD reference',kind:'number',critical:true,unit:'pcf'},
 proctor_id:{label:'Proctor report ID',kind:'id',critical:true,unit:'—'},
 project_id:{label:'Project ID',kind:'id',critical:true,unit:'—'},
 spec_revision:{label:'Project spec revision',kind:'id',critical:true,unit:'—'},
 slump:{label:'Concrete slump',kind:'number',critical:true,unit:'in'},
 air:{label:'Concrete air',kind:'number',critical:true,unit:'%'},
 temp:{label:'Concrete temperature',kind:'number',critical:false,unit:'°F'},
 break_load:{label:'Cylinder peak load',kind:'number',critical:true,unit:'lbf'},
 diameter:{label:'Cylinder measured diameter',kind:'number',critical:true,unit:'in'},
 sieve_mass:{label:'Sieve retained mass',kind:'number',critical:true,unit:'g'}
};
const validationStarter=()=>({schema:1,labels:[],pairs:[]});
function validationLoad(){try{const d=JSON.parse(localStorage.getItem(VALIDATION_KEY));if(d&&d.schema===1&&Array.isArray(d.labels)&&Array.isArray(d.pairs)&&d.labels.length<=2000&&d.pairs.length<=2000)return d;}catch(e){}return validationStarter()}
let vdb=validationLoad();
function validationSave(){try{localStorage.setItem(VALIDATION_KEY,JSON.stringify(vdb))}catch(e){$('valStatus').textContent='Local browser storage unavailable. Export the validation dataset now.'}}
const pilotId=()=>('PILOT-'+(globalThis.crypto?.randomUUID?.()||String(Date.now())+Math.random().toString(36).slice(2)));
function isPlainNumber(s){return /^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(String(s).trim())&&Number.isFinite(Number(s))}
function normalizedId(s){return String(s).trim().replace(/\s+/g,' ').toUpperCase()}
function labelResult(row){const field=PILOT_FIELDS[row.field];if(!field)return 'invalid';const gold=String(row.gold||'').trim(),pred=String(row.pred||'').trim();if(!gold)return 'invalid';if(!pred)return 'abstain';if(field.kind==='number'){
 if(!isPlainNumber(gold)||!isPlainNumber(pred)||!Number.isFinite(row.tolerance)||row.tolerance<0)return 'invalid';
 return Math.abs(Number(gold)-Number(pred))<=row.tolerance+1e-10?'match':'mismatch';
}return normalizedId(gold)===normalizedId(pred)?'match':'mismatch';}
function pilotLabelMetrics(rows){const valid=rows.filter(x=>labelResult(x)!=='invalid'),matches=valid.filter(x=>labelResult(x)==='match'),critical=valid.filter(x=>PILOT_FIELDS[x.field]?.critical),criticalCorrect=critical.filter(x=>labelResult(x)==='match');
 return {total:valid.length,correct:matches.length,mismatched:valid.filter(x=>labelResult(x)==='mismatch').length,abstained:valid.filter(x=>labelResult(x)==='abstain').length,accuracy:valid.length?100*matches.length/valid.length:null,criticalTotal:critical.length,criticalCorrect:criticalCorrect.length,criticalErrors:critical.length-criticalCorrect.length};}
function pilotTimeMetrics(rows){const valid=rows.filter(x=>x.baseline>0&&x.assisted>=0&&x.correction>=0&&Number.isFinite(x.baseline+x.assisted+x.correction));const vals=valid.map(x=>({saved:x.baseline-x.assisted-x.correction,baseline:x.baseline,assisted:x.assisted+x.correction}));const totalBaseline=vals.reduce((t,x)=>t+x.baseline,0),totalAssisted=vals.reduce((t,x)=>t+x.assisted,0),sorted=vals.map(x=>x.saved).sort((a,b)=>a-b),n=sorted.length;
 return {n,totalBaseline,totalAssisted,totalSaved:totalBaseline-totalAssisted,percentSaved:totalBaseline>0?100*(totalBaseline-totalAssisted)/totalBaseline:null,medianSaved:n%2?sorted[(n-1)/2]:n?(sorted[n/2-1]+sorted[n/2])/2:null,slower:vals.filter(x=>x.saved<0).length};}
const fmtMetric=(v,d=1)=>v==null?'—':Number(v).toFixed(d);
const calcFixtures=[
 ['NDG · dry density',()=>evaluate('soil',{wet:126,moisture:11.8,mdd:120,minComp:95,proctor:'DEMO'}).results.dryDensity,112.70,0.001],
 ['NDG · compaction %',()=>evaluate('soil',{wet:126,moisture:11.8,mdd:120,minComp:95,proctor:'DEMO'}).results.compaction,93.92,0.001],
 ['NDG · below job threshold is flagged',()=>evaluate('soil',{wet:126,moisture:11.8,mdd:120,minComp:95,proctor:'DEMO'}).flags.some(f=>/below/.test(f)),true,0],
 ['NDG · exactly at threshold is not flagged',()=>evaluate('soil',{wet:120,moisture:0,mdd:120,minComp:100,proctor:'DEMO'}).flags.some(f=>/below/.test(f)),false,0],
 ['Soil · oven water content %',()=>catalogCalculate('soil_moisture',{massWet:210,massDry:190,tare:90}).results.waterContent,20,0],
 ['Soil · plasticity index %',()=>catalogCalculate('atterberg',{ll:42,pl:23,piMax:null}).results.plasticityIndex,19,0],
 ['Soil · sand cone dry pcf',()=>catalogCalculate('sand_cone',{excavatedMass:7.8,holeVolume:.0625,sandMoist:10,refMdd:115,sandMinComp:95}).results.dryDensity,113.45,.001],
 ['Aggregates · one-sieve passing %',()=>catalogCalculate('sieve',{sampleMass:1000,retainedMass:225,sieveSize:'No 4',passMin:null,passMax:null}).results.percentPassing,77.5,0],
 ['Concrete · cylinder psi',()=>catalogCalculate('cylinder',{breakLoad:141372,diameter:4,age:28,designStrength:null}).results.strengthPsi,11250.03,.001],
 ['Concrete · unit weight pcf',()=>catalogCalculate('unit_weight',{fullMass:56,emptyMass:20.8,calVolume:.25,uwMin:null,uwMax:null}).results.unitWeightPcf,140.8,0],
 ['Asphalt · bulk SG',()=>catalogCalculate('asphalt_core',{dryCore:1160,ssdCore:1165,underCore:674,gmmCore:2.5,rcMin:null,rcMax:null}).results.bulkSG,2.36,0],
 ['Asphalt · air voids %',()=>catalogCalculate('asphalt_voids',{gmb:2.35,gmm:2.5,voidMin:null,voidMax:null}).results.airVoidsPercent,6,0],
 ['Reject · zero reference density',()=>inputErrors('soil',{wet:126,moisture:11.8,mdd:0,minComp:95}).length>0,true,0],
 ['Reject · inverted wet/dry oven masses',()=>catalogErrors('soil_moisture',{massWet:180,massDry:190,tare:90}).length>0,true,0],
 ['Reject · invalid sieve-stack order',()=>{const d=advTemplate('sieve_stack');d.points[1].mm=d.points[0].mm;return advancedErrors('sieve_stack',d).length>0},true,0],
 ['Cylinder set · mixed ages never mean',()=>{const d=advTemplate('cylinder_set');d.points[1].age=7;return calcAdvanced('cylinder_set',d).results.setMeanPsi},null,0],
 ['Proctor · end-point peak rejects fitted peak',()=>{const d=advTemplate('proctor_curve');d.points=[{moisture:5,wet:140},{moisture:7,wet:139},{moisture:9,wet:136},{moisture:11,wet:130}];return 'illustrativePeakMdd' in calcAdvanced('proctor_curve',d).results},false,0],
 ['Sieve stack · 1.5% mass loss',()=>{const d=advTemplate('sieve_stack');d.points[d.points.length-1].mass=45;return calcAdvanced('sieve_stack',d).results.massDifferencePct},1.5,0]
];
function runValidationFixtures(){const rows=calcFixtures.map(([name,fn,expected,tolerance])=>{try{const actual=fn();const pass=typeof expected==='number'?typeof actual==='number'&&Math.abs(actual-expected)<=tolerance+1e-9:actual===expected;return {name,expected,actual,pass}}catch(e){return{name,expected,actual:String(e),pass:false}}});$('fixtureSummary').textContent=`${rows.filter(x=>x.pass).length}/${rows.length} synthetic calculation/regression checks passed. These fixtures do NOT demonstrate ASTM procedural compliance, OCR accuracy, or production readiness.`;
 $('fixtureRows').innerHTML=rows.map(x=>`<tr><td>${esc(x.name)}</td><td class="mono">${esc(x.expected===null?'null':x.expected)}</td><td class="mono">${esc(x.actual===null?'null':x.actual)}</td><td>${x.pass?'✓ PASS':'✕ FAIL'}</td></tr>`).join('');return rows;}
function currentPilotSource(){return txt('valSourceFilter')}
function renderPilot(){const source=currentPilotSource(),labels=vdb.labels.filter(x=>x.source===source),pairs=vdb.pairs.filter(x=>x.source===source),a=pilotLabelMetrics(labels),b=pilotTimeMetrics(pairs);
 $('pilotMetrics').innerHTML=`<div class="detailgrid"><div><small>Verified extracted fields</small><strong>${a.total}</strong></div><div><small>Field match rate</small><strong>${a.total?fmtMetric(a.accuracy)+'%':'Not measured'}</strong></div><div><small>Critical field misses (incl. abstain)</small><strong>${a.criticalTotal?a.criticalErrors:'Not measured'}</strong></div><div><small>Paired tasks measured</small><strong>${b.n}</strong></div><div><small>Median minutes saved / task</small><strong>${b.n?fmtMetric(b.medianSaved)+' min':'Not measured'}</strong></div><div><small>Total minutes saved</small><strong>${b.n?fmtMetric(b.totalSaved)+' min':'Not measured'}</strong></div></div><p class="tiny muted">Source: ${esc(source)} only. AI extraction quality is measured per verified gold-value/AI draft pair, not inferred from calculator fixtures. Paired time results include correction minutes and can be negative.</p>`;
 $('labelRows').innerHTML=labels.length?labels.slice(-100).reverse().map(x=>`<tr><td>${esc(x.caseId)} · ${esc(PILOT_FIELDS[x.field]?.label||x.field)}</td><td class="mono">${esc(x.gold)}</td><td class="mono">${esc(x.pred||'ABSTAIN')}</td><td>${esc(labelResult(x))}</td><td><button class="btn small" data-del-label="${esc(x.id)}">Delete</button></td></tr>`).join(''):'<tr><td colspan="5">No labeled fields yet.</td></tr>';
 $('pairRows').innerHTML=pairs.length?pairs.slice(-100).reverse().map(x=>`<tr><td>${esc(x.caseId)} · ${esc(x.testType)}</td><td>${esc(x.baseline)}</td><td>${esc(x.assisted)} + ${esc(x.correction)}</td><td>${fmtMetric(x.baseline-x.assisted-x.correction)} min</td><td><button class="btn small" data-del-pair="${esc(x.id)}">Delete</button></td></tr>`).join(''):'<tr><td colspan="5">No paired time observations yet.</td></tr>';
 $('labelRows').querySelectorAll('[data-del-label]').forEach(b=>b.onclick=()=>{if(!confirm('Delete this local labeled field?'))return;vdb.labels=vdb.labels.filter(x=>x.id!==b.dataset.delLabel);validationSave();renderPilot()});
 $('pairRows').querySelectorAll('[data-del-pair]').forEach(b=>b.onclick=()=>{if(!confirm('Delete this local timed task?'))return;vdb.pairs=vdb.pairs.filter(x=>x.id!==b.dataset.delPair);validationSave();renderPilot()});}
function addPilotLabel(){const f=txt('valField'),caseId=txt('valCase'),gold=txt('valGold'),pred=txt('valPred'),tolerance=txt('valTol'),info=PILOT_FIELDS[f],source=txt('valSource');if(!caseId||caseId.length>64||!gold||gold.length>80||pred.length>80||!info){$('valStatus').textContent='Enter a non-identifying case ID, one field and the independently verified reference value.';return}
 const tol=info.kind==='number'&&isPlainNumber(tolerance)?Number(tolerance):info.kind==='id'?0:NaN;
 const x={id:pilotId(),caseId,field:f,gold,pred,tolerance:tol,unit:info.unit,source,time:now()};if(labelResult(x)==='invalid'||(info.kind==='number'&&(!isPlainNumber(gold)||pred!==''&&!isPlainNumber(pred)))){$('valStatus').textContent='Invalid numeric gold value, candidate value, or tolerance. Blank candidate means abstain.';return}
 if(vdb.labels.length>=2000){$('valStatus').textContent='Label limit reached. Export and archive before adding more.';return}vdb.labels.push(x);validationSave();$('valStatus').textContent=`Saved as ${source} case. Outcome: ${labelResult(x)}. No original document was uploaded.`;renderPilot()}
function addPilotPair(){const caseId=txt('timeCase'),testType=txt('timeType'),source=txt('timeSource'),vals=['timeManual','timeAssist','timeCorrection'].map(txt);if(!caseId||caseId.length>64||vals.some(x=>!isPlainNumber(x))){$('timeStatus').textContent='Enter a case ID and valid numeric minutes.';return}
 const [baseline,assisted,correction]=vals.map(Number);if(baseline<=0||assisted<0||correction<0||[baseline,assisted,correction].some(x=>x>1440)){$('timeStatus').textContent='Baseline must be positive; other durations nonnegative; all <= 1440 minutes.';return}
 if(vdb.pairs.length>=2000){$('timeStatus').textContent='Study limit reached. Export and archive.';return}
 vdb.pairs.push({id:pilotId(),caseId,testType,baseline,assisted,correction,source,time:now()});validationSave();$('timeStatus').textContent='Paired task recorded. These are user-entered times, not measured automatically.';renderPilot()}
function pilotExport(){const payload={schema:1,product:'CMT Intelligence OS v0.8',study:'Non-certified pilot measurements',generatedAt:now(),notes:'No full source documents or images. Numeric tolerance is evaluation tolerance, not ASTM acceptance precision.',labels:vdb.labels,pairs:vdb.pairs};download('CMT_pilot_evaluation_v08.json',JSON.stringify(payload,null,2),'application/json')}
function loadSyntheticPilot(){if(!confirm('Append 3 clearly marked SYNTHETIC field labels and 2 SYNTHETIC timing cases? They do NOT count toward authorized results.'))return;
 for(const [caseId,field,gold,pred,tolerance] of [['SYN-001','wet','126.0','126',.01],['SYN-001','moisture','11.8','18.8',.1],['SYN-002','proctor_id','DEMO-P-01','',0]])vdb.labels.push({id:pilotId(),caseId,field,gold,pred,tolerance,unit:PILOT_FIELDS[field].unit,source:'synthetic',time:now()});
 for(const [caseId,baseline,assisted,correction] of [['SYN-001',6.5,3,1],['SYN-002',5,4,2]])vdb.pairs.push({id:pilotId(),caseId,testType:'NDG',baseline,assisted,correction,source:'synthetic',time:now()});validationSave();$('valSourceFilter').value='synthetic';renderPilot()}
function renderValidation(){renderPilot();if(!$('fixtureRows').children.length)runValidationFixtures()}
$('valField').innerHTML=Object.entries(PILOT_FIELDS).map(([k,v])=>`<option value="${esc(k)}">${esc(v.label)}${v.critical?' · CRITICAL':''}</option>`).join('');
function selectedPilotField(){const p=PILOT_FIELDS[txt('valField')];$('valFieldHelp').textContent=p.kind==='number'?`Reference unit: ${p.unit}. Numeric evaluation tolerance is absolute, not a project acceptance tolerance.`:'Identifier comparison ignores capitalization and repeated spaces; enter no personal details.';$('valTol').disabled=p.kind==='id';$('valTol').value=p.kind==='id'?'0':'0';}
$('valField').onchange=selectedPilotField;selectedPilotField();
$('runFixtures').onclick=runValidationFixtures;
$('addLabel').onclick=addPilotLabel;
$('addTime').onclick=addPilotPair;
$('valSourceFilter').onchange=renderPilot;
$('loadPilotDemo').onclick=loadSyntheticPilot;
$('exportPilot').onclick=pilotExport;
$('resetPilot').onclick=()=>{if(!confirm('Permanently delete all locally stored validation labels AND timing cases? Export first.'))return;vdb=validationStarter();validationSave();renderPilot()};
