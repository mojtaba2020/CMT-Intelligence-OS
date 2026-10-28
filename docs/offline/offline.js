(()=>{'use strict';
const S=window.CMTOffline,Q=window.CMTQueue,C=window.CMTTestCatalog,DEM=window.CMTDemoSeed,$=id=>document.getElementById(id);
let pass=null,draft=null,version=null,selectedId=null,dirty=false,changeCounter=0,saveTimer=null,saveChain=Promise.resolve(),saving=false;
const cache=new Map();
function note(msg,err=false){$('offStatus').textContent=msg;$('offStatus').style.color=err?'#ffb6aa':'#90ded8';}
function showSave(message,mode='neutral') {const el=$('saveIndicator');if(!el)return;el.textContent=message;el.dataset.mode=mode;}
function showBackupReminder(count){const el=$('backupReminder');if(!el)return;
  if(count>=1800)el.textContent='DANGER: '+count+' local records; near the 2,000-record safety limit. Export a VERIFIED encrypted backup and archive old reports.';
  else if(count>=300)el.textContent=count+' local records. Large vaults can be slow to unlock. Export a verified encrypted backup after each shift and archive older tests.';
  else el.textContent='Local browser storage is not a durable backup. Export and verify an encrypted archive after every shift.';
}

function dayNow(){return new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);}
function blank(context={}){const category=C[context.category]?context.category:'density';return {client_id:crypto.randomUUID(),category,test_date:context.test_date||dayNow(),values:{},rows:C[category].rows.length?[{}]:[],project_id:context.project_id||null};}
function valueInputs(){const values={};$('categoryValues').querySelectorAll('[data-offvalue]').forEach(i=>values[i.dataset.offvalue]=i.value);return values;}
function writeModel(){if(!draft)return;draft.test_date=$('offDate').value;draft.values=valueInputs();draft.project_id=$('projectOffline').value?Number($('projectOffline').value):null;for(const el of document.querySelectorAll('[data-offrow]')){const i=Number(el.dataset.offrow);draft.rows[i][el.dataset.offcol]=el.value;}}
function scheduleSave(){if(!pass||!draft)return;dirty=true;changeCounter++;showSave('Unsaved changes · saving shortly…','pending');clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveNow(true).catch(e=>{showSave('Save failed · retry Save encrypted now','error');note(e.message,true)}),500);}
async function saveNow(auto=false){
 clearTimeout(saveTimer);if(!pass||!draft)return;writeModel();showSave('Encrypting and saving on this device…','pending');
 if(draft.conflict_guard)throw Error('Conflicted report is locked. Create a separate copy or review the conflict online.');
 S.validateDraft(draft);saving=true;const copy=structuredClone(draft),id=copy.client_id,checkpoint=changeCounter,password=pass;
 saveChain=saveChain.catch(()=>{}).then(async()=>{
   const latest=await Q.one(id),existing=latest?latest.version:null;
   if(existing!==version)throw Error('Offline report changed in another tab. Reopen it before saving.');
   const r=await Q.put(password,copy,version,'queued');cache.set(id,{version:r.version,draft:copy});
   if(draft?.client_id===id){version=r.version;if(changeCounter===checkpoint)dirty=false;}
   await list();await updateStorageIndicator();if(!auto)note('Encrypted locally. This standalone app does NOT submit to an engineer.');
 });try{await saveChain;showSave(dirty?'More edits to save…':'Saved encrypted locally · '+new Date().toLocaleTimeString(),dirty?'pending':'saved');}
 catch(e){showSave('Save failed · do not close this page','error');throw e}
 finally{saving=false;}return saveChain;
}
async function prepareSwitch(){clearTimeout(saveTimer);if(dirty&&draft?.conflict_guard){note('Conflicting copy is locked. Create a separate copy first.',true);return false;}else if(dirty){try{await saveNow(true)}catch(e){note(e.message,true);return false;}}await saveChain.catch(()=>{});return true;}
function render(){if(!draft)return;const def=C[draft.category];$('editor').hidden=false;$('title').textContent=def.name+' · #'+draft.client_id.slice(0,8);$('offDate').value=draft.test_date;$('projectOffline').value=draft.project_id||'';$('projectOffline').disabled=!!draft.server_id;$('offCategory').value=draft.category;$('offCategory').disabled=!!draft.server_id;
 $('testHint').textContent=def.notes;$('serverRef').textContent=draft.conflict_guard?'CONFLICT LOCKED — create a separate copy.':draft.server_id?`Server report #${draft.server_id}, base revision ${draft.base_revision}`:'Local draft · not submitted to engineer';
 const valueRoot=$('categoryValues');valueRoot.replaceChildren();for(const [key,label] of def.fields){const wrap=document.createElement('label');wrap.textContent=label;const input=document.createElement('input');input.maxLength=400;input.autocomplete='off';input.dataset.offvalue=key;input.value=draft.values[key]||'';wrap.append(input);valueRoot.append(wrap)}
 $('rows').replaceChildren();$('readingHeading').textContent=def.rows.length?'Repeatable readings':'No repeatable reading rows';$('addRow').hidden=!def.rows.length;
 draft.rows.forEach((r,i)=>{const section=document.createElement('section');section.className='offline-row';const heading=document.createElement('h4');heading.textContent='Reading '+(i+1);section.append(heading);const grid=document.createElement('div');grid.className='offline-grid';for(const [key,label] of def.rows){const wrap=document.createElement('label');wrap.textContent=label;const input=document.createElement('input');input.maxLength=400;input.autocomplete='off';input.dataset.offrow=i;input.dataset.offcol=key;input.value=r[key]||'';wrap.append(input);grid.append(wrap)}section.append(grid);const del=document.createElement('button');del.type='button';del.className='danger';del.textContent='Remove reading';del.onclick=()=>{writeModel();draft.rows.splice(i,1);render();scheduleSave()};section.append(del);$('rows').append(section)});
}
async function decrypted(item){const cached=cache.get(item.id);if(cached?.version===item.version)return cached.draft;const read=await Q.read(pass,item.id);cache.set(item.id,{version:item.version,draft:read.draft});return read.draft;}
async function list(){const items=await Q.all(),root=$('vaultList');root.replaceChildren();let visible=0,byType={};const day=$('dayFilter').value;
 for(const item of items){let data;try{data=await decrypted(item)}catch(e){note('Cannot decrypt vault. Check passphrase, or an encrypted record may be corrupted.',true);throw e;}
 if(day&&data.test_date!==day)continue;visible++;byType[data.category]=(byType[data.category]||0)+1;
 const div=document.createElement('div');div.className='offline-row';const label=document.createElement('strong');label.textContent=`${data.test_date} · ${C[data.category]?.name||data.category} · ${data.project_id?'Project #'+data.project_id:'project unassigned'} · ${item.state}`;div.append(label);
 const meta=document.createElement('p');meta.className='hint';meta.textContent=`Record ${item.id.slice(0,8)} · ${data.rows.length} readings · ${new Date(item.updated_at).toLocaleString()}`;div.append(meta);
 const button=document.createElement('button');button.className='outline';button.textContent='Open';button.onclick=async()=>{try{if(!await prepareSwitch())return;const result=await Q.read(pass,item.id);draft=result.draft;version=result.version;selectedId=item.id;dirty=false;render();note('Local record opened. Changes auto-save encrypted.');}catch(e){note(e.message,true)}};div.append(button);
 const repeat=document.createElement('button');repeat.className='outline';repeat.textContent='Repeat test · blank results';repeat.onclick=async()=>{try{if(!await prepareSwitch())return;const copy=blank({category:data.category,test_date:data.test_date,project_id:data.project_id});const shared=['location','samplingLocation','site','supplier','mixDesign','method','soilDescription','proctorNumber','testName'];for(const key of shared){if(data.values[key])copy.values[key]=data.values[key];}draft=copy;version=null;selectedId=copy.client_id;dirty=false;render();await saveNow();note('Independent blank repeat saved. Measurements are blank.');}catch(e){note(e.message,true)}};div.append(repeat);
 if(item.error){const p=document.createElement('p');p.className='hint';p.textContent=item.error;div.append(p)}root.append(div);}
 $('vaultCount').textContent=String(items.length);showBackupReminder(items.length);$('daySummary').textContent=`${visible} shown of ${items.length} saved · `+Object.entries(byType).map(([k,n])=>`${C[k]?.name||k}: ${n}`).join(' · ');
 if(!visible)root.textContent='No saved tests match this day. Choose All days or create a test.';
}
async function updateStorageIndicator(){
 const el=$('storageHealth');if(!el)return;
 try{const estimate=await navigator.storage?.estimate?.();
   const used=estimate?.usage,quota=estimate?.quota;
   const usage=Number.isFinite(used)?(used/1024/1024).toFixed(1)+' MB used':'usage unknown';
   const percent=Number.isFinite(quota)&&quota>0?` · ${(100*used/quota).toFixed(1)}% of browser quota`:'';
   el.textContent='Device vault: '+usage+percent+' · Storage can be evicted; encrypted exports are essential.';
 }catch{el.textContent='Storage quota unavailable. Save encrypted backups regularly.';}
}
$('unlockForm').onsubmit=async e=>{e.preventDefault();try{const p=$('draftPass').value;
 const existing=await Q.all();
 if(existing.length){
   // Reject a wrong key before changing UI state or allowing a mixed-key vault.
   const first=await S.unseal(p,existing[0].envelope);
   if(first.client_id.toLowerCase()!==existing[0].id.toLowerCase())throw Error('Encrypted vault identity mismatch');
 }
 pass=p;
  $('draftPass').value='';
  // Do not import legacy records from unrelated apps sharing this HTTPS origin.
  await list();
  await updateStorageIndicator();
  $('unlockForm').hidden=true;
  $('vaultControls').hidden=false;
  showSave('Vault unlocked · encrypted local storage ready.','success');
 try{if(navigator.storage?.persist) await navigator.storage.persist();}catch{}
 note('Unlocked for this tab. Multiple types and repeat tests are supported.');}catch(err){pass=null;cache.clear();$('unlockForm').hidden=false;$('vaultControls').hidden=true;showSave('Vault locked.','neutral');note(err.message,true)}};
