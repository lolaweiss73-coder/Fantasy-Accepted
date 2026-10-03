(function(){
  const MAX_FILES=8;
  const MAX_SOURCE_BYTES=10*1024*1024;
  const MAX_DIMENSION=1800;

  function apiPath(path){
    return path.startsWith('/api/')?`${API_BASE}${path}`:path;
  }

  async function imageElementFromFile(file){
    const url=URL.createObjectURL(file);
    try{
      const img=new Image();
      img.decoding='async';
      await new Promise((resolve,reject)=>{
        img.onload=resolve;
        img.onerror=()=>reject(new Error('Could not read this image.'));
        img.src=url;
      });
      return img;
    }finally{
      // The image pixels remain decoded after load.
      setTimeout(()=>URL.revokeObjectURL(url),0);
    }
  }

  async function prepareImage(file){
    if(!file || !String(file.type||'').startsWith('image/'))throw new Error('Please choose an image file.');
    if(file.size>MAX_SOURCE_BYTES)throw new Error('Each image must be smaller than 10 MB.');
    const img=await imageElementFromFile(file);
    const scale=Math.min(1,MAX_DIMENSION/Math.max(img.naturalWidth||img.width,img.naturalHeight||img.height));
    const width=Math.max(1,Math.round((img.naturalWidth||img.width)*scale));
    const height=Math.max(1,Math.round((img.naturalHeight||img.height)*scale));
    const canvas=document.createElement('canvas');
    canvas.width=width; canvas.height=height;
    const ctx=canvas.getContext('2d',{alpha:false});
    ctx.fillStyle='#fff'; ctx.fillRect(0,0,width,height);
    ctx.drawImage(img,0,0,width,height);
    return canvas.toDataURL('image/jpeg',0.84);
  }

  async function uploadPrepared(dataUrl,{purpose,fantasyId=null,visibility='public'}){
    return api('/api/photos',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({purpose,data_url:dataUrl,visibility,fantasy_id:fantasyId})
    });
  }

  async function uploadFiles(files,options){
    const list=[...(files||[])].slice(0,MAX_FILES);
    const out=[];
    for(const file of list){
      const dataUrl=await prepareImage(file);
      out.push(await uploadPrepared(dataUrl,options));
    }
    return out;
  }

  async function setProtectedImage(img,photo){
    if(!img||!photo?.id)return;
    img.classList.add('photo-loading');
    try{
      const url=photo.url||`${API_BASE}/api/photos/${photo.id}`;
      const response=await fetch(url,{headers:authHeaders()});
      if(!response.ok)throw new Error('Photo unavailable');
      const blob=await response.blob();
      const objectUrl=URL.createObjectURL(blob);
      img.onload=()=>{
        img.classList.remove('photo-loading');
        URL.revokeObjectURL(objectUrl);
      };
      img.onerror=()=>{
        img.classList.remove('photo-loading');
        URL.revokeObjectURL(objectUrl);
      };
      img.src=objectUrl;
    }catch{
      img.classList.remove('photo-loading');
      img.alt='Photo unavailable';
    }
  }

  function previewFiles(files,root){
    if(!root)return;
    root.replaceChildren();
    const list=[...(files||[])].slice(0,MAX_FILES);
    for(const file of list){
      const tile=document.createElement('div');
      tile.className='photo-tile preview';
      const img=document.createElement('img');
      img.alt='Selected photo preview';
      const url=URL.createObjectURL(file);
      img.onload=()=>URL.revokeObjectURL(url);
      img.src=url;
      tile.append(img);
      root.append(tile);
    }
  }

  window.FA_MEDIA={MAX_FILES,prepareImage,uploadPrepared,uploadFiles,setProtectedImage,previewFiles};
})();