function welcomeAppend(text){
  const root=$('#welcomeMorinChat');
  const bubble=document.createElement('div');
  bubble.className='welcome-bubble morin-bubble';
  bubble.textContent=text;
  root.append(bubble);
  bubble.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function normalizeInitials(value){
  return String(value||'')
    .toLowerCase()
    .replace(/[\s."'״׳’_-]/g,'');
}

$('#welcomeMorinBtn').onclick=()=>{
  $('#welcomeHowStep').classList.add('hidden');
  $('#welcomeAviStep').classList.add('hidden');
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');
  $('#welcomeInitials').value='';
  openModal('welcomeMorinModal');
};

$('#welcomeHowBtn').onclick=()=>{
  $('#welcomeHowStep').classList.remove('hidden');
  $('#welcomeHowBtn').disabled=true;
};

$('#welcomeFromAviBtn').onclick=()=>{
  $('#welcomeAviStep').classList.remove('hidden');
  $('#welcomeInitials').focus();
};

$('#welcomeDoneBtn').onclick=()=>closeModal('welcomeMorinModal');

$('#welcomeInitialsBtn').onclick=()=>{
  const initials=normalizeInitials($('#welcomeInitials').value);
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');

  if(initials==='אס' || initials==='as'){
    $('#welcomeAnnetteConfirm').classList.remove('hidden');
  }else if(initials){
    welcomeAppend('לא מצאתי הודעה אישית לפי ראשי התיבות האלה, אבל ההסבר על האתר כמובן פתוח לכולם.');
  }
};

$('#welcomeInitials').addEventListener('keydown',e=>{
  if(e.key==='Enter'){
    e.preventDefault();
    $('#welcomeInitialsBtn').click();
  }
});

$('#welcomeAnnetteYes').onclick=()=>{
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.remove('hidden');
};

$('#welcomeAnnetteNo').onclick=()=>{
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  welcomeAppend('אז כנראה שההודעה האישית לא נועדה לך — אבל עכשיו לפחות אני יודעת שלא לנחש אנשים לפי שתי אותיות 😄');
};
