let siteAnnouncements=[];
let editingAnnouncementId=null;

function buildTickerSet(texts){
  const set=document.createElement('div');
  set.className='announcement-set';
  set.setAttribute('dir','rtl');
  texts.forEach((text,index)=>{
    const item=document.createElement('span');
    item.className='ticker-message';
    item.setAttribute('dir','rtl');
    item.textContent=text;
    set.append(item);
    if(index<texts.length-1){
      const sep=document.createElement('span');
      sep.className='ticker-separator';
      sep.textContent='✦';
      sep.setAttribute('aria-hidden','true');
      set.append(sep);
    }
  });
  const tail=document.createElement('span');
  tail.className='ticker-separator';
  tail.textContent='✦';
  tail.setAttribute('aria-hidden','true');
  set.append(tail);
  return set;
}

function renderAnnouncementTicker(){
  const track=$('#announcementTrack');
  if(!track)return;
  const texts=siteAnnouncements.map(item=>String(item.text||'').trim()).filter(Boolean);
  const visible=texts.length?texts:['אין הודעות כרגע…'];
  track.replaceChildren(buildTickerSet(visible),buildTickerSet(visible));
}

function resetAnnouncementEditor(){
  editingAnnouncementId=null;
  $('#adminAnnouncementEditor').value='';
  $('#adminAnnouncementSubmit').textContent='הוסף הודעה';
  $('#adminAnnouncementCancel').classList.add('hidden');
  $('#adminEditorLabel').childNodes[0].nodeValue='הוסף הודעה';
}

function renderAdminAnnouncementList(){
  const root=$('#adminAnnouncementList');
  if(!root)return;
  root.replaceChildren();
  if(!siteAnnouncements.length){
    const empty=document.createElement('div');
    empty.className='empty admin-empty';
    empty.textContent='אין הודעות כרגע.';
    root.append(empty);
    return;
  }
  siteAnnouncements.forEach(item=>{
    const row=document.createElement('div');
    row.className='admin-announcement-row';

    const text=document.createElement('div');
    text.className='admin-announcement-text';
    text.setAttribute('dir','rtl');
    text.textContent=item.text;

    const actions=document.createElement('div');
    actions.className='admin-announcement-actions';

    const edit=document.createElement('button');
    edit.type='button';
    edit.className='ghost';
    edit.textContent='ערוך';
    edit.onclick=()=>{
      editingAnnouncementId=item.id;
      $('#adminAnnouncementEditor').value=item.text;
      $('#adminAnnouncementSubmit').textContent='שמור עריכה';
      $('#adminAnnouncementCancel').classList.remove('hidden');
      $('#adminEditorLabel').childNodes[0].nodeValue='עריכת הודעה';
      $('#adminAnnouncementEditor').focus();
    };

    const del=document.createElement('button');
    del.type='button';
    del.className='ghost danger';
    del.textContent='מחק';
    del.onclick=()=>deleteAnnouncement(item.id,item.text);

    actions.append(edit,del);
    row.append(text,actions);
    root.append(row);
  });
}

async function loadAnnouncements(){
  try{
    siteAnnouncements=await api('/api/announcements');
  }catch{
    siteAnnouncements=[];
  }
  renderAnnouncementTicker();
  renderAdminAnnouncementList();
}

function adminPassword(){
  return $('#adminPassword').value;
}

function adminHeaders(){
  return {'Content-Type':'application/json','X-Admin-Key':adminPassword()};
}

$('#adminBtn').onclick=()=>{
  $('#adminStatus').textContent='';
  const saved=sessionStorage.getItem('faAdminPassword');
  if(saved)$('#adminPassword').value=saved;
  resetAnnouncementEditor();
  renderAdminAnnouncementList();
  openModal('adminModal');
};

$('#adminAnnouncementCancel').onclick=resetAnnouncementEditor;

$('#adminAnnouncementSubmit').onclick=async()=>{
  const password=adminPassword();
  const text=$('#adminAnnouncementEditor').value.trim();
  $('#adminStatus').textContent='שומרת…';
  if(!password){$('#adminStatus').textContent='צריך סיסמת מנהל';return}
  if(!text){$('#adminStatus').textContent='צריך לכתוב הודעה';return}
  try{
    const path=editingAnnouncementId
      ? `/api/admin/announcements/${editingAnnouncementId}`
      : '/api/admin/announcements';
    const method=editingAnnouncementId?'PUT':'POST';
    await api(path,{
      method,
      headers:adminHeaders(),
      body:JSON.stringify({text})
    });
    sessionStorage.setItem('faAdminPassword',password);
    $('#adminStatus').textContent=editingAnnouncementId?'ההודעה עודכנה':'ההודעה נוספה';
    toast(editingAnnouncementId?'ההודעה עודכנה':'ההודעה נוספה');
    resetAnnouncementEditor();
    await loadAnnouncements();
  }catch(err){
    $('#adminStatus').textContent=err.message;
  }
};

