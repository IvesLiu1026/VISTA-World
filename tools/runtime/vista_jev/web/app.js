'use strict';
const $ = id => document.getElementById(id);
const video = $('video');
const titles = {wait:'暫不打擾',observe:'先確認狀況',notice_stove:'提醒爐火',notice_water:'立即提醒水位',notice_keys:'提醒鑰匙位置'};
const cues = {visible_stove_flame:'Stove flame visible',visible_stove_on_control:'Stove control ON',visible_running_bath_tap:'Tap running',visible_water_near_rim:'Water near rim',visible_water_on_floor:'Water on floor',visible_stove_off:'Stove OFF',visible_bath_tap_off:'Tap OFF',visible_keys:'Keys visible'};
let data, rows = [], current = null;
function stamp(t){const s=Math.max(0,Math.floor(t||0));return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;}
function showRow(row){
  current=row; if(!row)return;
  const answer=row.model.answer;
  $('decision-clock').textContent=stamp(row.video_s??row.relative_s);
  $('room').textContent=row.room;
  $('model-action').textContent=answer?titles[answer.action]:'沒有有效回覆';
  $('model-reason').textContent=answer?answer.reason:(row.model.error||'尚未執行');
  $('model-latency').textContent=row.model.latency_ms!=null?`API ${(row.model.latency_ms/1000).toFixed(2)} s`:'未量測';
  $('model-confidence').textContent=answer?`模型自評 ${Math.round(answer.confidence*100)}%`:'';
  $('rule-action').textContent=titles[row.rule.action];
  $('rule-reason').textContent=row.rule.reason.replaceAll('_',' ');
  $('caption').textContent=answer?data.actions[answer.action]:'No valid model response at this observation.';
  $('cues').replaceChildren();
  const values=row.observation.cues.map(v=>[cues[v]||v,v.includes('near_rim')||v.includes('on_floor')]);
  if(row.observation.human_activity==='phone_at_ear')values.push(['Human on a call',false]);
  if(!values.length)values.push(['No new visible cue',false]);
  for(const [label,urgent] of values){const el=document.createElement('span');el.className='cue'+(urgent?' urgent':'');el.textContent=label;$('cues').append(el);}
}
function update(){
  $('clock').textContent=`${stamp(video.currentTime)} / ${stamp(video.duration||174.9)}`;
  $('seek').value=video.currentTime;
  const row=rows.filter(r=>r.video_s<=video.currentTime).at(-1);
  if(row&&row!==current)showRow(row);
  if(!row&&current){current=null;$('decision-clock').textContent='00:00';$('room').textContent=rows[0]?.room||'';$('caption').textContent='The person starts a normal household routine.';$('model-action').textContent='等待第一筆觀察';$('model-reason').textContent='尚未到達第一個判斷時點。';$('rule-action').textContent='—';$('rule-reason').textContent='';$('model-latency').textContent='—';$('model-confidence').textContent='—';$('cues').replaceChildren();}
}
async function toggle(){try{if(video.paused)await video.play();else video.pause();}catch(error){$('caption').textContent='Press play again to start the video.';}}
$('play').addEventListener('click',toggle);$('center-play').addEventListener('click',toggle);
video.addEventListener('play',()=>{$('play').textContent='Ⅱ 暫停';$('center-play').hidden=true;});
video.addEventListener('pause',()=>{$('play').textContent='▶ 繼續播放';$('center-play').hidden=false;});
video.addEventListener('timeupdate',update);video.addEventListener('seeked',update);
video.addEventListener('loadedmetadata',()=>{$('seek').max=video.duration;update();});
$('seek').addEventListener('input',()=>{video.currentTime=Number($('seek').value);update();});
$('speed').addEventListener('change',()=>video.playbackRate=Number($('speed').value));
$('mute').addEventListener('click',()=>{video.muted=!video.muted;$('mute').textContent=video.muted?'聲音關閉':'英文旁白';$('mute').setAttribute('aria-label',video.muted?'開啟英文旁白':'關閉英文旁白');});
$('fullscreen').addEventListener('click',()=>{if(video.parentElement.requestFullscreen)video.parentElement.requestFullscreen();else if(video.webkitEnterFullscreen)video.webkitEnterFullscreen();});
$('inspect').addEventListener('click',()=>{if(current){$('detail-content').textContent=JSON.stringify(current,null,2);$('detail').showModal();}});
$('close-detail').addEventListener('click',()=>$('detail').close());
$('detail').addEventListener('click',event=>{if(event.target===$('detail'))$('detail').close();});
fetch('results.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json();}).then(result=>{
  data=result;rows=data.rows.filter(r=>r.episode==='native');const m=data.metrics;
  $('requests').textContent=`${m.valid} / ${m.expected}`;
  $('latency').textContent=m.p50_ms==null?'未量測':`${(m.p50_ms/1000).toFixed(2)} s`;
  $('checks').textContent=`${m.model_control_pass} / ${m.control_steps} · ${m.rule_control_pass} / ${m.control_steps}`;
  $('cost').textContent=`$${m.reported_cost_usd.toFixed(4)}`;
  const labels=['出門前的待辦','通話中的等待','水位迫近邊緣','關水後的待辦'];
  data.highlights.forEach((h,i)=>{const b=document.createElement('button');b.className='chapter';const t=document.createElement('span');t.textContent=stamp(h.time);b.append(t,document.createTextNode(labels[i]));b.addEventListener('click',()=>{video.currentTime=h.time+.05;update();});$('chapters').append(b);});
  data.rows.filter(r=>r.check).forEach(row=>{const tr=document.createElement('tr');
    const values=[row.check.check.replaceAll('_',' '),`${row.relative_s}s`,row.model.answer?titles[row.model.answer.action]:'沒有回覆',titles[row.rule.action],row.check.model_pass?'通過':'未通過'];
    values.forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i===4)td.className=row.check.model_pass?'pass':'fail';tr.append(td);});
    tr.tabIndex=0;tr.setAttribute('aria-label',`檢視 ${row.check.check} ${row.relative_s} 秒的紀錄`);
    const inspect=()=>{$('detail-content').textContent=JSON.stringify(row,null,2);$('detail').showModal();};
    tr.addEventListener('click',inspect);tr.addEventListener('keydown',e=>{if(e.key==='Enter')inspect();});$('checks-body').append(tr);
  });
  $('limits').textContent=data.limitations.join(' ');update();
}).catch(()=>document.body.classList.add('error'));
