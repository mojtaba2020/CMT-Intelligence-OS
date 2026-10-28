/* Encrypted, multi-report IndexedDB vault. Never store plaintext draft data in IndexedDB.
   Queue is intentionally NOT synchronized by a service worker: unlock + authenticated session are required. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.CMTQueue=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const DB='cmt-encrypted-standalone-v38', STORE='drafts', LIMIT=2000, MAX_BACKUP=32*1024*1024;
const ID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function open(){return new Promise((resolve,reject)=>{if(!globalThis.indexedDB)return reject(Error('IndexedDB unavailable on this device'));const r=indexedDB.open(DB,1);r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains(STORE))r.result.createObjectStore(STORE,{keyPath:'id'});};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error||Error('Cannot open offline vault'));r.onblocked=()=>reject(Error('Close other tabs using the offline vault'));});}
async function all(){const db=await open();return new Promise((res,rej)=>{const tx=db.transaction(STORE,'readonly'),req=tx.objectStore(STORE).getAll();req.onsuccess=()=>res(req.result.sort((a,b)=>b.updated_at-a.updated_at));req.onerror=()=>rej(req.error);tx.oncomplete=()=>db.close();tx.onerror=()=>{db.close();rej(tx.error)};});}
async function one(id){const db=await open();return new Promise((res,rej)=>{const tx=db.transaction(STORE,'readonly'),req=tx.objectStore(STORE).get(id);req.onsuccess=()=>res(req.result||null);req.onerror=()=>rej(req.error);tx.oncomplete=()=>db.close();tx.onerror=()=>{db.close();rej(tx.error)};});}
function mutate(id, transform){return open().then(db=>new Promise((resolve,reject)=>{let done=false,output;const tx=db.transaction(STORE,'readwrite'),s=tx.objectStore(STORE),r=s.get(id);r.onsuccess=()=>{try{const next=transform(r.result||null);if(next===null)s.delete(id);else s.put(next);output=next;}catch(e){done=true;tx.abort();reject(e);}};r.onerror=()=>{done=true;tx.abort();reject(r.error)};tx.oncomplete=()=>{db.close();if(!done)resolve(output)};tx.onabort=()=>{db.close();if(!done)reject(tx.error||Error('Offline save was cancelled'))};tx.onerror=()=>{db.close()};}));}
const summary=r=>({id:r.id,version:r.version,state:r.state,updated_at:r.updated_at,error:r.error||''});
async function put(pass,draft,expectedVersion=null,state='queued'){
 const S=globalThis.CMTOffline;if(!S)throw Error('Encryption module missing');S.validateDraft(draft);
 const id=draft.client_id.toLowerCase();if(!ID.test(id))throw Error('Invalid report ID');
 const encrypted=await S.seal(pass,draft);
 if(expectedVersion===null&&(await all()).length>=LIMIT)throw Error('Offline vault reached the 2,000-record safety limit. Export and reconcile earlier drafts.');
 const item=await mutate(id,current=>{if(expectedVersion===null&&current)throw Error('Draft already exists; select it instead');if(expectedVersion!==null&&(!current||current.version!==expectedVersion))throw Error('Draft changed in another tab. Reload before saving');return {id,envelope:encrypted,version:(current?.version||0)+1,state,updated_at:Date.now(),error:''};});return summary(item);
}
async function read(pass,id){const r=await one(id);if(!r)throw Error('Draft not found');return {...summary(r),draft:await globalThis.CMTOffline.unseal(pass,r.envelope)};}
async function status(id,version,state,error=''){if(!['queued','conflict','synced','blocked'].includes(state))throw Error('Invalid sync state');const next=await mutate(id,r=>{if(!r||r.version!==version)throw Error('Draft changed; refresh before updating sync status');return {...r,state,error:String(error).slice(0,180),updated_at:Date.now(),version:r.version+1};});return summary(next);}
async function erase(id,version){return mutate(id,r=>{if(!r||r.version!==version)throw Error('Draft changed; refresh before deleting');return null;});}
async function backup(pass){const entries=await all();
 if(pass!==undefined){if(typeof pass!=='string'||pass.length<12)throw Error('Unlock before exporting');for(const item of entries){
   const report=await globalThis.CMTOffline.unseal(pass,item.envelope);
   if(report.client_id.toLowerCase()!==item.id.toLowerCase())throw Error('Encrypted record identity mismatch. Backup cancelled.');
 }}const payload={type:'CMT_ENCRYPTED_OFFLINE_BACKUP',version:1,created_at:new Date().toISOString(),items:entries};const body=JSON.stringify(payload);if(body.length>MAX_BACKUP)throw Error('Encrypted backup too large');return body;}
async function restore(data,pass){
 if(typeof pass!=='string'||pass.length<12)throw Error('Unlock the vault before importing a backup');
 if(typeof data!=='string'||data.length>MAX_BACKUP)throw Error('Backup too large');
 let doc;try{doc=JSON.parse(data)}catch{throw Error('Invalid backup JSON')}
 if(doc?.type!=='CMT_ENCRYPTED_OFFLINE_BACKUP'||doc.version!==1||!Array.isArray(doc.items)||doc.items.length>LIMIT)throw Error('Unsupported encrypted archive');
 // Decrypt and verify ALL archive entries before altering the vault. This prevents
 // wrong-passphrase imports from poisoning an otherwise readable vault.
 const ids=new Set(), incoming=[];
 for(const record of doc.items){
   if(!record||!ID.test(record.id)||!Number.isInteger(record.version)||record.version<1||
      typeof record.envelope!=='string'||record.envelope.length>150000||
      !['queued','conflict','synced','blocked'].includes(record.state)||ids.has(record.id.toLowerCase()))throw Error('Corrupted or duplicate archive entry');
   let draft;try{draft=await globalThis.CMTOffline.unseal(pass,record.envelope)}
   catch{throw Error('Backup cannot be decrypted with the unlocked vault passphrase. Nothing was imported.');}
   if(draft.client_id.toLowerCase()!==record.id.toLowerCase())throw Error('Backup record identity mismatch. Nothing was imported.');
   ids.add(record.id.toLowerCase());incoming.push({...record,id:record.id.toLowerCase(),draft});
 }
 // Existing records are never overwritten or downgraded. Refuse the whole import
 // if a record ID is reused with different contents (no silent data loss).
 const originals=await all();const existing=new Map(originals.map(x=>[x.id,x]));
 for(const item of incoming){const current=existing.get(item.id);if(!current)continue;
   let saved;try{saved=await globalThis.CMTOffline.unseal(pass,current.envelope)}catch{throw Error('Existing vault cannot be decrypted. Import cancelled.');}
   if(JSON.stringify(saved)!==JSON.stringify(item.draft))throw Error('Backup conflicts with an existing report ID; export your current vault before resolving. Nothing was imported.');
 }
 if(originals.length+incoming.filter(x=>!existing.has(x.id)).length>LIMIT)throw Error('Offline vault would exceed its 2,000-record safety limit. Nothing was imported.');
 const db=await open();return new Promise((resolve,reject)=>{
   const tx=db.transaction(STORE,'readwrite'),store=tx.objectStore(STORE);let inserted=0,failed=false;
   const req=store.getAll();
   req.onsuccess=()=>{try{
     const latest=new Map(req.result.map(x=>[x.id,x]));
     if(latest.size+incoming.filter(x=>!latest.has(x.id)).length>LIMIT)throw Error('Offline vault changed during import. Capacity exceeded.');
     for(const item of incoming){if(latest.has(item.id)){
       const prior=existing.get(item.id);
       if(!prior||prior.version!==latest.get(item.id).version||prior.envelope!==latest.get(item.id).envelope)throw Error('Offline vault changed during import. Retry.');
       continue;
     }
       store.put({id:item.id,envelope:item.envelope,version:1,state:item.state,updated_at:Date.now(),error:''});inserted++;
     }
   }catch(e){failed=true;tx.abort();reject(e)}};
   req.onerror=()=>{failed=true;tx.abort();reject(req.error||Error('Archive read failed'))};
   tx.oncomplete=()=>{db.close();if(!failed)resolve(inserted)};
   tx.onabort=()=>{db.close();if(!failed)reject(tx.error||Error('Import failed; nothing was changed'))};
   tx.onerror=()=>{};
 });
}
async function legacy(pass){
 const S=globalThis.CMTOffline;if(!S?.has())return false;
 const d=await S.load(pass),existing=await one(d.client_id.toLowerCase());
 if(existing){
   const current=await S.unseal(pass,existing.envelope);
   if(JSON.stringify(current)!==JSON.stringify(d))throw Error('Legacy draft has same ID but different data. Export old local draft before migrating.');
 }else await put(pass,d);
 S.clear();return true;
}

return {open,all,one,put,read,status,erase,backup,restore,legacy,summary,DB,LIMIT};
});
