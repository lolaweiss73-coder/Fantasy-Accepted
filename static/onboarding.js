const welcomeIntro = [
  'היי, אני מורין. אני כאן כדי להסביר לך מה האתר הזה עושה ואיך משתמשים בו.'
];

const welcomeExplanation = [
  'Fantasy Accepted הוא מקום לבני 18 ומעלה שבו מתחילים ממשאלה או פנטזיה, מינית או לא מינית, ולא מטופס קר ומסורבל.',
  'מספרים לי מה רוצים. אני עוזרת להבין מי אמור להשתתף, מה חסר, אילו פרטים חשובים להתאמה, ואם משהו לא ברור אני שואלת. רק אחר כך נוצרת טיוטה שאפשר לבדוק ולפרסם.',
  'אחרי הפרסום אנשים שמתאימים לתפקידים החסרים יכולים למצוא את הפנטזיה ולהציע את עצמם. היוזם כבר נחשב קיים, אלא אם הוא רק מארגן משהו עבור אחרים.'
];

let welcomeVoiceMode='female';
let welcomeVoices=[];

function refreshWelcomeVoices(){
  if(!('speechSynthesis' in window))return;
  welcomeVoices=window.speechSynthesis.getVoices()||[];
}
refreshWelcomeVoices();
if('speechSynthesis' in window && 'onvoiceschanged' in window.speechSynthesis){
  window.speechSynthesis.onvoiceschanged=refreshWelcomeVoices;
}

function voiceScore(voice,mode){
  const name=String(voice?.name||'').toLowerCase();
  const lang=String(voice?.lang||'').toLowerCase();
  let score=0;
  if(lang==='he-il')score+=100;
  else if(lang.startsWith('he'))score+=80;
  const female=['hila','הילה','yael','יעל','carmit','כרמית','carmel','כרמל','ava','samantha','female'];
  const male=['asaf','אסף','avi','אבי','david','daniel','male'];
  const wanted=mode==='male'?male:female;
  const other=mode==='male'?female:male;
  if(wanted.some(t=>name.includes(t)))score+=35;
  if(other.some(t=>name.includes(t)))score-=15;
  return score;
}

function pickWelcomeVoice(mode){
  refreshWelcomeVoices();
  if(!welcomeVoices.length)return null;
  const ranked=[...welcomeVoices].sort((a,b)=>voiceScore(b,mode)-voiceScore(a,mode));
  return ranked[0]||null;
}

function appendWelcomeTranscript(text,speaker='מורין'){
  const box=$('#welcomeTranscript');
  const line=`${speaker}: ${String(text||'').trim()}`;
  box.value=(box.value?box.value+'\n\n':'')+line;
  box.scrollTop=box.scrollHeight;
}

function speakWelcome(text,mode=welcomeVoiceMode){
  if(!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window))return;
  const utterance=new SpeechSynthesisUtterance(String(text||''));
  utterance.lang='he-IL';
  utterance.rate=0.96;
  utterance.pitch=mode==='male'?0.86:1.06;
  const voice=pickWelcomeVoice(mode);
  if(voice)utterance.voice=voice;
  window.speechSynthesis.speak(utterance);
}

