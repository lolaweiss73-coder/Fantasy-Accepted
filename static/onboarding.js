const welcomeIntro = [
  SITE_MODE==='adult'
    ? 'היי, אני מורין. הגעתם ל-Fantasy Accepted, האזור הנפרד לפנטזיות למבוגרים. הנה הסבר קצר על האתר.'
    : 'היי, אני מורין. הגעתם למשאלה התקבלה. הנה הסבר קצר על האתר.'
];

const welcomeExplanation = SITE_MODE==='adult' ? [
  'מתחילים מפנטזיה שרוצים להגשים ומתארים אותה במילים חופשיות.',
  'אני עוזרת להבין מי צריך להשתתף, מה חסר ואילו פרטים חשובים להתאמה. האזור הזה נפרד מהאתר הכללי ומיועד לבני 18 ומעלה בלבד.',
  'אחר כך נוצרת טיוטה לבדיקה ולפרסום, והאתר ממשיך דרך התאמות, חיבור בין משתתפים ושלבי הביצוע.'
] : [
  'מתחילים ממשהו שרוצים שיקרה: עזרה, מחווה, יצירה, חוויה, הפתעה, שותפות לרעיון או משהו אחר שרוצים להגשים.',
  'זה האתר הכללי בלבד. פנטזיות ותוכן מיני נמצאים באזור נפרד ואינם מופיעים כאן.',
  'מספרים לי מה רוצים. אני עוזרת להבין מי צריך להשתתף, מה חסר ואילו פרטים חשובים להתאמה. אחר כך נוצרת טיוטה לבדיקה ולפרסום, והאתר ממשיך דרך ההתאמות ועד לביצוע.'
];

const WELCOME_SEEN_KEY=SITE_MODE==='adult'?'faAdultWelcomeExplainedV2':'faGeneralWelcomeExplainedV2';
let welcomeVoices=[];
let welcomeAudioEnabled=false;
let welcomeRecordedAudio=null;

function welcomeLines(){
  return [...welcomeIntro,...welcomeExplanation];
}

function refreshWelcomeVoices(){
  if(!('speechSynthesis' in window))return;
  welcomeVoices=window.speechSynthesis.getVoices()||[];
}
refreshWelcomeVoices();
if('speechSynthesis' in window && 'onvoiceschanged' in window.speechSynthesis){
  window.speechSynthesis.onvoiceschanged=refreshWelcomeVoices;
}

function pickWelcomeVoice(){
  refreshWelcomeVoices();
  if(!welcomeVoices.length)return null;
  const female=['hila','הילה','yael','יעל','carmit','כרמית','carmel','כרמל','ava','samantha','female'];
  return [...welcomeVoices].sort((a,b)=>{
    const score=v=>{
      const name=String(v?.name||'').toLowerCase();
      const lang=String(v?.lang||'').toLowerCase();
      let n=lang==='he-il'?100:(lang.startsWith('he')?80:0);
      if(female.some(t=>name.includes(t)))n+=30;
      return n;
    };
    return score(b)-score(a);
  })[0]||null;
}

function stopWelcomeAudio(){
  if('speechSynthesis' in window)window.speechSynthesis.cancel();
  if(welcomeRecordedAudio){
    try{
      welcomeRecordedAudio.pause();
      welcomeRecordedAudio.currentTime=0;
    }catch{}
  }
}

function recordedWelcomeUrl(){
  return String(document.body.dataset.welcomeAudio||'').trim();
}

async function playRecordedWelcome(){
  const src=recordedWelcomeUrl();
  if(!src)return false;
  try{
    if(!welcomeRecordedAudio || welcomeRecordedAudio.src!==new URL(src,location.href).href){
      welcomeRecordedAudio=new Audio(src);
      welcomeRecordedAudio.preload='auto';
    }
    welcomeRecordedAudio.currentTime=0;
    await welcomeRecordedAudio.play();
    return true;
  }catch{
    return false;
  }
}

function speakWelcome(text){
  if(!welcomeAudioEnabled)return false;
  if(!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window))return false;
  const utterance=new SpeechSynthesisUtterance(String(text||''));
  utterance.lang='he-IL';
  utterance.rate=0.94;
  utterance.pitch=1.02;
  const voice=pickWelcomeVoice();
  if(voice)utterance.voice=voice;
  try{
    window.speechSynthesis.speak(utterance);
    return true;
  }catch{
    return false;
  }
}

async function playWelcomeSequence(){
  stopWelcomeAudio();
  welcomeAudioEnabled=true;
  if(await playRecordedWelcome())return;
  for(const line of welcomeLines())speakWelcome(line);
}

function appendWelcomeTranscript(text,speaker='מורין'){
  const box=$('#welcomeTranscript');
  const line=`${speaker}: ${String(text||'').trim()}`;
  box.value=(box.value?box.value+'\n\n':'')+line;
  box.scrollTop=box.scrollHeight;
}

function appendWelcomeBubble(text){
  const root=$('#welcomeMorinChat');
  const bubble=document.createElement('div');
  bubble.className='welcome-bubble morin-bubble';
  bubble.textContent=text;
  root.append(bubble);
}

