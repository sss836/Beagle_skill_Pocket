'use strict';
const TaskUI={
  info:null,skill:null,selected:null,busy:false,lastSnapshot:'',
  async request(route,data){
    if(data && !this.info)await this.connect();
    const response=await fetch(route,data?{method:'POST',headers:{'Content-Type':'application/json','X-Beagle-Token':this.info.token},body:JSON.stringify(data)}:{});
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'连接没有完成，请重试。');
    return result;
  },
  error(error){$('jobError').textContent=error.message||String(error);$('jobError').hidden=false;},
  async connect(){
    this.info=await this.request('/api/runner');
    $('runnerState').textContent=this.info.available?'已连接本机 Codex · 使用已有登录':'未找到 Codex，请先安装并登录。';
    const prior=$('jobWorkspace').value;
    $('jobWorkspace').replaceChildren();
    this.info.workspaces.forEach(path=>{const option=el('option','',path);option.value=path;$('jobWorkspace').append(option);});
    if(this.info.workspaces.includes(prior))$('jobWorkspace').value=prior;
    return this.info;
  },
  start(skill,task=''){
    this.skill=skill; setView('tasks'); $('jobForm').hidden=false;$('jobSkillLabel').textContent=skill?'使用：'+skill.title:'自动选择技能';
    $('jobTask').value=task;$('jobFiles').value='';$('jobError').hidden=true;$('jobTask').focus();
    this.connect().catch(error=>this.error(error));
    this.loadModels();
  },
  async loadModels(){
    try{const result=await this.request('/api/models');const prior=$('jobModel').value;$('jobModel').replaceChildren(el('option','','沿用当前 Codex 设置'));$('jobModel').firstElementChild.value='';result.models.forEach(model=>{const option=el('option','',model.displayName);option.value=model.model;$('jobModel').append(option);});if([...$('jobModel').options].some(x=>x.value===prior))$('jobModel').value=prior;$('modelHint').textContent='模型来自当前 Codex 实际列表；子 Agent 的单独选型取决于执行环境。';}
    catch(error){$('modelHint').textContent='暂未取到模型列表，仍可沿用当前 Codex 设置。';}
  },
  async submit(event){
    event.preventDefault();$('jobError').hidden=true;$('submitJob').disabled=true;
    try{
      const job=await this.request('/api/jobs',{task:$('jobTask').value.trim(),workspace:$('jobWorkspace').value,
        files:$('jobFiles').value.split('\n').map(x=>x.trim()).filter(Boolean),skill_id:this.skill?.id,model:$('jobModel').value||null});
      $('jobForm').hidden=true;this.select(job.id);notify('比格已接单，真实进度会显示在这里。');
    }catch(error){this.error(error);}finally{$('submitJob').disabled=false;}
  },
  select(id){
    this.selected=id;this.lastSnapshot='';
    const url=new URL(location.href);url.searchParams.set('job',id);history.replaceState(null,'',url);
    this.refresh();
  },
  async refresh(){
    if(this.busy)return;
    this.busy=true;
    try{
      if(!this.info)await this.connect();
      const data=await this.request('/api/jobs');$('taskCount').textContent=data.jobs.length;
      $('jobList').replaceChildren();
      if(!data.jobs.length)$('jobList').append(el('p','task-empty','还没有任务。比格待命中。'));
      data.jobs.forEach(job=>{
        const node=button('','job-list-item'+(this.selected===job.id?' selected':''),()=>this.select(job.id));
        node.append(el('strong','',job.task),el('small','',job.status_label+' · '+job.skill_title));$('jobList').append(node);
      });
      if(this.selected){
        const job=await this.request('/api/job?id='+encodeURIComponent(this.selected));
        // Keep answer fields stable while a human is responding to a pending request.
        const snapshot=JSON.stringify(job.pending.length?{id:job.id,status:job.status,pending:job.pending}:job);
        if(snapshot!==this.lastSnapshot){this.lastSnapshot=snapshot;this.draw(job);}
      }
    }catch(error){this.error(error);}finally{this.busy=false;}
  },
  draw(job){
    const box=$('jobDetail');box.replaceChildren();
    const active=!['completed','failed','cancelled','interrupted'].includes(job.status);
    const top=el('div','job-top');top.append(el('span','job-state '+job.status,job.status_label));
    if(active)top.append(button('停止任务','job-stop',async()=>{try{await this.request('/api/job/cancel',{id:job.id});this.refresh();}catch(e){this.error(e);}}));
    box.append(top,el('h3','',job.task.length>65?job.task.slice(0,65)+'…':job.task),el('p','',job.skill_title+' · '+job.workspace));
    box.append(el('p','','执行模型：'+(job.actual_model||job.model_label||'沿用当前 Codex 设置')));
    if(job.task.length>65){const full=el('details');full.append(el('summary','','查看完整任务'),el('p','',job.task));box.append(full);}
    if(job.plan?.length){const plan=el('ul','job-timeline');job.plan.forEach(step=>plan.append(el('li','',(step.status==='completed'?'✓ ':step.status==='inProgress'||step.status==='in_progress'?'→ ':'○ ')+step.step)));box.append(plan);}
    job.pending.forEach(request=>box.append(this.requestCard(job,request)));
    const text=job.result||Object.values(job.messages).map(m=>m.text).filter(Boolean).join('\n\n');
    if(text)box.append(el('pre','',text));
    if(job.error)box.append(el('p','task-error',job.error));
    if(job.artifacts.length){
      const files=el('div','job-artifacts');files.append(el('h4','','成果文件'));
      job.artifacts.forEach(path=>{const link=el('a','',path.split(/[\\/]/).pop()+' ↓');link.href='/api/artifact?'+new URLSearchParams({id:job.id,path});link.download='';link.title=path;files.append(link);});box.append(files);
    }
    const timeline=el('ul','job-timeline');job.events.slice(-8).forEach(event=>timeline.append(el('li','',new Date(event.time*1000).toLocaleTimeString('zh-CN',{hour12:false})+' '+event.message)));box.append(timeline);
  },
  requestCard(job,request){
    const box=el('section','job-request');box.append(el('h4','',request.kind==='questions'?'比格有个问题，需要你补充。':'这一步，需要你确认。'));
    const params=request.params;
    const controls=[];
    if(request.kind==='questions'){
      (params.questions||[]).forEach(question=>{
        const label=el('label','',question.question||question.header||question.id);
        const input=el('input');input.placeholder='填写你的回答';input.setAttribute('aria-label',question.question||question.id);
        if(question.options?.length){
          const hints=el('div','');question.options.forEach(option=>hints.append(button(option.label,'',()=>{input.value=option.label;})));box.append(label,hints);
          box.append(el('p','option-hint',question.options.map(x=>x.label+'：'+(x.description||'')).join('；')));
        }else box.append(label);
        box.append(input);controls.push({id:question.id,input});
      });
    }else{
      if(params.reason)box.append(el('p','',params.reason));
      let details=params.command || params.grantRoot || params.commandActions;
      if(params.networkApprovalContext)details={网络访问:params.networkApprovalContext,操作:params.command};
      if(params.permissions)details=params.permissions;
      if(details)box.append(el('pre','',typeof details==='string'?details:JSON.stringify(details,null,2)));
      if(params.cwd)box.append(el('p','','工作文件夹：'+params.cwd));
    }
    const actions=el('div','request-actions');
    const respond=async(data)=>{try{await this.request('/api/job/respond',{id:job.id,request_id:request.id,...data});this.lastSnapshot='';this.refresh();}catch(error){this.error(error);}};
    if(request.kind==='questions')actions.append(button('提交回答','',()=>respond({answers:Object.fromEntries(controls.map(c=>[c.id,c.input.value]))})));
    else{
      const allowed=params.availableDecisions;
      if(!allowed||allowed.includes('accept'))actions.append(button('允许这一次','',()=>respond({decision:'accept'})));
      if(!allowed||allowed.includes('decline'))actions.append(button('拒绝','',()=>respond({decision:'decline'})));
    }
    box.append(actions);return box;
  }
};
$('newTask').addEventListener('click',()=>TaskUI.start(null,query()));
$('anotherTask').addEventListener('click',()=>TaskUI.start(null));
$('detailRun').addEventListener('click',()=>{const skill=state.detail;const task=$('task').value;$('detail').close();TaskUI.start(skill,task);});
$('jobForm').addEventListener('submit',event=>TaskUI.submit(event));
$('addWorkspace').addEventListener('click',async()=>{try{await TaskUI.request('/api/workspaces',{path:$('workspacePath').value.trim()});await TaskUI.connect();$('jobWorkspace').value=$('workspacePath').value.trim();$('workspacePath').value='';}catch(error){TaskUI.error(error);}});
TaskUI.connect().then(()=>TaskUI.refresh()).catch(()=>{$('runnerState').textContent='本机连接暂未完成，请稍后重试。';});
const requestedJob=new URLSearchParams(location.search).get('job');
if(requestedJob){setView('tasks');TaskUI.selected=requestedJob;}
setInterval(()=>{if(state.view==='tasks'&&!document.hidden)TaskUI.refresh();},1500);