let demoImportBusy=false;
$('loadDemo').onclick=async()=>{
 if(demoImportBusy)return;
 if(!pass)return note('Unlock the vault before adding demo tests.',true);
 if(!await prepareSwitch())return;
 if(!confirm('Load up to 10 SYNTHETIC training reports dated Oct 28, 2026? Existing reports are kept and matching test IDs are skipped. No network upload. Export a backup first if you have important data.'))return;
 demoImportBusy=true;$('loadDemo').disabled=true;
 try{
  if(!DEM)throw Error('Demo test catalog was not loaded. Reload online once.');
  const originals=await Q.all(), seen=new Set();
  for(const item of originals){const entry=await Q.read(pass,item.id);const label=DEM.identity(entry.draft);if(label)seen.add(label);}
  const demos=DEM.build(()=>crypto.randomUUID());
  for(const demo of demos)S.validateDraft(demo);
  const missing=demos.filter(d=>!seen.has(DEM.identity(d)));
  if(originals.length+missing.length>Q.LIMIT)throw Error('Offline storage limit reached. No new demo reports created.');
  let added=0;
  for(const item of missing){await Q.put(pass,item,null,'queued');added++;}
  cache.clear();$('dayFilter').value=DEM.DATE;
  await list();await updateStorageIndicator();
  note('Synthetic demo loaded: '+added+' new reports; '+(demos.length-added)+' matching reports already existed. All are encrypted on this device.');
  showSave('Demo import saved encrypted locally · '+new Date().toLocaleTimeString(),'saved');
 }catch(err){note('Demo import stopped: '+err.message+' Re-run to add missing demo IDs without duplicates.',true);}
 finally{demoImportBusy=false;$('loadDemo').disabled=false;}
};
$('newDraft').onclick=async()=>{if(!await prepareSwitch())return;draft=blank({test_date:$('dayFilter').value||dayNow()});version=null;dirty=false;selectedId=draft.client_id;render();try{await saveNow();note('New blank report already encrypted and saved. Enter readings; they will auto-save.');}catch(e){note(e.message,true)}};
$('offCategory').onchange=()=>{if(!draft)return;const next=$('offCategory').value;if(next===draft.category)return;if(draft.server_id){$('offCategory').value=draft.category;return note('Server-synced test type is immutable; create a separate test.',true);}if(!C[next])return;
 writeModel();
 if(Object.values(draft.values).some(Boolean)||draft.rows.some(x=>Object.values(x).some(Boolean))){if(!confirm('Switch test type? Existing unsaved field values and readings for this test will be cleared.')){$('offCategory').value=draft.category;return;}}
 draft.category=next;draft.values={};draft.rows=C[next].rows.length?[{}]:[];render();scheduleSave();};
