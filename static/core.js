const $ = (q) => document.querySelector(q);
const $$ = (q) => [...document.querySelectorAll(q)];

const SITE_MODE = document.body.dataset.siteMode === 'adult' ? 'adult' : 'general';
const API_BASE = document.body.dataset.apiBase || '';
window.FA_SITE_MODE = SITE_MODE;
const ADULT_GATE_KEY = 'faAdultAgeGateAccepted';

if(SITE_MODE === 'adult' && localStorage.getItem(ADULT_GATE_KEY) === '1'){
  document.body.classList.add('adult-age-confirmed');
}

const state = {
  token: localStorage.getItem('faToken') || '',
  me: null,
  fantasies: [],
  activeConversation: null,
  inbox: [],
  roleCount: 0,
  track: SITE_MODE,
  language: FAI18N.active(),
};

const labels = {
  gender: {
    female: 'אישה', male: 'גבר', nonbinary: 'א-בינארי/ת', trans_female: 'טרנסית', trans_male: 'טרנס', other: 'אחר', prefer_not_to_say: 'לא צוין'
  },
  mode: {online:'אונליין', meeting:'מפגש', either:'אונליין או מפגש'},
  status: {pending:'ממתינה', shortlisted:'ברשימה', accepted:'התקבלה', rejected:'נדחתה', withdrawn:'נמשכה'},
  workflow: {published:'פורסמה', matching:'מחפשת התאמות', connected:'מחוברת', in_progress:'בביצוע', fulfilled_pending:'ממתינה לאישור הגשמה', fulfilled:'הוגשמה ✓', cancelled:'בוטלה', hidden:'מוסתרת'},
  kind: {general:'משאלה כללית', adult:'פנטזיה למבוגרים'},
};

function escapeHtml(value='') {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[c]));
}
function toast(message) {
  const el = $('#toast'); el.textContent = message; el.classList.add('show');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove('show'), 2600);
}
function authHeaders(extra={}) { return state.token ? {Authorization:`Bearer ${state.token}`,...extra} : extra; }

function identityLabel(person){
  if(!person)return '';
  return [person.nickname,person.public_tag].filter(Boolean).join(' · ');
}

function recoveryCopy(text){
  if(!text)return Promise.resolve(false);
  if(navigator.clipboard?.writeText){
    return navigator.clipboard.writeText(text).then(()=>true).catch(()=>false);
  }
  return Promise.resolve(false);
}

function openRecoveryModal({accountId='',code='',configured=true}={}){
  if($('#recoveryAccountIdDisplay'))$('#recoveryAccountIdDisplay').value=accountId||state.me?.account_id||'';
  if($('#recoveryCodeDisplay'))$('#recoveryCodeDisplay').value=code||'';
  $('#recoveryCodeWrap')?.classList.toggle('hidden',!code);
  $('#recoveryNotConfigured')?.classList.toggle('hidden',Boolean(code));
  if($('#recoveryGenerateText')){
    $('#recoveryGenerateText').textContent=configured
      ?(state.language==='he'?'מפתח קיים לא ניתן להצגה מחדש. אם הוא אבד, אפשר ליצור מפתח חדש; הישן יפסיק לעבוד.':'An existing recovery key cannot be shown again. If it was lost, create a new one; the old key will stop working.')
      :(state.language==='he'?'לחשבון הזה עדיין אין מפתח שחזור. כדאי ליצור אחד עכשיו כדי שלא תהיה תלוי בדפדפן הנוכחי.':'This account does not have a recovery key yet. Create one now so this browser is not your only way back in.');
  }
  if($('#generateRecoveryCodeBtn')){
    $('#generateRecoveryCodeBtn').textContent=configured
      ?(state.language==='he'?'יצירת מפתח חדש':'Create a new recovery key')
      :(state.language==='he'?'יצירת מפתח שחזור':'Create recovery key');
  }
  if($('#accountRecoveryStatus'))$('#accountRecoveryStatus').textContent='';
  openModal('accountRecoveryModal');
}

