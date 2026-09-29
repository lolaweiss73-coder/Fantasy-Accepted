let myWishes=[];

function myWishCard(f){
  const card=document.createElement('article');
  card.className='fantasy-card my-wish-card';
  const mine=f.owner.id===state.me.id;
  const noun=f.kind==='general'?'משאלה':'פנטזיה';
  card.innerHTML=`
    <div class="eyebrow">${mine?'יצרתי':'אני משתתף/ת'} · ${escapeHtml(labels.kind[f.kind]||f.kind)}</div>
    <div class="row-top"><h3>${escapeHtml(f.title)}</h3><span class="workflow-pill ${escapeHtml(f.workflow?.status||f.status)}">${escapeHtml(labels.workflow[f.workflow?.status||f.status]||f.workflow?.status||f.status)}</span></div>
    <p class="fantasy-desc">${escapeHtml(f.description)}</p>
    <div class="workflow-mini">
      <span>${f.workflow?.accepted_count||0} משתתפים שהתקבלו</span>
      <span>·</span>
      <span>${f.workflow?.roles_filled?'כל התפקידים התמלאו':'עדיין חסרים אנשים'}</span>
    </div>
    <div class="card-actions">
      <button class="primary open-my-wish" type="button">פתיחת ה${noun}</button>
      ${mine&&['published','matching'].includes(f.workflow?.status||f.status)?'<button class="ghost open-my-apps" type="button">מועמדויות</button>':''}
    </div>`;
  card.querySelector('.open-my-wish').onclick=()=>openFantasy(f.id);
  const apps=card.querySelector('.open-my-apps');
  if(apps)apps.onclick=()=>openApplications(f.id);
  return card;
}

async function loadMyWishes(){
  if(!state.me)return;
  const root=$('#myWishesList');
  try{
    myWishes=await api('/api/me/wishes');
    root.replaceChildren();
    $('#myWishesEmpty').classList.toggle('hidden',myWishes.length>0);
    myWishes.forEach(f=>root.append(myWishCard(f)));
  }catch(err){
    toast(err.message);
  }
}

async function updateWishStage(fantasyId,status){
  const labelsByStatus={
    in_progress:'להעביר את המשאלה למצב „בביצוע”?',
    cancelled:'לבטל את המשאלה? אפשר יהיה לראות אותה בהיסטוריה אך לא לחפש לה משתתפים נוספים.'
  };
  if(labelsByStatus[status]&&!confirm(labelsByStatus[status]))return;
  try{
    const result=await api(`/api/fantasies/${fantasyId}/stage`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({status})
    });
    toast(`עודכן: ${labels.workflow[result.workflow?.status||result.status]||result.workflow?.status||result.status}`);
    closeModal('fantasyModal');
    await loadMyWishes();
    await loadFeed();
    if(typeof refreshMatchUi==='function')await refreshMatchUi();
    openFantasy(fantasyId);
  }catch(err){
    toast(err.message);
  }
}

async function confirmWishFulfilled(fantasyId){
  if(!confirm('לאשר שהמשאלה הוגשמה מבחינתך?'))return;
  try{
    const result=await api(`/api/fantasies/${fantasyId}/confirm-fulfilled`,{method:'POST'});
    const status=result.workflow?.status||result.status;
    toast(status==='fulfilled'?'המשאלה הוגשמה ואושרה משני הצדדים ✓':'האישור שלך נשמר. ממתינים לצד השני.');
    closeModal('fantasyModal');
    await loadMyWishes();
    if(typeof refreshMatchUi==='function')await refreshMatchUi();
    openFantasy(fantasyId);
  }catch(err){
    toast(err.message);
  }
}
