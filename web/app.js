'use strict';
const $ = id => document.getElementById(id);
const names = {antacil:'Antacil',betadine:'Betadine',fahtalaijone:'ฟ้าทะลายโจร',gaviscon:'Gaviscon',yoki:'Yoki'};
let stream = null, generation = 0, timer = null, controller = null, ready = false;
let streak = 0, lastKey = '', errors = 0;
const capture = document.createElement('canvas');
const ctx = capture.getContext('2d');
const snapshot = $('snapshot'), draw = snapshot.getContext('2d');
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function clearVerdict(label = 'รอเริ่มตรวจ') {
  $('verdict').className='verdict idle'; $('verdictIcon').textContent='—';
  $('verdictLabel').textContent=label; $('verdictText').textContent='ยังไม่มีผลตรวจ';
  $('medicine').textContent='—'; $('routeConfidence').textContent='—'; $('qcConfidence').textContent='—';
  document.querySelectorAll('.model').forEach(e=>e.classList.remove('active'));
}
async function cameras() {
  if (!navigator.mediaDevices?.enumerateDevices) return;
  const selected = stream?.getVideoTracks()[0]?.getSettings().deviceId || $('cameraSelect').value;
  const devices = (await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput');
  $('cameraSelect').replaceChildren();
  if (!devices.length) $('cameraSelect').add(new Option('ไม่พบกล้อง กรุณาเชื่อมต่อกล้อง USB',''));
  devices.forEach((d,i)=>$('cameraSelect').add(new Option(d.label || `กล้อง ${i+1}`, d.deviceId)));
  if ([...$('cameraSelect').options].some(o=>o.value===selected)) $('cameraSelect').value=selected;
}
function stop(message = 'หยุดกล้องแล้ว') {
  generation++; clearTimeout(timer); controller?.abort(); controller=null;
  if(stream) stream.getTracks().forEach(t=>t.stop());
  stream=null; $('video').srcObject=null; $('cameraEmpty').hidden=false;
  $('liveDot').className='dot'; $('frameStatus').textContent=message;
  $('start').disabled=!ready; $('stop').disabled=true; $('cameraSelect').disabled=false;
  streak=0;lastKey='';clearVerdict(message);
  snapshot.style.display='none';$('snapshotEmpty').hidden=false;
  $('details').textContent='ผลจะยืนยันเมื่อพบต่อเนื่อง 3 ภาพ';
  $('performance').textContent='— ms / ภาพ';
}
async function start() {
  stop(); error(''); $('start').disabled=true; $('stop').disabled=false;
  $('cameraSelect').disabled=true; $('frameStatus').textContent='รออนุญาตใช้กล้องในเบราว์เซอร์';
  const token=generation;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('เบราว์เซอร์นี้เปิดกล้องไม่ได้ กรุณาเปิดผ่าน Chrome หรือ Edge ที่ localhost');
    const id=$('cameraSelect').value;
    const permissionReminder=setTimeout(()=>{if(token===generation&&!stream)error('กำลังรอสิทธิ์กล้อง หากไม่มีหน้าต่างอนุญาต ให้เปิด http://127.0.0.1:8000 ใน Chrome, Edge หรือ Brave แล้วลองใหม่');},12000);
    let acquired;
    try { acquired = await navigator.mediaDevices.getUserMedia({audio:false,video:{...(id?{deviceId:{exact:id}}:{}),width:{ideal:1280},height:{ideal:720}}}); }
    finally {clearTimeout(permissionReminder);}
    if(token!==generation){acquired.getTracks().forEach(t=>t.stop());return;}
    stream=acquired;const video=$('video');video.srcObject=stream;await video.play();
    if(token!==generation)return;
    $('viewport').style.aspectRatio=`${video.videoWidth}/${video.videoHeight}`;
    $('cameraEmpty').hidden=true;$('liveDot').className='dot on';$('stop').disabled=false;
    $('cameraSelect').disabled=true;$('frameStatus').textContent='LIVE · กำลังตรวจ';
    $('streamInfo').textContent=`${video.videoWidth} × ${video.videoHeight}`;
    await cameras();errors=0;
    stream.getVideoTracks()[0].addEventListener('ended',()=>{stop('กล้องถูกตัดการเชื่อมต่อ');error('กล้องหยุดส่งภาพ กรุณาเชื่อมต่อและเปิดกล้องใหม่');},{once:true});
    await inspectFrame(token);
  } catch(e) {
    if(token!==generation)return;
    stop();
    const messages={NotAllowedError:'กรุณาอนุญาตให้เบราว์เซอร์ใช้กล้อง แล้วกดเปิดกล้องอีกครั้ง',NotFoundError:'ไม่พบกล้อง USB กรุณาเชื่อมต่อกล้องแล้วลองใหม่',NotReadableError:'เปิดกล้องไม่ได้ อาจมีแอปอื่นใช้งานอยู่ กรุณาปิดแอปนั้นแล้วลองใหม่',OverconstrainedError:'กล้องที่เลือกไม่พร้อมใช้งาน กรุณาเลือกกล้องใหม่'};
    error(messages[e.name]||e.message);
    cameras().catch(()=>{});
  }
}
function render(result) {
  const route=result.route;
  $('routeConfidence').textContent=`${(route.confidence*100).toFixed(1)}%`;
  $('qcConfidence').textContent=result.qc_confidence===null?'—':`${(result.qc_confidence*100).toFixed(1)}%`;
  $('medicine').textContent=result.medicine?names[result.medicine]:'ยังระบุไม่ได้';
  document.querySelectorAll('.model').forEach(e=>e.classList.toggle('active',e.dataset.id===result.medicine));
  const key=result.medicine+':'+result.status;
  streak=key===lastKey?streak+1:1;lastKey=key;
  const stable=streak>=3 && result.status!=='uncertain';
  const status=stable?result.status:'uncertain';
  $('verdict').className=`verdict ${status}`;
  $('verdictIcon').textContent=stable?(status==='normal'?'✓':'!'):'…';
  $('verdictLabel').textContent=stable?'ผลต่อเนื่องตรงกัน 3 ภาพขึ้นไป':'กำลังตรวจสอบ';
  $('verdictText').textContent=stable?(status==='normal'?'ปกติ / ผ่าน QC':'พบความเสียหาย'):(result.status==='uncertain'?'ยังยืนยันไม่ได้':`รอยืนยัน ${Math.min(streak,3)} / 3`);
  $('details').textContent=result.detections.length?[...new Set(result.detections.map(d=>d.label))].join(' · '):'จัดยาให้อยู่กลางกรอบ เห็นทั้งชิ้น และมีแสงเพียงพอ';
  snapshot.width=capture.width;snapshot.height=capture.height;
  draw.drawImage(capture,0,0);snapshot.style.display='block';$('snapshotEmpty').hidden=true;
  result.detections.forEach(d=>{
    const color=d.normal?'#42eeab':'#ff795f';draw.strokeStyle=color;draw.lineWidth=3;draw.fillStyle=d.normal?'#42eeab30':'#ff795f30';
    if(d.polygon.length){draw.beginPath();d.polygon.forEach(([x,y],i)=>i?draw.lineTo(x*snapshot.width,y*snapshot.height):draw.moveTo(x*snapshot.width,y*snapshot.height));draw.closePath();draw.fill();draw.stroke();}
    const [x1,y1,x2,y2]=d.box;draw.strokeRect(x1*snapshot.width,y1*snapshot.height,(x2-x1)*snapshot.width,(y2-y1)*snapshot.height);
  });
  $('performance').textContent=`${result.elapsed_ms} ms / ภาพ`;
  $('frameStatus').textContent=stable?(status==='normal'?'LIVE · ปกติ':'LIVE · พบความเสียหาย'):'LIVE · กำลังตรวจ';
}
async function inspectFrame(token) {
  if(!stream || token!==generation)return;
  const video=$('video');
  const sw=video.videoWidth*.7,sh=video.videoHeight*.7;
  const scale=Math.min(1,800/Math.max(sw,sh));
  capture.width=Math.round(sw*scale);capture.height=Math.round(sh*scale);
  ctx.drawImage(video,video.videoWidth*.15,video.videoHeight*.15,sw,sh,0,0,capture.width,capture.height);
  let timeout;
  try {
    const blob=await new Promise(resolve=>capture.toBlob(resolve,'image/jpeg',.88));
    if(token!==generation)return;
    controller=new AbortController();timeout=setTimeout(()=>controller?.abort(),15000);
    const response=await fetch('/api/inspect',{method:'POST',headers:{'Content-Type':'image/jpeg'},body:blob,signal:controller.signal});
    const result=await response.json();if(!response.ok)throw new Error(result.detail||'ตรวจภาพไม่สำเร็จ');
    if(token!==generation)return;
    render(result);errors=0;error('');
  } catch(e) {
    if(token!==generation)return;
    streak=0;lastKey='';clearVerdict('การตรวจสะดุด');
    snapshot.style.display='none';$('snapshotEmpty').hidden=false;
    error(e.name==='AbortError'?'ระบบใช้เวลาตรวจนานเกินไป กรุณาลองใหม่':e.message);
    if(++errors>=3){stop('การตรวจหยุดชั่วคราว');return;}
  } finally {clearTimeout(timeout);}
  if(token===generation && stream)timer=setTimeout(()=>inspectFrame(token),150);
}
async function health() {
  try{
    const response=await fetch('/api/health');if(!response.ok)throw new Error('health');
    const data=await response.json();ready=data.ready;
    $('systemStatus').textContent=ready?'ระบบพร้อมตรวจ':(data.error?'ระบบยังไม่พร้อม':'กำลังโหลดโมเดล…');
    $('start').disabled=!ready||!!stream;
    $('modelCount').textContent=`${ready?5:0} / 5 พร้อม`;
    $('models').replaceChildren(...data.models.map(m=>{const div=document.createElement('div');div.className='model';div.dataset.id=m.id;const title=document.createElement('strong');title.textContent=m.name;const status=document.createElement('span');status.textContent=m.loaded?'พร้อมใช้งาน':'กำลังโหลด';div.append(title,status);return div;}));
    if(data.error)error(data.error);
    if(!ready&&!data.error)setTimeout(health,1500);
  }catch(e){ready=false;$('start').disabled=true;$('systemStatus').textContent='เชื่อมต่อระบบไม่ได้';error('กรุณาตรวจว่า ARGUS ยังเปิดทำงานอยู่');setTimeout(health,3000);}
}
$('start').addEventListener('click',start);$('stop').addEventListener('click',()=>{stop();error('');});
navigator.mediaDevices?.addEventListener('devicechange',()=>cameras().catch(()=>{}));
document.addEventListener('visibilitychange',()=>{if(document.hidden&&stream)stop('พักกล้องเมื่อออกจากหน้านี้');});
window.addEventListener('pagehide',()=>stop());
setInterval(()=>$('clock').textContent=new Date().toLocaleTimeString('th-TH',{hour12:false}),1000);
cameras().catch(()=>{});health();
