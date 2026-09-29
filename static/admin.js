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
