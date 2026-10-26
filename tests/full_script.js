
'use strict';
const $=id=>document.getElementById(id), KEY='cmt-intelligence-os-v06', PREV_KEY='cmt-intelligence-os-v05', OLD_KEY='cmt-intelligence-os-v04', OLDER_KEY='cmt-intelligence-os-v03', FIRST_KEY='cmt-intelligence-os-v02';
const now=()=>new Date().toISOString(),round=n=>Math.round((n+Number.EPSILON)*100)/100,txt=id=>$(id).value.trim(),nval=id=>Number(txt(id));
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const localTime=()=>{const d=new Date();return new Date(d.getTime()-d.getTimezoneOffset()*6e4).toISOString().slice(0,16)};

// v0.6: stand-alone configurable multi-test catalog. This is NOT a replacement for licensed standards.
const CATALOG={
 soil_moisture:{name:'Soil — Oven moisture',group:'Soil',standard:'ASTM D2216',note:'Computes gravimetric water content from three recorded masses; oven procedure and drying completeness are not validated.',fields:[
  ['massWet','Container + moist soil (g)',210,0,100000],['massDry','Container + dry soil (g)',190,0,100000],['tare','Empty container mass (g)',90,0,100000]]},
 atterberg:{name:'Soil — Atterberg limits',group:'Soil',standard:'ASTM D4318',note:'Computes PI from entered LL/PL. Does not perform multi-point liquid-limit test or verify apparatus/procedure.',fields:[
  ['ll','Liquid limit LL (%)',42,0,200],['pl','Plastic limit PL (%)',23,0,200],['piMax','Project PI maximum (%) · optional',20,0,200,'optional']]},
 proctor:{name:'Soil — Proctor summary',group:'Soil',standard:'ASTM D698 / D1557',note:'Transcribes MDD and OMC from an independently approved Proctor curve; this does NOT calculate a compaction curve.',fields:[
  ['maxDry','Approved MDD (pcf)',121,1,300],['optMoist','Approved OMC (%)',12,0,100],['proctorMethod','Standard or modified effort', 'Standard (D698)',null,null,'text']]},
 sand_cone:{name:'Soil — Sand cone density',group:'Soil',standard:'ASTM D1556',note:'Calculates wet and dry densities from excavated wet mass, calibrated hole volume and independent moisture test.',fields:[
  ['excavatedMass','Moist excavated soil (lb)',7.8,0.001,10000],['holeVolume','Calibrated hole volume (ft³)',0.0625,0.00001,100],['sandMoist','Moisture content (%)',10,0,100],['refMdd','Approved reference MDD (pcf)',115,1,300],['sandMinComp','Project minimum compaction (%)',95,0,110]]},
 sieve:{name:'Aggregate — Single-sieve checkpoint',group:'Aggregates',standard:'ASTM C136 / C117',note:'One cumulative-retained sieve checkpoint only; not a full sieve stack, washing procedure or standard gradation test.',fields:[
  ['sampleMass','Dry sample mass (g)',1000,0.001,1e7],['retainedMass','Cumulative retained mass on selected sieve (g)',225,0,1e7],['sieveSize','Sieve designation', 'No. 4 (4.75 mm)',null,null,'text'],['passMin','Project passing minimum (%) · optional',70,0,100,'optional'],['passMax','Project passing maximum (%) · optional',90,0,100,'optional']]},
 cylinder:{name:'Concrete — Cylinder compressive strength',group:'Concrete',standard:'ASTM C39',note:'Calculates single-cylinder strength; acceptance of concrete requires the governing specification, specimen set and age criteria.',fields:[
  ['breakLoad','Recorded maximum load (lbf)',141372,0.001,1e8],['diameter','Measured average diameter (in)',4,0.1,24],['age','Specimen age (days)',28,0.01,730],['designStrength','Project reference strength f′c (psi) · optional',4000,0,50000,'optional']]},
 unit_weight:{name:'Concrete — Fresh unit weight',group:'Concrete',standard:'ASTM C138',note:'Computes fresh concrete unit weight from container calibration volume and masses; not full yield/air computation.',fields:[
  ['fullMass','Container + concrete (lb)',56.0,0,100000],['emptyMass','Empty container (lb)',20.8,0,100000],['calVolume','Calibrated container volume (ft³)',0.25,0.001,100],['uwMin','Job minimum (pcf) · optional',135,0,300,'optional'],['uwMax','Job maximum (pcf) · optional',155,0,300,'optional']]},
 asphalt_core:{name:'Asphalt — Core bulk SG / %Gmm',group:'Asphalt',standard:'ASTM D2726 / D2041',note:'Estimates bulk SG from dry/SSD/submerged masses and % of supplied Gmm; method applicability and water-temperature corrections are not checked.',fields:[
  ['dryCore','Core dry mass in air (g)',1160,0.001,1e7],['ssdCore','Core SSD mass in air (g)',1165,0.001,1e7],['underCore','Core submerged mass (g)',674,0,1e7],['gmmCore','Approved theoretical maximum SG Gmm',2.5,0.01,5],['rcMin','Project minimum %Gmm · optional',92,0,110,'optional'],['rcMax','Project maximum %Gmm · optional',98,0,110,'optional']]},
 asphalt_voids:{name:'Asphalt — Air voids from SG',group:'Asphalt',standard:'ASTM D2041 / D2726',note:'Calculates air voids from supplied Gmm and Gmb; does not itself test either specific gravity.',fields:[
  ['gmb','Bulk specific gravity Gmb',2.35,0.01,5],['gmm','Maximum theoretical specific gravity Gmm',2.50,0.01,5],['voidMin','Project air void minimum (%) · optional',3,0,100,'optional'],['voidMax','Project air void maximum (%) · optional',6,0,100,'optional']]},
 rebar_cover:{name:'Inspection — Rebar concrete cover',group:'Inspection',standard:'Approved structural plans / project requirements',note:'Field cover checkpoint only. Cover requirements and allowable tolerances must come from approved drawings/specifications.',fields:[
  ['cover','Measured clear cover (in)',2,0,30],['coverMin','Required cover minimum (in)',1.5,0,30],['coverMax','Allowed cover maximum (in) · optional',3,0,30,'optional'],['barRef','Bar/element ID','DEMO-RB-1',null,null,'text']]}
};
const CATALOG_KEYS=Object.keys(CATALOG);
function catalogErrors(type,d){const x=CATALOG[type],errors=[];if(!x)return ['Unknown test type.'];
 for(const [k,label,_def,min,max,mode] of x.fields){
  if(mode==='text'){if(!String(d[k]||'').trim())errors.push(`${label} is required.`);continue}
  const v=d[k];if(mode==='optional'&&v==null)continue;
  if(typeof v!=='number'||!Number.isFinite(v))errors.push(`${label} must be a valid number.`);
  else if(v<min||v>max)errors.push(`${label} outside demonstrator input bounds (${min}–${max}).`);
 }
 const greater=(a,b,msg)=>{if(Number.isFinite(d[a])&&Number.isFinite(d[b])&&!(d[a]>d[b]))errors.push(msg)};
 switch(type){
 case 'soil_moisture':greater('massWet','massDry','Wet mass must exceed dry mass.');greater('massDry','tare','Dry + container mass must exceed container mass.');break;
 case 'atterberg':if(d.ll<d.pl)errors.push('LL must not be below PL.');break;
 case 'sieve':if(d.retainedMass>d.sampleMass)errors.push('Cumulative retained cannot exceed sample mass.');break;
 case 'unit_weight':greater('fullMass','emptyMass','Full container must exceed empty container mass.');break;
 case 'asphalt_core':greater('ssdCore','underCore','SSD mass must exceed submerged mass.');if(d.ssdCore<d.dryCore)errors.push('SSD mass cannot be less than dry mass.');break;
 case 'sand_cone':break;
 }
 const pairs={sieve:['passMin','passMax'],unit_weight:['uwMin','uwMax'],asphalt_core:['rcMin','rcMax'],asphalt_voids:['voidMin','voidMax']};
 if(pairs[type]){const [a,b]=pairs[type];if(d[a]!=null&&d[b]!=null&&d[a]>d[b])errors.push('Project minimum cannot exceed maximum.');}
 if(type==='rebar_cover'&&d.coverMax!=null&&d.coverMin>d.coverMax)errors.push('Cover minimum cannot exceed maximum.');
 return errors;
}
function catalogCalculate(type,d){const f=[],v={},fmt=(x)=>round(x),check=(key,min,max,unit)=>{
 if(min!=null&&v[key]<min||max!=null&&v[key]>max)f.push(`${key} ${fmt(v[key])}${unit} is outside entered project bounds ${min??'—'}–${max??'—'}${unit}. Review source/specification.`)};
 switch(type){
 case 'soil_moisture': v.waterContent=fmt(100*(d.massWet-d.massDry)/(d.massDry-d.tare));break;
 case 'atterberg':v.plasticityIndex=fmt(d.ll-d.pl);if(d.piMax!=null&&v.plasticityIndex>d.piMax)f.push(`PI ${v.plasticityIndex}% exceeds project maximum ${d.piMax}%.`);break;
 case 'proctor':v.maxDry=fmt(d.maxDry);v.optMoist=fmt(d.optMoist);f.push('Reference Proctor curve and test method/effort require independent engineer verification.');break;
 case 'sand_cone':v.wetDensity=fmt(d.excavatedMass/d.holeVolume);v.dryDensity=fmt((d.excavatedMass/d.holeVolume)/(1+d.sandMoist/100));v.compaction=fmt(v.dryDensity/d.refMdd*100);if(v.compaction<d.sandMinComp)f.push(`Calculated compaction ${v.compaction}% is below entered job minimum ${d.sandMinComp}%.`);break;
 case 'sieve':v.percentPassing=fmt(100*(1-d.retainedMass/d.sampleMass));check('percentPassing',d.passMin,d.passMax,'%');break;
 case 'cylinder':v.strengthPsi=fmt(d.breakLoad/(Math.PI*d.diameter*d.diameter/4));if(d.designStrength!=null&&v.strengthPsi<d.designStrength)f.push(`Single cylinder ${v.strengthPsi} psi is below entered f′c reference ${d.designStrength} psi; this is NOT a concrete acceptance decision.`);break;
 case 'unit_weight':v.unitWeightPcf=fmt((d.fullMass-d.emptyMass)/d.calVolume);check('unitWeightPcf',d.uwMin,d.uwMax,' pcf');break;
 case 'asphalt_core':v.bulkSG=fmt(d.dryCore/(d.ssdCore-d.underCore));v.relativeGmm=fmt(v.bulkSG/d.gmmCore*100);check('relativeGmm',d.rcMin,d.rcMax,'%');if(v.bulkSG>d.gmmCore)f.push('Bulk SG exceeds theoretical maximum SG: verify sources, sampling, units and applicability.');break;
 case 'asphalt_voids':v.airVoidsPercent=fmt(100*(1-d.gmb/d.gmm));check('airVoidsPercent',d.voidMin,d.voidMax,'%');if(d.gmb>d.gmm)f.push('Gmb exceeds Gmm: check source data; reported air voids are physically implausible.');break;
 case 'rebar_cover':v.coverMeasured=d.cover;check('coverMeasured',d.coverMin,d.coverMax,' in');break;
 }
 return {flags:f,results:v};
}
function formatCatalogValues(type,r){const c=CATALOG[type];if(!c)return[];const items=c.fields.map(([k,label])=>[label, r.data[k]==null?'Not specified':String(r.data[k])]);for(const [k,v] of Object.entries(r.results||{}))items.push([({waterContent:'Calculated water content (%)',plasticityIndex:'Calculated PI (%)',wetDensity:'Wet density (pcf)',dryDensity:'Dry density (pcf)',compaction:'Compaction (%)',percentPassing:'Selected sieve passing (%)',strengthPsi:'Single-cylinder strength (psi)',unitWeightPcf:'Unit weight (pcf)',bulkSG:'Bulk SG',relativeGmm:'Density (% Gmm)',airVoidsPercent:'Air voids (%)',coverMeasured:'Cover reading (in)'})[k]||k,String(v)]);items.push(['Indicative test method',c.standard]);return items}