async function loadRecoveryStatus({open=false,promptIfMissing=false}={}){
  if(!state.token)return null;
  try{
    const status=await api('/api/me/recovery-status');
    if(open || (promptIfMissing && !status.configured)){
      openRecoveryModal({accountId:status.account_id,configured:status.configured});
    }
    return status;
  }catch{
    return null;
  }
}
async function api(path, options={}) {
  const requestPath = path.startsWith('/api/') ? `${API_BASE}${path}` : path;
  const response = await fetch(requestPath, {...options, headers: authHeaders(options.headers || {})});
  if (!response.ok) {
    let body = null; try { body = await response.json(); } catch {}
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || `שגיאה ${response.status}`;
    const err = new Error(message); err.status = response.status; err.body = body; throw err;
  }
  const type = response.headers.get('content-type') || '';
  return type.includes('application/json') ? response.json() : response.text();
}
function openModal(id){ $('#'+id).classList.add('open'); }
function closeModal(id){ $('#'+id).classList.remove('open'); }
function showView(name){
  $$('.view').forEach(v => v.classList.toggle('active-view', v.id === `${name}View`));
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  $('#sidebar').classList.remove('open');
  if(name === 'feed') loadFeed();
  if(name === 'inbox') loadInbox();
  if(name === 'wishes' && typeof loadMyWishes==='function') loadMyWishes();
}
function applyTrackUI(){
  state.track=SITE_MODE;
  state.language=FAI18N.active(state.me);
  const adult=SITE_MODE==='adult';
  const he=state.language==='he';
  $$('.track-tab,.track-choice').forEach(b=>b.classList.toggle('active',b.dataset.track===SITE_MODE));
  if($('#feedEyebrow'))$('#feedEyebrow').textContent=adult?'ADULT FANTASIES':'WISHES · IDEAS · EXPERIENCES';
  if($('#feedTitle'))$('#feedTitle').textContent=adult
    ?(he?'מה הפנטזיה שלך?':'What is your fantasy?')
    :(he?'מה היית רוצה שיקרה?':'What do you wish for?');
  if($('#feedLead'))$('#feedLead').textContent=adult
    ?(he?'ספרו למורין על פנטזיה למבוגרים. היא תעזור להבין מי חסר ומה חשוב להתאמה.':'Tell Morin about an adult fantasy. She will help clarify who is missing and what matters for a match.')
    :(he?'מחווה, עזרה, יצירה, חוויה, הפתעה או רעיון אחר — ספרו למורין מה הייתם רוצים להגשים.':'A gesture, help, creation, experience, surprise or another idea — tell Morin what you want to make real.');
  if($('#feedEmpty'))$('#feedEmpty').textContent=adult
    ?(he?'עדיין אין פנטזיות שמתאימות לחיפוש.':'No fantasies match this search yet.')
    :(he?'עדיין אין משאלות שמתאימות לחיפוש.':'No wishes match this search yet.');
  if($('#createHeading'))$('#createHeading').textContent=adult?(he?'יצירת פנטזיה':'Create a fantasy'):(he?'יצירת משאלה':'Create a wish');
  if($('#morinHeading'))$('#morinHeading').textContent=adult?(he?'ספרו לי את הפנטזיה כמו שהיא':'Tell me the fantasy in your own words'):(he?'ספרו לי מה הייתם רוצים שיקרה':'Tell me what you wish for');
  if($('#morinIntro'))$('#morinIntro').textContent=he
    ?'אפשר לדבר או לכתוב בכל שפה. מורין תבין אתכם; הקול המדובר שלה תמיד באנגלית.'
    :'Speak or write in any language. Morin will understand you; her spoken voice is always English.';
  if($('#fantasyKind'))$('#fantasyKind').value=state.track;
  if($('#ownerParticipationLabel'))$('#ownerParticipationLabel').textContent=adult?(he?'יוזם/ת הפנטזיה':'Fantasy creator'):(he?'יוזם/ת המשאלה':'Wish creator');
  if($('#ownerParticipatesNo'))$('#ownerParticipatesNo').textContent=adult?(he?'מארגן/ת בלבד — הפנטזיה מיועדת לאחרים':'Organizer only — the fantasy is for others'):(he?'מארגן/ת בלבד — המשאלה מיועדת לאחרים':'Organizer only — the wish is for others');
  if($('#fantasyPhotoHint'))$('#fantasyPhotoHint').textContent=adult
    ?(he?'אפשר לצרף עד 8 תמונות. תמונות גוף ללא פנים הן בסדר; העלו רק תמונות שמותר לכם לשתף. מידע EXIF מוסר אוטומטית.':'Attach up to 8 photos. Face-free body photos are fine; only upload images you have the right to share. EXIF metadata is removed automatically.')
    :(he?'אפשר לצרף עד 8 תמונות שיעזרו להסביר את המשאלה. מידע EXIF מוסר אוטומטית.':'Attach up to 8 photos that help explain the wish. EXIF metadata is removed automatically.');
}

