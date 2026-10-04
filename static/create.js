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

if($('#fantasyPhotos')){
  $('#fantasyPhotos').addEventListener('change',()=>{
    FA_MEDIA.previewFiles($('#fantasyPhotos').files,$('#fantasyPhotoPreview'));
  });
}

$('#fantasyForm').onsubmit=async(e)=>{
  e.preventDefault(); $('#createStatus').textContent='מפרסמת…';
  const payload={
    title:$('#fantasyTitle').value.trim(), description:$('#fantasyDescription').value.trim(), original_text:$('#fantasyDescription').dataset.original||'',
    mode:$('#fantasyMode').value, tags:$('#fantasyTags').value.split(',').map(x=>x.trim()).filter(Boolean), region:$('#fantasyRegion').value.trim(), visibility:$('#fantasyVisibility').value,
    owner_participates:$('#ownerParticipates').value==='yes',
    kind:$('#fantasyKind').value||state.track,
    roles:collectRoles()
  };
  if(payload.roles.some(r=>!r.name)){ $('#createStatus').textContent='צריך שם לכל תפקיד'; return; }
  try{
    const created=await api('/api/fantasies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const noun=payload.kind==='general'?'המשאלה':'הפנטזיה';
    const files=[...($('#fantasyPhotos')?.files||[])];
    if(files.length){
      $('#createStatus').textContent='הפרסום נשמר. מעלה תמונות…';
      try{
        await FA_MEDIA.uploadFiles(files,{purpose:'fantasy',fantasyId:created.id,visibility:'public'});
      }catch(photoErr){
        $('#createStatus').textContent='הפרסום נשמר, אבל לפחות תמונה אחת לא עלתה: '+photoErr.message;
        toast('הפרסום נשמר; הייתה בעיה בהעלאת תמונה');
        return;
      }
    }
    $('#createStatus').textContent='פורסם';
    toast(noun+' פורסמה');
    e.target.reset();
    $('#fantasyPhotoPreview')?.replaceChildren();
    $('#rolesEditor').replaceChildren();
    state.roleCount=0;
    addRole();
    resetMorinVoiceState({clearText:true});
    showView('feed');
  }catch(err){$('#createStatus').textContent=err.message}
};

$('#morinOpen').onclick=()=>{
  if(!$('#createView').classList.contains('active-view'))resetFantasyComposer();
  openModal('morinModal');
};
$('#morinDraftBtn').onclick=()=>openModal('morinModal');

const SpeechRecognitionAPI=window.SpeechRecognition||window.webkitSpeechRecognition;
let morinRecognition=null;
let morinWantsListening=false;
let morinRecognitionActive=false;
let morinRestartTimer=null;
let morinBaseText='';
let morinSegmentFinals=new Map();
let morinLastInterim='';
let morinPendingQuestions=[];

function resetMorinVoiceState({clearText=false}={}){
  morinWantsListening=false;
  clearTimeout(morinRestartTimer);
  morinRestartTimer=null;
  morinSegmentFinals.clear();
  morinLastInterim='';
  if(morinRecognitionActive && morinRecognition){
    try{morinRecognition.abort()}catch{}
  }
  morinRecognitionActive=false;
  morinRecognition=null;
  if(clearText){
    morinBaseText='';
    morinPendingQuestions=[];
    $('#morinText').value='';
    $('#morinStatus').textContent='';
    $('#morinReply').textContent='';
    $('#morinReply').classList.add('hidden');
    $('#morinQuestions').replaceChildren();
    $('#morinQuestions').classList.add('hidden');
    $('#morinStructureBtn').textContent='סיימתי — דברי איתי';
  }else{
    morinBaseText=cleanSpeech($('#morinText').value);
  }
  setSpeechVisual(false,'המיקרופון מוכן');
}

function resetFantasyComposer(){
  resetMorinVoiceState({clearText:true});
  $('#fantasyForm').reset();
  $('#fantasyDescription').dataset.original='';
  $('#createStatus').textContent='';
  $('#ownerParticipates').value='yes';
  $('#fantasyKind').value=state.track;
  $('#morinReviewNote').textContent='';
  $('#morinReviewNote').classList.add('hidden');
  if($('#fantasyPhotos'))$('#fantasyPhotos').value='';
  $('#fantasyPhotoPreview')?.replaceChildren();
  $('#rolesEditor').replaceChildren();
  state.roleCount=0;
  addRole();
}

function cleanSpeech(text){
  return String(text||'').replace(/\s+/g,' ').trim();
}

function speechKey(text){
  return cleanSpeech(text)
    .toLowerCase()
    .replace(/[.,!?;:״"'׳()[\]{}\-–—]/g,' ')
    .replace(/\s+/g,' ')
    .trim();
}

function fuzzyOverlapWords(leftWords,rightWords){
  const max=Math.min(80,leftWords.length,rightWords.length);
  for(let n=max;n>=4;n--){
    const a=leftWords.slice(-n).map(speechKey);
    const b=rightWords.slice(0,n).map(speechKey);
    let same=0;
    for(let i=0;i<n;i++)if(a[i] && a[i]===b[i])same++;
    if(same/n>=0.74)return n;
  }
  return 0;
}

function appendSpeech(existing,addition){
  const left=cleanSpeech(existing);
  const right=cleanSpeech(addition);
  if(!right)return left;
  if(!left)return right;

  const nl=speechKey(left);
  const nr=speechKey(right);
  if(!nr || nl===nr)return left;

  // Google/Samsung sometimes returns the whole sentence again, only longer.
  // Keep the longer cumulative hypothesis instead of appending it twice.
  if(nr.startsWith(nl))return right;
  if(nl.startsWith(nr) || nl.endsWith(nr))return left;

  const lw=left.split(/\s+/);
  const rw=right.split(/\s+/);
  const max=Math.min(40,lw.length,rw.length);
  for(let n=max;n>=1;n--){
    const a=speechKey(lw.slice(-n).join(' '));
    const b=speechKey(rw.slice(0,n).join(' '));
    if(a && a===b){
      return [left,rw.slice(n).join(' ')].filter(Boolean).join(' ');
    }
  }

  // Across recognition restarts Google may resend the last phrase with a few
  // words transcribed differently. Treat a strong fuzzy suffix/prefix match
  // as overlap instead of duplicating the whole block.
  const fuzzy=fuzzyOverlapWords(lw,rw);
  if(fuzzy){
    return [left,rw.slice(fuzzy).join(' ')].filter(Boolean).join(' ');
  }

  return left+' '+right;
}

function currentSegmentFinal(){
  // Some Android Chrome builds emit cumulative final hypotheses at
  // successive result indexes: "היי", "היי מורי", "היי מורי מה שלומך".
  // Fold them through appendSpeech so they become one growing sentence.
  return [...morinSegmentFinals.keys()]
    .sort((a,b)=>a-b)
    .map(k=>morinSegmentFinals.get(k))
    .filter(Boolean)
    .reduce((combined,part)=>appendSpeech(combined,part),'');
}

function renderSpeech(interim=''){
  let text=appendSpeech(morinBaseText,currentSegmentFinal());
  if(interim)text=appendSpeech(text,interim);
  $('#morinText').value=text.slice(0,12000);
}

function commitSegment(){
  morinBaseText=appendSpeech(morinBaseText,currentSegmentFinal());
  morinSegmentFinals.clear();
  morinLastInterim='';
  $('#morinText').value=morinBaseText.slice(0,12000);
}

function setSpeechVisual(live,message){
  const button=$('#morinMicBtn');
  const status=$('#morinMicStatus');
  button.classList.toggle('listening',live);
  status.classList.toggle('live',live);
  button.textContent=live?'⏹️ סיימתי לדבר':'🎙️ דברו אל מורין';
  status.textContent=message;
}

function makeRecognition(){
  const r=new SpeechRecognitionAPI();
  const speechLanguage=state.me?.preferred_language && state.me.preferred_language!=='auto'
    ? state.me.preferred_language
    : (navigator.language||'en-US');
  r.lang=speechLanguage;
  r.continuous=true;
  r.interimResults=true;
  r.maxAlternatives=1;
  if('unspokenPunctuation' in r){
    try{r.unspokenPunctuation=true}catch{}
  }

  r.onstart=()=>{
    morinRecognitionActive=true;
    setSpeechVisual(true,'מורין מקשיבה… אפשר לדבר ולהשהות');
  };

  r.onresult=(event)=>{
    let interim='';
    for(let i=event.resultIndex;i<event.results.length;i++){
      const transcript=cleanSpeech(event.results[i][0]?.transcript);
      if(!transcript)continue;
      if(event.results[i].isFinal){
        morinSegmentFinals.set(i,transcript);
      }else{
        interim=transcript;
      }
    }
    morinLastInterim=interim;
    renderSpeech(interim);
  };

  r.onerror=(event)=>{
    const fatal=['not-allowed','service-not-allowed','audio-capture'];
    const msg={
      'not-allowed':'צריך לאשר לדפדפן גישה למיקרופון.',
      'service-not-allowed':'הדפדפן חסם את שירות ההכתבה.',
      'audio-capture':'לא הצלחתי לגשת למיקרופון.',
      'network':'שירות ההכתבה נותק לרגע — מתחברת מחדש.',
      'no-speech':'לא שמעתי דיבור — ממשיכה להקשיב.'
    };
    if(fatal.includes(event.error)){
      morinWantsListening=false;
      clearTimeout(morinRestartTimer);
      setSpeechVisual(false,msg[event.error]||'המיקרופון נעצר.');
    }else if(morinWantsListening){
      setSpeechVisual(true,msg[event.error]||'ההאזנה נקטעה לרגע — ממשיכה.');
    }
  };

  r.onend=()=>{
    morinRecognitionActive=false;
    commitSegment();
    if(!morinWantsListening){
      setSpeechVisual(false,'קיבלתי. אפשר להמשיך לערוך או לבקש ממורין לסדר.');
      return;
    }
    setSpeechVisual(true,'הייתה הפסקה — מורין ממשיכה להקשיב…');
    clearTimeout(morinRestartTimer);
    morinRestartTimer=setTimeout(()=>{
      if(!morinWantsListening||morinRecognitionActive)return;
      morinRecognition=makeRecognition();
      try{morinRecognition.start()}catch{
        morinRestartTimer=setTimeout(()=>{
          if(morinWantsListening&&!morinRecognitionActive){
            morinRecognition=makeRecognition();
            try{morinRecognition.start()}catch{}
          }
        },600);
      }
    },180);
  };
  return r;
}

$('#morinText').addEventListener('input',()=>{
  // The textarea is the single source of truth. A manual correction or deletion
  // must immediately override anything the recognizer remembered internally.
  morinBaseText=cleanSpeech($('#morinText').value);
  morinSegmentFinals.clear();
  morinLastInterim='';
  if(morinWantsListening && morinRecognitionActive && morinRecognition){
    // Abort this recognition generation so stale cumulative Google results
    // cannot re-introduce text the user just deleted. onend will restart cleanly.
    try{morinRecognition.abort()}catch{}
  }
});

$('#morinResetBtn').onclick=()=>{
  resetMorinVoiceState({clearText:true});
  toast('הטיוטה של מורין נוקתה');
};

// Choosing "create fantasy" from outside the composer means a genuinely new draft.
$('#heroCreate').addEventListener('click',()=>resetFantasyComposer(),true);
const createNav=$('.nav-btn[data-view="create"]');
if(createNav)createNav.addEventListener('click',()=>resetFantasyComposer(),true);

if(!SpeechRecognitionAPI){
  $('#morinMicBtn').disabled=true;
  $('#morinMicStatus').textContent='הכתבה קולית אינה זמינה בדפדפן הזה — אפשר לכתוב כאן.';
}else{
  $('#morinMicBtn').onclick=()=>{
    if(morinWantsListening){
      morinWantsListening=false;
      clearTimeout(morinRestartTimer);
      if(morinRecognitionActive){
        try{morinRecognition.stop()}catch{}
      }else{
        commitSegment();
        setSpeechVisual(false,'קיבלתי. אפשר להמשיך לערוך או לבקש ממורין לסדר.');
      }
      return;
    }

    morinBaseText=cleanSpeech($('#morinText').value);
    morinSegmentFinals.clear();
    morinLastInterim='';
    morinWantsListening=true;
    setSpeechVisual(true,'פותחת את המיקרופון…');
    morinRecognition=makeRecognition();
    try{morinRecognition.start()}catch{
      morinWantsListening=false;
      setSpeechVisual(false,'לא הצלחתי לפתוח את המיקרופון.');
    }
  };
}

function speakMorinDynamic(text){
  const value=String(text||'').trim();
  if(!value || !('speechSynthesis' in window) || !window.SpeechSynthesisUtterance)return;
  try{
    window.speechSynthesis.cancel();
    const utterance=new SpeechSynthesisUtterance(value);
    const hebrew=/[\u0590-\u05FF]/.test(value);
    utterance.lang=hebrew?'he-IL':'en-US';
    utterance.rate=0.98;
    utterance.pitch=1;
    const voices=window.speechSynthesis.getVoices?.()||[];
    const wanted=voices.find(v=>String(v.lang||'').toLowerCase().startsWith(hebrew?'he':'en'));
    if(wanted)utterance.voice=wanted;
    window.speechSynthesis.speak(utterance);
  }catch{}
}

$('#morinStructureBtn').onclick=async()=>{
  const text=$('#morinText').value.trim();
  if(text.length<10){$('#morinStatus').textContent='ספרו לי קצת יותר';return}
  $('#morinStatus').textContent='מורין חושבת על מה שסיפרתם…';
  $('#morinStructureBtn').disabled=true;
  try{
    const result=await api('/api/morin/structure',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text,previous_questions:morinPendingQuestions,track_hint:$('#fantasyKind').value||state.track})
    });
    if(result.blocked_reason){$('#morinStatus').textContent=result.blocked_reason;return}

    const reply=String(result.morin_response||'').trim();
    if(reply){
      $('#morinReply').textContent=reply;
      $('#morinReply').classList.remove('hidden');
    }

    const questions=Array.isArray(result.clarifying_questions)?result.clarifying_questions.filter(Boolean):[];
    const qRoot=$('#morinQuestions');
    qRoot.replaceChildren();
    if(questions.length){
      const intro=document.createElement('div');
      intro.className='muted';
      intro.textContent='כדי למצוא התאמה טובה יותר, מורין רוצה לוודא:';
      qRoot.append(intro);
      for(const q of questions){
        const item=document.createElement('div');
        item.className='morin-question';
        item.textContent='• '+q;
        qRoot.append(item);
      }
      qRoot.classList.remove('hidden');
      morinPendingQuestions=questions.slice(0,2);
      $('#morinStatus').textContent='אפשר לענות בקול או בכתב, ואז לבדוק שוב.';
      $('#morinStructureBtn').textContent='עניתי — בדקי שוב';
      speakMorinDynamic([reply,...questions].filter(Boolean).join(' '));
      return;
    }

    morinPendingQuestions=[];
    qRoot.classList.add('hidden');
    $('#fantasyTitle').value=result.title||'';
    $('#fantasyDescription').value=result.description||text;
    $('#fantasyDescription').dataset.original=text;
    $('#ownerParticipates').value=result.owner_participates===false?'no':'yes';
    if(result.kind && ['general','adult'].includes(result.kind)){
      $('#fantasyKind').value=result.kind;
      if(result.kind!==state.track)setTrack(result.kind,{reload:false});
    }
    if(result.mode && ['online','meeting','either'].includes(result.mode))$('#fantasyMode').value=result.mode;
    $('#fantasyTags').value=(result.tags||[]).join(', ');
    $('#rolesEditor').replaceChildren();
    state.roleCount=0;
    for(const r of (result.roles||[]))addRole(r);
    if(!result.roles?.length)addRole();

    const review=$('#morinReviewNote');
    const structuredNoun=(result.kind||state.track)==='general'?'המשאלה':'הפנטזיה';
    review.textContent=reply||`מורין הבינה את ${structuredNoun} והכינה טיוטה לבדיקה.`;
    review.classList.remove('hidden');
    speakMorinDynamic(reply||review.textContent);

    closeModal('morinModal');
    showView('create');
    $('#morinStructureBtn').textContent='סיימתי — דברי איתי';
    toast(`מורין הבינה את ${structuredNoun} והכינה טיוטה`);
  }catch(err){
    $('#morinStatus').textContent=err.message;
  }finally{
    $('#morinStructureBtn').disabled=false;
  }
};

