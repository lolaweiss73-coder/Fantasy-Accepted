const WELCOME_SEEN_KEY=SITE_MODE==='adult'?'faAdultWelcomeExplainedV2':'faGeneralWelcomeExplainedV2';
let welcomeVoices=[];
let welcomeAutoReplayArmed=false;
let welcomeSpeechGeneration=0;
let welcomeActiveUtterances=0;

function welcomeLanguage(){
  return FAI18N.active(state.me);
}

function pair(en,he){
  return FAI18N.pair(en,he);
}

function captionOf(item){
  return FAI18N.text(item,state.me);
}

function currentWelcomeScript(){
  return FAI18N.script(SITE_MODE);
}

function refreshWelcomeVoices(){
  if(!('speechSynthesis' in window))return;
  welcomeVoices=window.speechSynthesis.getVoices()||[];
}
refreshWelcomeVoices();
if('speechSynthesis' in window && 'onvoiceschanged' in window.speechSynthesis){
  window.speechSynthesis.onvoiceschanged=refreshWelcomeVoices;
}

function voiceScore(voice){
  const name=String(voice?.name||'').toLowerCase();
  const lang=String(voice?.lang||'').toLowerCase();
  let score=0;
  if(lang==='en-us')score+=100;
  else if(lang.startsWith('en-us'))score+=90;
  else if(lang==='en-gb')score+=86;
  else if(lang.startsWith('en'))score+=75;
  const preferred=['samantha','ava','jenny','aria','sonia','serena','karen','moira','tessa','victoria','zira','susan','female'];
  const avoid=['david','daniel','alex','fred','tom','male'];
  if(preferred.some(t=>name.includes(t)))score+=35;
  if(avoid.some(t=>name.includes(t)))score-=18;
  return score;
}

function pickWelcomeVoice(){
  refreshWelcomeVoices();
  if(!welcomeVoices.length)return null;
  const english=welcomeVoices.filter(v=>String(v.lang||'').toLowerCase().startsWith('en'));
  const pool=english.length?english:welcomeVoices;
  return [...pool].sort((a,b)=>voiceScore(b)-voiceScore(a))[0]||null;
}

function appendWelcomeTranscript(text,speaker='Morin'){
  const box=$('#welcomeTranscript');
  if(!box)return;
  const line=`${speaker}: ${String(text||'').trim()}`;
  box.value=(box.value?box.value+'\n\n':'')+line;
  box.scrollTop=box.scrollHeight;
}

function showSubtitle(text){
  const wrap=$('#morinSubtitles');
  const box=$('#morinSubtitleText');
  if(!wrap||!box)return;
  box.textContent=String(text||'').trim();
  wrap.classList.toggle('hidden',!box.textContent);
}

function hideSubtitleSoon(generation,delay=500){
  setTimeout(()=>{
    if(generation!==welcomeSpeechGeneration || welcomeActiveUtterances>0)return;
    $('#morinSubtitles')?.classList.add('hidden');
  },delay);
}

function speakPair(item,{generation=welcomeSpeechGeneration}={}){
  if(!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window))return false;
  const spoken=String(item?.en||'').trim();
  if(!spoken)return false;
  const utterance=new SpeechSynthesisUtterance(spoken);
  utterance.lang='en-US';
  utterance.rate=0.96;
  utterance.pitch=1.02;
  const voice=pickWelcomeVoice();
  if(voice)utterance.voice=voice;
  utterance.onstart=()=>{
    if(generation!==welcomeSpeechGeneration)return;
    welcomeActiveUtterances++;
    showSubtitle(captionOf(item));
  };
  utterance.onend=()=>{
    if(generation!==welcomeSpeechGeneration)return;
    welcomeActiveUtterances=Math.max(0,welcomeActiveUtterances-1);
    hideSubtitleSoon(generation);
  };
  utterance.onerror=()=>{
    if(generation!==welcomeSpeechGeneration)return;
    welcomeActiveUtterances=Math.max(0,welcomeActiveUtterances-1);
    hideSubtitleSoon(generation);
  };
  try{
    window.speechSynthesis.speak(utterance);
    return true;
  }catch{
    return false;
  }
}

function stopWelcomeSpeech(){
  welcomeSpeechGeneration++;
  welcomeActiveUtterances=0;
  if('speechSynthesis' in window)window.speechSynthesis.cancel();
  $('#morinSubtitles')?.classList.add('hidden');
}

function speakWelcomeSequence(){
  stopWelcomeSpeech();
  const generation=welcomeSpeechGeneration;
  const script=currentWelcomeScript();
  for(const item of script)speakPair(item,{generation});
}

function welcomeSay(item,{showBubble=true,speak=true,speaker='Morin'}={}){
  const caption=captionOf(item);
  if(!caption)return;
  if(showBubble){
    const root=$('#welcomeMorinChat');
    if(root){
      const bubble=document.createElement('div');
      bubble.className='welcome-bubble morin-bubble';
      bubble.textContent=caption;
      root.append(bubble);
    }
  }
  appendWelcomeTranscript(caption,speaker);
  if(speak)speakPair(item);
}

