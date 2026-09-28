function roleEditorTemplate(index){
  return `<div class="role-editor" data-role-index="${index}">
    <div class="role-editor-head"><strong>תפקיד ${index+1}</strong><button type="button" class="remove-role" aria-label="הסרה">×</button></div>
    <div class="form-grid two"><label>שם התפקיד<input class="role-name" maxlength="80" required placeholder="למשל: משתתפת נוספת"></label><label>מספר אנשים<input class="role-capacity" type="number" min="1" max="20" value="1"></label></div>
    <label>תיאור התפקיד<input class="role-description" maxlength="700" placeholder="מה מחפשים בתפקיד הזה"></label>
    <div class="form-grid three"><label>גיל מינימלי<input class="role-min-age" type="number" min="18" max="120" value="18"></label><label>גיל מקסימלי<input class="role-max-age" type="number" min="18" max="120" value="99"></label><label>אזור<input class="role-region" maxlength="80" placeholder="ריק = כל אזור"></label></div>
    <label>מגדרים מתאימים<select class="role-genders" multiple size="5"><option value="female">אישה</option><option value="male">גבר</option><option value="nonbinary">א-בינארי/ת</option><option value="trans_female">טרנסית</option><option value="trans_male">טרנס</option></select></label>
  </div>`;
}
function addRole(prefill={}){
  const index=state.roleCount++;
  const box=document.createElement('div'); box.innerHTML=roleEditorTemplate(index); const el=box.firstElementChild;
  $('#rolesEditor').append(el);
  el.querySelector('.remove-role').onclick=()=>{if($$('.role-editor').length===1){toast('צריך לפחות תפקיד אחד');return;}el.remove()};
  if(prefill.name)el.querySelector('.role-name').value=prefill.name;
  if(prefill.description)el.querySelector('.role-description').value=prefill.description;
  if(prefill.capacity)el.querySelector('.role-capacity').value=prefill.capacity;
  if(prefill.min_age)el.querySelector('.role-min-age').value=Math.max(18,prefill.min_age);
  if(prefill.max_age)el.querySelector('.role-max-age').value=Math.max(18,prefill.max_age);
  if(prefill.region)el.querySelector('.role-region').value=prefill.region;
  if(prefill.allowed_genders){[...el.querySelector('.role-genders').options].forEach(o=>o.selected=prefill.allowed_genders.includes(o.value));}
}
function collectRoles(){
  return $$('.role-editor').map(el=>({
    name:el.querySelector('.role-name').value.trim(), description:el.querySelector('.role-description').value.trim(),
    capacity:Number(el.querySelector('.role-capacity').value||1), min_age:Number(el.querySelector('.role-min-age').value||18), max_age:Number(el.querySelector('.role-max-age').value||99),
    allowed_genders:[...el.querySelector('.role-genders').selectedOptions].map(o=>o.value), region:el.querySelector('.role-region').value.trim(),
    marital_status:'any', relationship_status:'any', required_verification:'none'
  }));
}
$('#addRoleBtn').onclick=()=>addRole();
addRole();

