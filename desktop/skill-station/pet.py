#!/usr/bin/env python3
"""A transparent, draggable beagle with a native hover skill pocket."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import threading
import time
from pathlib import Path

import cairo
import gi
_cairo_bridge=Path(__file__).resolve().parent/'vendor/usr/lib/python3/dist-packages/gi'
if _cairo_bridge.is_dir():
    gi.__path__.append(str(_cairo_bridge))
gi.require_foreign('cairo')
gi.require_version('Gtk','3.0')
gi.require_version('Gdk','3.0')
gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gdk,GdkPixbuf,Gio,GLib,Gtk,Pango

from app import BASE,CATEGORIES,catalog,search_online
from pet_support import HoverController,clamp_position,evaluation_prompt,invocation_prompt,popup_position,rank_skills

ASSET=BASE/'assets/beagle.png'
CSS=b'''
window { background-color: transparent; font-family: "Noto Sans CJK SC", sans-serif; font-size: 12px; color: #281e19; }
.pocket { background: #fff9ee; border: 2px solid #281e19; border-radius: 18px 13px 20px 12px; padding: 16px; margin: 3px 7px 7px 3px; box-shadow: 4px 4px 0 #281e19; }
.title { font-weight: 900; font-size: 17px; color: #281e19; }
.muted { color: #927958; font-size: 10px; }
.row-title { font-weight: 700; font-size: 12px; color: #281e19; }
.row-subtitle { color: #8e765b; font-size: 10px; }
button { background: #fffef8; background-image: none; border: 1px solid transparent; border-radius: 7px 10px 6px 9px; box-shadow: none; text-shadow: none; padding: 6px 9px; color: #715331; }
button:hover { background: #ffedbb; color: #281e19; }
button:checked { background: #ffe789; color: #281e19; border-color: #281e19; }
button:focus { outline: 2px dashed #a56a25; outline-offset: -4px; }
button:disabled { color: #ac967d; }
button.primary { background: #d9a568; color: #281e19; font-weight: 800; border: 2px solid #281e19; box-shadow: 2px 2px 0 #281e19; margin-right: 3px; margin-bottom: 3px; }
button.primary:hover { background: #ffe789; }
button.primary:active { box-shadow: none; }
.mini-button { border: 1px solid #b99465; padding: 3px 7px; font-size: 10px; }
.close-button { font-size: 20px; padding: 0 5px; }
.mood-ribbon { background: #ffe789; border: 1px solid #281e19; border-radius: 4px 8px 5px 7px; padding: 6px 9px; box-shadow: 2px 2px 0 #c49b65; margin: 0 3px 2px 0; }
.mood-ribbon label { color: #70502d; font-size: 10px; font-weight: 700; }
.mood-tag { background: #fffef8; border: 1px solid #281e19; border-radius: 4px; padding: 1px 5px; font-size: 9px; color: #281e19; }
.skill-row { background: #fffefb; border: 2px solid #281e19; border-radius: 8px 12px 9px 7px; margin: 0 4px 9px 0; padding: 8px; box-shadow: 2px 2px 0 #c5a377; }
.skill-row.cool-row { border-radius: 11px 7px 12px 9px; }
.skill-row:hover { background: #fff0c9; box-shadow: 3px 3px 0 #281e19; }
.row-icon { font-size: 21px; background: #ffe5a9; border: 1px solid #281e19; border-radius: 7px 9px 6px 8px; padding: 4px; min-width: 27px; min-height: 27px; }
.cool-row .row-icon { background: #d1eaf5; }
.row-arrow { color: #9a7445; font-size: 13px; }
entry { border: 2px solid #281e19; border-radius: 9px 7px 10px 8px; background: #fffefb; box-shadow: 2px 2px 0 #d6b895; padding: 7px; color: #281e19; margin-bottom: 3px; }
entry:focus { border-color: #a56a25; }
combobox button { border: 1px solid #281e19; background: #f2d4ad; padding: 5px 8px; box-shadow: 2px 2px 0 #c5a377; margin: 0 3px 3px 0; }
combobox button:hover { background: #ffe789; }
combobox arrow { color: #281e19; }
combobox:disabled button { background: #f5ead7; border-color: #c9b08d; }
.status { color: #92734f; font-size: 10px; }
.tabs { background: #f2d4ad; border: 1px solid #281e19; border-radius: 9px 12px 8px 10px; padding: 3px; }
.tabs button { background: transparent; font-weight: 700; }
.tabs button:checked { background: #fff9df; border: 1px solid #281e19; box-shadow: 2px 2px 0 #281e19; }
.footer { padding-top: 9px; border-top: 1px dashed #bea078; }
.footer button { background: #ffe789; border: 1px solid #281e19; padding: 6px 8px; font-size: 10px; font-weight: 700; box-shadow: 2px 2px 0 #281e19; margin: 0 3px 3px 0; }
.footer button.team-button { background: #d1eaf5; }
.footer button:hover { background: #ffdfa4; }
scrollbar { background: transparent; }
scrollbar slider { background: #c8ac85; border: 1px solid #fff9ee; border-radius: 8px; min-width: 5px; min-height: 28px; }
menu { background: #fff9ee; border: 2px solid #281e19; border-radius: 8px; padding: 5px; box-shadow: 3px 3px 0 #281e19; }
menuitem { color: #281e19; padding: 7px; }
menuitem:hover { background: #ffe789; border-radius: 5px; }
menuitem:checked { background: #f2d4ad; }
.task-window { background: #fff9ee; }
.task-input, .task-output { font-size: 12px; padding: 9px; }
.task-input text, .task-output text { background: #fffefb; color: #281e19; }
progressbar trough { background: #efdfbf; border: 1px solid #281e19; border-radius: 5px; min-height: 7px; }
progressbar progress { background: #d9a568; border-radius: 5px; }
'''


def style(widget,name):
    widget.get_style_context().add_class(name)
    return widget


def text(value,cls=None,xalign=0):
    label=Gtk.Label(label=value,xalign=xalign)
    if cls:
        style(label,cls)
    return label


def clear_background(_widget,cr):
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0,0,0,0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    return False


def transparent_window(window):
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_skip_taskbar_hint(True)
    window.set_skip_pager_hint(True)
    window.set_keep_above(True)
    window.set_app_paintable(True)
    visual=window.get_screen().get_rgba_visual()
    if visual:
        window.set_visual(visual)
    window.connect('draw',clear_background)
    window.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)


class SkillPocket(Gtk.Window):
    def __init__(self,owner):
        super().__init__(title='比格 · 技能口袋')
        self.owner=owner
        self.mode='local'
        self._switching_mode=False
        self.header_images={}
        self.results=[]
        self.result_query=''
        self.searching=False
        self.search_generation=0
        self.skills=[]
        self.jobs=[]
        self.jobs_loading=False
        transparent_window(self)
        self.set_application(owner)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_focus_on_map(False)
        self.connect('delete-event',lambda *_:self.hide() or True)
        self.connect('key-press-event',self.on_key)
        self.connect('enter-notify-event',lambda _w,e:self.crossing(e,True))
        self.connect('leave-notify-event',lambda _w,e:self.crossing(e,False))
        self.connect('size-allocate',self.update_round_shape)
        root=style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=11),'pocket')
        self.add(root)
        header=Gtk.Box(spacing=9)
        self.header_image=Gtk.Image.new_from_pixbuf(owner.original.scale_simple(45,45,GdkPixbuf.InterpType.BILINEAR))
        header.pack_start(self.header_image,False,False,0)
        titles=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=2)
        titles.pack_start(text('比格的技能口袋','title'),False,False,0)
        self.subtitle=text('这活，先让技能上。','muted')
        titles.pack_start(self.subtitle,False,False,0)
        header.pack_start(titles,True,True,0)
        pin=style(Gtk.ToggleButton(label='固定'),'mini-button')
        pin.set_tooltip_text('固定弹窗，鼠标移开也不收起')
        pin.connect('toggled',lambda b:owner.hover.set_pinned(b.get_active()))
        header.pack_start(pin,False,False,0)
        close=style(Gtk.Button(label='×'),'close-button')
        close.set_tooltip_text('收起技能口袋')
        close.connect('clicked',lambda _b:owner.hover.dismiss())
        header.pack_start(close,False,False,0)
        root.pack_start(header,False,False,0)
        ribbon=style(Gtk.Box(spacing=6),'mood-ribbon')
        self.mood=text('人没醒，技能已就位。')
        ribbon.pack_start(self.mood,True,True,0)
        self.mood_tag=style(text('勉强营业'),'mood-tag')
        ribbon.pack_start(self.mood_tag,False,False,0)
        root.pack_start(ribbon,False,False,0)
        tabs=style(Gtk.Box(spacing=4),'tabs')
        self.local_button=Gtk.ToggleButton(label='我的技能')
        self.find_button=Gtk.ToggleButton(label='发现新技能 ✧')
        self.tasks_button=Gtk.ToggleButton(label='任务进度')
        self.local_button.connect('toggled',self.mode_toggled,'local')
        self.find_button.connect('toggled',self.mode_toggled,'find')
        self.tasks_button.connect('toggled',self.mode_toggled,'tasks')
        tabs.pack_start(self.local_button,True,True,0)
        tabs.pack_start(self.find_button,True,True,0)
        tabs.pack_start(self.tasks_button,True,True,0)
        root.pack_start(tabs,False,False,0)
        searchbox=Gtk.Box(spacing=7)
        self.entry=Gtk.SearchEntry()
        self.entry.set_placeholder_text('把活说清楚：论文汇报 / 画图')
        self.entry.set_max_length(240)
        self.entry.connect('search-changed',lambda _e:self.render() if self.mode=='local' else None)
        self.entry.connect('activate',lambda _e:self.start_search() if self.mode=='find' else self.compose())
        searchbox.pack_start(self.entry,True,True,0)
        self.search_button=style(Gtk.Button(label='查找'),'primary')
        self.search_button.connect('clicked',lambda _b:self.start_search() if self.mode=='find' else self.compose())
        searchbox.pack_start(self.search_button,False,False,0)
        root.pack_start(searchbox,False,False,0)
        line=Gtk.Box(spacing=8)
        self.category=Gtk.ComboBoxText()
        for category in CATEGORIES:
            self.category.append_text(category)
        self.category.set_active(0)
        self.category.connect('changed',lambda _c:self.render())
        self.category.connect('notify::popup-shown',self.category_popup_changed)
        line.pack_start(self.category,False,False,0)
        self.count=text('','muted',1)
        line.pack_start(self.count,True,True,0)
        refresh=Gtk.Button(label='↻')
        refresh.set_tooltip_text('刷新本机技能')
        refresh.connect('clicked',lambda _b:self.refresh())
        line.pack_start(refresh,False,False,0)
        root.pack_start(line,False,False,0)
        scroller=Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroller.set_size_request(365,278)
        self.rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0)
        scroller.add(self.rows)
        root.pack_start(scroller,True,True,0)
        self.status=text('点技能填任务，比格直接开工，进度在这里看。','status')
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(48)
        root.pack_start(self.status,False,False,0)
        footer=style(Gtk.Box(spacing=7),'footer')
        full=Gtk.Button(label='打开完整技能小站 ↗')
        full.connect('clicked',lambda _b:owner.open_station())
        team=style(Gtk.Button(label='多 Agent 分工 🐾'),'team-button')
        team.connect('clicked',lambda _b:self.compose(next((s for s in self.skills if s['name']=='agent-team'),None)))
        footer.pack_start(full,True,True,0)
        footer.pack_start(team,False,False,0)
        root.pack_start(footer,False,False,0)
        self.refresh()
        self.set_mode('local')
        GLib.timeout_add(2500,self.refresh_jobs_if_visible)

    def update_round_shape(self,_widget,allocation):
        if not self.get_realized():
            return
        width,height=allocation.width,allocation.height
        if width<40 or height<40:
            return
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height)
        cr=cairo.Context(surface)
        radius=20
        for x,y,start in [(width-radius,radius,-math.pi/2),(width-radius,height-radius,0),
                           (radius,height-radius,math.pi/2),(radius,radius,math.pi)]:
            cr.arc(x,y,radius,start,start+math.pi/2)
        cr.close_path()
        cr.set_source_rgba(1,1,1,1)
        cr.fill()
        region=Gdk.cairo_region_create_from_surface(surface)
        self.input_shape_combine_region(region)
        if not self.get_screen().is_composited():
            self.shape_combine_region(region)

    def crossing(self,event,enter):
        if event.detail==Gdk.NotifyType.INFERIOR or event.mode!=Gdk.CrossingMode.NORMAL:
            return False
        (self.owner.hover.enter if enter else self.owner.hover.leave)('popup')
        return False

    def category_popup_changed(self,combo,_property):
        if combo.get_property('popup-shown'):
            self.owner.hover.hold_open('category-menu')
        else:
            # Wait for the menu's pointer grab to end before reconciling hover.
            GLib.idle_add(self.finish_category_interaction)

    def finish_category_interaction(self):
        if self.category.get_property('popup-shown'):
            return False
        pointer=self.get_display().get_default_seat().get_pointer()
        _screen,x,y=pointer.get_position()
        for surface,window in [('pet',self.owner.pet),('popup',self)]:
            left,top=window.get_position()
            width,height=window.get_size()
            inside=window.get_visible() and left<=x<left+width and top<=y<top+height
            (self.owner.hover.enter if inside else self.owner.hover.leave)(surface)
        self.owner.hover.release_open('category-menu')
        return False

    def on_key(self,_widget,event):
        if event.keyval==Gdk.KEY_Escape:
            if self.category.get_property('popup-shown'):
                self.category.popdown()
            else:
                self.owner.hover.dismiss()
            return True
        return False

    def refresh(self):
        try:
            settings=json.loads((BASE/'settings.json').read_text())
        except (OSError,ValueError):
            settings={}
        self.skills=catalog(workspaces=[Path(p) for p in settings.get('workspaces',[])])
        self.render()

    def mode_toggled(self,button,mode):
        if self._switching_mode:
            return
        if button.get_active() or self.mode==mode:
            self.set_mode(mode)

    def set_mode(self,mode):
        if self._switching_mode:
            return
        if mode not in ('local','find','tasks'):
            raise ValueError('Unknown pocket mode: '+str(mode))
        # GTK emits button signals from set_active too. Synchronizing tabs must
        # never re-enter the page switch through those programmatic signals.
        self._switching_mode=True
        try:
            self.mode=mode
            self.local_button.set_active(mode=='local')
            self.find_button.set_active(mode=='find')
            self.tasks_button.set_active(mode=='tasks')
        finally:
            self._switching_mode=False
        self.entry.set_placeholder_text('找什么外援？例如：React 性能排查' if mode=='find' else '把活说清楚：论文汇报 / 画图')
        self.search_button.set_label('联网查找' if mode=='find' else '开工 ⚡')
        self.mood.set_text('这活不会？去摇个外援。' if mode=='find' else '人没醒，技能已就位。')
        self.mood_tag.set_text('接待外援' if mode=='find' else '勉强营业')
        self.subtitle.set_text('技能已上桌，您慢用。' if mode=='find' else '这活，先让技能上。')
        image=BASE/'assets/beagle-service.png' if mode=='find' else ASSET
        if image not in self.header_images:
            self.header_images[image]=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(image),45,45,True)
        self.header_image.set_from_pixbuf(self.header_images[image])
        if mode=='tasks':
            self.mood.set_text('活已派出，盯进度就行。')
            self.mood_tag.set_text('任务看板')
            self.load_jobs()
        self.render()

    def compose(self,skill=None,job_id=None,task=None):
        from pet_tasks import TaskWindow
        previous=getattr(self.owner,'task_window',None)
        if previous:
            previous.destroy()
        self.owner.task_window=TaskWindow(self.owner,skill,self.entry.get_text() if task is None else task,job_id)

    def refresh_jobs_if_visible(self):
        if self.get_visible() and self.mode=='tasks':
            self.load_jobs()
        return True

    def load_jobs(self):
        if self.jobs_loading:
            return
        self.jobs_loading=True
        def work():
            from task_client import TaskClient
            try:
                jobs=TaskClient().request('GET','/api/jobs')['jobs']
                error=None
            except Exception as exc:
                jobs=[]
                error=str(exc)
            GLib.idle_add(self.loaded_jobs,jobs,error)
        threading.Thread(target=work,daemon=True).start()

    def loaded_jobs(self,jobs,error):
        self.jobs_loading=False
        self.jobs=jobs
        if self.mode=='tasks':
            if error:
                self.status.set_text(error)
            self.render()
        return False

    def row_button(self,icon,title,subtitle,action,hint='填写任务并直接开工 ↗'):
        button=style(Gtk.Button(),'skill-row')
        if len(self.rows.get_children())%2:
            style(button,'cool-row')
        box=Gtk.Box(spacing=8)
        box.pack_start(text(icon,'row-icon'),False,False,0)
        labels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
        for value,cls in ((title,'row-title'),(subtitle,'row-subtitle')):
            label=text(value,cls)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(30)
            label.set_width_chars(23)
            labels.pack_start(label,False,False,0)
        box.pack_start(labels,True,True,0)
        box.pack_end(text('↗','row-arrow'),False,False,0)
        button.add(box)
        button.set_tooltip_text(title+'\n'+subtitle+'\n'+hint)
        button.connect('clicked',lambda _b:action())
        self.rows.pack_start(button,False,False,0)

    def message(self,title,detail,image='please'):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
        box.set_border_width(16)
        asset=ASSET if image=='work' else BASE/f'assets/beagle-{image}.png'
        sticker=Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(asset),86,86,True))
        box.pack_start(sticker,False,False,0)
        label=text(title,'row-title',0.5)
        box.pack_start(label,False,False,0)
        label=text(detail,'muted',0.5)
        label.set_line_wrap(True)
        label.set_max_width_chars(33)
        box.pack_start(label,False,False,0)
        self.rows.pack_start(box,True,True,0)

    def render(self):
        if not hasattr(self,'rows'):
            return
        for row in self.rows.get_children():
            self.rows.remove(row)
            row.destroy()
        self.category.set_sensitive(self.mode=='local')
        self.search_button.set_sensitive(not self.searching)
        if self.mode=='local':
            selected=self.category.get_active_text()
            rows=rank_skills(self.skills,self.entry.get_text())
            if selected and selected!='全部技能':
                rows=[s for s in rows if s['category']==selected]
            self.count.set_text(f'{len(rows)} 个技能')
            for skill in rows:
                subtitle=skill['summary']
                if skill.get('connection'):
                    subtitle='插件 · 需确认连接｜'+subtitle
                self.row_button(skill['icon'],skill['title'],subtitle,
                    lambda s=skill:self.compose(s))
            if not rows:
                self.message('口袋翻完了，没找到这个。','换个关键词，或去“发现新技能”摇个外援。')
        elif self.mode=='tasks':
            self.count.set_text(f'{len(self.jobs)} 项任务')
            for job in self.jobs:
                icon='✓' if job['status']=='completed' else '!' if job['status']=='waiting' else '🐾'
                self.row_button(icon,job['task'],job['status_label']+' · '+job['skill_title'],
                    lambda j=job:self.compose(job_id=j['id']),'查看真实进度与结果 ↗')
            if not self.jobs:
                self.message('比格还没接到活。','写下任务，点“开工”。完成后可以在这里找结果。','work')
        else:
            self.count.set_text(f'{len(self.results)} 个社区候选')
            if self.searching:
                self.message('比格出门摇人了……','正在查找社区技能，通常需要几秒钟。','work')
            elif not self.results:
                self.message('本店缺人？去摇个外援。','写下需求，点“联网查找”。先看来源，再交给 Codex 评估。','service')
            else:
                for candidate in self.results:
                    detail=f'{candidate["source"]} · {candidate["installs"]:,} 次安装'
                    self.row_button('🌱',candidate['name'],detail,
                        lambda s=candidate:self.owner.open_station(source=s['source'],slug=s['slug']),
                        '自动打开中文说明，查看原文后再决定是否交给 Codex 评估。')
        self.rows.show_all()

    def copy(self,prompt):
        clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(prompt,-1)
        clipboard.store()
        self.status.set_text('✓ 指令打包好了，去 Codex 开工。')

    def copy_team(self):
        task=self.entry.get_text().strip() or '请填写目标，并提供必要资料。'
        self.copy('使用 $agent-team，由你担任主 agent，组织 3 个子 agent，按调查与方案、实施与产出、独立验收分工。明确范围和依赖，检查并整合真实成果。\n任务：'+task)

    def start_search(self):
        query=self.entry.get_text().strip()
        if not query:
            self.entry.grab_focus()
            self.status.set_text('先写下想完成的事情，再开始查找。')
            return
        if self.searching:
            return
        self.search_generation+=1
        generation=self.search_generation
        self.searching=True
        self.result_query=query
        self.status.set_text('正在查找 skills.sh 社区候选…')
        self.render()
        def work():
            try:
                result=search_online(query)
            except Exception:
                result={'skills':[],'error':'本次连接未完成，可以稍后重试。'}
            GLib.idle_add(self.finish_search,generation,result)
        threading.Thread(target=work,daemon=True).start()

    def finish_search(self,generation,result):
        if generation!=self.search_generation:
            return False
        self.searching=False
        self.results=result.get('skills',[])[:15]
        self.status.set_text(result.get('error') or '点击候选复制评估指令；安装量不代表已核验。')
        self.render()
        return False


class BeagleWindow(Gtk.Window):
    def __init__(self,owner):
        super().__init__(title='比格技能宠物')
        self.owner=owner
        self.pet_size=144
        self.start=time.monotonic()
        self.save_timer=None
        self.dragged=False
        self.set_application(owner)
        transparent_window(self)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.stick()
        self.area=Gtk.DrawingArea()
        self.area.set_size_request(self.pet_size,self.pet_size)
        self.add(self.area)
        self.area.connect('draw',self.draw_pet)
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|
                             Gdk.EventMask.ENTER_NOTIFY_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.area.connect('enter-notify-event',lambda _w,e:self.crossing(e,True))
        self.area.connect('leave-notify-event',lambda _w,e:self.crossing(e,False))
        self.area.connect('button-press-event',self.press)
        self.area.connect('button-release-event',self.release)
        self.connect('realize',self.update_shape)
        self.connect('configure-event',self.configured)
        self.connect('delete-event',lambda *_:owner.quit() or False)
        self.reload_image()
        self.restore_position()
        self.animation=GLib.timeout_add(80,lambda:self.area.queue_draw() or True)

    def reload_image(self):
        self.pixbuf=self.owner.original.scale_simple(self.pet_size-8,self.pet_size-8,GdkPixbuf.InterpType.BILINEAR)
        if self.get_realized():
            self.update_shape()

    def update_shape(self,*_):
        surface=Gdk.cairo_surface_create_from_pixbuf(self.pixbuf,1,self.get_window())
        region=Gdk.cairo_region_create_from_surface(surface)
        self.input_shape_combine_region(region)
        if not self.get_screen().is_composited():
            self.shape_combine_region(region)

    def draw_pet(self,_area,cr):
        offset=3+math.sin((time.monotonic()-self.start)*2.2)*1.2
        Gdk.cairo_set_source_pixbuf(cr,self.pixbuf,4,offset)
        cr.paint()
        return False

    def workarea(self):
        display=self.get_display()
        monitor=display.get_monitor_at_window(self.get_window()) if self.get_realized() else display.get_primary_monitor()
        monitor=monitor or display.get_monitor(0)
        rect=monitor.get_workarea()
        return rect.x,rect.y,rect.width,rect.height

    def restore_position(self):
        workarea=self.workarea()
        default=(workarea[0]+workarea[2]-self.pet_size-35,workarea[1]+workarea[3]-self.pet_size-24)
        try:
            data=json.loads(self.owner.state_file.read_text())
            desired=(data['x'],data['y'])
        except (OSError,ValueError,KeyError):
            desired=default
        self.move(*clamp_position(*desired,workarea,(self.pet_size,self.pet_size)))

    def configured(self,*_):
        if self.save_timer:
            GLib.source_remove(self.save_timer)
        self.save_timer=GLib.timeout_add(700,self.save_position)
        if getattr(self.owner,'hover',None) and self.owner.hover.visible:
            self.owner.place_pocket()
        return False

    def save_position(self):
        self.save_timer=None
        x,y=self.get_position()
        try:
            self.owner.state_file.write_text(json.dumps({'x':x,'y':y,'size':self.pet_size}))
        except OSError:
            pass
        return False

    def crossing(self,event,enter):
        if event.detail!=Gdk.NotifyType.INFERIOR and event.mode==Gdk.CrossingMode.NORMAL:
            (self.owner.hover.enter if enter else self.owner.hover.leave)('pet')
        return False

    def press(self,_widget,event):
        if event.button==3:
            self.context_menu(event)
            return True
        if event.button==1:
            self.owner.hover.dismiss()
            self.begin_move_drag(1,int(event.x_root),int(event.y_root),event.time)
            return True
        return False

    def release(self,_widget,event):
        if event.button==1:
            self.owner.hover.enter('pet')
        return False

    def context_menu(self,event):
        self.owner.hover.dismiss()
        menu=Gtk.Menu()
        for label,action in [('打开技能口袋',self.owner.hover.show_now),('打开完整技能小站',self.owner.open_station),('退出比格',self.owner.quit)]:
            item=Gtk.MenuItem(label=label)
            item.connect('activate',lambda _i,f=action:f())
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        self.menu=menu


class PetApplication(Gtk.Application):
    def __init__(self,args):
        flags=Gio.ApplicationFlags.NON_UNIQUE if args.smoke_test else Gio.ApplicationFlags.DEFAULT_FLAGS
        super().__init__(application_id='io.skillstation.DesktopPet',flags=flags)
        self.args=args
        self.state_file=args.state_file or BASE/'pet-state.json'
        self.pet=None
        self.errors=[]

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider=Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.original=GdkPixbuf.Pixbuf.new_from_file(str(ASSET))

    def do_activate(self):
        if self.pet:
            self.pet.show()
            self.pet.get_window().raise_()
            return
        self.pet=BeagleWindow(self)
        self.pocket=SkillPocket(self)
        self.hover=HoverController(GLib.timeout_add,GLib.source_remove,self.show_pocket,self.pocket.hide)
        self.pet.show_all()
        print(json.dumps({'pet_started':True,'pid':__import__('os').getpid(),'position':list(self.pet.get_position()),
                          'size':self.pet.pet_size,'composited':self.pet.get_screen().is_composited()},ensure_ascii=False),flush=True)
        if self.args.smoke_test:
            GLib.timeout_add(300,self.test_enter)
            GLib.timeout_add(12000,self.test_timeout)

    def place_pocket(self):
        x,y=self.pet.get_position()
        width,height=self.pocket.get_size()
        if width<100:
            width,height=415,560
        position=popup_position((x,y,self.pet.pet_size,self.pet.pet_size),self.pet.workarea(),(width,height))
        self.pocket.move(*position)

    def show_pocket(self):
        self.pocket.show_all()
        self.place_pocket()

    def open_station(self,job_id=None,skill_id=None,source=None,slug=None):
        command=[sys.executable,str(BASE/'launch.py')]
        if job_id:
            command.extend(['--task',job_id])
        if skill_id:
            command.extend(['--skill',skill_id])
        if source and slug:
            command.extend(['--source',source,'--slug',slug])
        subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

    def check(self,condition,message):
        if not condition:
            self.errors.append(message)

    def test_enter(self):
        self.check(not self.pet.get_decorated(),'pet has window decorations')
        self.check(self.pet.get_visual().get_depth()==32,'pet does not have an alpha visual')
        self.check(self.original.get_has_alpha(),'pet asset is not transparent')
        self.check(bool(self.pocket.skills),'skill list is empty')
        self.hover.enter('pet')
        GLib.timeout_add(280,self.test_transfer)
        return False

    def test_transfer(self):
        self.check(self.pocket.get_visible(),'hover did not show pocket')
        self.hover.leave('pet')
        self.hover.enter('popup')
        GLib.timeout_add(780,self.test_find_tab)
        return False

    def check_tab(self,mode,button):
        self.check(self.pocket.mode==mode,'tab click did not select '+mode)
        self.check(button.get_active(),'selected tab is not active: '+mode)
        self.check(sum(b.get_active() for b in (self.pocket.local_button,self.pocket.find_button,self.pocket.tasks_button))==1,
                   'tab selection is not exclusive')

    def test_find_tab(self):
        self.pocket.find_button.clicked()
        self.check_tab('find',self.pocket.find_button)
        self.check(self.pocket.search_button.get_label()=='联网查找','discovery view was not displayed')
        # A later main-loop callback must still run after a real button click.
        GLib.timeout_add(100,self.test_tasks_tab)
        return False

    def test_tasks_tab(self):
        # Only exercise navigation here; backend requests have separate tests.
        original=self.pocket.load_jobs
        self.pocket.load_jobs=lambda:None
        try:
            self.pocket.tasks_button.clicked()
            self.check_tab('tasks',self.pocket.tasks_button)
            self.check('项任务' in self.pocket.count.get_text(),'tasks view was not displayed')
        finally:
            self.pocket.load_jobs=original
        GLib.timeout_add(100,self.test_repeated_tab_switches)
        return False

    def test_repeated_tab_switches(self):
        original=self.pocket.load_jobs
        self.pocket.load_jobs=lambda:None
        self.tab_clicks=0
        try:
            for _ in range(8):
                for mode,button in [('local',self.pocket.local_button),('find',self.pocket.find_button),('tasks',self.pocket.tasks_button)]:
                    button.clicked()
                    self.tab_clicks+=1
                    self.check_tab(mode,button)
            self.pocket.local_button.clicked()
            self.pocket.local_button.clicked()
            self.check_tab('local',self.pocket.local_button)
            self.check(bool(self.pocket.rows.get_children()),'local skill list was lost after switching tabs')
        finally:
            self.pocket.load_jobs=original
        GLib.timeout_add(100,self.test_open_category)
        return False

    def test_open_category(self):
        self.check(self.pocket.get_visible(),'crossing to popup dismissed it')
        self.pocket.category.popup()
        GLib.timeout_add(150,self.test_category_hold)
        return False

    def test_category_hold(self):
        self.check(self.pocket.category.get_property('popup-shown'),'category dropdown did not open')
        self.check('category-menu' in self.hover.interactions,'category dropdown did not hold pocket open')
        self.hover.leave('popup')
        GLib.timeout_add(950,self.test_category_selection)
        return False

    def test_category_selection(self):
        self.check(self.pocket.get_visible(),'category dropdown caused pocket to disappear')
        self.check(self.pocket.category.get_property('popup-shown'),'category dropdown disappeared before selection')
        self.pocket.category.set_active(CATEGORIES.index('论文与研究'))
        self.pocket.category.popdown()
        GLib.timeout_add(150,self.test_category_result)
        return False

    def test_category_result(self):
        self.check(self.pocket.get_visible(),'selecting a category dismissed pocket')
        self.check('category-menu' not in self.hover.interactions,'category hold remained after selection')
        expected=rank_skills([s for s in self.pocket.skills if s['category']=='论文与研究'],'')
        self.check(len(self.pocket.rows.get_children())==len(expected),'category did not filter skill rows')
        self.check(self.pocket.category.get_active_text()=='论文与研究','selected category was not retained')
        self.category_count=len(expected)
        self.hover.enter('popup')
        self.pocket.category.set_active(0)
        GLib.timeout_add(150,self.test_pin)
        return False

    def test_pin(self):
        self.check(self.pocket.get_visible(),'crossing to popup dismissed it')
        self.hover.set_pinned(True)
        self.hover.leave('popup')
        GLib.timeout_add(780,self.test_preview)
        return False

    def test_preview(self):
        self.check(self.pocket.get_visible(),'pinned pocket was dismissed')
        self.entry_count=len(self.pocket.rows.get_children())
        if self.args.preview:
            width,height=self.pocket.get_size()
            surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width+195,height+32)
            cr=cairo.Context(surface)
            cr.set_source_rgb(.935,.95,.92)
            cr.paint()
            panel=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height)
            self.pocket.draw(cairo.Context(panel))
            cr.set_source_surface(panel,12,12)
            cr.paint()
            dog=self.original.scale_simple(160,160,GdkPixbuf.InterpType.BILINEAR)
            Gdk.cairo_set_source_pixbuf(cr,dog,width+24,height-156)
            cr.paint()
            surface.write_to_png(str(self.args.preview))
        self.hover.set_pinned(False)
        GLib.timeout_add(800,self.test_finish)
        return False

    def test_finish(self):
        self.check(not self.pocket.get_visible(),'leaving did not dismiss pocket')
        print(json.dumps({'native_hover_test':'passed' if not self.errors else 'failed','errors':self.errors,
                          'tab_switch_clicks':self.tab_clicks,
                          'skill_rows':self.entry_count,'popup_size':list(self.pocket.get_size()),
                          'category_filter_rows':self.category_count,
                          'preview':str(self.args.preview) if self.args.preview else None},ensure_ascii=False),flush=True)
        self.quit()
        return False

    def test_timeout(self):
        self.errors.append('native test did not finish within 12 seconds')
        print(json.dumps({'native_hover_test':'failed','errors':self.errors}),flush=True)
        self.quit()
        return False


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--preview',type=Path)
    parser.add_argument('--state-file',type=Path)
    args=parser.parse_args()
    application=PetApplication(args)
    code=application.run([])
    raise SystemExit(1 if application.errors else code)


if __name__=='__main__':
    main()