function setTrack(_track,{reload=true}={}){
  state.track=SITE_MODE;
  applyTrackUI();
  if(reload && state.me)loadFeed();
}

$$('[data-track]').forEach(btn=>btn.addEventListener('click',()=>{
  setTrack(SITE_MODE);
}));

function applySiteModeUI(){
  state.language=FAI18N.active(state.me);
  const he=state.language==='he';
  const adult=SITE_MODE==='adult';
  document.documentElement.lang=state.language;
  document.documentElement.dir=he?'rtl':'ltr';
  const brand=$('.brand');
  const tagline=$('.tagline');
  const gateEyebrow=$('#gate .eyebrow');
  const gateTitle=$('#gate h1');
  const gateLead=$('#gate .lead');
  if(brand)brand.textContent=adult?'Fantasy Accepted 18+':(he?'משאלה התקבלה':'Fantasy Accepted');
  if(tagline)tagline.textContent=adult?'ADULT · NAME IT · MATCH IT · MAKE IT REAL':(he?'FANTASY ACCEPTED · לבקש. להתחבר. להגשים.':'FANTASY ACCEPTED · NAME IT · MATCH IT · MAKE IT REAL');
  if(gateEyebrow)gateEyebrow.textContent=adult?'FANTASY ACCEPTED · 18+':(he?'משאלה התקבלה · FANTASY ACCEPTED':'FANTASY ACCEPTED');
  if(gateTitle)gateTitle.textContent=adult?(he?'מה הפנטזיה שלך?':'What is your fantasy?'):(he?'מה המשאלה שלך?':'What do you wish for?');
  if(gateLead)gateLead.textContent=FAI18N.text(FAI18N.script(SITE_MODE)[1],state.me);
  if($('#enterBtn'))$('#enterBtn').textContent=adult?(he?'כניסה ל־Fantasy Accepted':'Enter Fantasy Accepted'):(he?'כניסה ל־משאלה התקבלה':'Enter Fantasy Accepted');
  if($('#gateFineprint'))$('#gateFineprint').textContent=adult
    ?(he?'הכניסה לאתר זה מיועדת לבני 18 ומעלה בלבד.':'This area is for adults aged 18 and over only.')
    :(he?'בשלב ההשקה השירות הכללי מיועד לבני 18 ומעלה.':'During launch, the general service is currently for adults aged 18 and over.');
  if($('#welcomeLanguageNotice'))$('#welcomeLanguageNotice').textContent=he
    ?'אפשר לדבר או לכתוב למורין בכל שפה. מורין מבינה אותך, והקול המדובר שלה תמיד באנגלית.'
    :'Speak or write to Morin in any language. She will understand you, and her spoken voice is always English.';
  if($('#languageSelect')){
    const raw=state.me?.preferred_language||FAI18N.preferredRaw();
    $('#languageSelect').value=['auto','he','en'].includes(raw)?raw:'auto';
  }
  if(adult && $('#adultConfirm'))$('#adultConfirm').checked=true;
  applyTrackUI();
}
window.applyLanguageUI=applySiteModeUI;