const required={soil:['wet','moisture','mdd','minComp'],concrete:['slump','slumpMin','slumpMax','air','airMin','airMax','temp','tempMax']};
for(const [t,c] of Object.entries(CATALOG))required[t]=c.fields.filter(f=>f[5]!=='optional'&&f[5]!=='text').map(f=>f[0]);
const labels={wet:'Wet density',moisture:'Moisture content',mdd:'Reference dry density',minComp:'Required compaction',slump:'Slump',slumpMin:'Minimum slump',slumpMax:'Maximum slump',air:'Air content',airMin:'Minimum air',airMax:'Maximum air',temp:'Temperature',tempMax:'Maximum temperature'};
function evaluate(type,d){if(CATALOG[type])return catalogCalculate(type,d);const flags=[],results={};if(type==='soil'){
  const rawDry=d.wet/(1+d.moisture/100);results.dryDensity=round(rawDry);results.compaction=round(100*rawDry/d.mdd);results.compactionUnrounded=round(100000*(100*rawDry/d.mdd))/100000;
  if(100*rawDry/d.mdd<d.minComp)flags.push(`Compaction ${results.compactionUnrounded}% (unrounded evaluation) is below the entered job requirement of ${d.minComp}%.`);
  if(results.compaction>110)flags.push(`Unusually high compaction ${results.compaction}%; verify Proctor selection and readings.`);
  if(!d.proctor)flags.push('Reference Proctor report number is missing.');
}else{results.slump=d.slump;results.air=d.air;results.temp=d.temp;
  if(d.slump<d.slumpMin||d.slump>d.slumpMax)flags.push(`Slump ${d.slump} in is outside the entered job range ${d.slumpMin}–${d.slumpMax} in.`);
  if(d.air<d.airMin||d.air>d.airMax)flags.push(`Air ${d.air}% is outside the entered job range ${d.airMin}–${d.airMax}%.`);
  if(d.temp>d.tempMax)flags.push(`Concrete temperature ${d.temp}°F exceeds the entered job max ${d.tempMax}°F.`);
 }return {flags,results}}
function contextFlags(rec,records,excludeId=null){
 const flags=[];
 if(!rec.specRef)flags.push('Project specification/revision reference is missing; entered limits are not traceable.');
 if(!rec.evidence)flags.push('Original measurement evidence reference is missing.');
 if(rec.source==='Mapped CSV draft (unverified)' || rec.source==='Transcription draft (unverified)')flags.push('Imported/transcribed values must be checked against original evidence before review.');
 const same=records.find(x=>x.id!==excludeId && x.id!==rec.parentId && !x.replacedBy && x.status!=='returned' &&
  x.project===rec.project && x.type===rec.type && x.location===rec.location && x.date===rec.date &&
  JSON.stringify(x.data)===JSON.stringify(rec.data));
 if(same)flags.push(`Potential duplicate of ${same.id}: same project, location, time and measurements. Check whether this is a separate reading.`);
 return flags;
}
function evaluateFull(rec,records,excludeId=null){const out=evaluate(rec.type,rec.data);return {...out,flags:[...out.flags,...contextFlags(rec,records,excludeId)]}}

function inputErrors(type,d){if(CATALOG[type])return catalogErrors(type,d);const out=[];for(const key of required[type])if(!Number.isFinite(d[key]))out.push(`${labels[key]} must be a finite number.`);
if(type==='soil'){if(!(d.wet>0)||d.wet>1000)out.push('Wet density must be above zero and not exceed the demonstrator safety bound of 1000 pcf.');if(!(d.mdd>0)||d.mdd>1000)out.push('Reference dry density must be above zero and not exceed the demonstrator safety bound of 1000 pcf.');if(d.moisture<0||d.moisture>=100)out.push('Moisture must be at least 0% and below 100%.');if(d.minComp<0||d.minComp>110)out.push('Required compaction must be between 0% and 110%.');}
else{if(d.slump<0||d.slump>24||d.slumpMin<0||d.slumpMax>24)out.push('Slump and its project limits must be in 0–24 in for this demo.');if(d.air<0||d.air>100||d.airMin<0||d.airMax>100)out.push('Air values must be in 0–100%.');if(d.slumpMin>d.slumpMax)out.push('Slump min cannot exceed max.');if(d.airMin>d.airMax)out.push('Air min cannot exceed max.');if(d.temp<0||d.temp>250||d.tempMax<0||d.tempMax>250)out.push('Temperatures must be in 0–250°F for this demo.');}
return out}
function sample(){const a={id:'DEMO-S-001',parentId:null,version:1,type:'soil',project:'DEMO-001',tech:'Example Technician',location:'Area A / lift 2',date:localTime(),source:'Synthetic demo',evidence:'SAMPLE-NDG-FORM',specRef:'DEMO-SPEC-REV-A',data:{wet:126,moisture:11.8,mdd:120,minComp:95,proctor:'DEMO-PROCTOR-01'},status:'review',reviewer:'',note:''};const b={id:'DEMO-C-002',parentId:null,version:1,type:'concrete',project:'DEMO-001',tech:'Example Technician',location:'Slab pour / truck 12',date:localTime(),source:'Synthetic demo',evidence:'SAMPLE-TRUCK-12',specRef:'DEMO-SPEC-REV-A',data:{slump:5.25,slumpMin:4,slumpMax:6,air:5.2,airMin:4,airMax:7,temp:78,tempMax:95,mix:'DEMO-MIX'},status:'review',reviewer:'',note:''};for(const a0 of [a,b])Object.assign(a0,evaluate(a0.type,a0.data));return{schema:6,records:[a,b],audit:[{time:now(),event:'DEMO INIT',id:'—',actor:'System',detail:'Synthetic testing data; not actual field measurements.'}]}}
function isRecord(r){return r&&typeof r.id==='string'&&['soil','concrete',...CATALOG_KEYS].includes(r.type)&&r.data&&typeof r.data==='object'&&['review','approved','returned'].includes(r.status)&&Array.isArray(r.flags)&&r.results&&typeof r.results==='object'&&typeof r.project==='string'&&typeof r.tech==='string'&&typeof r.location==='string'&&typeof r.date==='string'}
function migrate(v){
 if(!v || ![2,3,4,5,6].includes(v.schema) || !Array.isArray(v.records) || !v.records.every(isRecord) || !Array.isArray(v.audit))return null;
 if(v.schema===2){for(const r of v.records){r.specRef='';if(r.status==='review'&&!r.flags.includes('Project specification/revision reference is missing; entered limits are not traceable.'))r.flags.push('Project specification/revision reference is missing; entered limits are not traceable.');}
  v.schema=3;v.audit.unshift({time:now(),event:'BACKUP MIGRATED',id:'ALL',actor:'System',detail:'V0.2 records imported; unspecified project-specification references must be verified.'});}
 if(v.schema===3){v.schema=4;v.audit.unshift({time:now(),event:'BACKUP MIGRATED',id:'ALL',actor:'System',detail:'V0.3 records carried forward; no independent evidence check exists for older records.'});}
 if(v.schema===4){v.schema=5;v.audit.unshift({time:now(),event:'BACKUP MIGRATED',id:'ALL',actor:'System',detail:'V0.4 records carried forward; photo drafts are never restored from an older backup.'});}
 if(v.schema===5){v.schema=6;v.audit.unshift({time:now(),event:'BACKUP MIGRATED',id:'ALL',actor:'System',detail:'V0.5 records carried forward into multi-test catalog.'});}
 return v;
}
function load(){try{let raw=localStorage.getItem(KEY);if(!raw)raw=localStorage.getItem(PREV_KEY);if(!raw)raw=localStorage.getItem(OLD_KEY);if(!raw)raw=localStorage.getItem(OLDER_KEY);if(!raw)raw=localStorage.getItem(FIRST_KEY);return migrate(JSON.parse(raw))||sample()}catch{return sample()}}

