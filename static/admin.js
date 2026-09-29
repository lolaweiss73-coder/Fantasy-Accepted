async function loadAnnouncement(){
  try{
    const result=await api('/api/announcement');
    const text=String(result.text||'').trim();
    $('#announcementText').textContent=text;
    $('#announcementBar').classList.toggle('hidden',!text);
    if($('#adminAnnouncement'))$('#adminAnnouncement').value=text;
  }catch{}
}

$('#adminBtn').onclick=()=>{
  $('#adminStatus').textContent='';
  const saved=sessionStorage.getItem('faAdminPassword');
  if(saved)$('#adminPassword').value=saved;
  openModal('adminModal');
};

$('#adminSaveBtn').onclick=async()=>{
  const password=$('#adminPassword').value;
  const text=$('#adminAnnouncement').value.trim();
  $('#adminStatus').textContent='שומרת…';
  if(!password){$('#adminStatus').textContent='צריך סיסמת מנהל';return}
  if(!text){$('#adminStatus').textContent='ההודעה לא יכולה להיות ריקה';return}
  try{
    const result=await api('/api/admin/announcement',{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Admin-Key':password},
      body:JSON.stringify({text})
    });
    sessionStorage.setItem('faAdminPassword',password);
    $('#announcementText').textContent=result.text;
    $('#announcementBar').classList.remove('hidden');
    $('#adminStatus').textContent='נשמר';
    toast('הודעת האתר עודכנה');
  }catch(err){
    $('#adminStatus').textContent=err.message;
  }
};

loadAnnouncement();