if($('#adultAgeAccept')){
  $('#adultAgeAccept').addEventListener('click',()=>{
    localStorage.setItem(ADULT_GATE_KEY,'1');
    document.body.classList.add('adult-age-confirmed');
    if($('#adultConfirm'))$('#adultConfirm').checked=true;
    document.dispatchEvent(new CustomEvent('fa:adult-gate-accepted'));
  });
}

applySiteModeUI();

if($('#languageSelect')){
  $('#languageSelect').value=['auto','he','en'].includes(FAI18N.preferredRaw())?FAI18N.preferredRaw():'auto';
  $('#languageSelect').addEventListener('change',()=>{
    FAI18N.set($('#languageSelect').value);
    state.language=FAI18N.active(state.me);
    applySiteModeUI();
    if(typeof window.refreshWelcomeLanguage==='function')window.refreshWelcomeLanguage();
  });
}

function formatDate(ts){ return new Date(ts*1000).toLocaleString(state.language==='he'?'he-IL':'en-US',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }

function openProfileForIncompleteAccount(){
  setTimeout(()=>$('#profileBtn')?.click(),120);
}

async function restoreSession(){
  if(!state.token) return;
  try{
    state.me = await api('/api/me');
    const startStatus = await api('/api/me/start-status');
    enterApp();
    if(startStatus?.needs_profile) openProfileForIncompleteAccount();
  }catch{
    localStorage.removeItem('faToken'); state.token='';
  }
}
function enterApp(){
  if(state.me?.preferred_language && state.me.preferred_language!=='auto')FAI18N.set(state.me.preferred_language);
  applySiteModeUI();
  $('#gate').classList.remove('open'); $('#app').classList.remove('hidden');
  $('#logoutBtn').classList.remove('hidden'); $('#dndBtn').classList.remove('hidden'); $('#meBadge').classList.remove('hidden');
  if($('#profileBtn'))$('#profileBtn').classList.remove('hidden');
  if($('#notificationsBtn'))$('#notificationsBtn').classList.remove('hidden');
  $('#meBadge').textContent = `${identityLabel(state.me)} · ${state.me.age}`;
  $('#dndBtn').textContent = `בהפסקה: ${state.me.dnd ? 'פעיל' : 'כבוי'}`;
  applyTrackUI();
  loadFeed();
  if(typeof refreshMatchUi==='function') refreshMatchUi();
  setTimeout(()=>loadRecoveryStatus({promptIfMissing:true}),250);
}

async function submitRegistration(){
  const button=$('#enterBtn');
  const error=$('#gateError');
  error.textContent='';
  const payload = {
    nickname: $('#nickname').value.trim(), pin: $('#signupPin').value.trim(), age:Number($('#age').value), gender:$('#gender').value,
    region:$('#region').value.trim(), marital_status:$('#maritalStatus')?.value||'prefer_not_to_say',
    relationship_status:$('#relationshipStatus')?.value||'prefer_not_to_say',
    preferred_language:$('#languageSelect')?.value||FAI18N.preferredRaw()||'auto',
    adult_confirm:SITE_MODE==='adult' ? localStorage.getItem(ADULT_GATE_KEY)==='1' : $('#adultConfirm').checked
  };
  if(!payload.nickname || !/^\d{6}$/.test(payload.pin) || payload.age < 18 || !payload.gender || !payload.adult_confirm){
    error.textContent=state.language==='he'
      ?'צריך כינוי, PIN בן 6 ספרות, גיל 18+, מגדר ואישור גיל.'
      :'Please enter a nickname, 6-digit PIN, age 18+, gender, and confirm your age.';
    toast(error.textContent);
    error.scrollIntoView({behavior:'smooth',block:'nearest'});
    return;
  }
  button.disabled=true;
  const previousText=button.textContent;
  button.textContent=state.language==='he'?'נכנסת…':'Entering…';
  try{
    const result = await api('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    state.token=result.token;
    state.me=result.identity;
    localStorage.setItem('faToken',state.token);
    enterApp();
    window.faNewRegistrationNeedsProfile=true;
    setTimeout(()=>{
      if(typeof window.startNewUserWelcome==='function'){
        window.startNewUserWelcome();
      }else{
        openProfileForIncompleteAccount();
      }
    },120);
  }catch(err){
    error.textContent=err.message;
    toast(err.message);
    error.scrollIntoView({behavior:'smooth',block:'nearest'});
  }finally{
    button.disabled=false;
    button.textContent=previousText;
  }
}

$('#enterBtn').addEventListener('click',submitRegistration);


function showAccountMode(mode){
  const login=mode!=='signup';
  $('#loginPanel')?.classList.toggle('hidden',!login);
  $('#signupPanel')?.classList.toggle('hidden',login);
  $('#showLoginBtn')?.classList.toggle('primary',login);
  $('#showLoginBtn')?.classList.toggle('ghost',!login);
  $('#showSignupBtn')?.classList.toggle('primary',!login);
  $('#showSignupBtn')?.classList.toggle('ghost',login);
  setTimeout(()=>$(login?'#loginNickname':'#nickname')?.focus(),40);
}

$('#showLoginBtn')?.addEventListener('click',()=>showAccountMode('login'));
$('#showSignupBtn')?.addEventListener('click',()=>showAccountMode('signup'));

async function submitLogin(){
  const button=$('#loginBtn');
  const error=$('#loginError');
  const nickname=$('#loginNickname')?.value.trim()||'';
  const pin=$('#loginPin')?.value.trim()||'';
  error.textContent='';
  if(!nickname || !/^\d{6}$/.test(pin)){
    error.textContent=state.language==='he'?'צריך כינוי ו-PIN בן 6 ספרות.':'Enter your nickname and 6-digit PIN.';
    return;
  }
  button.disabled=true;
  const previous=button.textContent;
  button.textContent=state.language==='he'?'נכנסת…':'Signing in…';
  try{
    const result=await api('/api/session/login',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nickname,pin})
    });
    state.token=result.token;
    state.me=result.identity;
    localStorage.setItem('faToken',state.token);
    enterApp();
    if(result.needs_profile)openProfileForIncompleteAccount();
  }catch(err){
    error.textContent=err.message;
  }finally{
    button.disabled=false;
    button.textContent=previous;
  }
}