let db=load(),chosen=db.records[0]?.id||null,editing=null;
const store=()=>{try{localStorage.setItem(KEY,JSON.stringify(db))}catch{$('saveMsg').textContent='Browser storage unavailable. Export JSON backup before closing this page.'}};
function log(event,id,actor,detail){db.audit.unshift({time:now(),event,id,actor,detail})}
function counts(){const q=db.records.filter(r=>r.status==='review');$('total').textContent=db.records.length;$('pending').textContent=q.length;$('flags').textContent=q.filter(r=>r.flags.length).length;$('approved').textContent=db.records.filter(r=>r.status==='approved').length}
function page(name){for(const e of document.querySelectorAll('.page'))e.classList.toggle('hidden',e.id!==name);for(const e of document.querySelectorAll('[data-page]'))e.classList.toggle('on',e.dataset.page===name);if(name==='queue')renderQueue();if(name==='audit')renderAudit();if(name==='reconcile')renderReconcilePicker();if(name==='photo')renderPhotoPicker();if(name==='catalog')renderCatalog()}
for(const e of document.querySelectorAll('[data-page]'))e.addEventListener('click',()=>page(e.dataset.page));
function renderCatalog(){const rows=[['Soil','Soil — NDG field compaction','ASTM D6938','Field density & compaction only','soil'],['Concrete','Fresh concrete slump/air/temp','ASTM C143 / C231 / C1064','Project-entered limits; not full method validation','concrete'],...CATALOG_KEYS.map(k=>[CATALOG[k].group,CATALOG[k].name,CATALOG[k].standard,CATALOG[k].note,k])];$('catalogRows').innerHTML=rows.map(([group,name,std,note,key])=>`<tr><td>${esc(group)}</td><td><strong>${esc(name)}</strong></td><td>${esc(std)}</td><td>${esc(note)}</td><td><button class="btn small" data-use="${esc(key)}">Enter</button></td></tr>`).join('');for(const b of $('catalogRows').querySelectorAll('[data-use]'))b.onclick=()=>{$('testType').value=b.dataset.use;switchType();page('capture')}}
function switchType(){const type=txt('testType');$('soilFields').classList.toggle('hidden',type!=='soil');$('concreteFields').classList.toggle('hidden',type!=='concrete');$('catalogFields').classList.toggle('hidden',!CATALOG[type]);
 if(CATALOG[type]){const c=CATALOG[type];$('catalogHeading').textContent=c.name;$('catalogMethod').textContent=`Indicative: ${c.standard}. ${c.note} Use actual job specification for decisions.`;
 $('catalogForm').innerHTML=c.fields.map(([k,label,def,min,max,mode])=>`<div><label for="${esc(k)}">${esc(label)} ${mode==='optional'?'':'*'}</label><input id="${esc(k)}" ${mode==='text'?'type="text"':'type="number" step="any"'} value="${esc(def)}" ${mode==='text'?'maxlength="120"':''}></div>`).join('');
 if(!editing)$('paste').value=c.fields.map(([k,,def])=>`${k}: ${def}`).join('\n');
 }else if(!editing)$('paste').value=type==='soil'?'wet_density: 126\nmoisture: 11.8\nmax_dry_density: 120\nmin_compaction: 95\nlocation: Area A':'slump: 5.25\nslump_min: 4\nslump_max: 6\nair: 5.2\nair_min: 4\nair_max: 7\ntemperature: 78';
 $('aiExtract').disabled=!aiReady||!!CATALOG[type];
}
$('testType').addEventListener('change',switchType);$('switch').onclick=()=>{$('testType').value=txt('testType')==='soil'?'concrete':'soil';switchType()};$('date').value=localTime();
function readData(type){if(CATALOG[type]){const d={};for(const [k,label,def,min,max,mode] of CATALOG[type].fields){const val=txt(k);d[k]=mode==='text'?val:mode==='optional'&&val===''?null:val===''?NaN:Number(val)}return d}const d={};for(const k of required[type])d[k]=txt(k)===''?NaN:nval(k);if(type==='soil')d.proctor=txt('proctor');else d.mix=txt('mix');return d}
function readCommon(){return{project:txt('project'),tech:txt('tech'),location:txt('location'),date:txt('date'),source:txt('source'),evidence:txt('evidence'),specRef:txt('specRef')}}
function makeID(){let id;do{id='CMT-'+Date.now().toString(36).toUpperCase()+'-'+Math.random().toString(36).slice(2,6).toUpperCase()}while(db.records.some(x=>x.id===id));return id}
function save(){const type=txt('testType'),common=readCommon(),data=readData(type);const err=inputErrors(type,data);
for(const f of ['project','tech','location','date'])if(!common[f])err.push(`${f} is required.`);
if(err.length){$('saveMsg').textContent='Cannot save: '+err.join(' ');return}
const recBase={id:makeID(),type,...common,data,parentId:editing?editing.id:null};const out=evaluateFull(recBase,db.records);const rec={...recBase,...out,status:'review',reviewer:'',note:'',version:editing?editing.version+1:1,parentId:editing?editing.id:null};db.records.unshift(rec);
log(editing?'REVISED':'CREATED',rec.id,rec.tech,`${type} test; ${out.flags.length} flag(s).`+(editing?` Previous version ${editing.id}.`:''));
if(editing){const r=db.records.find(r=>r.id===editing.id);if(r)r.replacedBy=rec.id;editing=null;}
store();counts();chosen=rec.id;resetForm(false);page('queue')}
$('save').onclick=save;
function resetForm(resetValues=true){editing=null;$('entryTitle').textContent='New field test';$('revisionBadge').textContent='New record';$('cancelEdit').classList.add('hidden');$('save').textContent='Save & run QA checks';$('testType').disabled=false;$('saveMsg').textContent='';if(resetValues){$('project').value='DEMO-001';$('tech').value='Training Technician';$('location').value='Area A / lift 2';$('date').value=localTime();$('evidence').value='';$('specRef').value='';}}
$('cancelEdit').onclick=()=>resetForm();
function fillFromRecord(r){editing=r;$('testType').value=r.type;switchType();$('testType').disabled=true;for(const k of ['project','tech','location','date','evidence','specRef'])$(k).value=r[k]||'';$('source').value=['Manual entry','Transcription draft (unverified)','Mapped CSV draft (unverified)','Voice transcript draft (verified)'].includes(r.source)?r.source:'Manual entry';for(const k of required[r.type])$(k).value=r.data[k];if(CATALOG[r.type]){for(const [k] of CATALOG[r.type].fields)$(k).value=r.data[k]??'';}else if(r.type==='soil')$('proctor').value=r.data.proctor||'';else $('mix').value=r.data.mix||'';$('entryTitle').textContent='Correct returned test';$('revisionBadge').textContent=`Version ${r.version+1} · supersedes ${r.id}`;$('cancelEdit').classList.remove('hidden');$('save').textContent='Save corrected version';page('capture');window.scrollTo({top:0,behavior:'smooth'})}
const pasteMap={wet_density:'wet',wet:'wet',moisture:'moisture',water_content:'moisture',max_dry_density:'mdd',mdd:'mdd',min_compaction:'minComp',proctor:'proctor',slump:'slump',slump_min:'slumpMin',slump_max:'slumpMax',air:'air',air_min:'airMin',air_max:'airMax',temperature:'temp',temp:'temp',temp_max:'tempMax',location:'location',project:'project',technician:'tech',mix:'mix',evidence:'evidence',spec_reference:'specRef',spec_ref:'specRef'};
for(const c of Object.values(CATALOG))for(const [k] of c.fields)pasteMap[k.toLowerCase()]=k;
$('applyPaste').onclick=()=>{let count=0;const issues=[],applied=[];const t=txt('testType');const allowed=new Set([...required[t],...['location','project','tech','evidence','specRef'],...(CATALOG[t]?CATALOG[t].fields.map(f=>f[0]):[t==='soil'?'proctor':'mix'])]);for(const line of txt('paste').split(/\r?\n/)){if(!line.trim())continue;const m=line.match(/^\s*([\w ]+)\s*[:=]\s*(.*?)\s*$/);if(!m){issues.push('Unparsed line');continue}const k=pasteMap[m[1].toLowerCase().replace(/\s+/g,'_')];if(!k||!allowed.has(k)){issues.push(m[1]+' not recognized for this test');continue}if($(k).type==='number'){if(!/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(m[2])){issues.push(m[1]+' is not a plain number');continue}$(k).value=m[2]}else $(k).value=m[2];count++;applied.push(k)}if(count)$('source').value='Transcription draft (unverified)';$('pasteMsg').textContent=`Applied ${count} field(s): ${applied.join(', ')}. ${issues.length?'Ignored: '+issues.join('; ')+'. ':''}Every value still requires source verification.`}
let aiReady=false;
async function checkAI(){if(location.protocol==='file:'){ $('aiStatus').textContent='Offline HTML mode. To use AI, start the included local server.';return }try{const response=await fetch('/api/status',{cache:'no-store'});if(!response.ok)throw Error('Unavailable');const data=await response.json();aiReady=!!data.configured;$('aiStatus').textContent=aiReady?'Local AI backend configured. Upload is opt-in and requires authorization.':'Local server detected; set OPENAI_API_KEY to activate extraction.';$('aiExtract').disabled=!aiReady||!!CATALOG[txt('testType')]}catch{$('aiStatus').textContent='AI server not connected. Manual entry and paste adapter still work offline.'}}
$('aiExtract').onclick=async()=>{if(!aiReady){$('aiStatus').textContent='Server unavailable';return}const f=$('imageFile').files?.[0];if(!f){$('aiStatus').textContent='Choose a photo first.';return}if(!['image/jpeg','image/png','image/webp'].includes(f.type)||f.size>4e6){$('aiStatus').textContent='Use JPEG, PNG or WEBP under 4 MB.';return}if(!$('aiConsent').checked){$('aiStatus').textContent='Please confirm authorization before uploading.';return}const data=new FormData();data.append('file',f);data.append('type_hint',txt('testType'));data.append('consent','true');$('aiExtract').disabled=true;$('aiStatus').textContent='Analyzing selected image on the configured AI backend…';try{const response=await fetch('/api/extract',{method:'POST',body:data});const ans=await response.json();if(!response.ok)throw Error(ans.detail||'AI extraction failed');const lines=(ans.fields||[]).map(x=>`${x.key}: ${x.value}`);if(!lines.length)throw Error('No reliable fields detected. Enter them manually.');$('paste').value=lines.join('\n');$('pasteMsg').textContent='Draft from image extraction; click Fill fields from text, then compare against the original photo.';$('aiStatus').textContent=`AI draft: ${lines.length} values. ${ans.uncertain_fields?.length?'Uncertain fields: '+ans.uncertain_fields.join(', ')+'. ':''}${ans.notes||''}`;}catch(err){$('aiStatus').textContent='Extraction unavailable: '+err.message}finally{$('aiExtract').disabled=!aiReady||!!CATALOG[txt('testType')]}};
checkAI();
const stateLabel=r=>r.status==='approved'?'Reviewed':r.status==='returned'?'Returned':r.flags.length?'Needs QA review':'Pending';const pillClass=r=>r.status==='approved'?'approved':r.status==='returned'?'returned':r.flags.length?'flag':'';
function summarize(r){if(CATALOG[r.type])return Object.entries(r.results||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')||'Entered measurements; manual review required';return r.type==='soil'?`Dry density ${r.results.dryDensity} pcf · Compaction ${r.results.compaction}%`:`Slump ${r.data.slump} in · Air ${r.data.air}% · Temp ${r.data.temp}°F`}
function renderQueue(){const search=txt('filterText').toLowerCase(),s=txt('filterStatus');const list=db.records.filter(r=>(s==='all'||s==='flagged'&&r.status==='review'&&r.flags.length||r.status===s)&&[r.id,r.project,r.location,r.tech].some(v=>String(v).toLowerCase().includes(search)));const host=$('records');host.innerHTML='';if(!list.length)host.innerHTML='<div class="empty">No matching test records.</div>';for(const r of list){const row=document.createElement('article');row.className='rowitem'+(chosen===r.id?' selected':'');row.innerHTML=`<div class="between"><h4>${esc(r.project)} · ${esc(CATALOG[r.type]?.name|| (r.type==='soil'?'Soil compaction':'Fresh concrete'))}</h4><span class="pill ${pillClass(r)}">${stateLabel(r)}</span></div><div class="meta">${esc(r.id)} · ${esc(r.location)} · ${esc(r.tech)}</div><div>${esc(summarize(r))}</div><div class="buttons"><button class="btn small">Open</button></div>`;row.querySelector('button').onclick=()=>{chosen=r.id;renderQueue()};host.appendChild(row)}renderDetail()}
for(const id of ['filterText','filterStatus'])$(id).addEventListener('input',renderQueue);
function detailValues(r){if(CATALOG[r.type])return formatCatalogValues(r.type,r);const d=r.data;return r.type==='soil'?[
['Wet density',`${d.wet} pcf`],['Moisture',`${d.moisture}%`],['Dry density',`${r.results.dryDensity} pcf`],['Relative compaction',`${r.results.compaction}%`],['Required compaction',`${d.minComp}%`],['Proctor reference',d.proctor||'Not provided']
]:[['Slump',`${d.slump} in`],['Job slump range',`${d.slumpMin}–${d.slumpMax} in`],['Air',`${d.air}%`],['Job air range',`${d.airMin}–${d.airMax}%`],['Temperature',`${d.temp}°F`],['Job temp max',`${d.tempMax}°F`],['Mix / truck',d.mix||'Not provided']]}
function renderDetail(){const r=db.records.find(x=>x.id===chosen),host=$('detail');if(!r){host.className='empty';host.textContent='Select a record';return}host.className='';host.innerHTML=`<div class="between"><strong class="mono">${esc(r.id)}</strong><span class="pill ${pillClass(r)}">${stateLabel(r)}</span></div><p class="tiny muted">${esc(r.project)} · ${esc(r.location)}<br> ${esc(r.date)} · ${esc(r.source)} · v${r.version}<br> Evidence ref: ${esc(r.evidence||'Not linked')}<br> Project spec/revision: ${esc(r.specRef||'NOT SUPPLIED')}</p><div class="detailgrid">${detailValues(r).map(([k,v])=>`<div><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('')}</div><h3>NDG evidence comparison</h3>${r.type==='soil'?renderEvidenceDetail(r):'<p class="tiny muted">Gauge cross-check currently supports soil NDG only.</p>'}<h3>Automated QA exceptions</h3>${r.flags.length?r.flags.map(f=>`<div class="warning">⚠ ${esc(f)}</div>`).join(''):'<div class="success">No exceptions against entered job limits. This does not constitute ASTM compliance or official acceptance.</div>'}${r.parentId?`<p class="tiny muted">Revision of ${esc(r.parentId)}</p>`:''}${r.replacedBy?`<p class="tiny muted">Superseded by ${esc(r.replacedBy)}</p>`:''}<div class="buttons"><button id="printRecord" class="btn small">Print review worksheet</button></div>`;
if(r.status==='review')host.innerHTML+=`<div style="margin-top:20px"><label for="reviewer">Reviewer (required)</label><input id="reviewer" maxlength="100" placeholder="Engineer / quality reviewer"></div><div style="margin-top:10px"><label for="reason">Decision rationale ${r.flags.length?'(required for exceptions)':''}</label><textarea id="reason" placeholder="Evidence reviewed, acceptance rationale or correction required"></textarea></div><div class="buttons"><button class="btn main" id="approveRecord">Mark manually reviewed</button><button class="btn warn" id="returnRecord">Return for correction</button></div><p class="tiny muted" id="reviewMsg" role="status"></p>`;
else host.innerHTML+=`<div class="note">Decision: ${esc(stateLabel(r))} by ${esc(r.reviewer||'Unknown')}.<br>Rationale: ${esc(r.note||'None')}</div>${r.status==='returned'&&!r.replacedBy?'<div class="buttons"><button id="revise" class="btn main">Create corrected version</button></div>':''}`;
$('printRecord').onclick=()=>printRecord(r);if(r.status==='review'){$('approveRecord').onclick=()=>decision('approved');$('returnRecord').onclick=()=>decision('returned')}else if(r.status==='returned'&&!r.replacedBy)$('revise').onclick=()=>fillFromRecord(r)}
function decision(s){const r=db.records.find(x=>x.id===chosen),who=txt('reviewer'),note=txt('reason');if(!who){$('reviewMsg').textContent='Enter a reviewer name.';return}if((s==='returned'||r.flags.length)&&!note){$('reviewMsg').textContent='A rationale is required for returned or flagged tests.';return}r.status=s;r.reviewer=who;r.note=note;log(s==='approved'?'MANUALLY REVIEWED':'RETURNED',r.id,who,note||'No QA exception against entered limits; source verified by reviewer.');store();counts();renderQueue()}
function renderAudit(){$('auditBody').innerHTML=db.audit.map(a=>`<tr><td>${esc(new Date(a.time).toLocaleString())}</td><td>${esc(a.event)}</td><td class="mono">${esc(a.id)}</td><td>${esc(a.actor)}</td><td>${esc(a.detail)}</td></tr>`).join('')}
function download(filename,s,mime){const u=URL.createObjectURL(new Blob([s],{type:mime})),a=document.createElement('a');a.href=u;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000)}
$('exportJSON').onclick=()=>download('CMT_Intelligence_OS_backup_v06.json',JSON.stringify(db,null,2),'application/json');
function csvCell(v){let s=String(v==null?'':v);if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'}
$('exportCSV').onclick=()=>{const cols=['id','parentId','version','type','project','tech','location','date','source','evidence','specRef','status','reviewer','note','flags','evidenceCheck','wet','moisture','mdd','minComp','dryDensity','compaction','slump','slumpMin','slumpMax','air','airMin','airMax','temp','tempMax','mix','proctor',...new Set(Object.values(CATALOG).flatMap(c=>c.fields.map(f=>f[0])))];const rows=db.records.map(r=>cols.map(k=>csvCell(k==='flags'?r.flags.join(' | '):k==='evidenceCheck'?(r.evidenceChecks?.at(-1)?.status||'NOT CHECKED'):r[k]??r.data[k]??r.results[k]??'')).join(','));download('CMT_Intelligence_OS_records_v06.csv',[cols.join(','),...rows].join('\r\n'),'text/csv;charset=utf-8')};
$('importTrigger').onclick=()=>$('importJSON').click();$('importJSON').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>5e6)throw Error('Backup exceeds 5 MB.');const payload=JSON.parse(await f.text());if(![2,3,4,5,6].includes(payload.schema)||!Array.isArray(payload.records)||!payload.records.every(isRecord)||!Array.isArray(payload.audit)||payload.records.length>5000||payload.audit.length>20000||new Set(payload.records.map(r=>r.id)).size!==payload.records.length)throw Error('Invalid or unsupported backup structure.');if(!confirm(`Replace all local data with ${payload.records.length} imported records?`))return;db=migrate(payload);chosen=db.records[0]?.id||null;store();counts();renderQueue();renderAudit();alert('Backup restored into this browser.')}catch(err){alert('Restore failed: '+err.message)}finally{$('importJSON').value=''}};
$('reset').onclick=()=>{if(confirm('Reset all local records and audit entries to two synthetic examples? Export a backup first.')){db=sample();chosen=db.records[0].id;editing=null;store();counts();renderQueue();renderAudit()}};
function printRecord(r){const table=detailValues(r).map(([k,v])=>`<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('');$('report').innerHTML=`<h1>CMT Intelligence OS — TEST REVIEW WORKSHEET</h1><p>Record: <strong>${esc(r.id)}</strong> | Type: ${esc(r.type)} | Project: ${esc(r.project)}</p><p>Technician: ${esc(r.tech)} | Location: ${esc(r.location)} | Test date: ${esc(r.date)}</p><p>Source: ${esc(r.source)} | NDG comparison: ${esc(r.evidenceChecks?.at(-1)?.status||'NOT CHECKED')} | Evidence reference: ${esc(r.evidence||'Not attached')} | Project spec/revision: ${esc(r.specRef||'NOT SUPPLIED')}</p><table>${table}</table><h3>QA exceptions</h3><p>${r.flags.map(esc).join(' / ')||'None against entered project limits'}</p><p>Status: ${esc(stateLabel(r))} | Reviewer: ${esc(r.reviewer||'Not yet reviewed')}</p><p>Decision note: ${esc(r.note||'None')}</p><div class="printnotice">DEMONSTRATION ONLY. NOT AN OFFICIAL TEST REPORT, ENGINEER'S SIGNATURE, OR ASTM CERTIFICATION. Measurements and project limits require source verification.</div>`;window.print()}

// Neutral CSV intake only; never writes to any vendor's system.
const CSV_COLS=['type','project','tech','location','date','evidence','specRef','wet','moisture','mdd','minComp','proctor','slump','slumpMin','slumpMax','air','airMin','airMax','temp','tempMax','mix',...new Set(Object.values(CATALOG).flatMap(c=>c.fields.map(f=>f[0])))];
const normHeader=s=>String(s).trim().toLowerCase().replace(/[^a-z0-9]/g,'');
const HEADER_ALIASES={
 type:['testtype','testcategory','materialtype'],project:['job','jobnumber','projectnumber','jobno','projectid'],
 tech:['technician','inspector','fieldtechnician'],location:['station','testlocation','lift','pourarea'],
 date:['testdate','testedat','datetime','testdatetime'],evidence:['formref','formnumber','gaugeticket','ticket'],
 specRef:['spec','specification','specificationref','specreference','specificationrevision'],
 wet:['wetdensity','wetdensitypcf','measuredwetdensity'],moisture:['moisturepercent','watercontent'],
 mdd:['maxdrydensity','maximumdrydensity','proctormdd'],minComp:['minimumcompaction','requiredcompaction'],
 proctor:['proctorref','proctornumber','proctorreport'],slump:['slumpin','slumpinches'],
 slumpMin:['minslump','slumpminimum'],slumpMax:['maxslump','slumpmaximum'],
 air:['aircontent','airpercent'],airMin:['minair','airminimum'],airMax:['maxair','airmaximum'],
 temp:['temperature','concretetemperature','tempf'],tempMax:['maxtemp','maximumtemperature'],
 mix:['mixid','mixnumber','truck','trucknumber']};
const LOOKUP={};for(const k of CSV_COLS){LOOKUP[normHeader(k)]=k;for(const a of HEADER_ALIASES[k]||[])LOOKUP[normHeader(a)]=k}
function parseCSV(text){
 const rows=[];let row=[],val='',quoted=false;const s=text.replace(/^\uFEFF/,'');
 for(let i=0;i<s.length;i++){
  const c=s[i];if(quoted){if(c==='"'&&s[i+1]==='"'){val+='"';i++}else if(c==='"')quoted=false;else val+=c}
  else if(c==='"'){if(val!=='')throw Error('Unexpected quote in CSV');quoted=true}
  else if(c===','){row.push(val);val=''}
  else if(c==='\n'||c==='\r'){if(c==='\r'&&s[i+1]==='\n')i++;row.push(val);val='';if(row.some(x=>x!==''))rows.push(row);row=[]}
  else val+=c;
 }
 if(quoted)throw Error('Unclosed CSV quote');row.push(val);if(row.some(x=>x!==''))rows.push(row);
 return rows;
}
function readCSVRecord(row,col,rowNo){
 const f={};for(const [key,idx] of Object.entries(col))f[key]=(row[idx]||'').trim();
 const type=(f.type||'').toLowerCase();if(!['soil','concrete',...CATALOG_KEYS].includes(type))throw Error('Unknown test type: '+type);
 for(const k of ['project','tech','location','date'])if(!f[k])throw Error('Missing '+k);
 if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(f.date)||!Number.isFinite(new Date(f.date).getTime()))throw Error('date must be YYYY-MM-DDTHH:MM');
 const d={};if(CATALOG[type]){for(const [k,label,def,min,max,mode] of CATALOG[type].fields){const raw=f[k]||'';if(mode==='text'){d[k]=raw;continue}if(mode==='optional'&&raw===''){d[k]=null;continue}if(!/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(raw))throw Error('Missing/non-numeric '+k);d[k]=Number(raw)}}else{for(const k of required[type]){if(!/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(f[k]||''))throw Error('Missing/non-numeric '+k);d[k]=Number(f[k]);}if(type==='soil')d.proctor=f.proctor||'';else d.mix=f.mix||'';}
 const errors=inputErrors(type,d);if(errors.length)throw Error(errors.join(' '));
 const rec={id:makeID(),parentId:null,version:1,type,project:f.project.slice(0,80),tech:f.tech.slice(0,80),location:f.location.slice(0,120),date:f.date,
  evidence:(f.evidence||'').slice(0,120),specRef:(f.specRef||'').slice(0,120),source:'Mapped CSV draft (unverified)',data:d,status:'review',reviewer:'',note:'',originRow:rowNo};
 return {...rec,...evaluateFull(rec,db.records)};
}
let csvStaged=null;
$('templateCSV').onclick=()=>{
 const a={type:'soil',project:'DEMO-JOB',tech:'Demo Tech',location:'Station 10+00',date:localTime(),evidence:'DEMO-NDG-1',specRef:'DEMO-SPEC-A',wet:126,moisture:11.8,mdd:120,minComp:95,proctor:'DEMO-PROCTOR'};
 const b={type:'concrete',project:'DEMO-JOB',tech:'Demo Tech',location:'Pour A',date:localTime(),evidence:'DEMO-CONCRETE-1',specRef:'DEMO-SPEC-A',slump:5.25,slumpMin:4,slumpMax:6,air:5.2,airMin:4,airMax:7,temp:78,tempMax:95,mix:'DEMO-MIX'};
 download('CMT_neutral_intake_template.csv',[CSV_COLS.map(csvCell).join(','),...[a,b].map(r=>CSV_COLS.map(k=>csvCell(r[k]??'')).join(','))].join('\r\n'),'text/csv;charset=utf-8');
};
$('csvFile').addEventListener('change',()=>{csvStaged=null;$('commitCSV').disabled=true;$('csvPreview').textContent='';$('csvMsg').textContent='New file selected. Click Validate & preview.'});
$('previewCSV').onclick=async()=>{
 csvStaged=null;$('commitCSV').disabled=true;$('csvPreview').textContent='';const f=$('csvFile').files?.[0];
 if(!f){$('csvMsg').textContent='Choose a CSV first.';return}
 if(f.size>250_000){$('csvMsg').textContent='File must be 250 KB or less.';return}
 try{
  const rows=parseCSV(await f.text());if(rows.length<2||rows.length>151)throw Error('CSV must contain a header and 1–150 data rows.');
  const keys=rows[0].map(h=>LOOKUP[normHeader(h)]||null),col={};keys.forEach((k,i)=>{if(k){if(k in col)throw Error('Duplicate mapped column '+k);col[k]=i}});
  if(!['type','project','tech','location','date'].every(k=>k in col))throw Error('Required columns: type, project, tech, location, date.');
  const accepted=[],rejected=[];
  for(let i=1;i<rows.length;i++){
   try{const rec=readCSVRecord(rows[i],col,i+1);if(rows[i].length!==rows[0].length)throw Error('Column count mismatch');
     if(accepted.some(x=>x.project===rec.project&&x.type===rec.type&&x.location===rec.location&&x.date===rec.date&&JSON.stringify(x.data)===JSON.stringify(rec.data)))rec.flags.push('Possible duplicate of another row in this CSV batch.');
     accepted.push(rec);
   }catch(e){rejected.push({row:i+1,error:String(e.message).slice(0,220)})}
  }
  csvStaged=accepted.length?{accepted,rejected}:null;
  $('commitCSV').disabled=!csvStaged;
  $('csvMsg').textContent=`Preview only: ${accepted.length} valid draft(s), ${rejected.length} rejected. ${accepted.length?'Original evidence still requires human review.':''}`;
  const frag=document.createElement('div');const tbl=document.createElement('table');
  const tr=document.createElement('tr');for(const t of ['Row','Project','Type','Compaction / slump','QA observations']){const th=document.createElement('th');th.textContent=t;tr.appendChild(th)}tbl.appendChild(tr);
  for(const r of accepted.slice(0,30)){const tr=document.createElement('tr');for(const val of [r.originRow,r.project,r.type,r.type==='soil'?r.results.compaction+'%':r.data.slump+' in',r.flags.length+' flagged']){const td=document.createElement('td');td.textContent=val;tr.appendChild(td)}tbl.appendChild(tr)}
  for(const r of rejected.slice(0,20)){const tr=document.createElement('tr');for(const val of [r.row,'REJECTED','', '',r.error]){const td=document.createElement('td');td.textContent=val;tr.appendChild(td)}tbl.appendChild(tr)}
  frag.appendChild(tbl);$('csvPreview').appendChild(frag);
 }catch(e){$('csvMsg').textContent='Could not preview: '+e.message}
};
$('commitCSV').onclick=()=>{
 if(!csvStaged?.accepted.length)return;
 const arr=csvStaged.accepted;if(!confirm(`Add ${arr.length} unverified draft records to the local review queue?`))return;
 for(const r of arr){r.flags=[...evaluateFull(r,db.records).flags,...r.flags.filter(x=>x.includes('another row in this CSV batch'))];db.records.unshift(r);log('IMPORTED DRAFT',r.id,r.tech,'Unverified neutral CSV row '+r.originRow+'; original evidence requires verification.');}
 const rejected=csvStaged.rejected.length;chosen=arr[0].id;csvStaged=null;$('commitCSV').disabled=true;store();counts();renderQueue();
 $('csvMsg').textContent=`Imported ${arr.length} local drafts for review; ${rejected} rejected row(s) were not added. No external system changed.`;page('queue');
};