$('#fantasyForm').onsubmit=async(e)=>{
  e.preventDefault(); $('#createStatus').textContent='מפרסמת…';
  const payload={
    title:$('#fantasyTitle').value.trim(), description:$('#fantasyDescription').value.trim(), original_text:$('#fantasyDescription').dataset.original||'',
    mode:$('#fantasyMode').value, tags:$('#fantasyTags').value.split(',').map(x=>x.trim()).filter(Boolean), region:$('#fantasyRegion').value.trim(), visibility:$('#fantasyVisibility').value,
    roles:collectRoles()
  };
  if(payload.roles.some(r=>!r.name)){ $('#createStatus').textContent='צריך שם לכל תפקיד'; return; }
  try{
    await api('/api/fantasies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('#createStatus').textContent='פורסם'; toast('הפנטזיה פורסמה'); e.target.reset(); $('#rolesEditor').replaceChildren();state.roleCount=0;addRole();showView('feed');
  }catch(err){$('#createStatus').textContent=err.message}
};

$('#morinOpen').onclick=()=>openModal('morinModal');
$('#morinDraftBtn').onclick=()=>openModal('morinModal');

const MediaRecorderAPI=window.MediaRecorder;
let morinMediaRecorder=null;
let morinMediaStream=null;
let morinAudioChunks=[];
let morinRecordingStartedAt=0;
let morinRecordingTimer=null;
let morinTranscribing=false;

function normalizeTranscript(text){
  return String(text||'').replace(/\s+/g,' ').trim();
}

function appendMorinTranscript(existing,addition){
  const left=String(existing||'').trim();
  const right=String(addition||'').trim();
  if(!right)return left;
  if(!left)return right;

  const nl=normalizeTranscript(left).toLowerCase();
  const nr=normalizeTranscript(right).toLowerCase();
  if(nl===nr || nl.endsWith(nr))return left;
  return left+'\n'+right;
}

function preferredRecordingMime(){
  if(!MediaRecorderAPI?.isTypeSupported)return '';
  const choices=[
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg'
  ];
  return choices.find(type=>MediaRecorderAPI.isTypeSupported(type))||'';
}

function formatFromMime(mime){
  const value=String(mime||'').toLowerCase();
  if(value.includes('ogg'))return 'ogg';
  if(value.includes('wav'))return 'wav';
  if(value.includes('mpeg')||value.includes('mp3'))return 'mp3';
  if(value.includes('mp4')||value.includes('m4a'))return 'm4a';
  if(value.includes('aac'))return 'aac';
  if(value.includes('flac'))return 'flac';
  return 'webm';
}

function blobToBase64(blob){
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(reader.error||new Error('audio read failed'));
    reader.onloadend=()=>{
      const result=String(reader.result||'');
      resolve(result.includes(',')?result.split(',').pop():result);
    };
    reader.readAsDataURL(blob);
  });
}

function stopMorinTracks(){
  if(morinMediaStream){
    for(const track of morinMediaStream.getTracks())track.stop();
  }
  morinMediaStream=null;
}

function setMorinMicVisual(recording,message){
  const button=$('#morinMicBtn');
  const status=$('#morinMicStatus');
  button.classList.toggle('listening',recording);
  status.classList.toggle('live',recording);
  button.textContent=recording?'⏹️ סיימתי לדבר':'🎙️ דברו אל מורין';
  status.textContent=message;
}

function startMorinTimer(){
  clearInterval(morinRecordingTimer);
  morinRecordingStartedAt=Date.now();
  morinRecordingTimer=setInterval(()=>{
    if(!morinMediaRecorder || morinMediaRecorder.state!=='recording')return;
    const seconds=Math.floor((Date.now()-morinRecordingStartedAt)/1000);
    const minutes=Math.floor(seconds/60);
    const remain=String(seconds%60).padStart(2,'0');
    $('#morinMicStatus').textContent=`מורין מקליטה ברצף… ${minutes}:${remain}`;
  },1000);
}

function finishMorinTimer(){
  clearInterval(morinRecordingTimer);
  morinRecordingTimer=null;
}

async function transcribeMorinRecording(blob,mimeType){
  if(blob.size<800){
    $('#morinMicStatus').textContent='ההקלטה הייתה קצרה מדי. אפשר לנסות שוב.';
    return;
  }
  morinTranscribing=true;
  $('#morinMicBtn').disabled=true;
  $('#morinMicStatus').textContent='מורין מתמללת את כל ההקלטה…';
  try{
    const audio_base64=await blobToBase64(blob);
    const result=await api('/api/morin/transcribe',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        audio_base64,
        format:formatFromMime(mimeType),
        language:'he'
      })
    });
    const transcript=String(result.text||'').trim();
    if(!transcript)throw new Error('לא התקבל תמלול');
    const current=$('#morinText').value;
    const combined=appendMorinTranscript(current,transcript);
    $('#morinText').value=combined.slice(0,12000);
    $('#morinMicStatus').textContent='התמלול נוסף. אפשר להמשיך לדבר או לערוך אותו.';
  }catch(err){
    $('#morinMicStatus').textContent=err?.message||'לא הצלחתי לתמלל את ההקלטה.';
  }finally{
    morinTranscribing=false;
    $('#morinMicBtn').disabled=false;
  }
}