$('#loginBtn')?.addEventListener('click',submitLogin);
$('#loginPin')?.addEventListener('keydown',e=>{
  if(e.key==='Enter'){
    e.preventDefault();
    submitLogin();
  }
});

function googleAuthStartUrl(){
  return `${API_BASE}/api/auth/google/start`;
}

async function refreshGoogleLoginAvailability(){
  const wrap=$('#googleLoginWrap');
  if(!wrap)return;
  if(SITE_MODE!=='general'){
    wrap.classList.add('hidden');
    return;
  }
  try{
    const config=await api('/api/site-config');
    wrap.classList.toggle('hidden',!config.google_auth_configured);
  }catch{
    wrap.classList.add('hidden');
  }
}
refreshGoogleLoginAvailability();

$('#googleLoginBtn')?.addEventListener('click',()=>{
  if(SITE_MODE!=='general')return;
  window.location.assign(googleAuthStartUrl());
});

function showGooglePendingChoice(mode){
  const existing=mode!=='new';
  $('#googleLinkExistingPanel')?.classList.toggle('hidden',!existing);
  $('#googleCreatePanel')?.classList.toggle('hidden',existing);
  $('#googleLinkExistingChoice')?.classList.toggle('primary',existing);
  $('#googleLinkExistingChoice')?.classList.toggle('ghost',!existing);
  $('#googleCreateChoice')?.classList.toggle('primary',!existing);
  $('#googleCreateChoice')?.classList.toggle('ghost',existing);
}