// ---- NDG evidence comparison: independent typed sources, NEVER an automatic field-acceptance decision. ----
let evPreview=null;
const evNum=id=>txt(id)===''?NaN:Number(txt(id));
const normalizeId=x=>String(x||'').trim().replace(/\s+/g,' ').toUpperCase();
function compareNDGEvidence(r,s){
 if(!r||r.type!=='soil'||r.status!=='review'||r.replacedBy)throw Error('Choose an active soil test awaiting review.');
 for(const k of ['density','moisture','mdd','minComp','tolDensity','tolMoisture'])if(!Number.isFinite(s[k]))throw Error('All independent numerical readings and tolerances must be entered.');
 if(!s.ticket||!s.spec||!s.proctor)throw Error('Printout, project specification and Proctor source references are required.');
 if(!['wet','dry'].includes(s.densityType)||!['pcf','kgm3'].includes(s.unit))throw Error('Unsupported density type or unit.');
 if(!(s.density>0&&s.density<20000&&s.mdd>0&&s.mdd<=1000&&s.moisture>=0&&s.moisture<100&&s.minComp>=0&&s.minComp<=110&&s.tolDensity>=0&&s.tolDensity<=2&&s.tolMoisture>=0&&s.tolMoisture<=2))throw Error('Source numbers/tolerances are outside demonstrator input bounds.');
 const gaugeDensity=s.density*(s.unit==='kgm3'?0.0624279606:1);
 const gaugeWet=s.densityType==='wet'?gaugeDensity:gaugeDensity*(1+s.moisture/100);
 const gaugeDry=s.densityType==='dry'?gaugeDensity:gaugeDensity/(1+s.moisture/100);
 if(gaugeWet>1000)throw Error('Normalized gauge density exceeds demo safety bound. Check unit and printed reading.');
 const checks=[];
 const numeric=(label,fieldValue,sourceValue,tolerance,unit)=>{const delta=fieldValue-sourceValue;checks.push({label,fieldValue:round(fieldValue),sourceValue:round(sourceValue),delta:round(delta),unit,status:Math.abs(delta)<=tolerance+1e-9?'match':'conflict'});};
 const reference=(label,a,b)=>checks.push({label,fieldValue:String(a??''),sourceValue:String(b??''),delta:'—',unit:'',status:normalizeId(a)===normalizeId(b)?'match':'conflict'});
 numeric('Field wet density vs gauge wet density',r.data.wet,gaugeWet,s.tolDensity,'pcf');
 numeric('Field moisture vs gauge moisture',r.data.moisture,s.moisture,s.tolMoisture,'pp');
 numeric('Proctor max dry density',r.data.mdd,s.mdd,0.01,'pcf');
 numeric('Project minimum compaction',r.data.minComp,s.minComp,0.001,'pp');
 reference('Proctor report ID',r.data.proctor,s.proctor);
 if(r.specRef)reference('Specification revision reference',r.specRef,s.spec);
 if(s.project)reference('Project on printout',r.project,s.project);
 if(s.location)reference('Station / lift on printout',r.location,s.location);
 const notes=[];
 if(!s.project)notes.push('Project ID is not independently shown on the transcribed gauge source.');
 if(!s.location)notes.push('Location is not independently shown on the transcribed gauge source.');
 if(!r.evidence)notes.push('Saved field sheet has no evidence reference.');
 if(!r.specRef)notes.push('Saved field sheet has no specification/revision reference.');
 // Relative compaction against independent MDD is informative only, never field acceptance.
 const gaugeCompaction=100*gaugeDry/s.mdd;
 if(gaugeCompaction<s.minComp)notes.push('Gauge-derived compaction is below the separately transcribed project minimum; engineer must investigate.');
 const discrepancies=checks.filter(c=>c.status==='conflict');
 const status=discrepancies.length?'DISCREPANCY':notes.length?'MATCHED_WITH_GAPS':'MATCHED_UNVERIFIED';
 return {status,checks,notes,discrepancies:discrepancies.length,gaugeDry:round(gaugeDry),gaugeWet:round(gaugeWet),gaugeCompaction:round(gaugeCompaction),warning:'Typed source values were not authenticated. All readings, gauges, printouts and project limits require independent verification.'};
}
function renderReconcilePicker(){
 const selector=$('evRecord'),previous=selector.value;
 selector.innerHTML='';
 const eligible=db.records.filter(r=>r.type==='soil'&&r.status==='review'&&!r.replacedBy);
 for(const r of eligible){const opt=document.createElement('option');opt.value=r.id;opt.textContent=`${r.id} · ${r.project} · ${r.location}`;selector.appendChild(opt)}
 if(eligible.some(r=>r.id===previous))selector.value=previous;
 evPreview=null;$('evAttach').disabled=true;
 if(!eligible.length){$('evMessage').textContent='No active pending soil tests. Create a soil test first.';$('evResults').textContent='';}
}
for(const [button,mismatch] of [['evDemoMatch',false],['evDemoMismatch',true]])$(button).onclick=()=>{
 if(txt('evRecord')!=='DEMO-S-001'){$('evMessage').textContent='Synthetic example buttons only work with built-in DEMO-S-001. Enter actual authorized values manually for other records.';return}
 const fixed={evTicket:'DEMO-GAUGE-41',evSpec:'DEMO-SPEC-REV-A',evDensity:String(mismatch?132:126),evMoisture:'11.8',evMDD:'120',evMinComp:'95',evProctor:'DEMO-PROCTOR-01',evProject:'DEMO-001',evLocation:'Area A / lift 2',evTolDensity:'0.10',evTolMoisture:'0.10'};
 for(const [k,v] of Object.entries(fixed))$(k).value=v;
 $('evUnit').value='pcf';$('evDensityType').value='wet';evPreview=null;$('evAttach').disabled=true;$('evResults').textContent='';
 $('evMessage').textContent=`SYNTHETIC ${mismatch?'mismatch':'match'} loaded for training. These values are fictional; click Compare sources.`;
};
$('evRecord').onchange=()=>{evPreview=null;$('evAttach').disabled=true;$('evResults').textContent='';$('evMessage').textContent='Enter values independently from the gauge and approved specification; do not copy the field sheet.'};
for(const id of ['evTicket','evSpec','evDensityType','evUnit','evDensity','evMoisture','evMDD','evMinComp','evProctor','evProject','evLocation','evTolDensity','evTolMoisture'])$(id).addEventListener('input',()=>{evPreview=null;$('evAttach').disabled=true});
$('evCompare').onclick=()=>{
 const r=db.records.find(r=>r.id===$('evRecord').value);
 const source={ticket:txt('evTicket'),spec:txt('evSpec'),densityType:txt('evDensityType'),unit:txt('evUnit'),density:evNum('evDensity'),moisture:evNum('evMoisture'),mdd:evNum('evMDD'),minComp:evNum('evMinComp'),proctor:txt('evProctor'),project:txt('evProject'),location:txt('evLocation'),tolDensity:evNum('evTolDensity'),tolMoisture:evNum('evTolMoisture')};
 try{
  const result=compareNDGEvidence(r,source);const provenance=verifiedPhotoProvenance(r.id);if(provenance.gaps.length)result.notes.push(...provenance.gaps);if(provenance.checks.length){result.checks.push(...provenance.checks);result.discrepancies+=provenance.checks.filter(c=>c.status==='conflict').length;if(result.discrepancies)result.status='DISCREPANCY';}evPreview={recordId:r.id,source,result,provenance:provenance.sources};
  $('evAttach').disabled=false;
  $('evMessage').textContent=`Comparison preview: ${result.discrepancies} discrepancy(s), ${result.notes.length} follow-up note(s). Preview alone changes no record.`;
  const rows=result.checks.map(c=>`<tr><td>${esc(c.label)}</td><td>${esc(c.fieldValue)} ${esc(c.unit)}</td><td>${esc(c.sourceValue)} ${esc(c.unit)}</td><td>${esc(c.delta)} ${esc(c.unit)}</td><td><span class="pill ${c.status==='match'?'approved':'flag'}">${esc(c.status.toUpperCase())}</span></td></tr>`).join('');
  $('evResults').innerHTML=`<h3>${esc(result.status)} · NDG evidence comparison</h3><p class="muted">Gauge-derived wet density: ${result.gaugeWet} pcf · dry density: ${result.gaugeDry} pcf · compaction: ${result.gaugeCompaction}% against the independently entered MDD.</p><div class="tableout"><table><thead><tr><th>Check</th><th>Field sheet</th><th>Independent source</th><th>Field minus source</th><th>Result</th></tr></thead><tbody>${rows}</tbody></table></div>${result.notes.map(n=>`<div class="warning">${esc(n)}</div>`).join('')}<p class="tiny muted">${esc(result.warning)}</p>`;
 }catch(err){evPreview=null;$('evAttach').disabled=true;$('evMessage').textContent='Cannot compare: '+err.message;$('evResults').textContent='';}
};
$('evAttach').onclick=()=>{
 if(!evPreview)return;
 const r=db.records.find(x=>x.id===evPreview.recordId);
 if(!r||r.status!=='review'||r.replacedBy){$('evMessage').textContent='Record is no longer available for review.';return;}
 const snapshot={...structuredClone(evPreview),time:now()};
 r.evidenceChecks=[...(r.evidenceChecks||[]).slice(-29),snapshot];
 r.flags=r.flags.filter(x=>!x.startsWith('Evidence reconciliation:'));
 if(snapshot.result.discrepancies)r.flags.push(`Evidence reconciliation: ${snapshot.result.discrepancies} conflicting field(s) against separately transcribed gauge/specification values.`);
 if(snapshot.result.notes.length)r.flags.push(`Evidence reconciliation: ${snapshot.result.notes.length} unresolved source/engineering note(s); see latest evidence snapshot.`);
 log('EVIDENCE COMPARED',r.id,'Demo evidence reviewer',`${snapshot.result.status}; ${snapshot.result.discrepancies} mismatches; ${snapshot.result.notes.length} notes; typed references: ${snapshot.source.ticket}, ${snapshot.source.spec}.`);
 store();counts();chosen=r.id;evPreview=null;$('evAttach').disabled=true;
 $('evMessage').textContent='Comparison snapshot attached to local record. Status remains PENDING engineering review. Original field measurements were not modified.';
};
function renderEvidenceDetail(r){
 const snapshots=r.evidenceChecks||[],s=snapshots.at(-1);
 if(!s)return '<p class="warning">No independent gauge-vs-form reconciliation has been attached to this record.</p>';
 return `<div class="note"><strong>${esc(s.result.status)}</strong> · ${esc(s.time)}<br>Gauge source: ${esc(s.source.ticket)}<br>Independent specification: ${esc(s.source.spec)}<br>Conflicts: ${s.result.discrepancies}; follow-up notes: ${s.result.notes.length}; snapshots retained: ${snapshots.length}.<br>Typed evidence only — original documents not authenticated.<br>Photo provenance: ${esc(s.provenance?.map(p=>p.source_type+': '+p.mode+(p.source_sha256?' / SHA-256 '+p.source_sha256.slice(0,16)+'…':'')).join('; ')||'Not used')}</div>${s.result.checks.filter(c=>c.status==='conflict').map(c=>`<div class="warning">${esc(c.label)}: saved ${esc(c.fieldValue)} vs source ${esc(c.sourceValue)} ${esc(c.unit)}</div>`).join('')}`;
}


