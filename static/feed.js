async function loadFeed(){
  if(!state.me)return;
  const p=new URLSearchParams();
  const q=$('#searchInput').value.trim(),region=$('#regionFilter').value.trim();
  if(q)p.set('q',q);
  if(region)p.set('region',region);
  p.set('kind',state.track);
  try{
    state.fantasies=await api('/api/fantasies?'+p.toString());
    renderFeed();
  }catch(err){toast(err.message)}
}

function itemNoun(f){
  return f.kind==='general'?'משאלה':'פנטזיה';
}

function workflowLabel(f){
  return labels.workflow[f.workflow?.status||f.status]||f.workflow?.status||f.status;
}

function renderFeed(){
  const root=$('#fantasyFeed');
  root.replaceChildren();
  $('#feedEmpty').classList.toggle('hidden',state.fantasies.length>0);
  for(const f of state.fantasies){
    const card=document.createElement('article');
    card.className='fantasy-card';
    const matches=f.roles.filter(r=>r.eligible).length;
    const ownerChip=f.owner_participates
      ? `<span class="role-chip match">יוזם/ת ה${itemNoun(f)} ✓</span>`
      :'';
    card.innerHTML=`
      <div class="eyebrow">${escapeHtml(labels.kind[f.kind]||f.kind)} · ${escapeHtml(labels.mode[f.mode]||f.mode)}${f.region?` · ${escapeHtml(f.region)}`:''}</div>
      <div class="row-top"><h3>${escapeHtml(f.title)}</h3><span class="workflow-pill ${escapeHtml(f.workflow?.status||f.status)}">${escapeHtml(workflowLabel(f))}</span></div>
      <div class="meta-row"><span>${escapeHtml(f.owner.nickname)}</span><span>·</span><span>${f.owner.age}</span><span>·</span><span>${escapeHtml(labels.gender[f.owner.gender]||f.owner.gender)}</span></div>
      <p class="fantasy-desc">${escapeHtml(f.description)}</p>
      <div class="tag-row">${f.tags.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
      <div class="role-chips">${ownerChip}${f.roles.map(r=>`<span class="role-chip ${r.eligible?'match':'no-match'}">${escapeHtml(r.name)}${r.eligible?' ✓':''}</span>`).join('')}</div>
      <div class="card-actions"><button class="primary open-detail">פתיחה</button>${f.owner.id===state.me.id?'<button class="ghost manage-apps">מועמדויות</button>':matches?`<span class="status-pill">${matches} תפקידים מתאימים</span>`:''}</div>`;
    card.querySelector('.open-detail').onclick=()=>openFantasy(f.id);
    const manage=card.querySelector('.manage-apps');
    if(manage)manage.onclick=()=>openApplications(f.id);
    root.append(card);
  }
}

function workflowActionsHtml(f,mine){
  const status=f.workflow?.status||f.status;
  const actions=[];
  if(mine && ['published','matching'].includes(status)){
    actions.push('<button id="detailApps" class="ghost">ניהול מועמדויות</button>');
  }
  if(mine && status==='connected'){
    actions.push('<button id="startExecutionBtn" class="primary">התחלנו לבצע</button>');
  }
  if(f.workflow?.can_confirm && !f.workflow.viewer_confirmed){
    actions.push('<button id="confirmFulfilledBtn" class="primary">המשאלה הוגשמה מבחינתי ✓</button>');
  }
  if(mine && ['published','matching','connected','in_progress','fulfilled_pending'].includes(status)){
    actions.push('<button id="cancelWishBtn" class="ghost danger">ביטול המשאלה</button>');
  }
  if(status==='fulfilled'){
    actions.push('<span class="success-note">✓ ההגשמה אושרה משני הצדדים</span>');
  }else if(status==='fulfilled_pending'){
    actions.push('<span class="status-text">ממתינים לאישור הגשמה מהצד השני.</span>');
  }
  return actions.join('');
}