$('#googleLinkExistingChoice')?.addEventListener('click',()=>showGooglePendingChoice('existing'));
$('#googleCreateChoice')?.addEventListener('click',()=>showGooglePendingChoice('new'));

async function finishGoogleSession(result,{isNew=false}={}){
  state.token=result.token;
  state.me=result.identity;
  localStorage.setItem('faToken',state.token);
  const url=new URL(window.location.href);
  url.searchParams.delete('google_login');
  url.searchParams.delete('google_pending');
  url.searchParams.delete('google_error');
  history.replaceState({},'',url.pathname+url.search+url.hash);
  enterApp();
  if(isNew){
    window.faNewRegistrationNeedsProfile=true;
    setTimeout(()=>{
      if(typeof window.startNewUserWelcome==='function'){
        window.startNewUserWelcome();
      }else{
        openProfileForIncompleteAccount();
      }
    },120);
  }else if(result.needs_profile){
    openProfileForIncompleteAccount();
  }
}

async function consumeGoogleLogin(code){
  try{
    const result=await api(`/api/session/google/consume?code=${encodeURIComponent(code)}`,{method:'POST'});
    await finishGoogleSession(result);
  }catch(err){
    toast(err.message||'Google login failed');
  }
}

async function openGooglePending(token){
  const gate=$('#gate');
  gate?.classList.add('open');
  $('#loginPanel')?.classList.add('hidden');
  $('#signupPanel')?.classList.add('hidden');
  $('#accountModeTabs')?.classList.add('hidden');
  $('#googlePendingPanel')?.classList.remove('hidden');
  showGooglePendingChoice('existing');
  window.faGooglePendingToken=token;
  try{
    const info=await api(`/api/session/google/pending?token=${encodeURIComponent(token)}`);
    if($('#googlePendingIdentity')){
      const label=[info.display_name,info.email].filter(Boolean).join(' · ');
      $('#googlePendingIdentity').textContent=label||'Google';
    }
  }catch(err){
    $('#googlePendingError').textContent=err.message;
  }
}

$('#googleLinkExistingBtn')?.addEventListener('click',async()=>{
  const nickname=$('#googleExistingNickname')?.value.trim()||'';
  const pin=$('#googleExistingPin')?.value.trim()||'';
  const error=$('#googlePendingError');
  error.textContent='';
  if(!nickname || !/^\d{6}$/.test(pin)){
    error.textContent='צריך כינוי ו־PIN בן 6 ספרות.';
    return;
  }
  try{
    const result=await api('/api/session/google/link-existing',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        pending_token:window.faGooglePendingToken,
        nickname,
        pin
      })
    });
    await finishGoogleSession(result);
  }catch(err){
    error.textContent=err.message;
  }
});

