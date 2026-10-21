"""Display-independent behavior for the desktop pet and its hover menu."""
from __future__ import annotations

import re


def popup_position(pet, workarea, size, gap=12):
    x, y, width, height = pet
    left, top, screen_width, screen_height = workarea
    popup_width, popup_height = size
    right = x + width + gap
    candidate = right if right + popup_width <= left + screen_width else x - popup_width - gap
    return (max(left, min(candidate, left + screen_width - popup_width)),
            max(top, min(y + height - popup_height, top + screen_height - popup_height)))


def clamp_position(x, y, workarea, size):
    left, top, width, height = workarea
    return (max(left, min(int(x), left + width - size[0])),
            max(top, min(int(y), top + height - size[1])))


def rank_skills(skills, query):
    query = query.strip().casefold()
    terms = set(re.findall(r'[a-z0-9._-]+', query))
    groups = [('论文','文献','学术','nature','research'), ('汇报','ppt','幻灯','paper2ppt','presentation'),
              ('绘图','图表','画图','figure'), ('润色','翻译','polishing'), ('协作','分工','agent','team'),
              ('表格','excel','csv','spreadsheet'), ('网站','网页','前端','sites','web'),
              ('图片','插画','imagegen'), ('文档','word','docx','documents'), ('引用','citation')]
    for group in groups:
        if any(word in query for word in group):
            terms.update(group)
    priority = {'agent-team':0, 'skill-hub':1, 'find-skills':2}
    def score(skill):
        content = ' '.join(str(skill.get(k,'')) for k in ('name','title','summary','description')).casefold()
        value = 30 if query and query in content else 0
        for term in terms:
            if term in content:
                value += 2
            if term in skill['name'].casefold() or term in skill['title'].casefold():
                value += 3
        return value
    rows = [s for s in skills if s.get('enabled',True) and s.get('invocable',True)]
    if query:
        rows = [s for s in rows if score(s)>0]
        return sorted(rows,key=lambda s:(-score(s),priority.get(s['name'],9),s['name']))
    return sorted(rows,key=lambda s:(priority.get(s['name'],9),s.get('connection',False),s['name']))


def invocation_prompt(skill, task=''):
    name = skill.get('invocation',skill['name'])
    return f'使用 ${name}，{task.strip()}' if task.strip() else skill.get('prompt',f'使用 ${name}，帮我完成以下任务：')


def evaluation_prompt(skill, task):
    return (f'使用 $skill-hub 和可用的 find-skills，评估候选技能是否适合我的需求。\n'
            f'需求：{task}\n候选：{skill["source"]}@{skill["slug"]}\n来源：{skill["url"]}\n'
            '请读取真实 SKILL.md，核查来源、维护状态、所需工具与权限，给出适用性和替代选项。先评估，不安装。')


class HoverController:
    def __init__(self, schedule, cancel, show, hide):
        self.schedule, self.cancel = schedule,cancel
        self.show,self.hide = show,hide
        self.inside = set()
        self.interactions = set()
        self.visible = False
        self.pinned = False
        self.pending_show = self.pending_hide = None

    def _cancel(self,name):
        timer=getattr(self,name)
        if timer is not None:
            self.cancel(timer)
            setattr(self,name,None)

    def enter(self,surface):
        self.inside.add(surface)
        self._cancel('pending_hide')
        if not self.visible and self.pending_show is None:
            self.pending_show=self.schedule(180,self._show)

    def leave(self,surface):
        self.inside.discard(surface)
        self._cancel('pending_show')
        self._cancel('pending_hide')
        if self.visible and not self.inside and not self.pinned and not self.interactions:
            self.pending_hide=self.schedule(650,self._hide)

    def _show(self):
        self.pending_show=None
        self.visible=True
        self.show()
        return False

    def _hide(self):
        self.pending_hide=None
        if not self.inside and not self.pinned and not self.interactions:
            self.visible=False
            self.hide()
        return False

    def show_now(self):
        self._cancel('pending_show')
        self._cancel('pending_hide')
        self._show()

    def set_pinned(self,value):
        self.pinned=value
        if value:
            self._cancel('pending_hide')
        elif not self.inside and self.visible and not self.interactions:
            self.pending_hide=self.schedule(650,self._hide)

    def hold_open(self,reason):
        self.interactions.add(reason)
        self._cancel('pending_hide')

    def release_open(self,reason):
        self.interactions.discard(reason)
        self._cancel('pending_hide')
        if self.visible and not self.inside and not self.pinned and not self.interactions:
            self.pending_hide=self.schedule(650,self._hide)

    def dismiss(self):
        self._cancel('pending_show')
        self._cancel('pending_hide')
        self.visible=False
        self.inside.discard('popup')
        self.interactions.clear()
        self.hide()