async function openFantasy(id){
  try{
    const f=await api(`/api/fantasies/${id}`);
    const mine=f.owner.id===state.me.id;
    const noun=itemNoun(f);
    const searching=['published','matching'].includes(f.workflow?.status||f.status);
    const root=$('#fantasyDetail');
    root.className='fantasy-detail';
    root.innerHTML=`
      <div class="eyebrow">${escapeHtml(labels.kind[f.kind]||f.kind)} · ${escapeHtml(labels.mode[f.mode]||f.mode)}${f.region?` · ${escapeHtml(f.region)}`:''}</div>
      <div class="row-top"><h2>${escapeHtml(f.title)}</h2><span class="workflow-pill ${escapeHtml(f.workflow?.status||f.status)}">${escapeHtml(workflowLabel(f))}</span></div>
      <div class="workflow-summary">
        <span>משתתפים שהתקבלו: ${Number(f.workflow?.accepted_count||0)}</span>
        <span>·</span>
        <span>${f.workflow?.roles_filled?'כל התפקידים התמלאו':'עדיין מחפשים אנשים'}</span>
      </div>
      <div class="meta-row"><span>${escapeHtml(f.owner.nickname)}</span><span>·</span><span>${f.owner.age}</span><span>·</span><span>${escapeHtml(labels.gender[f.owner.gender]||f.owner.gender)}</span></div>
      <p class="detail-description">${escapeHtml(f.description)}</p>
      <div class="tag-row">${f.tags.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
      <h3>תפקידים</h3>
      ${f.owner_participates?`<div class="role-detail"><h4>יוזם/ת ה${noun}</h4><div class="muted">כבר בפנים — לא נדרשת מועמדות.</div></div>`:''}
      <div id="detailRoles"></div>
      <div class="workflow-actions">${workflowActionsHtml(f,mine)}</div>
      <div class="card-actions">${!mine?`<button id="messageOwner" class="ghost">שיחה פרטית עם ${escapeHtml(f.owner.nickname)}</button>`:''}<button id="reportFantasy" class="ghost">דיווח</button></div>`;

    const roles=$('#detailRoles');
    for(const r of f.roles){
      const row=document.createElement('div');
      row.className='role-detail '+(!mine&&!r.eligible?'ineligible':'');
      const age=`${r.min_age}–${r.max_age}`;
      const genders=r.allowed_genders.length?r.allowed_genders.map(g=>labels.gender[g]||g).join(', '):'כל מגדר';
      let action='';
      if(!mine && searching){
        action=r.eligible
          ?'<button class="primary apply-btn">הגשת מועמדות</button>'
          :'<div class="status-text">התפקיד אינו עומד כרגע בפרטי ההתאמה שלך.</div>';
      }else if(!searching){
        action='<div class="status-text">הגיוס לתפקיד הזה הסתיים כרגע.</div>';
      }
      row.innerHTML=`<h4>${escapeHtml(r.name)}</h4><div class="muted">${escapeHtml(r.description||'')} ${r.description?'· ':''}גיל ${age} · ${escapeHtml(genders)}${r.region?` · ${escapeHtml(r.region)}`:''}</div>${action}`;
      const btn=row.querySelector('.apply-btn');
      if(btn)btn.onclick=()=>applyFor(f.id,r.id,r.name);
      roles.append(row);
    }

    const apps=$('#detailApps');
    if(apps)apps.onclick=()=>{closeModal('fantasyModal');openApplications(f.id)};
    const start=$('#startExecutionBtn');
    if(start)start.onclick=()=>updateWishStage(f.id,'in_progress');
    const confirm=$('#confirmFulfilledBtn');
    if(confirm)confirm.onclick=()=>confirmWishFulfilled(f.id);
    const cancel=$('#cancelWishBtn');
    if(cancel)cancel.onclick=()=>updateWishStage(f.id,'cancelled');
    const message=$('#messageOwner');
    if(message)message.onclick=()=>{closeModal('fantasyModal');openConversation(f.owner.id,f.owner.nickname)};
    $('#reportFantasy').onclick=()=>reportFantasy(f.id);
    openModal('fantasyModal');
  }catch(err){toast(err.message)}
}

async function applyFor(fantasyId,roleId,roleName){
  const message=prompt(`הודעה למפרסם/ת עבור התפקיד “${roleName}” (אפשר להשאיר ריק):`)??null;
  if(message===null)return;
  try{
    await api(`/api/fantasies/${fantasyId}/apply`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({role_id:roleId,message})
    });
    toast('המועמדות נשלחה');
    closeModal('fantasyModal');
    if(typeof refreshMatchUi==='function')refreshMatchUi();
  }catch(err){toast(err.message)}
}

async function reportFantasy(id){
  const reason=prompt('סיבת הדיווח:');
  if(!reason)return;
  try{
    await api('/api/reports',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({target_fantasy_id:id,reason,details:''})
    });
    toast('הדיווח נשלח לבדיקה');
  }catch(err){toast(err.message)}
}

async function openApplications(fantasyId){
  try{
    const rows=await api(`/api/fantasies/${fantasyId}/applications`);
    const root=$('#applicationsList');
    root.replaceChildren();
    if(!rows.length)root.innerHTML='<div class="empty">עדיין אין מועמדויות.</div>';
    for(const a of rows){
      const el=document.createElement('div');
      el.className='application-row';
      const completed=Number(a.completion_stats?.fulfilled_total||0);
      el.innerHTML=`<div class="row-top"><strong>${escapeHtml(a.nickname)} · ${a.age}</strong><span class="status-pill">${escapeHtml(labels.status[a.status]||a.status)}</span></div><div class="muted">${escapeHtml(labels.gender[a.gender]||a.gender)}${a.region?` · ${escapeHtml(a.region)}`:''} · תפקיד: ${escapeHtml(a.role_name)}</div><div class="activity-fact">${completed} משאלות הוגשמו ואושרו בהשתתפות/יוזמת המשתמש הזה</div><p>${escapeHtml(a.message||'ללא הודעה')}</p><div class="card-actions"><button class="ghost shortlist">רשימה</button><button class="primary accept">קבלה</button><button class="ghost reject">דחייה</button><button class="ghost chat">שיחה פרטית</button></div>`;
      el.querySelector('.shortlist').onclick=()=>setApplicationStatus(a.id,'shortlisted',fantasyId);
      el.querySelector('.accept').onclick=()=>setApplicationStatus(a.id,'accepted',fantasyId);
      el.querySelector('.reject').onclick=()=>setApplicationStatus(a.id,'rejected',fantasyId);
      el.querySelector('.chat').onclick=()=>{closeModal('applicationsModal');openConversation(a.applicant_id,a.nickname)};
      root.append(el);
    }
    openModal('applicationsModal');
  }catch(err){toast(err.message)}
}

async function setApplicationStatus(id,status,fantasyId){
  try{
    const result=await api(`/api/applications/${id}/status`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({status})
    });
    toast(result.fantasy_status==='connected'?'עודכן — כל התפקידים התמלאו':'עודכן');
    await openApplications(fantasyId);
    if(typeof loadMyWishes==='function')loadMyWishes();
    if(typeof refreshMatchUi==='function')refreshMatchUi();
  }catch(err){toast(err.message)}
}