$('addRow').onclick=()=>{if(!draft||!C[draft.category].rows.length)return;writeModel();if(draft.rows.length>=100)return note('Maximum 100 readings per test',true);draft.rows.push({});render();scheduleSave()};
$('save').onclick=async()=>{try{await saveNow()}catch(err){note(err.message,true)}};
$('makeCopy').onclick=async()=>{if(!draft)return;if(!draft.conflict_guard&&!await prepareSwitch())return;writeModel();if(!confirm('Create a separate draft with COPIED readings? Every measurement must be checked. For repeat tests use the blank-results button in the saved list.'))return;draft={...draft,client_id:crypto.randomUUID(),conflict_guard:false,server_id:undefined,base_revision:undefined,bound_user_id:undefined,rows:draft.rows.map(x=>({...x})),values:{...draft.values}};version=null;dirty=false;selectedId=draft.client_id;render();try{await saveNow();note('Independent copy encrypted and saved. Validate every copied reading.');}catch(e){note(e.message,true)}};
$('erase').onclick=async()=>{clearTimeout(saveTimer);await saveChain.catch(()=>{});if(!selectedId||version===null)return note('Select a saved draft first',true);if(!confirm('Permanently remove encrypted local report? Export a backup first.'))return;try{await Q.erase(selectedId,version);cache.delete(selectedId);draft=null;version=null;dirty=false;selectedId=null;$('editor').hidden=true;await list();note('Encrypted report removed.')}catch(e){note(e.message,true)}};
$('lock').onclick=async()=>{if(!await prepareSwitch())return;pass=null;cache.clear();draft=null;version=null;dirty=false;selectedId=null;$('editor').hidden=true;$('editor').querySelectorAll('input').forEach(i=>i.value='');$('categoryValues').replaceChildren();$('vaultControls').hidden=true;$('unlockForm').hidden=false;$('rows').replaceChildren();note('Vault locked. No uploads while locked.');};
$('dayFilter').onchange=()=>{if(pass)list().catch(e=>note(e.message,true));};$('clearFilter').onclick=()=>{$('dayFilter').value='';list().catch(e=>note(e.message,true));};
$('exportVault').onclick=async()=>{try{if(!await prepareSwitch())return;const contents=await Q.backup(pass);const blob=new Blob([contents],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='cmt-encrypted-tests-'+dayNow()+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);note('Encrypted backup cryptographically checked before download. Confirm the actual file exists in Files/Downloads.');}catch(e){note(e.message,true)}};
$('importVault').onchange=async e=>{const f=e.target.files?.[0];if(!f)return;try{if(f.size>32*1024*1024)throw Error('Backup too large');if(!await prepareSwitch())return;const count=await Q.restore(await f.text(),pass);cache.clear();await list();note('Imported '+count+' encrypted records.');}catch(err){note(err.message,true)}finally{e.target.value=''}};
window.addEventListener('beforeunload',e=>{if(dirty||saving){e.preventDefault();e.returnValue='Unsaved encrypted field test';}});
window.addEventListener('pagehide',()=>{if(pass&&dirty)saveNow(true).catch(()=>{});});
$('editor').addEventListener('input',scheduleSave);$('editor').addEventListener('change',e=>{if(e.target.id!=='offCategory')scheduleSave()});document.addEventListener('visibilitychange',()=>{if(document.hidden&&dirty)saveNow(true).catch(()=>{})});
for(const [key,def] of Object.entries(C)){const option=document.createElement('option');option.value=key;option.textContent=def.name;$('offCategory').append(option);}
$('dayFilter').value=dayNow();$('title').textContent='Unlock encrypted multi-test vault · v3.8.2';showSave('Vault locked.','neutral');note('Install while online, then work offline. Export backups frequently; browser storage can be cleared.');
})();
