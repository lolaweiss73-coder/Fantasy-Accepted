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

const SpeechRecognitionAPI=window.SpeechRecognition||window.webkitSpeechRecognition;
let morinRecognition=null;
let morinWantsListening=false;
let morinRecognitionActive=false;
let morinSpeechBase='';
let morinSessionFinal='';
let morinRestartTimer=null;

function normalizeSpeech(text){
  return String(text||'')
    .toLowerCase()
    .replace(/[.,!?;:״"'׳()[\]{}\-–—]/g,' ')
    .replace(/\s+/g,' ')
    .trim();
}

function collapseSpeechRepeats(text){
  const words=String(text||'').trim().split(/\s+/).filter(Boolean);
  const out=[];
  let i=0;
  const equalBlock=(a,b,size)=>{
    for(let j=0;j<size;j++){
      if(normalizeSpeech(words[a+j])!==normalizeSpeech(words[b+j]))return false;
    }
    return true;
  };
  while(i<words.length){
    let collapsed=false;
    const max=Math.min(8,Math.floor((words.length-i)/2));
    for(let size=max;size>=2;size--){
      if(!equalBlock(i,i+size,size))continue;
      let repeats=2;
      while(i+size*(repeats+1)<=words.length && equalBlock(i,i+size*repeats,size))repeats++;
      out.push(...words.slice(i,i+size));
      i+=size*repeats;
      collapsed=true;
      break;
    }
    if(collapsed)continue;

    let same=1;
    while(i+same<words.length && normalizeSpeech(words[i])===normalizeSpeech(words[i+same]))same++;
    if(same>=3){
      out.push(words[i]);
      i+=same;
      continue;
    }
    out.push(words[i]);
    i++;
  }
  return out.join(' ');
}

function appendUniqueSpeech(existing,addition){
  const left=String(existing||'').trim();
  const right=collapseSpeechRepeats(addition);
  if(!right)return left;
  if(!left)return right;

  const nl=normalizeSpeech(left), nr=normalizeSpeech(right);
  if(nl.endsWith(nr))return left;
  if(nr===nl)return left;

  const lw=left.split(/\s+/), rw=right.split(/\s+/);
  const max=Math.min(16,lw.length,rw.length);
  for(let n=max;n>=1;n--){
    const a=normalizeSpeech(lw.slice(-n).join(' '));
    const b=normalizeSpeech(rw.slice(0,n).join(' '));
    if(a && a===b){
      return [left,rw.slice(n).join(' ')].filter(Boolean).join(' ');
    }
  }
  return left+' '+right;
}

function renderMorinTranscript(interim=''){
  let text=appendUniqueSpeech(morinSpeechBase,morinSessionFinal);
  text=appendUniqueSpeech(text,interim);
  $('#morinText').value=text.slice(0,12000);
}

function setMicVisual(live,message){
  const button=$('#morinMicBtn'), status=$('#morinMicStatus');
  button.classList.toggle('listening',live);
  status.classList.toggle('live',live);
  button.textContent=live?'⏹️ סיימתי לדבר':'🎙️ דברו אל מורין';
  status.textContent=message;
}

function commitMorinSession(){
  morinSpeechBase=appendUniqueSpeech(morinSpeechBase,morinSessionFinal);
  morinSessionFinal='';
  renderMorinTranscript('');
}

function scheduleRecognitionRestart(delay=300){
  clearTimeout(morinRestartTimer);
  if(!morinWantsListening)return;
  morinRestartTimer=setTimeout(()=>{
    if(!morinWantsListening||morinRecognitionActive)return;
    morinSessionFinal='';
    try{
      morinRecognition.start();
    }catch{
      scheduleRecognitionRestart(700);
    }
  },delay);
}

if(!SpeechRecognitionAPI){
  $('#morinMicBtn').disabled=true;
  $('#morinMicStatus').textContent='הכתבה קולית אינה זמינה בדפדפן הזה — אפשר לכתוב כאן.';
}else{
  morinRecognition=new SpeechRecognitionAPI();
  morinRecognition.lang='he-IL';
  morinRecognition.continuous=true;
  morinRecognition.interimResults=true;
  morinRecognition.maxAlternatives=1;

  morinRecognition.onstart=()=>{
    morinRecognitionActive=true;
    setMicVisual(true,'מורין מקשיבה… אפשר לדבר ברצף');
  };

  morinRecognition.onresult=(event)=>{
    let finalText='';
    let interim='';
    for(let i=0;i<event.results.length;i++){
      const transcript=event.results[i][0].transcript.trim();
      if(!transcript)continue;
      if(event.results[i].isFinal){
        finalText=appendUniqueSpeech(finalText,transcript);
      }else{
        interim=appendUniqueSpeech(interim,transcript);
      }
    }
    morinSessionFinal=collapseSpeechRepeats(finalText);
    renderMorinTranscript(interim);
  };

  morinRecognition.onerror=(event)=>{
    const fatal=['not-allowed','service-not-allowed','audio-capture'];
    const messages={
      'not-allowed':'צריך לאשר לדפדפן גישה למיקרופון.',
      'service-not-allowed':'הדפדפן חסם את שירות ההכתבה.',
      'no-speech':'לא שמעתי דיבור — אני ממשיכה להקשיב.',
      'audio-capture':'לא הצלחתי לגשת למיקרופון.',
      'network':'שירות ההכתבה נותק לרגע — אני מתחברת מחדש.'
    };
    if(fatal.includes(event.error)){
      morinWantsListening=false;
      clearTimeout(morinRestartTimer);
      setMicVisual(false,messages[event.error]||'המיקרופון נעצר.');
    }else if(morinWantsListening){
      setMicVisual(true,messages[event.error]||'ההאזנה נקטעה לרגע — אני מתחברת מחדש.');
    }
  };

  morinRecognition.onend=()=>{
    morinRecognitionActive=false;
    commitMorinSession();
    if(morinWantsListening){
      setMicVisual(true,'מורין עדיין מקשיבה… ממשיכים');
      scheduleRecognitionRestart(250);
    }else{
      setMicVisual(false,'קיבלתי. אפשר לעבור על התמלול או לבקש ממורין לסדר אותו.');
    }
  };

  $('#morinMicBtn').onclick=()=>{
    if(morinWantsListening){
      morinWantsListening=false;
      clearTimeout(morinRestartTimer);
      if(morinRecognitionActive){
        try{morinRecognition.stop()}catch{}
      }else{
        commitMorinSession();
        setMicVisual(false,'קיבלתי. אפשר לעבור על התמלול או לבקש ממורין לסדר אותו.');
      }
      return;
    }

    morinSpeechBase=collapseSpeechRepeats($('#morinText').value.trim());
    morinSessionFinal='';
    morinWantsListening=true;
    setMicVisual(true,'פותחת את המיקרופון…');
    scheduleRecognitionRestart(0);
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