function renderWelcomeCopy({speak=false}={}){
  const script=currentWelcomeScript();
  const root=$('#welcomeMorinChat');
  if(root)root.replaceChildren();
  if($('#welcomeTranscript'))$('#welcomeTranscript').value='';
  for(const item of script){
    const caption=captionOf(item);
    const bubble=document.createElement('div');
    bubble.className='welcome-bubble morin-bubble';
    bubble.textContent=caption;
    root?.append(bubble);
    appendWelcomeTranscript(caption);
  }

  const he=welcomeLanguage()==='he';
  if($('#welcomeMorinModal .morin-header h2')){
    $('#welcomeMorinModal .morin-header h2').textContent=he?'היי, אני מורין. הנה איך זה עובד.':'Hi, I’m Morin. Here’s how this works.';
  }
  if($('#welcomeLanguageNotice')){
    $('#welcomeLanguageNotice').textContent=he
      ?'אפשר לדבר או לכתוב לי בכל שפה. אני אבין אותך. הקול שלי תמיד באנגלית, והכתוביות מוצגות בשפה שלך.'
      :'Speak or write to me in any language. I’ll understand you. My voice is always English, and subtitles appear in your language.';
  }
  if($('#welcomeReplayBtn'))$('#welcomeReplayBtn').textContent=he?'🔊 השמיעי שוב':'🔊 Replay';
  if($('#welcomeHowBtn'))$('#welcomeHowBtn').textContent=he?'איך זה עובד בפועל?':'How does it work in practice?';
  if($('#welcomeFromAviBtn'))$('#welcomeFromAviBtn').textContent=he?'אבי שלח לי את הקישור':'Avi sent me the link';
  if($('#welcomeDoneBtn'))$('#welcomeDoneBtn').textContent=he?'הבנתי — בואי ניכנס':'Got it — let’s enter';
  const transcriptLabel=document.querySelector('label[for="welcomeTranscript"]');
  if(transcriptLabel)transcriptLabel.textContent=he?'תמלול השיחה':'Conversation transcript';

  if(speak)speakWelcomeSequence();
}

