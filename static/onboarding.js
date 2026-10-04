const WELCOME_SEEN_KEY=SITE_MODE==='adult'?'faAdultWelcomeExplainedV3':'faGeneralWelcomeExplainedV3';
let welcomeAudioGeneration=0;
let welcomeCurrentAudio=null;
let welcomeBlockedAudio=null;
let welcomeAutoReplayArmed=false;
const welcomeAudioUrlCache=new Map();

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

function hideSubtitle(){
  $('#morinSubtitles')?.classList.add('hidden');
}

function normalLanguageNotice(){
  return welcomeLanguage()==='he'
    ?'אפשר לדבר או לכתוב לי בכל שפה. אני אבין אותך. הקול שלי תמיד באנגלית, והכתוביות מוצגות בשפה שלך. הקול שאת/ה שומע/ת נוצר באמצעות בינה מלאכותית.'
    :'Speak or write to me in any language. I’ll understand you. My voice is always English, and subtitles appear in your language. The voice you hear is AI-generated.';
}

function tapLanguageNotice(){
  return welcomeLanguage()==='he'
    ?'הדפדפן מחכה ללחיצה הראשונה כדי לאפשר קול. גע/י במסך פעם אחת ומורין תתחיל לדבר.'
    :'Your browser is waiting for the first tap before it can play sound. Tap once and Morin will start speaking.';
}

function setLanguageNotice(text=normalLanguageNotice()){
  if($('#welcomeLanguageNotice'))$('#welcomeLanguageNotice').textContent=text;
}

function audioPath(path){
  return `${API_BASE}${path}`;
}

function cachedAudioUrl(key,path){
  if(welcomeAudioUrlCache.has(key))return welcomeAudioUrlCache.get(key);
  const promise=fetch(audioPath(path))
    .then(response=>{
      if(!response.ok)throw new Error(`Voice request failed (${response.status})`);
      return response.blob();
    })
    .then(blob=>URL.createObjectURL(blob))
    .catch(err=>{
      welcomeAudioUrlCache.delete(key);
      throw err;
    });
  welcomeAudioUrlCache.set(key,promise);
  return promise;
}

function preloadWelcomeAudio(){
  const script=currentWelcomeScript();
  script.forEach((_,index)=>{
    cachedAudioUrl(`base:${SITE_MODE}:${index}`,`/api/morin/welcome-audio/${index}`).catch(()=>{});
  });
}

function stopWelcomeSpeech(){
  welcomeAudioGeneration++;
  welcomeAutoReplayArmed=false;
  welcomeBlockedAudio=null;
  if(welcomeCurrentAudio){
    try{welcomeCurrentAudio.pause()}catch{}
    welcomeCurrentAudio=null;
  }
  hideSubtitle();
  setLanguageNotice();
}

function attachAndPlayAudio(url,caption,{generation,onended}){
  if(generation!==welcomeAudioGeneration)return;
  const audio=new Audio(url);
  audio.preload='auto';
  welcomeCurrentAudio=audio;
  audio.onplay=()=>{
    if(generation!==welcomeAudioGeneration)return;
    showSubtitle(caption);
    setLanguageNotice();
  };
  audio.onended=()=>{
    if(generation!==welcomeAudioGeneration)return;
    welcomeCurrentAudio=null;
    welcomeBlockedAudio=null;
    if(typeof onended==='function')onended();
  };
  audio.onerror=()=>{
    if(generation!==welcomeAudioGeneration)return;
    welcomeCurrentAudio=null;
    welcomeBlockedAudio=null;
    if(typeof onended==='function')setTimeout(onended,250);
  };

  const playResult=audio.play();
  if(playResult&&typeof playResult.catch==='function'){
    playResult.catch(()=>{
      if(generation!==welcomeAudioGeneration)return;
      welcomeBlockedAudio={audio,caption,generation};
      welcomeAutoReplayArmed=true;
      showSubtitle(caption);
      setLanguageNotice(tapLanguageNotice());
    });
  }
}

async function playWelcomeSegment(index,generation){
  const script=currentWelcomeScript();
  if(generation!==welcomeAudioGeneration)return;
  if(index>=script.length){
    welcomeAutoReplayArmed=false;
    welcomeBlockedAudio=null;
    setLanguageNotice();
    setTimeout(()=>{
      if(generation===welcomeAudioGeneration)hideSubtitle();
    },600);
    return;
  }

  const item=script[index];
  const caption=captionOf(item);
  try{
    const url=await cachedAudioUrl(
      `base:${SITE_MODE}:${index}`,
      `/api/morin/welcome-audio/${index}`
    );
    attachAndPlayAudio(url,caption,{
      generation,
      onended:()=>playWelcomeSegment(index+1,generation)
    });
  }catch{
    showSubtitle(caption);
    setTimeout(()=>playWelcomeSegment(index+1,generation),700);
  }
}