function renderWelcomeText(){
  $('#welcomeMorinChat').replaceChildren();
  $('#welcomeTranscript').value='';
  for(const line of welcomeLines()){
    appendWelcomeBubble(line);
    appendWelcomeTranscript(line);
  }
}

function welcomeSay(text,{speak=false,speaker='מורין'}={}){
  const clean=String(text||'').trim();
  if(!clean)return;
  appendWelcomeBubble(clean);
  appendWelcomeTranscript(clean,speaker);
  if(speak && welcomeAudioEnabled && !recordedWelcomeUrl())speakWelcome(clean);
}

function normalizeInitials(value){
  return String(value||'')
    .toLowerCase()
    .replace(/[\s."'״׳’_-]/g,'');
}

function resetWelcome(){
  stopWelcomeAudio();
  welcomeAudioEnabled=false;
  $('#welcomeMorinChat').replaceChildren();
  $('#welcomeTranscript').value='';
  $('#welcomeVoiceStep').classList.remove('hidden');
  $('#welcomeHowStep').classList.add('hidden');
  $('#welcomeAviStep').classList.add('hidden');
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');
  $('#welcomeInitials').value='';
  $('#welcomeHowBtn').disabled=false;
}

function markWelcomeSeen(){
  localStorage.setItem(WELCOME_SEEN_KEY,'1');
}

async function startWelcomeWithAudio(){
  renderWelcomeText();
  $('#welcomeVoiceStep').classList.add('hidden');
  await playWelcomeSequence();
}

function startWelcomeTextOnly(){
  stopWelcomeAudio();
  welcomeAudioEnabled=false;
  renderWelcomeText();
  $('#welcomeVoiceStep').classList.add('hidden');
}

$('#welcomeMorinBtn').onclick=()=>{
  resetWelcome();
  openModal('welcomeMorinModal');
};

$('#welcomeFemaleVoice').onclick=startWelcomeWithAudio;
$('#welcomeTextOnly').onclick=startWelcomeTextOnly;

$('#welcomeReplayBtn').onclick=async()=>{
  if(!$('#welcomeMorinChat').children.length)renderWelcomeText();
  await playWelcomeSequence();
};

$('#welcomeHowBtn').onclick=()=>{
  $('#welcomeHowStep').classList.remove('hidden');
  $('#welcomeHowBtn').disabled=true;
  const text=SITE_MODE==='adult'
    ? 'דוגמה: מתארים פנטזיה במילים חופשיות. אני מזהה מי חסר כדי להגשים אותה, שואלת רק שאלות שמשפיעות על ההתאמה, ובונה טיוטה שאפשר לבדוק לפני הפרסום.'
    : 'דוגמה: אפשר לומר “אני רוצה שמישהו יבוא לגרושה שלי וישיר לה שיר”. אני מזהה שהיוזם מארגן את המשאלה, שהאדם החסר הוא מבצע או מבצעת, ושואלת רק שאלות שמשפיעות על ההתאמה.';
  welcomeSay(text,{speak:true});
};

$('#welcomeFromAviBtn').onclick=()=>{
  $('#welcomeAviStep').classList.remove('hidden');
  const text='אבי אולי השאיר כאן הודעה אישית. אפשר להזין את ראשי התיבות של השם.';
  welcomeSay(text,{speak:true});
  $('#welcomeInitials').focus();
};

$('#welcomeDoneBtn').onclick=()=>{
  markWelcomeSeen();
  stopWelcomeAudio();
  closeModal('welcomeMorinModal');
};

$('#welcomeInitialsBtn').onclick=()=>{
  const initials=normalizeInitials($('#welcomeInitials').value);
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');

  if(initials==='אס' || initials==='as'){
    $('#welcomeAnnetteConfirm').classList.remove('hidden');
    welcomeSay('רק כדי לוודא, מדובר באנט סמירנוף?',{speak:true});
  }else if(initials){
    welcomeSay('לא נמצאה הודעה אישית לפי ראשי התיבות האלה, אבל ההסבר על האתר פתוח לכולם.',{speak:true});
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
  for(const text of lines)welcomeSay(text,{speak:true});
};

$('#welcomeAnnetteNo').onclick=()=>{
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  welcomeSay('אז כנראה שההודעה האישית לא נועדה לכאן. שתי אותיות הן עדיין לא מערכת זיהוי מושלמת 😄',{speak:true});
};

const welcomeCloseBtn=$('#welcomeMorinModal [data-close="welcomeMorinModal"]');
if(welcomeCloseBtn){
  welcomeCloseBtn.addEventListener('click',()=>{
    markWelcomeSeen();
    stopWelcomeAudio();
  });
}

$('#welcomeMorinModal').addEventListener('click',e=>{
  if(e.target===$('#welcomeMorinModal')){
    markWelcomeSeen();
    stopWelcomeAudio();
  }
});

function maybeOpenWelcome(){
  if(SITE_MODE==='adult' && !document.body.classList.contains('adult-age-confirmed'))return;
  if(!state.token && !localStorage.getItem(WELCOME_SEEN_KEY) && !$('#welcomeMorinModal').classList.contains('open')){
    resetWelcome();
    openModal('welcomeMorinModal');
  }
}

document.addEventListener('fa:adult-gate-accepted',()=>{
  setTimeout(maybeOpenWelcome,80);
});

setTimeout(maybeOpenWelcome,120);