$('#googleCreateAccountBtn')?.addEventListener('click',async()=>{
  const error=$('#googlePendingError');
  error.textContent='';
  const payload={
    pending_token:window.faGooglePendingToken,
    nickname:$('#googleNewNickname')?.value.trim()||'',
    age:Number($('#googleNewAge')?.value||0),
    gender:$('#googleNewGender')?.value||'',
    region:$('#googleNewRegion')?.value.trim()||'',
    preferred_language:FAI18N.preferredRaw()||'auto',
    adult_confirm:Boolean($('#googleNewAdultConfirm')?.checked)
  };
  if(!payload.nickname || payload.age<18 || !payload.gender || !payload.adult_confirm){
    error.textContent='צריך כינוי, גיל 18+, מגדר ואישור גיל.';
    return;
  }
  try{
    const result=await api('/api/session/google/create',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    await finishGoogleSession(result,{isNew:true});
  }catch(err){
    error.textContent=err.message;
  }
});

async function handleGoogleReturn(){
  const params=new URLSearchParams(window.location.search);
  const loginCode=params.get('google_login');
  const pending=params.get('google_pending');
  const error=params.get('google_error');
  if(error){
    toast('ההתחברות עם Google לא הושלמה.');
    return;
  }
  if(loginCode){
    await consumeGoogleLogin(loginCode);
    return;
  }
  if(pending){
    await openGooglePending(pending);
  }
}

setTimeout(handleGoogleReturn,0);

$('#recoverAccountBtn')?.addEventListener('click',async()=>{
  const button=$('#recoverAccountBtn');
  const status=$('#recoverAccountStatus');
  const accountId=$('#recoverAccountId').value.trim();
  const code=$('#recoverCode').value.trim();
  status.textContent='';
  if(!accountId || !code){
    status.textContent=state.language==='he'?'צריך מזהה חשבון ומפתח שחזור.':'Enter the account ID and recovery key.';
    return;
  }
  button.disabled=true;
  const previous=button.textContent;
  button.textContent=state.language==='he'?'משחזרת…':'Recovering…';
  try{
    const result=await api('/api/session/recover',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({account_id:accountId,recovery_code:code})
    });
    state.token=result.token;
    state.me=result.identity;
    localStorage.setItem('faToken',state.token);
    enterApp();
    toast(state.language==='he'?'החשבון שוחזר במכשיר הזה.':'Account restored on this device.');
  }catch(err){
    status.textContent=err.message;
  }finally{
    button.disabled=false;
    button.textContent=previous;
  }
});

$('#copyAccountIdBtn')?.addEventListener('click',async()=>{
  const ok=await recoveryCopy($('#recoveryAccountIdDisplay')?.value||'');
  toast(ok?(state.language==='he'?'מזהה החשבון הועתק.':'Account ID copied.'):(state.language==='he'?'לא הצלחתי להעתיק אוטומטית.':'Automatic copy failed.'));
});

$('#copyRecoveryCodeBtn')?.addEventListener('click',async()=>{
  const ok=await recoveryCopy($('#recoveryCodeDisplay')?.value||'');
  toast(ok?(state.language==='he'?'מפתח השחזור הועתק.':'Recovery key copied.'):(state.language==='he'?'לא הצלחתי להעתיק אוטומטית.':'Automatic copy failed.'));
});

$('#generateRecoveryCodeBtn')?.addEventListener('click',async()=>{
  const button=$('#generateRecoveryCodeBtn');
  button.disabled=true;
  try{
    const result=await api('/api/me/recovery-key',{method:'POST'});
    openRecoveryModal({accountId:result.account_id,code:result.recovery_code,configured:true});
  }catch(err){
    $('#accountRecoveryStatus').textContent=err.message;
  }finally{
    button.disabled=false;
  }
});

$('#recoveryDoneBtn')?.addEventListener('click',()=>closeModal('accountRecoveryModal'));

$('#logoutBtn').onclick=()=>{localStorage.removeItem('faToken'); location.reload();};
$('#dndBtn').onclick=async()=>{
  try{
    const result=await api(`/api/me/dnd?enabled=${!state.me.dnd}`,{method:'POST'}); state.me.dnd=result.dnd;
    $('#dndBtn').textContent=`בהפסקה: ${state.me.dnd?'פעיל':'כבוי'}`; toast(state.me.dnd?'פניות חדשות הושהו':'חזרת לקבל פניות');
  }catch(err){toast(err.message)}
};



if($('#nameStoryBtn')){
  $('#nameStoryBtn').onclick=()=>openModal('nameStoryModal');
}

