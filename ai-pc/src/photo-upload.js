export function photoDimensions(width,height,max=1600){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)throw new Error('Choose a valid photo.');
  const scale=Math.min(1,max/Math.max(width,height));
  return {width:Math.max(1,Math.round(width*scale)),height:Math.max(1,Math.round(height*scale))};
}
export async function preparePhoto(file){
  if(!file||file.size>25_000_000)throw new Error('Choose a photo smaller than 25 MB.');
  if(file.type&&!file.type.startsWith('image/'))throw new Error('Choose a photo or take a new one.');
  const url=URL.createObjectURL(file),image=new Image();
  try{
    await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(new Error('This photo format could not be opened. Choose JPEG, PNG or WebP, or take a new photo.'));image.src=url});
    const size=photoDimensions(image.naturalWidth,image.naturalHeight),canvas=document.createElement('canvas');
    canvas.width=size.width;canvas.height=size.height;
    const context=canvas.getContext('2d');
    if(!context)throw new Error('Photo preparation failed. Try a different photo.');
    context.fillStyle='#ffffff';context.fillRect(0,0,size.width,size.height);context.drawImage(image,0,0,size.width,size.height);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.88));
    if(!blob||blob.size>5_000_000)throw new Error('Choose a smaller photo.');
    return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read this photo.'));reader.readAsDataURL(blob)});
  }finally{URL.revokeObjectURL(url)}
}