function normalizeInitials(value){
  return String(value||'')
    .toLowerCase()
    .replace(/[\s."'״׳’_-]/g,'');
}

function resetWelcome({auto=false}={}){
  stopWelcomeSpeech();
  $('#welcomeVoiceStep')?.classList.remove('hidden');
  $('#welcomeHowStep')?.classList.add('hidden');
  $('#welcomeAviStep')?.classList.add('hidden');
  $('#welcomeAnnetteConfirm')?.classList.add('hidden');
  $('#welcomePersonalMessage')?.classList.add('hidden');
  if($('#welcomeInitials'))$('#welcomeInitials').value='';
  if($('#welcomeHowBtn'))$('#welcomeHowBtn').disabled=false;
  renderWelcomeCopy({speak:true});
  welcomeAutoReplayArmed=auto;
}

function markWelcomeSeen(){
  localStorage.setItem(WELCOME_SEEN_KEY,'1');
  welcomeAutoReplayArmed=false;
}

$('#welcomeMorinBtn').onclick=()=>{
  resetWelcome({auto:false});
  openModal('welcomeMorinModal');
};

$('#welcomeReplayBtn').onclick=()=>{
  welcomeAutoReplayArmed=false;
  speakWelcomeSequence();
};

$('#welcomeHowBtn').onclick=()=>{
  $('#welcomeHowStep').classList.remove('hidden');
  $('#welcomeHowBtn').disabled=true;
  const item=SITE_MODE==='adult'
    ?pair(
      'For example, tell me the fantasy in your own words. I can identify the people or roles that are missing, ask only the questions that affect the match, and prepare a draft for you to review before anything is published.',
      'לדוגמה, ספרו לי את הפנטזיה במילים שלכם. אני יכולה לזהות מי או אילו תפקידים חסרים, לשאול רק שאלות שמשפיעות על ההתאמה, ולהכין טיוטה לבדיקה לפני שמשהו מתפרסם.'
    )
    :pair(
      'For example, you can say: I want someone to sing a song to my ex. I can understand that you are organizing the wish, identify the performer as the missing person, and ask only the questions that actually affect the match.',
      'לדוגמה, אפשר לומר: אני רוצה שמישהו ישיר שיר לגרושה שלי. אני אבין שאתם מארגנים את המשאלה, אזהה שהאדם החסר הוא מבצע או מבצעת, ואשאל רק שאלות שבאמת משפיעות על ההתאמה.'
    );
  const bubble=$('#welcomeHowStep .welcome-bubble');
  if(bubble)bubble.textContent=captionOf(item);
  appendWelcomeTranscript(captionOf(item));
  speakPair(item);
};

$('#welcomeFromAviBtn').onclick=()=>{
  $('#welcomeAviStep').classList.remove('hidden');
  const item=pair(
    'Avi may have left a personal message for you. What are the initials of your name?',
    'אבי אולי השאיר לך הודעה אישית. מה ראשי התיבות של השם שלך?'
  );
  const bubble=$('#welcomeAviStep .welcome-bubble');
  if(bubble)bubble.textContent=captionOf(item);
  appendWelcomeTranscript(captionOf(item));
  speakPair(item);
  $('#welcomeInitials').focus();
};

$('#welcomeDoneBtn').onclick=()=>{
  markWelcomeSeen();
  stopWelcomeSpeech();
  closeModal('welcomeMorinModal');
};

$('#welcomeInitialsBtn').onclick=()=>{
  const initials=normalizeInitials($('#welcomeInitials').value);
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  $('#welcomePersonalMessage').classList.add('hidden');

  if(initials==='אס' || initials==='as'){
    $('#welcomeAnnetteConfirm').classList.remove('hidden');
    const item=pair('Just to make sure, are you Annette Smirnoff?','רק כדי לוודא — את אנט סמירנוף?');
    const bubble=$('#welcomeAnnetteConfirm .welcome-bubble');
    if(bubble)bubble.textContent=captionOf(item);
    appendWelcomeTranscript(captionOf(item));
    speakPair(item);
  }else if(initials){
    const item=pair(
      'I did not find a personal message for those initials, but the explanation of the site is open to everyone.',
      'לא מצאתי הודעה אישית לפי ראשי התיבות האלה, אבל ההסבר על האתר כמובן פתוח לכולם.'
    );
    welcomeSay(item);
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
  const items=[
    pair(
      'Annette, Avi asked me to tell you something personal. Behind the unusual choices you see here is a long-term entrepreneurial vision, not just another website.',
      'אנט, אבי ביקש ממני למסור לך משהו אישי. מאחורי הבחירות הלא־שגרתיות שאת רואה עכשיו עומד אצלו חזון יזמי ארוך טווח, לא רק עוד אתר.'
    ),
    pair(
      'He is working on several ideas that he believes could change entire fields, including scent technology for movies and virtual reality, and the E L project for products designed to last an extremely long time.',
      'הוא עובד על כמה רעיונות שהוא מאמין שיכולים לשנות תחומים שלמים, למשל טכנולוגיית ריח לסרטים ול־VR, ומיזם EL של מוצרים שנועדו להחזיק מעמד זמן קיצוני.'
    ),
    pair(
      'He also thinks a lot about the economic impact of artificial intelligence and ways to reduce the cost of living and give people more security and meaning. He asked me to tell you that his ambitions are much bigger than his current situation, and that is exactly the gap he intends to close.',
      'הוא גם חושב הרבה על ההשפעה הכלכלית של בינה מלאכותית ועל דרכים להוריד יוקר מחיה ולתת לאנשים יותר ביטחון ומשמעות. הוא ביקש שאגיד לך שהשאיפות שלו הרבה יותר גדולות מהמצב שבו הוא נמצא היום, ושזה בדיוק הפער שהוא מתכוון לסגור.'
    )
  ];
  const bubbles=[...$('#welcomePersonalMessage').querySelectorAll('.welcome-bubble')];
  items.forEach((item,index)=>{
    if(bubbles[index])bubbles[index].textContent=captionOf(item);
    appendWelcomeTranscript(captionOf(item));
    speakPair(item);
  });
};

$('#welcomeAnnetteNo').onclick=()=>{
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  welcomeSay(pair(
    'Then the personal message probably was not meant for you. At least now I know not to identify people from two letters.',
    'אז כנראה שההודעה האישית לא נועדה לך. לפחות עכשיו אני יודעת שלא לנחש אנשים לפי שתי אותיות.'
  ));
};

const welcomeCloseBtn=$('#welcomeMorinModal [data-close="welcomeMorinModal"]');
if(welcomeCloseBtn){
  welcomeCloseBtn.addEventListener('click',()=>{
    markWelcomeSeen();
    stopWelcomeSpeech();
  });
}

$('#welcomeMorinModal').addEventListener('click',e=>{
  if(e.target===$('#welcomeMorinModal')){
    markWelcomeSeen();
    stopWelcomeSpeech();
  }
});

document.addEventListener('pointerdown',()=>{
  if(!welcomeAutoReplayArmed || !$('#welcomeMorinModal').classList.contains('open'))return;
  welcomeAutoReplayArmed=false;
  speakWelcomeSequence();
},{capture:true,once:false});

function maybeOpenWelcome(){
  if(SITE_MODE==='adult' && !document.body.classList.contains('adult-age-confirmed'))return;
  if(!state.token && !localStorage.getItem(WELCOME_SEEN_KEY) && !$('#welcomeMorinModal').classList.contains('open')){
    resetWelcome({auto:true});
    openModal('welcomeMorinModal');
  }
}

window.refreshWelcomeLanguage=()=>{
  if($('#welcomeMorinModal')?.classList.contains('open')){
    stopWelcomeSpeech();
    renderWelcomeCopy({speak:false});
  }
};

document.addEventListener('fa:adult-gate-accepted',()=>{
  setTimeout(maybeOpenWelcome,80);
});

setTimeout(maybeOpenWelcome,120);