async function deleteAnnouncement(id,text){
  const password=adminPassword();
  if(!password){$('#adminStatus').textContent='צריך סיסמת מנהל';return}
  if(!confirm(`למחוק את ההודעה “${text}”?`))return;
  $('#adminStatus').textContent='מוחקת…';
  try{
    await api(`/api/admin/announcements/${id}`,{
      method:'DELETE',
      headers:{'X-Admin-Key':password}
    });
    sessionStorage.setItem('faAdminPassword',password);
    if(editingAnnouncementId===id)resetAnnouncementEditor();
    $('#adminStatus').textContent='נמחק';
    toast('ההודעה נמחקה');
    await loadAnnouncements();
  }catch(err){
    $('#adminStatus').textContent=err.message;
  }
}

loadAnnouncements();


function adminStatCard(label,value){
  const card=document.createElement('div');
  card.className='admin-stat-card';
  card.innerHTML=`<strong>${Number(value||0)}</strong><span>${escapeHtml(label)}</span>`;
  return card;
}

function renderAdminOverview(data){
  const root=$('#adminStats');
  root.replaceChildren(
    adminStatCard('משתמשים',data.users),
    adminStatCard('משתמשים מושעים',data.suspended_users),
    adminStatCard('כל המשאלות',data.wishes),
    adminStatCard('משאלות פעילות',data.active_wishes),
    adminStatCard('הוגשמו ואושרו',data.fulfilled_wishes),
    adminStatCard('דיווחים ממתינים',data.pending_reports),
    adminStatCard('מועמדויות',data.applications)
  );
}

function renderAdminReports(rows){
  const root=$('#adminReports');
  root.replaceChildren();
  if(!rows.length){
    root.innerHTML='<div class="empty">אין דיווחים כרגע.</div>';
    return;
  }
  rows.forEach(row=>{
    const el=document.createElement('div');
    el.className='admin-data-row';
    const target=row.fantasy_title
      ? `משאלה: ${escapeHtml(row.fantasy_title)}`
      : `משתמש/ת: ${escapeHtml(row.target_nickname||'לא זמין')}`;
    el.innerHTML=`
      <div class="admin-data-copy">
        <div class="row-top"><strong>${escapeHtml(row.reason)}</strong><span class="status-pill">${escapeHtml(row.status)}</span></div>
        <div class="muted">דיווח מאת ${escapeHtml(row.reporter_nickname)} · ${target}</div>
        ${row.details?`<p>${escapeHtml(row.details)}</p>`:''}
      </div>
      <div class="admin-data-actions">
        <button class="ghost reviewed" type="button">נבדק</button>
        <button class="primary resolved" type="button">טופל</button>
        <button class="ghost dismissed" type="button">נדחה</button>
      </div>`;
    el.querySelector('.reviewed').onclick=()=>setAdminReportStatus(row.id,'reviewed');
    el.querySelector('.resolved').onclick=()=>setAdminReportStatus(row.id,'resolved');
    el.querySelector('.dismissed').onclick=()=>setAdminReportStatus(row.id,'dismissed');
    root.append(el);
  });
}

function renderAdminWishes(rows){
  const root=$('#adminWishes');
  root.replaceChildren();
  if(!rows.length){
    root.innerHTML='<div class="empty">אין פרסומים.</div>';
    return;
  }
  rows.forEach(row=>{
    const el=document.createElement('div');
    el.className='admin-data-row';
    const kind=row.kind==='general'?'משאלה כללית':'פנטזיה למבוגרים';
    el.innerHTML=`
      <div class="admin-data-copy">
        <div class="row-top"><strong>${escapeHtml(row.title)}</strong><span class="workflow-pill ${escapeHtml(row.status)}">${escapeHtml(labels.workflow[row.status]||row.status)}</span></div>
        <div class="muted">${escapeHtml(kind)} · ${escapeHtml(row.owner_nickname)} · ${Number(row.application_count||0)} מועמדויות · ${Number(row.pending_reports||0)} דיווחים ממתינים</div>
      </div>
      <div class="admin-data-actions">
        ${row.status==='hidden'?'<button class="ghost publish" type="button">החזרה לאוויר</button>':'<button class="ghost hide-wish" type="button">הסתרה</button>'}
        ${!['cancelled','fulfilled'].includes(row.status)?'<button class="ghost danger cancel-wish-admin" type="button">ביטול</button>':''}
      </div>`;
    const publish=el.querySelector('.publish');
    if(publish)publish.onclick=()=>setAdminWishStatus(row.id,'published');
    const hide=el.querySelector('.hide-wish');
    if(hide)hide.onclick=()=>setAdminWishStatus(row.id,'hidden');
    const cancel=el.querySelector('.cancel-wish-admin');
    if(cancel)cancel.onclick=()=>setAdminWishStatus(row.id,'cancelled');
    root.append(el);
  });
}

