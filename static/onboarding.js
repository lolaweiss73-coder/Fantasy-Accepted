const welcomeIntro = [
  'היי, אני מורין. אני כאן כדי להסביר לך מה האתר הזה עושה ואיך משתמשים בו.'
];

const welcomeExplanation = [
  'משאלה התקבלה הוא מקום שבו מתחילים ממשהו שהייתם רוצים שיקרה: עזרה, מחווה, יצירה, חוויה, הפתעה, שותף לרעיון או משהו אחר שאתם רוצים להגשים.',
  'יש באתר שני מסלולים נפרדים: משאלות כלליות, ופנטזיות למבוגרים. לכן מי שבא בשביל רעיון לא מיני לא צריך לעבור דרך תוכן אינטימי בכלל.',
  'מספרים לי מה רוצים. אני עוזרת להבין מי אמור להשתתף, מה חסר ואילו פרטים באמת חשובים להתאמה. אחר כך נוצרת טיוטה שאפשר לבדוק ולפרסם, והאתר ממשיך איתכם דרך ההתאמות ועד לביצוע.'
];

const WELCOME_SEEN_KEY='faWelcomeExplainedV4';
let welcomeVoiceMode=localStorage.getItem('faPreferredVoice')==='male'?'male':'female';
let welcomeVoices=[];
let welcomeAutoReplayArmed=false;

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
  if(!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window))return false;
  const utterance=new SpeechSynthesisUtterance(String(text||''));
  utterance.lang='he-IL';
  utterance.rate=0.96;
  utterance.pitch=mode==='male'?0.86:1.06;
  const voice=pickWelcomeVoice(mode);
  if(voice)utterance.voice=voice;
  try{
    window.speechSynthesis.speak(utterance);
    return true;
  }catch{
    return false;
  }
}

function speakWelcomeSequence(){
  if('speechSynthesis' in window)window.speechSynthesis.cancel();
  for(const line of [...welcomeIntro,...welcomeExplanation])speakWelcome(line,welcomeVoiceMode);
}

function welcomeSay(text,{showBubble=true,voiceMode=welcomeVoiceMode,speaker='מורין',speak=true}={}){
  const clean=String(text||'').trim();
  if(!clean)return;
  if(showBubble){
    const root=$('#welcomeMorinChat');
    const bubble=document.createElement('div');
    bubble.className='welcome-bubble morin-bubble';
    bubble.textContent=clean;
    root.append(bubble);
  }
  appendWelcomeTranscript(clean,speaker);
  if(speak)speakWelcome(clean,voiceMode);
}

function normalizeInitials(value){
  return String(value||'')
    .toLowerCase()
    .replace(/[\s."'״׳’_-]/g,'');
}

function resetWelcome({auto=false}={}){
  if('speechSynthesis' in window)window.speechSynthesis.cancel();
  welcomeVoiceMode=localStorage.getItem('faPreferredVoice')==='male'?'male':'female';
  $('#welcomeMorinChat').replaceChildren();
  $('#welcomeTranscript').value='';
  $('#welcomeVoiceStep').classList.remove('hidden');
  $('#welcomeHowStep').classList.add('hidden');
  $('#welcomeAviStep').classList.add('hidden');
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');
  $('#welcomeInitials').value='';
  $('#welcomeHowBtn').disabled=false;

  for(const line of welcomeIntro)welcomeSay(line,{voiceMode:welcomeVoiceMode});
  for(const line of welcomeExplanation)welcomeSay(line,{voiceMode:welcomeVoiceMode});

  const voiceQuestion='אם תרצו, אפשר לבחור כאן קול נשי או גברי להסבר.';
  appendWelcomeTranscript(voiceQuestion);
  welcomeAutoReplayArmed=auto;
}

function markWelcomeSeen(){
  localStorage.setItem(WELCOME_SEEN_KEY,'1');
  welcomeAutoReplayArmed=false;
}

function continueWelcomeAfterVoiceChoice(mode){
  welcomeVoiceMode=mode;
  localStorage.setItem('faPreferredVoice',mode);
  if('speechSynthesis' in window)window.speechSynthesis.cancel();
  const answer=mode==='male'
    ? 'מעולה. ממשיכים בקול גברי.'
    : 'מעולה. ממשיכים איתי, מורין.';
  welcomeSay(answer,{voiceMode:mode});
  speakWelcomeSequence();
}

$('#welcomeMorinBtn').onclick=()=>{
  resetWelcome({auto:false});
  openModal('welcomeMorinModal');
};

$('#welcomeReplayBtn').onclick=()=>{
  welcomeAutoReplayArmed=false;
  speakWelcomeSequence();
};

$('#welcomeFemaleVoice').onclick=()=>continueWelcomeAfterVoiceChoice('female');
$('#welcomeMaleVoice').onclick=()=>continueWelcomeAfterVoiceChoice('male');

$('#welcomeHowBtn').onclick=()=>{
  $('#welcomeHowStep').classList.remove('hidden');
  $('#welcomeHowBtn').disabled=true;
  const text='דוגמה: אפשר לומר “אני רוצה שמישהו יבוא לגרושה שלי וישיר לה שיר”. זו משאלה כללית. אני אבין שהיוזם הוא מארגן בלבד, שהאדם החסר הוא מבצע או מבצעת, ואשאל רק שאלות שבאמת משפיעות על ההתאמה. אם מדובר בפנטזיה אינטימית, היא עוברת למסלול המבוגרים הנפרד.';
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
  markWelcomeSeen();
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

const welcomeCloseBtn=$('#welcomeMorinModal [data-close="welcomeMorinModal"]');
if(welcomeCloseBtn){
  welcomeCloseBtn.addEventListener('click',()=>{
    markWelcomeSeen();
    if('speechSynthesis' in window)window.speechSynthesis.cancel();
  });
}

$('#welcomeMorinModal').addEventListener('click',e=>{
  if(e.target===$('#welcomeMorinModal')){
    markWelcomeSeen();
    if('speechSynthesis' in window)window.speechSynthesis.cancel();
  }
});

// Mobile browsers may refuse text-to-speech until the first user gesture.
// If the automatic attempt was blocked, the first tap inside the explanation
// replays it without requiring a special "start" flow.
document.addEventListener('pointerdown',()=>{
  if(!welcomeAutoReplayArmed || !$('#welcomeMorinModal').classList.contains('open'))return;
  welcomeAutoReplayArmed=false;
  speakWelcomeSequence();
},{capture:true});

setTimeout(()=>{
  if(!state.token && !localStorage.getItem(WELCOME_SEEN_KEY)){
    resetWelcome({auto:true});
    openModal('welcomeMorinModal');
  }
},120);
