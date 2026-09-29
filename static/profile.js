function fillProfileForm(){
  if(!state.me)return;
  $('#profileRegion').value=state.me.region||'';
  $('#profileMaritalStatus').value=state.me.marital_status||'prefer_not_to_say';
  $('#profileRelationshipStatus').value=state.me.relationship_status||'prefer_not_to_say';
  $('#profileSkills').value=(state.me.skills||[]).join(', ');
  $('#profileAvailability').value=state.me.availability||'';
  $('#profileTravel').value=Number(state.me.travel_radius_km||0);
  $('#profileBio').value=state.me.bio||'';
  $('#profileAdultDiscovery').checked=Boolean(state.me.adult_discovery);
}

async function saveMatchingProfile(){
  const skills=$('#profileSkills').value.split(',').map(x=>x.trim()).filter(Boolean);
  const payload={
    region:$('#profileRegion').value.trim(),
    marital_status:$('#profileMaritalStatus').value,
    relationship_status:$('#profileRelationshipStatus').value,
    skills,
    availability:$('#profileAvailability').value.trim(),
    travel_radius_km:Number($('#profileTravel').value||0),
    bio:$('#profileBio').value.trim(),
    adult_discovery:SITE_MODE==='adult' ? $('#profileAdultDiscovery').checked : Boolean(state.me?.adult_discovery)
  };
  $('#profileStatus').textContent='שומרת ומרעננת התאמות…';
  try{
    state.me=await api('/api/me/profile',{
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    $('#meBadge').textContent=`${state.me.nickname} · ${state.me.age}`;
    $('#region').value=state.me.region||'';
    $('#profileStatus').textContent='נשמר';
    toast('הפרופיל נשמר ומורין חיפשה התאמות מחדש');
    await refreshMatchUi();
  }catch(err){
    $('#profileStatus').textContent=err.message;
  }
}

function notificationCard(item){
  const el=document.createElement('button');
  el.type='button';
  el.className='notification-item'+(item.read_at?'':' unread');
  const time=formatDate(item.created_at);
  el.innerHTML=`<span class="notification-copy">${escapeHtml(item.text)}</span><span class="notification-time">${escapeHtml(time)}</span>`;
  el.onclick=async()=>{
    try{
      if(!item.read_at)await api(`/api/notifications/${item.id}/read`,{method:'POST'});
    }catch{}
    if(item.kind==='message'&&item.actor_id){
      closeModal('notificationsModal');
      openConversation(item.actor_id,'שיחה');
    }else if(item.fantasy_id){
      closeModal('notificationsModal');
      openFantasy(item.fantasy_id);
    }
    await refreshMatchUi();
  };
  return el;
}

function matchCard(item){
  const el=document.createElement('article');
  el.className='match-card';
  const reasons=(item.reasons||[]).map(r=>`<span class="tag">${escapeHtml(r)}</span>`).join('');
  el.innerHTML=`
    <div class="row-top"><strong>${escapeHtml(item.title)}</strong><span class="match-score">ציון התאמה ${Number(item.score)}/100</span></div>
    <div class="muted">תפקיד: ${escapeHtml(item.role_name)} · מאת ${escapeHtml(item.owner_nickname)}${item.fantasy_region?` · ${escapeHtml(item.fantasy_region)}`:''}</div>
    ${item.role_description?`<p>${escapeHtml(item.role_description)}</p>`:''}
    <div class="tag-row">${reasons}</div>
    <div class="card-actions"><button class="primary open-match" type="button">לראות את המשאלה</button></div>`;
  el.querySelector('.open-match').onclick=()=>{closeModal('notificationsModal');openFantasy(item.fantasy_id)};
  return el;
}

async function refreshMatchUi(){
  if(!state.me)return;
  try{
    const [notifications,matches]=await Promise.all([
      api('/api/notifications'),
      api('/api/me/matches')
    ]);
    state.notifications=notifications;
    state.matches=matches;
    const unread=notifications.filter(n=>!n.read_at).length;
    $('#notificationsBadge').textContent=String(unread);
    $('#notificationsBadge').classList.toggle('hidden',unread===0);

    const nr=$('#notificationsList');
    nr.replaceChildren();
    if(!notifications.length){
      const empty=document.createElement('div');
      empty.className='empty';
      empty.textContent='אין התראות חדשות כרגע.';
      nr.append(empty);
    }else{
      notifications.slice(0,30).forEach(n=>nr.append(notificationCard(n)));
    }

    const mr=$('#matchesList');
    mr.replaceChildren();
    if(!matches.length){
      const empty=document.createElement('div');
      empty.className='empty';
      empty.textContent='עדיין אין התאמות פעילות. כדאי להשלים יכולות וזמינות בפרופיל.';
      mr.append(empty);
    }else{
      matches.forEach(m=>mr.append(matchCard(m)));
    }
  }catch(err){
    console.warn('match ui refresh failed',err);
  }
}

async function loadMyActivitySummary(){
  const root=$('#profileActivitySummary');
  if(!root)return;
  root.textContent='הגשמות מתועדות: טוענת…';
  try{
    const stats=await api('/api/me/activity-summary');
    root.innerHTML=`
      <span><strong>${Number(stats.fulfilled_total||0)}</strong> הגשמות מאושרות ומתועדות</span>
      <span>·</span>
      <span>${Number(stats.fulfilled_as_owner||0)} כיוזם/ת</span>
      <span>·</span>
      <span>${Number(stats.fulfilled_as_participant||0)} כמשתתף/ת</span>`;
  }catch{
    root.textContent='נתוני ההגשמות אינם זמינים כרגע.';
  }
}

$('#profileBtn').onclick=async()=>{
  fillProfileForm();
  $('#profileStatus').textContent='';
  openModal('profileModal');
  await loadMyActivitySummary();
};
$('#profileSaveBtn').onclick=saveMatchingProfile;

$('#notificationsBtn').onclick=async()=>{
  await refreshMatchUi();
  openModal('notificationsModal');
};

setInterval(()=>{if(state.me)refreshMatchUi()},60000);