function renderAdminUsers(rows){
  const root=$('#adminUsers');
  root.replaceChildren();
  if(!rows.length){
    root.innerHTML='<div class="empty">אין משתמשים.</div>';
    return;
  }
  rows.forEach(row=>{
    const el=document.createElement('div');
    el.className='admin-data-row';
    const completions=row.completion_stats?.fulfilled_total||0;
    el.innerHTML=`
      <div class="admin-data-copy">
        <div class="row-top"><strong>${escapeHtml(row.nickname)} · ${Number(row.age)}</strong>${row.suspended?'<span class="status-pill danger-pill">מושעה</span>':''}</div>
        <div class="muted">${escapeHtml(labels.gender[row.gender]||row.gender)}${row.region?` · ${escapeHtml(row.region)}`:''} · ${Number(completions)} הגשמות מאושרות ומתועדות</div>
      </div>
      <div class="admin-data-actions">
        <button class="${row.suspended?'primary':'ghost danger'} suspension" type="button">${row.suspended?'שחזור':'השעיה'}</button>
      </div>`;
    el.querySelector('.suspension').onclick=()=>setAdminUserSuspension(row.id,!row.suspended,row.nickname);
    root.append(el);
  });
}

async function loadAdminDashboard(){
  const password=adminPassword();
  if(!password){
    $('#adminStatus').textContent='צריך סיסמת מנהל';
    return;
  }
  $('#adminStatus').textContent='טוענת מרכז ניהול…';
  try{
    const options={headers:{'X-Admin-Key':password}};
    const [overview,reports,wishes,users]=await Promise.all([
      api('/api/admin/overview',options),
      api('/api/admin/reports',options),
      api('/api/admin/fantasies?limit=100',options),
      api('/api/admin/users?limit=100',options)
    ]);
    sessionStorage.setItem('faAdminPassword',password);
    renderAdminOverview(overview);
    renderAdminReports(reports);
    renderAdminWishes(wishes);
    renderAdminUsers(users);
    $('#adminDashboard').classList.remove('hidden');
    $('#adminStatus').textContent='נתוני הניהול מעודכנים';
  }catch(err){
    $('#adminStatus').textContent=err.message;
  }
}

async function setAdminReportStatus(id,status){
  try{
    await api(`/api/admin/reports/${id}/status`,{
      method:'POST',
      headers:adminHeaders(),
      body:JSON.stringify({status})
    });
    toast('הדיווח עודכן');
    await loadAdminDashboard();
  }catch(err){toast(err.message)}
}

async function setAdminWishStatus(id,status){
  const verb=status==='hidden'?'להסתיר':status==='cancelled'?'לבטל':'להחזיר לאוויר';
  if(!confirm(`${verb} את הפרסום הזה?`))return;
  try{
    await api(`/api/admin/fantasies/${id}/status`,{
      method:'POST',
      headers:adminHeaders(),
      body:JSON.stringify({status})
    });
    toast('הפרסום עודכן');
    await loadAdminDashboard();
    if(state.me)loadFeed();
  }catch(err){toast(err.message)}
}

async function setAdminUserSuspension(id,suspended,nickname){
  if(!confirm(`${suspended?'להשעות':'לשחזר'} את ${nickname}?`))return;
  try{
    await api(`/api/admin/users/${id}/suspension`,{
      method:'POST',
      headers:adminHeaders(),
      body:JSON.stringify({suspended})
    });
    toast(suspended?'המשתמש הושעה':'המשתמש שוחזר');
    await loadAdminDashboard();
  }catch(err){toast(err.message)}
}

$('#adminLoadDashboard').onclick=loadAdminDashboard;
