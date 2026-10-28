/* CMT v2.6 offline field drafts: encrypted-at-rest browser prototype.
   No server login is possible offline. These are NOT authenticated submissions. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.CMTOffline=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const KEY='cmt-field-v26-encrypted-draft', VERSION=1, ITERATIONS=260000;
  const TEST_CATALOG=globalThis.CMTTestCatalog||(typeof module==='object'&&module.exports?require('./test_catalog.js'):null);
  const bytesToB64=bytes=>{let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s)};
  const b64ToBytes=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  const cryptoAPI=()=>{const c=globalThis.crypto;if(!c?.subtle||!c?.getRandomValues)throw Error('Secure browser context required');return c;};
  function validateDraft(d){
    if(!d||typeof d!=='object'||Array.isArray(d))throw Error('Invalid draft');
    if(!/^[0-9a-f-]{36}$/i.test(d.client_id||''))throw Error('Draft ID missing');
    const def=TEST_CATALOG?.[d.category];if(!def)throw Error('Unknown offline test category');
    if(typeof d.test_date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d.test_date))throw Error('Invalid test date');
    if(!d.values||typeof d.values!=='object'||Array.isArray(d.values)||!Array.isArray(d.rows)||d.rows.length>100)throw Error('Invalid draft fields');
    const allowed=new Set(def.fields.map(x=>x[0]));
    const rowKeys=new Set(def.rows.map(x=>x[0]));
    if(!def.rows.length&&d.rows.length)throw Error('This type has no repeated readings');
    const validMap=(item,permitted)=>item&&typeof item==='object'&&!Array.isArray(item)&&Object.entries(item).every(([k,v])=>permitted.has(k)&&typeof v==='string'&&v.length<=400);
    if(!validMap(d.values,allowed)||!d.rows.every(row=>validMap(row,rowKeys)))throw Error('Invalid values or row fields');
    // Optional offline-first sync metadata is also protected by AES-GCM.
    if(d.project_id!==undefined&&d.project_id!==null&&(!Number.isSafeInteger(d.project_id)||d.project_id<=0))throw Error('Invalid project ID');
    for(const key of ['server_id','base_revision','bound_user_id'])if(d[key]!==undefined&&d[key]!==null&&(!Number.isSafeInteger(d[key])||d[key]<=0))throw Error('Invalid server binding');
    if(d.server_id!=null&&(!d.base_revision||!d.bound_user_id))throw Error('Incomplete server binding');
    if(d.conflict_guard!==undefined&&typeof d.conflict_guard!=='boolean')throw Error('Invalid conflict protection flag');
    return d;
  }
  async function derive(pass,salt){
    if(typeof pass!=='string'||pass.length<12||pass.length>200)throw Error('Draft passphrase must have 12–200 characters');
    const c=cryptoAPI(),base=await c.subtle.importKey('raw',new TextEncoder().encode(pass),'PBKDF2',false,['deriveKey']);
    return c.subtle.deriveKey({name:'PBKDF2',salt,iterations:ITERATIONS,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
  }
  async function seal(pass,draft){
    validateDraft(draft);
    const payload=new TextEncoder().encode(JSON.stringify(draft));
    if(payload.length>70000)throw Error('Draft too large');
    const c=cryptoAPI(),salt=c.getRandomValues(new Uint8Array(16)),iv=c.getRandomValues(new Uint8Array(12));
    const key=await derive(pass,salt);
    const ciphertext=await c.subtle.encrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode('CMT-OFFLINE-1')},key,payload);
    return JSON.stringify({v:VERSION,kdf:'PBKDF2-SHA256',rounds:ITERATIONS,salt:bytesToB64(salt),iv:bytesToB64(iv),ciphertext:bytesToB64(new Uint8Array(ciphertext))});
  }
  async function unseal(pass,envelope){
    try{
      if(typeof envelope!=='string'||envelope.length>150000)throw Error('Invalid encrypted draft');
      const p=JSON.parse(envelope);
      if(p.v!==VERSION||p.kdf!=='PBKDF2-SHA256'||p.rounds!==ITERATIONS||typeof p.ciphertext!=='string')throw Error('Unsupported draft format');
      const salt=b64ToBytes(p.salt),iv=b64ToBytes(p.iv),encrypted=b64ToBytes(p.ciphertext);
      if(salt.length!==16||iv.length!==12||encrypted.length>71000)throw Error('Invalid encrypted draft');
      const key=await derive(pass,salt);
      const decoded=await cryptoAPI().subtle.decrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode('CMT-OFFLINE-1')},key,encrypted);
      return validateDraft(JSON.parse(new TextDecoder().decode(decoded)));
    }catch(e){throw Error('Cannot unlock draft. Check the passphrase or encrypted data.');}
  }
  function has(){return !!localStorage.getItem(KEY)}
  async function save(pass,draft){const value=await seal(pass,draft);localStorage.setItem(KEY,value);return true}
  async function load(pass){const value=localStorage.getItem(KEY);if(!value)throw Error('No saved encrypted draft on this device');return unseal(pass,value)}
  function clear(){localStorage.removeItem(KEY)}
  return {seal,unseal,has,save,load,clear,validateDraft,KEY,VERSION};
});
