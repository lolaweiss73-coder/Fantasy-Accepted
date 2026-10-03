(function(){
  const supported=new Set(['he','en']);

  function normalize(raw){
    const value=String(raw||'').trim().toLowerCase().replace('_','-');
    if(!value||value==='auto'){
      const browser=String(navigator.language||navigator.languages?.[0]||'en').toLowerCase();
      return browser.startsWith('he')?'he':'en';
    }
    const base=value.split('-')[0];
    return supported.has(base)?base:'en';
  }

  function preferredRaw(){
    return localStorage.getItem('faLanguage')||'auto';
  }

  function active(me=null){
    const fromProfile=me?.preferred_language;
    return normalize(fromProfile&&fromProfile!=='auto'?fromProfile:preferredRaw());
  }

  function set(raw){
    const value=String(raw||'auto').toLowerCase();
    localStorage.setItem('faLanguage',value);
    document.documentElement.lang=normalize(value);
    document.documentElement.dir=normalize(value)==='he'?'rtl':'ltr';
    return normalize(value);
  }

  function text(pair,me=null){
    const lang=active(me);
    return pair?.[lang]||pair?.en||pair?.he||'';
  }

  const generalScript=[
    {en:"Hi, I’m Morin.",he:"היי, אני מורין."},
    {en:"Fantasy Accepted is a place where you can share a wish that other people may be able to help you make real.",he:"Fantasy Accepted הוא מקום שבו אפשר לשתף משאלה שאנשים אחרים אולי יוכלו לעזור לך להפוך למציאות."},
    {en:"Your wish should be something another person can actually help with.",he:"המשאלה צריכה להיות משהו שאדם אחר באמת יכול לעזור בו."},
    {en:"For example: I want a musician to write a song for my mother.",he:"למשל: אני רוצה שמוזיקאי יכתוב שיר לאמא שלי."},
    {en:"Or: I want someone to teach me piano.",he:"או: אני רוצה שמישהו ילמד אותי לנגן בפסנתר."},
    {en:"A wish like, I want to win the lottery, doesn’t really fit, because nobody here can control the result.",he:"משאלה כמו ״אני רוצה לזכות בלוטו״ לא ממש מתאימה, כי אף אחד כאן לא יכול לשלוט בתוצאה."},
    {en:"You don’t need to know exactly how to make your wish happen.",he:"אתה לא צריך לדעת מראש איך לגרום למשאלה להתגשם."},
    {en:"Just tell me what you want, and I’ll do my AI magic to help make it happen.",he:"פשוט ספר לי מה אתה רוצה, ואני אעשה את קסמי הבינה המלאכותית שלי כדי לעזור לזה לקרות."},
    {en:"You can speak or write to me in any language. I’ll understand you. My spoken voice is always in English.",he:"אפשר לדבר או לכתוב לי בכל שפה. אני אבין אותך. הקול המדובר שלי תמיד יהיה באנגלית."},
    {en:"So, what do you wish for?",he:"אז, מה המשאלה שלך?"}
  ];

  const adultScript=[
    {en:"Hi, I’m Morin.",he:"היי, אני מורין."},
    {en:"Fantasy Accepted eighteen-plus is a place where adults can share a fantasy that other adults may be able to help make real.",he:"Fantasy Accepted שמונה־עשרה פלוס הוא מקום שבו מבוגרים יכולים לשתף פנטזיה שמבוגרים אחרים אולי יוכלו לעזור להגשים."},
    {en:"Your fantasy should involve something another person can actually choose to take part in or help with.",he:"הפנטזיה צריכה להיות משהו שאדם אחר באמת יכול לבחור להשתתף בו או לעזור בו."},
    {en:"Tell me what you want in your own words. I can help clarify the people, roles and details that matter.",he:"ספר לי במילים שלך מה אתה רוצה. אני יכולה לעזור להבין אילו אנשים, תפקידים ופרטים באמת חשובים."},
    {en:"You can speak or write to me in any language. I’ll understand you. My spoken voice is always in English.",he:"אפשר לדבר או לכתוב לי בכל שפה. אני אבין אותך. הקול המדובר שלי תמיד יהיה באנגלית."},
    {en:"Nothing is published until you review it.",he:"שום דבר לא מתפרסם לפני שאתה בודק אותו."},
    {en:"So, what do you wish for?",he:"אז, מה היית רוצה להגשים?"}
  ];

  window.FAI18N={
    normalize,
    active,
    preferredRaw,
    set,
    text,
    script(mode){return mode==='adult'?adultScript:generalScript;},
    pair(en,he){return {en,he};}
  };

  const initial=set(preferredRaw());
  document.addEventListener('DOMContentLoaded',()=>{
    document.documentElement.lang=initial;
    document.documentElement.dir=initial==='he'?'rtl':'ltr';
  });
})();