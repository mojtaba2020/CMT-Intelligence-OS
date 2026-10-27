/* CMT Mobile field math / review rules. Neutral, synthetic-first, no automatic engineering acceptance. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.CMTCore=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const CURRENT='cmt-mobile-2.0';
  const numeric=x=>{if(x===null||x===undefined||String(x).trim()==='')return null;const s=String(x).trim();if(!/^-?(?:\d+\.?\d*|\.\d+)$/.test(s))return null;const n=Number(s);return Number.isFinite(n)?n:null;};
  const round=(n,p=1)=>Number(n.toFixed(p));
  const dry=(wet,moisture)=>{wet=numeric(wet);moisture=numeric(moisture);return wet!==null&&wet>0&&moisture!==null&&moisture>=0&&moisture<=100?wet/(1+moisture/100):null;};
  const compaction=(dryDensity,maxDry)=>{dryDensity=numeric(dryDensity);maxDry=numeric(maxDry);return dryDensity!==null&&dryDensity>0&&maxDry!==null&&maxDry>0?100*dryDensity/maxDry:null;};
  const issue=(type,level,code,message,ref)=>({type,level,code,message,ref:ref||''});
  function assessRecord(rec){
    const a=[],v=rec.values||{};const rows=rec.rows||[];
    if(!rec.projectKey||!rec.date)a.push(issue('identity','needs-review','PROJECT_DATE_REQUIRED','Project and date required',rec.id));
    if(rec.type==='density'){
      const p=numeric(v.page),n=numeric(v.pageTotal);
      if((p!==null&&(!Number.isInteger(p)||p<1||p>200))||(n!==null&&(!Number.isInteger(n)||n<1||n>200))||(p!==null&&n!==null&&p>n))a.push(issue('paging','needs-review','PAGE_INVALID','Invalid page numbering',rec.id));
      if(!rows.length)a.push(issue('completeness','needs-review','EMPTY_TABLE','No density tests entered',rec.id));
      rows.forEach((r,i)=>{
        const pref=`${rec.id}#${i+1}`,wet=numeric(r.wet),m=numeric(r.moisture),reported=numeric(r.dry),ref=numeric(r.mdd),reportedPct=numeric(r.percent);
        if(!String(r.testId||'').trim())a.push(issue('identity','needs-review','TEST_ID_REQUIRED',`Row ${i+1}: test ID required`,pref));
        if([r.wet,r.moisture,r.dry].some(x=>numeric(x)===null))a.push(issue('completeness','needs-review','REQUIRED_DENSITY',`Row ${i+1}: density/moisture value missing or invalid`,pref));
        if((wet!==null&&wet<=0)||(m!==null&&(m<0||m>100))||(reported!==null&&reported<=0)||(ref!==null&&ref<=0))a.push(issue('range','needs-review','INVALID_RANGE',`Row ${i+1}: measurement out of expected numerical range`,pref));
        const expected=dry(r.wet,r.moisture);
        if(expected!==null&&reported!==null&&Math.abs(expected-reported)>1.0)a.push(issue('arithmetic','conflict','DRY_MISMATCH',`Row ${i+1}: dry density ${round(reported)} vs calculated ${round(expected)} pcf`,pref));
        const calc=compaction(r.dry,r.mdd);
        if(reportedPct!==null&&calc!==null&&Math.abs(calc-reportedPct)>0.6)a.push(issue('arithmetic','conflict','PERCENT_MISMATCH',`Row ${i+1}: reported ${round(reportedPct)}% vs calculated ${round(calc)}%`,pref));
        if(reportedPct!==null&&ref===null)a.push(issue('reference','needs-review','PROCTOR_REQUIRED',`Row ${i+1}: max dry density / Proctor reference missing`,pref));
      });
    }
    if(rec.type==='concrete'){
      ['slump','air','temperature'].forEach(k=>{if(String(v[k]??'').trim()!==''&&numeric(v[k])===null)a.push(issue('range','needs-review','INVALID_NUMBER',`${k} must be a number`,rec.id));});
      const air=numeric(v.air),slump=numeric(v.slump),temp=numeric(v.temperature);
      if(air!==null&&(air<0||air>30))a.push(issue('range','needs-review','AIR_RANGE','Air content outside broad screening range',rec.id));
      if(slump!==null&&(slump<0||slump>18))a.push(issue('range','needs-review','SLUMP_RANGE','Slump outside broad screening range',rec.id));
      if(temp!==null&&(temp<0||temp>150))a.push(issue('range','needs-review','TEMP_RANGE','Concrete temp outside broad screening range',rec.id));
    }
    if(rec.type==='daily'){
      for(const k of ['densityCount','castCount','pickupCount']){
        if(String(v[k]??'').trim()==='')continue;const q=numeric(v[k]);if(q===null||q<0||!Number.isInteger(q))a.push(issue('range','needs-review','COUNT_INVALID',`${k} must be whole number >= 0`,rec.id));
      }
    }
    return a;
  }
  function assessCollection(records){
    const issues=[];const per=new Map();
    for(const r of records){const individual=assessRecord(r);per.set(r.id,individual);issues.push(...individual);}
    const groups=new Map();
    for(const r of records){const groupKey=`${r.projectKey||''}|${r.date||''}`;if(!groups.has(groupKey))groups.set(groupKey,[]);groups.get(groupKey).push(r);}
    for(const [group,rs] of groups){
      const dens=rs.filter(r=>r.type==='density'); const dailies=rs.filter(r=>r.type==='daily');
      const allIds=new Set(); for(const r of dens){const series=String(r.values?.series||'').trim();const key=`${series}|${r.values?.page}`;if(series&&r.values?.page&&allIds.has(key))issues.push(issue('paging','conflict','DUPLICATE_PAGE',`Duplicate density page ${key}`,r.id));if(series&&r.values?.page)allIds.add(key);}
      const seriesGroups=new Map();for(const r of dens){const series=String(r.values?.series||'').trim();if(!series)continue;if(!seriesGroups.has(series))seriesGroups.set(series,[]);seriesGroups.get(series).push(r);}
      for(const [series,sheets] of seriesGroups){const totals=new Set(sheets.map(r=>numeric(r.values.pageTotal)).filter(x=>x!==null));if(totals.size>1)issues.push(issue('paging','conflict','PAGE_TOTAL_CONFLICT',`Series ${series}: inconsistent total pages`,sheets[0].id));const total=[...totals][0];if(total&&total<=200){const found=new Set(sheets.map(r=>numeric(r.values.page)).filter(x=>x!==null));for(let j=1;j<=total;j++)if(!found.has(j))issues.push(issue('paging','needs-review','MISSING_PAGE',`Series ${series}: page ${j} not recorded`,sheets[0].id));}}
      const ids=new Set();for(const r of dens)for(const [i,row]of(r.rows||[]).entries()){const id=String(row.testId||'').trim().toUpperCase();if(!id)continue;const key=`${r.values?.series||''}|${id}`;if(ids.has(key))issues.push(issue('identity','conflict','DUPLICATE_TEST',`Repeated test ID ${id}`,`${r.id}#${i+1}`));ids.add(key);}
      for(const daily of dailies){const count=numeric(daily.values?.densityCount);const observed=dens.reduce((s,r)=>s+(r.rows||[]).length,0);if(count!==null&&count!==observed)issues.push(issue('cross-form','needs-review','COUNT_UNRECONCILED',`Daily lists ${count} density tests; captured detail contains ${observed} (may be incomplete)`,daily.id));
        const cast=numeric(daily.values?.castCount);const inConcrete=rs.filter(r=>r.type==='concrete').reduce((sum,r)=>sum+(numeric(r.values?.castCount)||0),0);if(cast!==null&&cast!==inConcrete)issues.push(issue('cross-form','needs-review','CYLINDER_COUNT_UNRECONCILED',`Daily reports ${cast} cylinders cast; captured concrete forms show ${inConcrete}`,daily.id));
      }
    }
    return issues;
  }
  function pendingCount(records){let count=0;for(const r of records){const req=['projectKey','date'];for(const k of req)if(!r.checked?.[k])count++;for(const [k,v]of Object.entries(r.values||{}))if(String(v??'').trim()&&!r.checked?.[k])count++;for(const row of(r.rows||[]))if(!row.reviewed)count++;}return count;}
  function createDemo(){const now='2026-10-26',key='DEMO-010',mk=(id,type,values,rows=[])=>({id,projectKey:key,date:now,type,values,rows,checked:{},photoIds:[],note:'SYNTHETIC — demo only',createdAt:now});return[
    mk('demo-daily','daily',{densityCount:'3',castCount:'4',pickupCount:'0',notes:'Synthetic inspection day'}),
    mk('demo-dens-1','density',{series:'SER-01',page:'1',pageTotal:'2'},[{testId:'T-01',station:'26+00',lift:'1',wet:'119.6',moisture:'12.0',dry:'106.8',mdd:'112.0',percent:'95.4',reviewed:false},{testId:'T-02',station:'26+25',lift:'1',wet:'122.4',moisture:'11.0',dry:'108.0',mdd:'112.0',percent:'96.4',reviewed:false}]),
    mk('demo-conc-1','concrete',{slump:'4.5',air:'5.5',temperature:'77',castCount:'4',supplier:'Sample Ready Mix',samplingLocation:'Demo manhole'}),
  ];}
  const CATEGORY=['density','concrete','daily','rebar'];
  const OPTIONS={density:'Soil density',concrete:'Concrete',daily:'General report',rebar:'Rebar observation'};
  return {CURRENT,numeric,round,dry,compaction,assessRecord,assessCollection,pendingCount,createDemo,CATEGORY,OPTIONS};
});