// ---- v0.5: photo source draft staging, never automatic engineering approval. ----
let stagedPhoto=null;
let photoUrl=null;
const appliedPhotos={};
const PHOTO_REQUIRED={
 gauge_printout:['ticket','density','density_type','density_unit','moisture'],
 proctor_spec:['spec','mdd','minComp','proctor']
};
const PHOTO_FIELDS={
 gauge_printout:['ticket','density','density_type','density_unit','moisture','project','location'],
 proctor_spec:['spec','mdd','minComp','proctor','project']
};
const PHOTO_TARGET={
 gauge_printout:{ticket:'evTicket',density:'evDensity',density_type:'evDensityType',density_unit:'evUnit',moisture:'evMoisture',project:'evProject',location:'evLocation'},
 proctor_spec:{spec:'evSpec',mdd:'evMDD',minComp:'evMinComp',proctor:'evProctor'}
};
const PHOTO_LABELS={ticket:'Gauge printout reference',density:'Printed gauge density',density_type:'Wet or dry reading',density_unit:'Printed density unit',moisture:'Printed moisture (%)',project:'Project identifier',location:'Station / location',spec:'Approved spec reference',mdd:'Proctor max dry density (pcf)',minComp:'Job min compaction (%)',proctor:'Proctor report ID'};
const PHOTO_NUMBER=new Set(['density','moisture','mdd','minComp']);
function renderPhotoPicker(){
 const sel=$('photoRecord'),prev=sel.value;
 sel.replaceChildren();
 for(const r of db.records.filter(x=>x.type==='soil'&&x.status==='review'&&!x.replacedBy)){
  const o=document.createElement('option');o.value=r.id;o.textContent=`${r.id} · ${r.project} · ${r.location}`;sel.appendChild(o);
 }
 if([...sel.options].some(o=>o.value===prev))sel.value=prev;
 discardPhotoDraft();updateAppliedPhotoStatus();
}
function discardPhotoDraft(){stagedPhoto=null;$('photoDraft').classList.add('hidden');$('photoRows').replaceChildren();$('photoApply').disabled=true;}
function updateAppliedPhotoStatus(){
 const entries=Object.entries(appliedPhotos[$('photoRecord').value]||{});
 $('photoApplied').textContent=entries.length?entries.map(([kind,a])=>`${kind}: ${a.mode} · ${a.keys.length} checked values · ${a.source_sha256?'SHA-256 '+a.source_sha256.slice(0,16)+'…':'synthetic data only'}`).join(' | '):'No verified source draft transferred for this record in this browser session.';
}
$('photoRecord').addEventListener('change',()=>{discardPhotoDraft();updateAppliedPhotoStatus();});
$('photoKind').addEventListener('change',()=>{discardPhotoDraft();$('photoStatus').textContent='Source category changed; select or generate a new draft.';});
$('photoFile').addEventListener('change',()=>{
 if(photoUrl){URL.revokeObjectURL(photoUrl);photoUrl=null;}
 $('photoPreview').classList.add('hidden');discardPhotoDraft();
 const f=$('photoFile').files?.[0];
 if(f&&['image/png','image/jpeg','image/webp'].includes(f.type)&&f.size<=4e6){photoUrl=URL.createObjectURL(f);$('photoPreview').src=photoUrl;$('photoPreview').classList.remove('hidden');}
 $('photoStatus').textContent=f?`Local image selected: ${f.name}. No upload has occurred.`:'No image selected.';
});
function stagePhoto(ans){
 if(!PHOTO_FIELDS[ans.source_type])throw Error('Unsupported extraction source type.');
 const recordId=$('photoRecord').value;if(!recordId)throw Error('Choose a pending soil record.');
 const filtered=(ans.fields||[]).filter(x=>PHOTO_FIELDS[ans.source_type].includes(x.key)&&typeof x.value==='string');
 stagedPhoto={recordId,source_type:ans.source_type,mode:ans.mode,source_sha256:ans.source_sha256||null,fields:filtered,uncertain_fields:ans.uncertain_fields||[],notes:ans.notes||''};
 const host=$('photoRows');host.replaceChildren();
 for(const field of filtered){
  const tr=document.createElement('tr');tr.dataset.key=field.key;
  const name=document.createElement('td');name.textContent=PHOTO_LABELS[field.key]||field.key;
  const val=document.createElement('td');const input=document.createElement('input');input.value=field.value;input.maxLength=120;input.setAttribute('aria-label',field.key+' extracted value');input.dataset.key=field.key;val.appendChild(input);
  const verified=document.createElement('td');const check=document.createElement('input');check.type='checkbox';check.dataset.verify=field.key;check.setAttribute('aria-label','Verify '+field.key);verified.appendChild(check);
  input.oninput=()=>{check.checked=false;$('photoApply').disabled=false};check.onchange=()=>{$('photoApply').disabled=false};
  tr.append(name,val,verified);host.appendChild(tr);
 }
 $('photoDraft').classList.remove('hidden');$('photoApply').disabled=false;
 $('photoKind').value=ans.source_type;
 const missing=PHOTO_REQUIRED[ans.source_type].filter(k=>!filtered.some(f=>f.key===k));
 $('photoSourceNote').textContent=`${ans.mode==='synthetic'?'SYNTHETIC DEMO — NO IMAGE WAS READ.':'LIVE AI DRAFT — HUMAN VERIFICATION REQUIRED.'} ${ans.source_sha256?'Uploaded bytes SHA-256: '+ans.source_sha256+'.':''} ${ans.uncertain_fields?.length?'Uncertain: '+ans.uncertain_fields.join(', ')+'.':''} ${missing.length?'Missing required fields: '+missing.join(', ')+'. They must be obtained from source; do not invent values.':''} ${ans.notes||''}`;
 $('photoApplyStatus').textContent='Review candidate values and tick verified for each value to be transferred. This is not a source authenticity check.';
 $('photoStatus').textContent=`Draft extracted for ${recordId}: ${filtered.length} proposed fields. No engineering record has changed.`;
}
function syntheticPhoto(kind){
 const ans=kind==='gauge_printout' ? {
 source_type:kind,fields:[{key:'ticket',value:'DEMO-GAUGE-41'},{key:'density',value:'132'},{key:'density_type',value:'wet'},{key:'density_unit',value:'pcf'},{key:'moisture',value:'11.8'},{key:'project',value:'DEMO-001'},{key:'location',value:'Area A / lift 2'}]
 } : {source_type:kind,fields:[{key:'spec',value:'DEMO-SPEC-REV-A'},{key:'mdd',value:'120'},{key:'minComp',value:'95'},{key:'proctor',value:'DEMO-PROCTOR-01'},{key:'project',value:'DEMO-001'}]};
 if($('photoRecord').value!=='DEMO-S-001'){$('photoStatus').textContent='Synthetic samples are for DEMO-S-001 only. Choose that pending record or use authorized documents.';return;}
 stagePhoto({...ans,mode:'synthetic',source_sha256:null,notes:'Fictional training values, never extracted from a real photo.',uncertain_fields:[]});
}
$('photoDemoGauge').onclick=()=>syntheticPhoto('gauge_printout');
$('photoDemoSpec').onclick=()=>syntheticPhoto('proctor_spec');
$('photoClear').onclick=()=>{discardPhotoDraft();$('photoStatus').textContent='Draft discarded.';};
$('photoExtract').onclick=async()=>{
 const f=$('photoFile').files?.[0],kind=txt('photoKind');
 if(!f||!['image/png','image/jpeg','image/webp'].includes(f.type)||!f.size||f.size>4e6){$('photoStatus').textContent='Select JPEG/PNG/WEBP photo between 1 byte and 4 MB.';return;}
 if(!$('photoConsent').checked){$('photoStatus').textContent='Explicit permission and consent are required before upload.';return;}
 if(location.protocol==='file:'){$('photoStatus').textContent='Offline mode cannot call AI. To read a real image, start the included local Python server with your server-side API key.';return;}
 const recordId=$('photoRecord').value;if(!recordId){$('photoStatus').textContent='Choose an active pending soil record.';return;}
 const fdata=new FormData();fdata.append('file',f);fdata.append('consent','true');fdata.append('source_kind',kind);
 discardPhotoDraft();$('photoExtract').disabled=true;$('photoStatus').textContent='Submitting authorized image to local AI backend for draft transcription…';
 try{
  const res=await fetch('/api/evidence/extract',{method:'POST',body:fdata});const obj=await res.json();
  if(!res.ok)throw Error(typeof obj.detail==='string'?obj.detail:'Extraction returned an error');
  if(recordId!==$('photoRecord').value||kind!==$('photoKind').value)throw Error('Selected record or source changed during extraction; discard the stale result.');
  stagePhoto(obj);
 }catch(err){$('photoStatus').textContent='Photo extraction unavailable: '+err.message;}
 finally{$('photoExtract').disabled=false;}
};
$('photoApply').onclick=()=>{
 if(!stagedPhoto)return;
 const a=stagedPhoto;const rec=db.records.find(r=>r.id===a.recordId&&r.type==='soil'&&r.status==='review'&&!r.replacedBy);
 if(!rec||$('photoRecord').value!==a.recordId||txt('photoKind')!==a.source_type){$('photoApplyStatus').textContent='Stale selection; reload the draft for the active soil test.';return;}
 const out={},unchecked=[];
 for(const tr of $('photoRows').querySelectorAll('tr')){
  const k=tr.dataset.key,val=tr.querySelector('input:not([type=checkbox])').value.trim(),checked=tr.querySelector('input[type=checkbox]').checked;
  if(!checked){unchecked.push(k);continue;}
  if(!val){$('photoApplyStatus').textContent='Verified values cannot be blank: '+k;return;}
  if(PHOTO_NUMBER.has(k)&&(!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(val)||!Number.isFinite(Number(val)))){$('photoApplyStatus').textContent='Only plain numeric values are accepted: '+k;return;}
  if(k==='density_type'&&!['wet','dry'].includes(val)||k==='density_unit'&&!['pcf','kgm3'].includes(val)){$('photoApplyStatus').textContent='Unit and density type must match supported explicit options.';return;}
  out[k]=val;
 }
 const missing=PHOTO_REQUIRED[a.source_type].filter(k=>!Object.prototype.hasOwnProperty.call(out,k));
 if(missing.length){$('photoApplyStatus').textContent='Cannot transfer: independently check these REQUIRED source fields: '+missing.join(', ')+'. Missing readings must not be guessed.';return;}
 // A partially verified photo must not silently become an asserted complete source.
 // Discard stale values from this same source category before applying the newly checked image.
 for(const id of Object.values(PHOTO_TARGET[a.source_type]))$(id).value='';
 for(const [key,value] of Object.entries(out)){
  if(PHOTO_TARGET[a.source_type][key])$(PHOTO_TARGET[a.source_type][key]).value=value;
 }
 if(txt('evRecord')!==a.recordId){renderReconcilePicker();$('evRecord').value=a.recordId;}
 const mapped={};for(const [key,value] of Object.entries(out))if(PHOTO_TARGET[a.source_type][key])mapped[PHOTO_TARGET[a.source_type][key]]=value;
 if(!appliedPhotos[a.recordId])appliedPhotos[a.recordId]={};
 appliedPhotos[a.recordId][a.source_type]={source_type:a.source_type,mode:a.mode,source_sha256:a.source_sha256,keys:Object.keys(out),values:out,mapped,verified_at:now(),notices:unchecked};
 evPreview=null;$('evAttach').disabled=true;
 $('photoApplyStatus').textContent=`Transferred ${Object.keys(out).length} visually confirmed ${a.mode==='synthetic'?'DEMO':'AI-draft'} values into the comparison form. They are not accepted, signed or certified. Continue to NDG evidence check and compare.`;
 updateAppliedPhotoStatus();
};
function verifiedPhotoProvenance(recordId){
 const src=[],gaps=[],checks=[],entries=Object.values(appliedPhotos[recordId]||{});
 for(const a of entries){
  if(!Object.entries(a.mapped).every(([id,val])=>$(id).value===val)){
   gaps.push(`Photo-derived ${a.source_type} readings changed after verification. Re-verify the original document.`);continue;
  }
  src.push({source_type:a.source_type,mode:a.mode,source_sha256:a.source_sha256,keys:a.keys,verified_at:a.verified_at});
  if(a.source_type==='proctor_spec'&&a.values.project){
   const rec=db.records.find(x=>x.id===recordId);
   checks.push({label:'Proctor/spec image project vs field form',fieldValue:rec?.project||'',sourceValue:a.values.project,delta:'—',unit:'',status:normalizeId(rec?.project)===normalizeId(a.values.project)?'match':'conflict'});
  }
  if(a.mode==='synthetic')gaps.push('Synthetic training source used; this is not actual instrument/project evidence.');
 }
 if(src.length===1)gaps.push('Only one document category was photo-checked; remaining sources are independent typed values.');
 return {sources:src,gaps,checks};
}

counts();store();switchType();