function speakWelcomeSequence(){
  stopWelcomeSpeech();
  const generation=welcomeAudioGeneration;
  preloadWelcomeAudio();
  playWelcomeSegment(0,generation);
}

async function playExtraVoice(key,item){
  stopWelcomeSpeech();
  const generation=welcomeAudioGeneration;
  const caption=captionOf(item);
  showSubtitle(caption);
  try{
    const url=await cachedAudioUrl(
      `extra:${key}`,
      `/api/morin/welcome-extra-audio/${encodeURIComponent(key)}`
    );
    attachAndPlayAudio(url,caption,{
      generation,
      onended:()=>{
        if(generation===welcomeAudioGeneration)setTimeout(hideSubtitle,500);
      }
    });
  }catch{
    setTimeout(hideSubtitle,1200);
  }
}

function resumeBlockedAudio(){
  const pending=welcomeBlockedAudio;
  if(!pending || pending.generation!==welcomeAudioGeneration)return false;
  welcomeAutoReplayArmed=false;
  setLanguageNotice();
  try{
    const result=pending.audio.play();
    if(result&&typeof result.catch==='function'){
      result.catch(()=>setLanguageNotice(tapLanguageNotice()));
    }
    return true;
  }catch{
    setLanguageNotice(tapLanguageNotice());
    return false;
  }
}

function renderWelcomeCopy({speak=false}={}){
  const root=$('#welcomeMorinChat');
  if(root)root.replaceChildren();

  const he=welcomeLanguage()==='he';
  if($('#welcomeMorinModal .morin-header h2')){
    $('#welcomeMorinModal .morin-header h2').textContent=he?'היי, אני מורין. הנה איך זה עובד.':'Hi, I’m Morin. Here’s how this works.';
  }
  setLanguageNotice();
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
  playExtraVoice(SITE_MODE==='adult'?'how_adult':'how_general',item);
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
  playExtraVoice('avi_prompt',item);
  $('#welcomeInitials').focus();
};

$('#welcomeDoneBtn').onclick=()=>{
  markWelcomeSeen();
  stopWelcomeSpeech();
  closeModal('welcomeMorinModal');
  setTimeout(()=>$('#nickname')?.focus(),80);
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
    playExtraVoice('annette_confirm',item);
  }else if(initials){
    const item=pair(
      'I did not find a personal message for those initials, but the explanation of the site is open to everyone.',
      'לא מצאתי הודעה אישית לפי ראשי התיבות האלה, אבל ההסבר על האתר כמובן פתוח לכולם.'
    );
    appendWelcomeTranscript(captionOf(item));
    const root=$('#welcomeMorinChat');
    const bubble=document.createElement('div');
    bubble.className='welcome-bubble morin-bubble';
    bubble.textContent=captionOf(item);
    root?.append(bubble);
    playExtraVoice('no_personal_message',item);
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
  });

  stopWelcomeSpeech();
  const generation=welcomeAudioGeneration;
  const keys=['annette_message_1','annette_message_2','annette_message_3'];
  const playAt=index=>{
    if(index>=items.length || generation!==welcomeAudioGeneration)return;
    const item=items[index];
    const key=keys[index];
    cachedAudioUrl(`extra:${key}`,`/api/morin/welcome-extra-audio/${key}`)
      .then(url=>attachAndPlayAudio(url,captionOf(item),{
        generation,
        onended:()=>playAt(index+1)
      }))
      .catch(()=>playAt(index+1));
  };
  playAt(0);
};

$('#welcomeAnnetteNo').onclick=()=>{
  $('#welcomeAnnetteConfirm').classList.add('hidden');
  const item=pair(
    'Then the personal message probably was not meant for you. At least now I know not to identify people from two letters.',
    'אז כנראה שההודעה האישית לא נועדה לך. לפחות עכשיו אני יודעת שלא לנחש אנשים לפי שתי אותיות.'
  );
  appendWelcomeTranscript(captionOf(item));
  const root=$('#welcomeMorinChat');
  const bubble=document.createElement('div');
  bubble.className='welcome-bubble morin-bubble';
  bubble.textContent=captionOf(item);
  root?.append(bubble);
  playExtraVoice('annette_no',item);
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
  if(!$('#welcomeMorinModal')?.classList.contains('open'))return;
  if(welcomeBlockedAudio)resumeBlockedAudio();
},{capture:true});

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
