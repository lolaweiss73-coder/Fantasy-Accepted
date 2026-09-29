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
  const adult=SITE_MODE==='adult';
  $$('.track-tab,.track-choice').forEach(b=>b.classList.toggle('active',b.dataset.track===SITE_MODE));
  if($('#feedEyebrow'))$('#feedEyebrow').textContent=adult?'ADULT FANTASIES':'WISHES · IDEAS · EXPERIENCES';
  if($('#feedTitle'))$('#feedTitle').textContent=adult?'מה הפנטזיה שלך?':'מה היית רוצה שיקרה?';
  if($('#feedLead'))$('#feedLead').textContent=adult
    ?'ספרו למורין על פנטזיה למבוגרים. היא תעזור להבין מי חסר ומה חשוב להתאמה.'
    :'מחווה, עזרה, יצירה, חוויה, הפתעה או רעיון אחר — ספרו למורין מה הייתם רוצים להגשים.';
  if($('#feedEmpty'))$('#feedEmpty').textContent=adult?'עדיין אין פנטזיות שמתאימות לחיפוש.':'עדיין אין משאלות שמתאימות לחיפוש.';
  if($('#createHeading'))$('#createHeading').textContent=adult?'יצירת פנטזיה':'יצירת משאלה';
  if($('#morinHeading'))$('#morinHeading').textContent=adult?'ספרו לי את הפנטזיה כמו שהיא':'ספרו לי מה הייתם רוצים שיקרה';
  if($('#morinIntro'))$('#morinIntro').textContent=adult
    ?'אפשר לדבר אליי בקול או לכתוב. אני אעזור להפוך את הפנטזיה לטיוטה ברורה להתאמה.'
    :'אפשר לדבר אליי בקול או לכתוב. ספרו על המשאלה בדרך שלכם ואני אעזור להבין מה צריך כדי להגשים אותה.';
  if($('#fantasyKind'))$('#fantasyKind').value=state.track;
  if($('#ownerParticipationLabel'))$('#ownerParticipationLabel').textContent=adult?'יוזם/ת הפנטזיה':'יוזם/ת המשאלה';
  if($('#ownerParticipatesNo'))$('#ownerParticipatesNo').textContent=adult?'מארגן/ת בלבד — הפנטזיה מיועדת לאחרים':'מארגן/ת בלבד — המשאלה מיועדת לאחרים';
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
  const adult=SITE_MODE==='adult';
  const brand=$('.brand');
  const tagline=$('.tagline');
  const gateEyebrow=$('#gate .eyebrow');
  const gateTitle=$('#gate h1');
  const gateLead=$('#gate .lead');
  if(brand)brand.textContent=adult?'Fantasy Accepted 18+':'משאלה התקבלה';
  if(tagline)tagline.textContent=adult?'ADULT · לבקש. להתחבר. להגשים.':'FANTASY ACCEPTED · לבקש. להתחבר. להגשים.';
  if(gateEyebrow)gateEyebrow.textContent=adult?'FANTASY ACCEPTED · 18+':'משאלה התקבלה · FANTASY ACCEPTED';
  if(gateTitle)gateTitle.textContent=adult?'מה הפנטזיה שלך?':'יש משהו שהיית רוצה שיקרה?';
  if(gateLead)gateLead.textContent=adult
    ?'ספרו למורין על פנטזיה למבוגרים. היא תעזור להבין מי חסר, למצוא התאמות וללוות את התהליך עד לביצוע.'
    :'ספרו למורין משהו שהייתם רוצים שיקרה. היא תעזור להבין מי או מה חסר, למצוא התאמות, וללוות את המשאלה עד לביצוע.';
  if($('#enterBtn'))$('#enterBtn').textContent=adult?'כניסה ל־Fantasy Accepted':'כניסה ל־משאלה התקבלה';
  if($('#gateFineprint'))$('#gateFineprint').textContent=adult
    ?'הכניסה לאתר זה מיועדת לבני 18 ומעלה בלבד.'
    :'בשלב ההשקה השירות הכללי מיועד לבני 18 ומעלה.';
  if(adult && $('#adultConfirm'))$('#adultConfirm').checked=true;
  applyTrackUI();
}

if($('#adultAgeAccept')){
  $('#adultAgeAccept').addEventListener('click',()=>{
    localStorage.setItem(ADULT_GATE_KEY,'1');
    document.body.classList.add('adult-age-confirmed');
    if($('#adultConfirm'))$('#adultConfirm').checked=true;
    document.dispatchEvent(new CustomEvent('fa:adult-gate-accepted'));
  });
}

applySiteModeUI();

function formatDate(ts){ return new Date(ts*1000).toLocaleString('he-IL',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }

async function restoreSession(){
  if(!state.token) return;
  try{
    state.me = await api('/api/me');
    enterApp();
  }catch{
    localStorage.removeItem('faToken'); state.token='';
  }
}
function enterApp(){
  $('#gate').classList.remove('open'); $('#app').classList.remove('hidden');
  $('#logoutBtn').classList.remove('hidden'); $('#dndBtn').classList.remove('hidden'); $('#meBadge').classList.remove('hidden');
  if($('#profileBtn'))$('#profileBtn').classList.remove('hidden');
  if($('#notificationsBtn'))$('#notificationsBtn').classList.remove('hidden');
  $('#meBadge').textContent = `${state.me.nickname} · ${state.me.age}`;
  $('#dndBtn').textContent = `בהפסקה: ${state.me.dnd ? 'פעיל' : 'כבוי'}`;
  applyTrackUI();
  loadFeed();
  if(typeof refreshMatchUi==='function') refreshMatchUi();
}

$('#enterBtn').onclick = async () => {
  $('#gateError').textContent='';
  const payload = {
    nickname: $('#nickname').value.trim(), age:Number($('#age').value), gender:$('#gender').value,
    region:$('#region').value.trim(), marital_status:$('#maritalStatus')?.value||'prefer_not_to_say',
    relationship_status:$('#relationshipStatus')?.value||'prefer_not_to_say',
    adult_confirm:SITE_MODE==='adult' ? localStorage.getItem(ADULT_GATE_KEY)==='1' : $('#adultConfirm').checked
  };
  if(!payload.nickname || payload.age < 18 || !payload.gender || !payload.adult_confirm){
    $('#gateError').textContent='צריך כינוי, גיל 18+, מגדר ואישור גיל.'; return;
  }
  try{
    const result = await api('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    state.token=result.token; state.me=result.identity; localStorage.setItem('faToken',state.token); enterApp();
  }catch(err){ $('#gateError').textContent=err.message; }
};

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