async function startMorinRecording(){
  if(morinTranscribing)return;
  if(!MediaRecorderAPI || !navigator.mediaDevices?.getUserMedia){
    $('#morinMicStatus').textContent='הקלטה קולית אינה זמינה בדפדפן הזה — אפשר לכתוב כאן.';
    return;
  }
  try{
    morinMediaStream=await navigator.mediaDevices.getUserMedia({
      audio:{
        echoCancellation:true,
        noiseSuppression:true,
        autoGainControl:true
      }
    });
    const mimeType=preferredRecordingMime();
    const options={audioBitsPerSecond:64000};
    if(mimeType)options.mimeType=mimeType;

    morinAudioChunks=[];
    morinMediaRecorder=new MediaRecorderAPI(morinMediaStream,options);
    morinMediaRecorder.ondataavailable=(event)=>{
      if(event.data && event.data.size>0)morinAudioChunks.push(event.data);
    };
    morinMediaRecorder.onerror=()=>{
      finishMorinTimer();
      stopMorinTracks();
      setMorinMicVisual(false,'המיקרופון נעצר בגלל שגיאת הקלטה.');
    };
    morinMediaRecorder.onstop=async()=>{
      finishMorinTimer();
      const actualMime=morinMediaRecorder?.mimeType||mimeType||'audio/webm';
      const blob=new Blob(morinAudioChunks,{type:actualMime});
      morinAudioChunks=[];
      stopMorinTracks();
      morinMediaRecorder=null;
      setMorinMicVisual(false,'ההקלטה הסתיימה. מתחילה תמלול…');
      await transcribeMorinRecording(blob,actualMime);
    };
    morinMediaRecorder.start(1000);
    setMorinMicVisual(true,'מורין מקליטה ברצף… 0:00');
    startMorinTimer();
  }catch(err){
    stopMorinTracks();
    const denied=err?.name==='NotAllowedError'||err?.name==='SecurityError';
    setMorinMicVisual(false,denied?'צריך לאשר לדפדפן גישה למיקרופון.':'לא הצלחתי לפתוח את המיקרופון.');
  }
}

function stopMorinRecording(){
  if(!morinMediaRecorder || morinMediaRecorder.state!=='recording')return;
  finishMorinTimer();
  $('#morinMicBtn').disabled=true;
  $('#morinMicStatus').textContent='מסיימת את ההקלטה…';
  morinMediaRecorder.stop();
}

if(!MediaRecorderAPI || !navigator.mediaDevices?.getUserMedia){
  $('#morinMicBtn').disabled=true;
  $('#morinMicStatus').textContent='הקלטה קולית אינה זמינה בדפדפן הזה — אפשר לכתוב כאן.';
}else{
  $('#morinMicBtn').onclick=()=>{
    if(morinMediaRecorder?.state==='recording'){
      stopMorinRecording();
    }else{
      startMorinRecording();
    }
  };
}

$('#morinStructureBtn').onclick=async()=>{
  const text=$('#morinText').value.trim(); if(text.length<10){$('#morinStatus').textContent='ספרו לי קצת יותר';return}
  $('#morinStatus').textContent='מורין מסדרת את הטיוטה…'; $('#morinStructureBtn').disabled=true;
  try{
    const result=await api('/api/morin/structure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
    if(result.blocked_reason){$('#morinStatus').textContent=result.blocked_reason;return}
    $('#fantasyTitle').value=result.title||''; $('#fantasyDescription').value=result.description||text; $('#fantasyDescription').dataset.original=text;
    if(result.mode && ['online','meeting','either'].includes(result.mode))$('#fantasyMode').value=result.mode;
    $('#fantasyTags').value=(result.tags||[]).join(', ');
    $('#rolesEditor').replaceChildren();state.roleCount=0; for(const r of (result.roles||[]))addRole(r); if(!result.roles?.length)addRole();
    closeModal('morinModal');showView('create');toast('הטיוטה מוכנה לבדיקה שלך');
  }catch(err){$('#morinStatus').textContent=err.message}
  finally{$('#morinStructureBtn').disabled=false}
};

