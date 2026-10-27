/* Import only externally generated v1.9 OCR draft JSON; all fields remain unreviewed. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.CMTImport=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const typemap={density_sheet:'density',concrete_strength:'concrete',general_report:'daily',rebar_observation:'rebar'};
  const fields={slump_in:'slump',air_percent:'air',concrete_temp_f:'temperature',reported_density_tests:'densityCount',reported_concrete_cylinders_cast:'castCount',reported_concrete_cylinders_picked_up:'pickupCount',report_id:'report',supplier:'supplier',sampling_location:'samplingLocation',truck_number:'truck',ticket_number:'ticket',page_number:'page',page_count:'pageTotal',series_id:'series',location:'location'};
  function importDraft(packet){
    if(!packet||typeof packet!=='object'||packet.schema!=='cmt-capture-v1.8')throw Error('Expected approved v1.8-form capture draft schema');
    if(packet.data_mode==='authorized'&&packet.authorization_attested!==true)throw Error('Authorization attestation missing');
    if(!Array.isArray(packet.documents)||!packet.documents.length||packet.documents.length>15)throw Error('Invalid document list');
    const records=[];
    for(const d of packet.documents){
      const type=typemap[d.form_type];if(!type)throw Error('Unknown form type');
      if(!Array.isArray(d.fields)||d.fields.length>80||!Array.isArray(d.rows)||d.rows.length>100)throw Error('Invalid field collection');
      const values={}; const checked={};
      for(const f of d.fields){if(!f||typeof f.key!=='string'||typeof f.value!=='string'||f.value.length>200)throw Error('Invalid proposal');const name=fields[f.key];if(name)values[name]=f.value;}
      const project=String(packet.project_key||'').trim().slice(0,90),date=String(packet.work_date||'');
      if(!project||!/^(\d{4})-(\d{2})-(\d{2})$/.test(date))throw Error('Invalid project/date');
      records.push({projectKey:project,date,type,values,rows:[],checked,photoIds:[],note:'Imported UNREVIEWED OCR draft; source image must be independently verified',createdAt:new Date().toISOString()});
    }
    return records;
  }
  return {importDraft};
});
