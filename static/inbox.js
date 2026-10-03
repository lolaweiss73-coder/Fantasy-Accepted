async function loadInbox(){
  try{state.inbox=await api('/api/inbox');renderInbox()}catch(err){toast(err.message)}
}
function renderInbox(){
  const root=$('#inboxList');root.replaceChildren();
  if(!state.inbox.length)root.innerHTML='<div class="empty">אין עדיין שיחות.</div>';
  for(const item of state.inbox){
    const el=document.createElement('div');el.className='inbox-person'+(state.activeConversation?.id===item.identity.id?' active':'');
    el.innerHTML=`<strong>${escapeHtml(identityLabel(item.identity))}</strong><div class="muted">${item.unread?`${item.unread} חדשות · `:''}${formatDate(item.last_ts)}</div>`;
    el.onclick=()=>openConversation(item.identity.id,identityLabel(item.identity));root.append(el);
  }
}
async function openConversation(id,nickname='שיחה פרטית'){
  showView('inbox');state.activeConversation={id,nickname};$('#conversationTitle').textContent=nickname;$('#composerWrap').classList.remove('hidden');
  try{
    const messages=await api(`/api/messages/${id}`); const root=$('#conversationMessages');root.replaceChildren();
    for(const m of messages){const el=document.createElement('div');el.className='message '+(m.sender_id===state.me.id?'mine':'');el.innerHTML=`${escapeHtml(m.text)}<div class="message-time">${formatDate(m.created_at)}</div>`;root.append(el)}
    root.scrollTop=root.scrollHeight; loadInbox();
  }catch(err){toast(err.message)}
}
$('#sendMessageBtn').onclick=async()=>{
  const text=$('#messageText').value.trim();if(!text||!state.activeConversation)return;
  try{await api('/api/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipient_id:state.activeConversation.id,text})});$('#messageText').value='';openConversation(state.activeConversation.id,state.activeConversation.nickname)}catch(err){toast(err.message)}
};
$('#messageText').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#sendMessageBtn').click()}});

$$('.nav-btn').forEach(b=>b.onclick=()=>showView(b.dataset.view));
$('#heroCreate').onclick=()=>{resetFantasyComposer();openModal('morinModal');};
$('#refreshBtn').onclick=loadFeed;
$('#searchInput').addEventListener('input',()=>{clearTimeout(loadFeed.timer);loadFeed.timer=setTimeout(loadFeed,300)});
$('#regionFilter').addEventListener('input',()=>{clearTimeout(loadFeed.timer);loadFeed.timer=setTimeout(loadFeed,300)});
$('#menuBtn').onclick=()=>$('#sidebar').classList.toggle('open');
$$('[data-close]').forEach(btn=>btn.onclick=()=>closeModal(btn.dataset.close));
$$('.overlay').forEach(el=>el.addEventListener('click',e=>{if(e.target===el && el.id!=='gate')closeModal(el.id)}));

restoreSession();
