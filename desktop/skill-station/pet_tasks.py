"""Native task composer and live result window for the beagle pet."""
import threading
from pathlib import Path

from gi.repository import Gdk, GLib, Gtk
from task_client import TaskClient


def styled(widget, name):
    widget.get_style_context().add_class(name)
    return widget


def label(value, name='muted'):
    widget = styled(Gtk.Label(label=value, xalign=0), name)
    widget.set_line_wrap(True)
    return widget


class TaskWindow(Gtk.Window):
    def __init__(self, owner, skill=None, task='', job_id=None):
        super().__init__(title='比格接单处 · 直接开工')
        styled(self, 'task-window')
        self.owner, self.skill, self.job_id = owner, skill, job_id
        self.client, self.busy, self.disposed = TaskClient(), False, False
        self.files, self.poll_timer, self.workspace_paths = [], None, []
        self.set_application(owner)
        self.set_transient_for(owner.pocket)
        self.set_keep_above(True)
        self.set_default_size(520, 640)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', self.closed)
        owner.hover.hold_open('task-window')
        root = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 'pocket')
        self.add(root)
        root.pack_start(label('这活，比格接了。', 'title'), False, False, 0)
        root.pack_start(label('任务写清楚，进度和结果都在这里。'), False, False, 0)
        self.form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.pack_start(self.form, False, False, 0)
        self.form.pack_start(label('使用：'+(skill['title'] if skill else '自动选择技能'), 'row-title'), False, False, 0)
        self.workspace = Gtk.ComboBoxText()
        self.workspace.set_hexpand(True)
        self.form.pack_start(label('新对话所在的项目 / 工作文件夹', 'row-title'), False, False, 0)
        row = Gtk.Box(spacing=7)
        row.pack_start(self.workspace, True, True, 0)
        folder = Gtk.Button(label='选文件夹')
        folder.connect('clicked', self.choose_workspace)
        row.pack_start(folder, False, False, 0)
        self.form.pack_start(row, False, False, 0)
        self.form.pack_start(label('执行模型（任务主 Agent）', 'row-title'), False, False, 0)
        self.model = Gtk.ComboBoxText()
        self.model.append('default', '沿用当前 Codex 设置')
        self.model.set_active_id('default')
        self.form.pack_start(self.model, False, False, 0)
        self.form.pack_start(label('任务与要求', 'row-title'), False, False, 0)
        self.task = styled(Gtk.TextView(), 'task-input')
        self.task.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.task.get_buffer().set_text(task)
        input_scroll = Gtk.ScrolledWindow()
        input_scroll.set_min_content_height(110)
        input_scroll.add(self.task)
        self.form.pack_start(input_scroll, False, False, 0)
        attachment = Gtk.Box(spacing=7)
        add_file = Gtk.Button(label='附上本机文件 ＋')
        add_file.connect('clicked', self.choose_files)
        attachment.pack_start(add_file, False, False, 0)
        self.file_count = label('未附文件')
        attachment.pack_start(self.file_count, True, True, 0)
        self.form.pack_start(attachment, False, False, 0)
        self.submit_button = styled(Gtk.Button(label='让比格开工 ⚡'), 'primary')
        self.submit_button.connect('clicked', self.submit)
        self.form.pack_start(self.submit_button, False, False, 0)
        self.state = label('正在连接本机 Codex…', 'row-title')
        root.pack_start(self.state, False, False, 0)
        self.progress = Gtk.ProgressBar()
        root.pack_start(self.progress, False, False, 0)
        self.output = styled(Gtk.TextView(), 'task-output')
        self.output.set_editable(False)
        self.output.set_cursor_visible(False)
        self.output.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        output_scroll = Gtk.ScrolledWindow()
        output_scroll.set_min_content_height(130)
        output_scroll.add(self.output)
        root.pack_start(output_scroll, True, True, 0)
        controls = styled(Gtk.Box(spacing=8), 'footer')
        self.open_button = Gtk.Button(label='完整进度与成果文件 ↗')
        self.open_button.connect('clicked', lambda _b: owner.open_station(self.job_id))
        controls.pack_start(self.open_button, True, True, 0)
        self.cancel_button = Gtk.Button(label='停止任务')
        self.cancel_button.connect('clicked', self.cancel)
        self.cancel_button.set_sensitive(bool(job_id))
        controls.pack_start(self.cancel_button, False, False, 0)
        root.pack_start(controls, False, False, 0)
        self.chat_button = Gtk.LinkButton.new_with_label('codex://threads/new', '打开 Codex 对话 ↗')
        self.chat_button.set_no_show_all(True)
        root.pack_start(self.chat_button, False, False, 0)
        self.show_all()
        if job_id:
            self.form.hide()
            self.load_job()
        else:
            self.submit_button.set_sensitive(False)
            self.background(self.client.connect, self.connected)

    def background(self, work, callback):
        def run():
            try:
                value, error = work(), None
            except Exception as exc:
                value, error = None, str(exc)
            GLib.idle_add(self.deliver, callback, value, error)
        threading.Thread(target=run, daemon=True).start()

    def deliver(self, callback, value, error):
        if not self.disposed:
            if error:
                self.state.set_text(error)
                self.busy = False
                if not self.job_id:
                    self.submit_button.set_sensitive(True)
            else:
                callback(value)
        return False

    def connected(self, info):
        self.workspace_paths = info['workspaces']
        self.workspace.remove_all()
        for path in self.workspace_paths:
            self.workspace.append_text(path)
        if self.workspace_paths:
            self.workspace.set_active(0)
        self.state.set_text('本机连接已就绪' if info['available'] else '请先安装并登录 Codex')
        self.submit_button.set_sensitive(info['available'])
        self.background(lambda: self.client.request('GET', '/api/models'), self.loaded_models)

    def loaded_models(self, result):
        prior = self.model.get_active_id()
        self.model.remove_all()
        self.model.append('default', '沿用当前 Codex 设置')
        for item in result['models']:
            self.model.append(item['model'], item['displayName'])
        if not self.model.set_active_id(prior or 'default'):
            self.model.set_active_id('default')

    def choose_workspace(self, _button):
        dialog = Gtk.FileChooserDialog(title='选择任务的工作文件夹', parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '使用这个文件夹', Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.background(lambda: self.client.request('POST', '/api/workspaces', {'path': path}), self.connected)
        dialog.destroy()

    def choose_files(self, _button):
        dialog = Gtk.FileChooserDialog(title='附上任务需要的本机文件', parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.set_select_multiple(True)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '附上文件', Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.files = list(dict.fromkeys(self.files+dialog.get_filenames()))[:20]
            self.file_count.set_text(f'已附 {len(self.files)} 个文件')
            self.file_count.set_tooltip_text('\n'.join(self.files))
        dialog.destroy()

    def submit(self, _button):
        if self.busy:
            return
        buffer = self.task.get_buffer()
        task = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()
        if not task:
            self.state.set_text('先把任务写下来，比格才知道干什么。')
            self.task.grab_focus()
            return
        if self.workspace.get_active() < 0:
            self.state.set_text('先选一个工作文件夹，成果会保存在这里。')
            return
        self.busy = True
        self.submit_button.set_sensitive(False)
        data = {'task': task, 'workspace': self.workspace.get_active_text(), 'files': self.files,
                'skill_id': self.skill['id'] if self.skill else None,
                'model': self.model.get_active_id() if self.model.get_active_id() != 'default' else None}
        self.background(lambda: self.client.request('POST', '/api/jobs', data), self.submitted)

    def submitted(self, job):
        self.job_id, self.busy = job['id'], False
        self.form.hide()
        self.show_job(job)
        self.poll_timer = GLib.timeout_add(1300, self.poll)

    def load_job(self):
        self.background(lambda: self.client.job(self.job_id), self.loaded)

    def loaded(self, job):
        self.busy = False
        self.show_job(job)
        if not self.poll_timer and job['status'] not in ('completed', 'failed', 'interrupted', 'cancelled'):
            self.poll_timer = GLib.timeout_add(1300, self.poll)

    def poll(self):
        if self.disposed:
            return False
        if not self.busy:
            self.busy = True
            self.load_job()
        return True

    def show_job(self, job):
        active = job['status'] not in ('completed', 'failed', 'cancelled', 'interrupted')
        self.state.set_text(job['status_label']+' · '+job['skill_title'])
        if active:
            self.progress.pulse()
        else:
            self.progress.set_fraction(1 if job['status'] == 'completed' else 0)
            if self.poll_timer:
                GLib.source_remove(self.poll_timer)
                self.poll_timer = None
        self.cancel_button.set_sensitive(active)
        if job.get('thread_url'):
            self.chat_button.set_uri(job['thread_url'])
            self.chat_button.set_tooltip_text('对话工作目录：'+job['workspace'])
            self.chat_button.show()
        else:
            self.chat_button.hide()
        self.open_button.set_label('处理请求，继续开工 ↗' if job['pending'] else '完整进度与成果文件 ↗')
        parts = [job['task'], '执行模型：'+(job.get('actual_model') or job.get('model_label') or '沿用当前 Codex 设置'), '\n'.join(e['message'] for e in job['events'][-5:])]
        if job['pending']:
            parts.append('需要你的确认或补充信息。点下方“处理请求”继续。')
        parts.append(job['result'] or '\n\n'.join(m['text'] for m in job['messages'].values()))
        if job['error']:
            parts.append(job['error'])
        if job['artifacts']:
            parts.append('成果文件：\n'+'\n'.join(job['artifacts']))
        self.output.get_buffer().set_text('\n\n'.join(p for p in parts if p))

    def cancel(self, _button):
        self.background(lambda: self.client.request('POST', '/api/job/cancel', {'id': self.job_id}), self.show_job)

    def closed(self, *_):
        self.disposed = True
        if self.poll_timer:
            GLib.source_remove(self.poll_timer)
        self.owner.hover.release_open('task-window')
        self.owner.task_window = None
