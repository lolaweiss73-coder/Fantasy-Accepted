const $ = (q) => document.querySelector(q);
const $$ = (q) => [...document.querySelectorAll(q)];

const state = {
  token: localStorage.getItem('faToken') || '',
  me: null,
  fantasies: [],
  activeConversation: null,
  inbox: [],
  roleCount: 0,
};

const labels = {
  gender: {
    female: 'אישה', male: 'גבר', nonbinary: 'א-בינארי/ת', trans_female: 'טרנסית', trans_male: 'טרנס', other: 'אחר', prefer_not_to_say: 'לא צוין'
  },
  mode: {online:'אונליין', meeting:'מפגש', either:'אונליין או מפגש'},
  status: {pending:'ממתינה', shortlisted:'ברשימה', accepted:'התקבלה', rejected:'נדחתה', withdrawn:'נמשכה'},
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
  const response = await fetch(path, {...options, headers: authHeaders(options.headers || {})});
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
}
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
  $('#meBadge').textContent = `${state.me.nickname} · ${state.me.age}`;
  $('#dndBtn').textContent = `בהפסקה: ${state.me.dnd ? 'פעיל' : 'כבוי'}`;
  loadFeed();
}

$('#enterBtn').onclick = async () => {
  $('#gateError').textContent='';
  const payload = {
    nickname: $('#nickname').value.trim(), age:Number($('#age').value), gender:$('#gender').value,
    region:$('#region').value.trim(), marital_status:$('#maritalStatus').value,
    relationship_status:$('#relationshipStatus').value, adult_confirm:$('#adultConfirm').checked
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