function welcomeSay(text,{showBubble=true,voiceMode=welcomeVoiceMode,speaker='מורין'}={}){
  const clean=String(text||'').trim();
  if(!clean)return;
  if(showBubble){
    const root=$('#welcomeMorinChat');
    const bubble=document.createElement('div');
    bubble.className='welcome-bubble morin-bubble';
    bubble.textContent=clean;
    root.append(bubble);
    bubble.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  appendWelcomeTranscript(clean,speaker);
  speakWelcome(clean,voiceMode);
}

function welcomeAppend(text){
  welcomeSay(text);
}

function normalizeInitials(value){
  return String(value||'')
    .toLowerCase()
    .replace(/[\s."'״׳’_-]/g,'');
}

function resetWelcome(){
  if('speechSynthesis' in window)window.speechSynthesis.cancel();
  welcomeVoiceMode='female';
  $('#welcomeMorinChat').replaceChildren();
  $('#welcomeTranscript').value='';
  $('#welcomeVoiceStep').classList.add('hidden');
  $('#welcomeHowStep').classList.add('hidden');
  $('#welcomeAviStep').classList.add('hidden');
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');
  $('#welcomeInitials').value='';
  $('#welcomeHowBtn').disabled=false;

  for(const line of welcomeIntro)welcomeSay(line,{voiceMode:'female'});
  const voiceQuestion='נוח לך להמשיך איתי בקול נשי, או שעדיף לך קול גברי?';
  $('#welcomeVoiceStep').classList.remove('hidden');
  appendWelcomeTranscript(voiceQuestion);
  speakWelcome(voiceQuestion,'female');
}

function continueWelcomeAfterVoiceChoice(mode){
  welcomeVoiceMode=mode;
  localStorage.setItem('faPreferredVoice',mode);
  $('#welcomeVoiceStep').classList.add('hidden');
  if('speechSynthesis' in window)window.speechSynthesis.cancel();

  const answer=mode==='male'
    ? 'מעולה. ממשיכים בקול גברי.'
    : 'מעולה. ממשיכים איתי, מורין.';
  welcomeSay(answer,{voiceMode:mode});
  for(const line of welcomeExplanation)welcomeSay(line,{voiceMode:mode});
}

$('#welcomeMorinBtn').onclick=()=>{
  resetWelcome();
  openModal('welcomeMorinModal');
};

$('#welcomeFemaleVoice').onclick=()=>continueWelcomeAfterVoiceChoice('female');
$('#welcomeMaleVoice').onclick=()=>continueWelcomeAfterVoiceChoice('male');

$('#welcomeHowBtn').onclick=()=>{
  $('#welcomeHowStep').classList.remove('hidden');
  $('#welcomeHowBtn').disabled=true;
  const text='דוגמה: אפשר לומר “אני רוצה שמישהו יבוא לגרושה שלי וישיר לה שיר”. אני אבין שהיוזם הוא מארגן בלבד, שהאדם החסר הוא מבצע או מבצעת, ואשאל רק שאלות שבאמת משפיעות על ההתאמה.';
  appendWelcomeTranscript(text);
  speakWelcome(text);
};

$('#welcomeFromAviBtn').onclick=()=>{
  $('#welcomeAviStep').classList.remove('hidden');
  const text='אבי אולי השאיר לך הודעה אישית. מה ראשי התיבות של השם שלך?';
  appendWelcomeTranscript(text);
  speakWelcome(text);
  $('#welcomeInitials').focus();
};

$('#welcomeDoneBtn').onclick=()=>{
  if('speechSynthesis' in window)window.speechSynthesis.cancel();
  closeModal('welcomeMorinModal');
};

$('#welcomeInitialsBtn').onclick=()=>{
  const initials=normalizeInitials($('#welcomeInitials').value);
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');

  if(initials==='אס' || initials==='as'){
    $('#welcomeAnnetteConfirm').classList.remove('hidden');
    const text='רק כדי לוודא, את אנט סמירנוף?';
    appendWelcomeTranscript(text);
    speakWelcome(text);
  }else if(initials){
    welcomeSay('לא מצאתי הודעה אישית לפי ראשי התיבות האלה, אבל ההסבר על האתר כמובן פתוח לכולם.');
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
  const lines=[
    'אנט, אבי ביקש ממני למסור לך משהו אישי. מאחורי הבחירות הלא שגרתיות שאת רואה עכשיו עומד אצלו חזון יזמי ארוך טווח, לא רק עוד אתר.',
    'הוא עובד על כמה רעיונות שהוא מאמין שיכולים לשנות תחומים שלמים, למשל טכנולוגיית ריח לסרטים ול-VR, ומיזם EL של מוצרים שנועדו להחזיק מעמד זמן קיצוני כדי להפחית את הצורך לקנות שוב ושוב.',
    'הוא גם חושב הרבה על ההשפעה הכלכלית של בינה מלאכותית ועל דרכים להוריד יוקר מחיה ולתת לאנשים יותר ביטחון ומשמעות. הוא ביקש שאגיד לך שהשאיפות שלו הרבה יותר גדולות מהמצב שבו הוא נמצא היום, ושזה בדיוק הפער שהוא מתכוון לסגור.'
  ];
  for(const text of lines){
    appendWelcomeTranscript(text);
    speakWelcome(text);
  }
};

$('#welcomeAnnetteNo').onclick=()=>{
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  welcomeSay('אז כנראה שההודעה האישית לא נועדה לך. עכשיו לפחות אני יודעת שלא לנחש אנשים לפי שתי אותיות 😄');
};
