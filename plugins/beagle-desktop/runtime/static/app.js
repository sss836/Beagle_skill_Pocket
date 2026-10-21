'use strict';
const $ = id => document.getElementById(id);
const state = {skills: [], categories: [], view: 'local', category: '全部技能', online: [], onlineQuery: '', searched: false, loading: false, detail: null, favorites: new Set(), searchEpoch: 0};
try { state.favorites = new Set(JSON.parse(localStorage.getItem('skill-station-favorites') || '[]')); } catch (_) {}
const icons = {'全部技能':'▦','协作与导航':'🐾','论文与研究':'📚','图表与设计':'🎨','文档与办公':'📝','网站与开发':'🌐','工具与连接':'🔌','模板与其他':'🗂️'};
const hints = [['论文','文献','学术','research','academic'],['润色','翻译','polishing','editing'],['ppt','汇报','幻灯','presentation','paper2ppt'],['画图','绘图','图表','figure','visualization'],['agent','分工','协作','team'],['网页','网站','前端','sites','web'],['表格','excel','csv','spreadsheets'],['word','文档','documents','docx'],['图片','插画','imagegen'],['审稿','reviewer','review'],['引用','citation'],['调试','bug','测试','testing'],['性能','performance'],['pdf']];
const el = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; };
const button = (text, cls, action) => { const node = el('button', cls, text); node.type = 'button'; node.addEventListener('click', action); return node; };
function notify(message) { $('toast').textContent = message; $('toast').classList.add('visible'); clearTimeout(notify.timer); notify.timer = setTimeout(() => $('toast').classList.remove('visible'), 2800); }
async function copy(text) {
  try { await navigator.clipboard.writeText(text); notify('已复制，粘贴到 Codex 就能使用'); }
  catch (_) { const area = el('textarea'); area.value = text; document.body.append(area); area.select(); const done = document.execCommand('copy'); area.remove(); notify(done ? '已复制，粘贴到 Codex 就能使用' : '复制受浏览器限制，请在技能说明中手动复制名称'); }
}
function query() { return $('query').value.trim(); }
function hubPrompt() { return `使用 $skill-hub，${query() || '先展示当前可用技能的分类入口，并根据我的目标选择合适的技能。'}`; }
function paintHero(view) {
  const moods = {
    local: {lead:'这活，非得我来？',strong:'让技能先上。',description:'论文、图表、PPT……活你来点，技能去干。',mood:'今日状态：人没醒，技能已就位',speech:'还不下班吗？',image:'work',alt:'趴在键盘前半眯着眼的比格',label:'本店店长 · 精神离线',kicker:'挑一个，少熬一点。'},
    discover: {lead:'这活不会？',strong:'去摇个外援。',description:'说清楚需求，去社区找个能干的。先核查，再决定。',mood:'今日营业：找帮手可以，瞎装不行',speech:'技能已上桌，您慢用。',image:'service',alt:'端着蛋糕和果汁的比格',label:'外援接待员 · 勉强营业',kicker:'外援可以摇，来源得看好。'},
    favorites: {lead:'好用的先囤着。',strong:'下次少熬一点。',description:'常用的小帮手放在这里，下次不用翻箱倒柜。',mood:'比格私藏：这几个，是真想留',speech:'收藏一下嘛……',image:'please',alt:'睁着大眼睛求收藏的比格',label:'求收藏专员 · 眼神就位',kicker:'谁好用，谁就有位置。'}
  };
  const mood=moods[view] || moods.local;
  $('heroTitle').replaceChildren(document.createTextNode(mood.lead),el('strong','',mood.strong));
  $('heroDescription').textContent=mood.description; $('heroMood').textContent=mood.mood;
  $('heroSpeech').textContent=mood.speech; $('heroImage').src=`/media/beagle-${mood.image}.png`; $('heroImage').alt=mood.alt;
  $('petLabel').textContent=mood.label; $('sectionKicker').textContent=mood.kicker;
}
function setView(view) {
  state.view = view; state.category = '全部技能';
  document.querySelector('main').classList.toggle('task-mode',view==='tasks');
  document.querySelectorAll('[data-view]').forEach(node => node.classList.toggle('selected', node.dataset.view === view));
  const discover = view === 'discover';
  $('breadcrumb').textContent = view==='tasks'?'任务进度':discover ? '发现新技能' : view === 'favorites' ? '我的收藏' : '我的技能';
  paintHero(view);
  $('searchButton').textContent = discover ? '联网查找 →' : '匹配技能 →';
  $('query').placeholder = discover ? '想找什么外援？例如：React 性能排查 / PDF 表格提取' : '把活儿说清楚：论文汇报 / 画图 / 多 Agent 分工';
  $('teamBanner').hidden = discover || view==='tasks'; $('networkNote').hidden = !discover; $('popularLabel').hidden = !discover;
  $('categories').hidden = discover || view==='tasks'; document.querySelector('.category-caption').hidden = discover || view==='tasks';
  $('taskPanel').hidden=view!=='tasks'; $('grid').hidden=view==='tasks'; $('catalogHeading').hidden=view==='tasks'; document.querySelector('.search-area').hidden=view==='tasks';
  if(view==='tasks') { $('heroTitle').replaceChildren(document.createTextNode('活已派出，'),el('strong','','盯进度就行。'));$('heroDescription').textContent='任务、进度、确认和成果，都在比格这儿。'; }
  $('notice').hidden = true; render();
  if(view==='tasks' && typeof TaskUI!=='undefined')TaskUI.refresh();
}
function score(skill, term) {
  if (!term) return 1;
  const lower = term.toLocaleLowerCase();
  const text = `${skill.name} ${skill.title} ${skill.summary} ${skill.description} ${skill.category}`.toLocaleLowerCase();
  let value = text.includes(lower) ? 30 : 0;
  const pieces = new Set(lower.match(/[a-z0-9._-]+/g) || []);
  hints.forEach(group => { if (group.some(word => lower.includes(word))) group.forEach(word => pieces.add(word)); });
  pieces.forEach(piece => { if (text.includes(piece)) value += 2; if (skill.name.includes(piece)) value += 3; if (skill.title.includes(piece)) value += 3; });
  return value;
}
function renderCategories() {
  $('categories').replaceChildren();
  state.categories.forEach(category => {
    const items = state.skills.filter(s => category === '全部技能' || s.category === category);
    if (!items.length) return;
    const node = button('', `category-item${state.category === category ? ' selected' : ''}`, () => { state.category = category; if (state.view === 'discover') setView('local'); render(); });
    node.append(el('span', '', icons[category] || '·'), document.createTextNode(category), el('b', '', String(items.length))); $('categories').append(node);
  });
}
function empty(icon, title, description, actionText, action) {
  const loading=title.includes('正在') || title.includes('摇人');
  const box=el('div',`empty${loading?' loading':''}`);
  const pet=el('img','empty-pet'); pet.src=`/media/beagle-${loading?'work':icon==='🌱'?'service':'please'}.png`; pet.alt=loading?'比格正在键盘前找技能':'比格表情贴纸';
  box.append(pet,el('strong','',title),el('p','',description)); if(action)box.append(button(actionText,'',action));return box;
}
function localCard(skill) {
  const card = el('article','skill-card');
  const top = el('div','card-top');
  const favorite = state.favorites.has(skill.id);
  const star = button(favorite ? '♥' : '♡','star', () => { if (state.favorites.has(skill.id)) state.favorites.delete(skill.id); else state.favorites.add(skill.id); try { localStorage.setItem('skill-station-favorites',JSON.stringify([...state.favorites])); } catch (_) { notify('浏览器无法保存收藏'); } render(); });
  star.setAttribute('aria-label',`${favorite ? '取消收藏' : '收藏'}${skill.title}`); star.setAttribute('aria-pressed',String(favorite));
  top.append(el('span','card-icon',skill.icon),star);
  card.append(top,el('h3','card-title',skill.title),el('code','skill-name',skill.name),el('p','card-summary',skill.summary));
  const stamps={'agent-team':'别单扛，组队！','skill-hub':'选择困难看这。','find-skills':'缺谁，去摇。','supervisor':'糊弄？不行。','nature-polishing':'字给我，我来改。','nature-paper2ppt':'论文，端上来。'};
  if(stamps[skill.name])card.append(el('span','card-stamp',stamps[skill.name]));
  const bottom = el('div','card-bottom'); const badge = el('span',`badge${skill.connection ? ' connection' : ''}`, !skill.enabled ? '已停用' : skill.connection ? '插件 · 需确认连接' : skill.origin); badge.title = skill.origin;
  bottom.append(badge,button('查看与调用 ↗','card-action',()=>openDetail(skill))); card.append(bottom); return card;
}
function onlineCard(skill) {
  const card = el('article','skill-card online-card'); const top = el('div','card-top'); top.append(el('span','card-icon','🌱'),el('span','badge','社区候选'));
  card.append(top,el('h3','card-title',skill.name),el('p','source',skill.source));
  const meta = el('div','online-meta'); meta.append(el('span','badge',`${new Intl.NumberFormat('zh-CN',{notation:'compact'}).format(skill.installs)} 次安装`));
  if (skill.known_publisher) meta.append(el('span','badge','已知发布方'));
  meta.append(el('span','badge connection','待核验适用性')); card.append(meta,el('p','card-summary',`匹配检索词：${skill.matched.join('、')}`));
  const bottom = el('div','card-bottom'); const link = el('a','','查看来源 ↗'); link.href = skill.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
  const prompt = `使用 $skill-hub 和可用的 find-skills，评估这个候选技能是否适合我的需求。\n需求：${state.onlineQuery}\n候选：${skill.source}@${skill.slug}\n来源：${skill.url}\n请读取真实 SKILL.md，核查来源仓库、维护状态、安装量、所需工具与权限，给出适用性和替代选项。先评估，不安装。`;
  bottom.append(link,button('复制评估指令 ↗','card-action',()=>copy(prompt)));card.append(bottom);return card;
}
function render() {
  $('navCount').textContent = String(state.skills.length); $('favCount').textContent = String(state.skills.filter(s=>state.favorites.has(s.id)).length); renderCategories(); $('grid').replaceChildren();
  if (state.view === 'discover') {
    const rows = state.online.filter(s=>!$('popular').checked || s.installs >= 1000);
    $('sectionTitle').replaceChildren(document.createTextNode('社区候选 '),el('span','',String(rows.length)));
    $('sectionSubtitle').textContent = state.searched ? `“${state.onlineQuery}”的社区候选。看好来源，复制指令继续评估。` : '写下需求，点击“联网查找”。比格去找外援。';
    if (state.loading) { $('grid').append(empty('🔎','比格出门摇人了……','正在检索社区技能，通常需要几秒钟。')); return; }
    if (!state.searched) { $('grid').append(empty('🌱','本店缺人？去社区摇一个。','试试“前端设计”“React 性能排查”或“PDF”。')); return; }
    if (!rows.length) { $('grid').append(empty('🔎','翻遍口袋，暂时没有。','换几个关键词，或者让 Codex 继续查找与评估。','复制查找指令',()=>copy(`使用 $skill-hub，帮我寻找并评估适合这个需求的新技能：${state.onlineQuery}。先检查本地能力，再检索候选，核查来源与实际适用性。先评估，不安装。`))); return; }
    rows.forEach(s=>$('grid').append(onlineCard(s))); return;
  }
  let rows = state.skills.filter(s => (state.category === '全部技能' || s.category === state.category) && (state.view !== 'favorites' || state.favorites.has(s.id)));
  rows = rows.map(skill=>({skill,score:score(skill,query())})).filter(item=>item.score>0).sort((a,b)=>b.score-a.score).map(item=>item.skill);
  const title = state.view === 'favorites' ? '我的收藏' : state.category === '全部技能' ? query() ? '匹配到的技能' : '我的技能' : state.category;
  $('sectionTitle').replaceChildren(document.createTextNode(title+' '),el('span','',String(rows.length)));
  $('sectionSubtitle').textContent = query() ? '比格先按关键词翻了一遍。复杂任务可以让 Codex 再帮你挑。' : state.view==='favorites' ? '好用就留下。下次开工，直接来这里。' : '本机库存已点清。新增技能后，刷新就能看见。';
  if (!rows.length) { $('grid').append(empty(state.view === 'favorites' ? '♡' : '🌿', state.view === 'favorites' ? '给好用的留个位置？' : '口袋翻完了，没找到这个。',state.view === 'favorites' ? '点技能卡片右上角的小爱心，比格替你收好。' : '换个关键词，或者去社区摇个新外援。', '去发现新技能',()=>setView('discover')));return; }
  rows.forEach(s=>$('grid').append(localCard(s)));
}
async function openDetail(skill) {
  state.detail = skill; $('detailIcon').textContent = skill.icon; $('detailTitle').textContent = skill.title; $('detailSummary').textContent = skill.summary; $('detailName').textContent = '$'+skill.invocation;
  $('detailMeta').replaceChildren(el('span','badge',skill.category),el('span','badge',skill.origin));
  $('task').value = query(); $('detailContent').textContent = '正在读取…'; $('detailPath').textContent = skill.path; $('detailCopy').disabled = !skill.enabled || !skill.invocable; $('detailCopy').textContent = !skill.enabled ? '此技能当前已停用' : !skill.invocable ? '此技能声明禁止模型调用' : '复制完整调用指令';
  $('detail').showModal();
  $('detailRun').disabled = !skill.enabled || !skill.invocable;
  try { const response = await fetch('/api/skill?id='+encodeURIComponent(skill.id)); const data = await response.json(); if (state.detail?.id === skill.id) $('detailContent').textContent = data.content || data.error; } catch (_) { $('detailContent').textContent = '读取失败，请刷新后再试。'; }
}
async function load() {
  $('refresh').disabled = true;
  try { const response = await fetch('/api/skills'); if (!response.ok) throw Error(); const data = await response.json(); state.skills = data.skills; state.categories = data.categories; $('notice').hidden = true; render(); }
  catch (_) { $('notice').textContent = '本地服务暂时无法读取。请重新点击桌面图标打开。'; $('notice').hidden = false; }
  finally { $('refresh').disabled = false; }
}
async function search(event) {
  event?.preventDefault();
  if (state.view !== 'discover') { render(); return; }
  if (!query()) { $('query').focus(); notify('先写下你想完成的事'); return; }
  const epoch = ++state.searchEpoch; const term = query(); state.onlineQuery = term; state.loading = true; state.searched = true; $('notice').hidden = true; $('searchButton').disabled = true; render();
  try { const response = await fetch('/api/search?q='+encodeURIComponent(term)); const data = await response.json(); if (epoch !== state.searchEpoch) return; state.online = data.skills || []; if (data.error || data.partial) { $('notice').textContent = data.error || '部分关键词连接失败，下面展示已取得的候选。'; $('notice').hidden = state.view !== 'discover'; } else if (data.terms?.length) { $('notice').textContent = '本次检索词：'+data.terms.join(' · '); $('notice').hidden = state.view !== 'discover'; } }
  catch (_) { if (epoch === state.searchEpoch) { state.online = []; $('notice').textContent = '查找暂时未完成，请稍后再试；本地技能仍可使用。'; $('notice').hidden = state.view !== 'discover'; } }
  finally { if (epoch === state.searchEpoch) { state.loading = false; $('searchButton').disabled = false; render(); } }
}
document.querySelectorAll('[data-view]').forEach(n=>n.addEventListener('click',()=>setView(n.dataset.view)));
document.querySelectorAll('[data-query]').forEach(n=>n.addEventListener('click',()=>{ $('query').value=n.dataset.query; if(state.view==='discover')search(); else render(); }));
$('searchForm').addEventListener('submit',search); $('query').addEventListener('input',()=>{if(state.view!=='discover')render();}); $('popular').addEventListener('change',render); $('refresh').addEventListener('click',load);
$('hubPrompt').addEventListener('click',()=>copy(hubPrompt()));
$('teamPrompt').addEventListener('click',()=>copy(`使用 $agent-team，由你担任主 agent，组织 3 个子 agent，按调查与方案、实施与产出、独立验收分工完成任务。请说明各自的具体范围，协调依赖，检查并整合真实成果。\n任务：${query() || '请在这里填写目标，并提供必要文件。'}`));
$('detailCopy').addEventListener('click',()=>{const task=$('task').value.trim();copy(task ? `使用 $${state.detail.invocation}，${task}` : state.detail.prompt);});
$('petBanter').addEventListener('click',()=>{const jokes=['别催，先把需求写清。','我不困，我在省电。','干活可以，加班再议。','戳我没用，戳技能卡。'];state.banter=(state.banter||0)+1;$('heroSpeech').textContent=jokes[(state.banter-1)%jokes.length];});
$('closeDialog').addEventListener('click',()=>$('detail').close()); $('help').addEventListener('click',()=>$('helpDialog').showModal()); $('closeHelp').addEventListener('click',()=>$('helpDialog').close());
[$('detail'),$('helpDialog')].forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
load();
