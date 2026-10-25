import json, random, sys, time, threading, gzip, os
from pathlib import Path
from collections import OrderedDict
from datetime import datetime
from PIL import Image
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPoint, QRect, QRectF, QSize, QSettings, QUrl
from PySide6.QtGui import QImage, QPixmap, QPainter, QRegion, QCursor, QIcon
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar, QMenu, QMessageBox, QProgressDialog, QPushButton, QSystemTrayIcon, QTextBrowser
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from quota import read_quota, quota_windows
from version import VERSION
from runtime_paths import resource_root, data_root
from animation_frames import AnimationFrameStore, LazyAnimationFrames

ROOT=resource_root()
STATE=data_root()
ASSETS=ROOT/'outputs/白龙桌宠素材'
FLAGS=Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool

def clamp_position(position,size,area):
    """Keep the full pet window inside one monitor's usable rectangle."""
    max_x=max(area.left(),area.right()-size.width()+1)
    max_y=max(area.top(),area.bottom()-size.height()+1)
    return QPoint(max(area.left(),min(position.x(),max_x)),
                  max(area.top(),min(position.y(),max_y)))

class QuotaWorker(QThread):
    ready=Signal(object)
    failed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.cancel=threading.Event()
    def run(self):
        try: self.ready.emit(quota_windows(read_quota(cancel=self.cancel)))
        except Exception as error: self.failed.emit(str(error))

class Bubble(QWidget):
    def __init__(self):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if sys.platform=='darwin':self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.layout=QVBoxLayout(self); self.layout.setContentsMargins(13,10,13,10);self.layout.setSpacing(5)
        self.setFixedWidth(256)
        self.setStyleSheet('QLabel {color:#332644;font-size:12px;font-family:"PingFang SC","Microsoft YaHei","Segoe UI";} QProgressBar {background:#eee8f5;border:1px solid #c8b5dc;border-radius:7px;height:14px;} QProgressBar::chunk {background:#a47bc9;border-radius:6px;}')
    def showEvent(self,event):
        super().showEvent(event)
        from desktop_visibility import configure_macos_window
        if QApplication.platformName()=='cocoa':configure_macos_window(int(self.winId()))
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.white);painter.setPen(Qt.GlobalColor.transparent)
        painter.drawRoundedRect(self.rect(),16,16)
    def clear(self):
        while self.layout.count():
            widget=self.layout.takeAt(0).widget();widget.hide();widget.setParent(None);widget.deleteLater()
    def label(self,text):
        label=QLabel(text);label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.PlainText);self.layout.addWidget(label)
    def message(self,text):
        self.is_task_progress=False
        self.is_quota_result=False
        self.setFixedWidth(256)
        self.clear();self.label(text);self.adjustSize();self.show()
    def task_result(self,title,text,details):
        self.is_task_progress=False
        self.is_quota_result=True
        self.setFixedWidth(300)
        self.clear();self.label(title)
        self.result_title=self.layout.itemAt(0).widget()
        result=QTextBrowser();result.setPlainText(text);result.setOpenLinks(False)
        result.setStyleSheet('QTextBrowser {color:#332644;background:transparent;border:0;font-size:12px;font-family:"PingFang SC","Microsoft YaHei","Segoe UI";}')
        result.setFixedHeight(150 if len(text)>180 or len(text.splitlines())>6 else 76)
        self.result_view=result
        self.layout.addWidget(result)
        button=QPushButton('详情');button.setStyleSheet('color:#60358c;background:#eee5f7;border:0;border-radius:7px;padding:7px;')
        button.clicked.connect(lambda checked=False:details());self.layout.addWidget(button)
        self.adjustSize();self.show()
    def quota(self,windows):
        self.is_task_progress=False
        self.is_quota_result=True
        self.setFixedWidth(256)
        self.clear();self.label('Codex 剩余额度')
        for window in windows:
            value=window['remaining']
            self.label(window['name']+' · '+(f'剩余 {value:g}%' if value is not None else '暂未提供'))
            bar=QProgressBar();bar.setRange(0,100)
            bar.setValue(round(value) if value is not None else 0);bar.setTextVisible(False);self.layout.addWidget(bar)
            if window['resetsAt']:
                self.label('重置：'+datetime.fromtimestamp(window['resetsAt']).strftime('%m月%d日 %H:%M'))
        self.adjustSize();self.show()

class Pet(QWidget):
    def __init__(self):
        super().__init__(None,FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if sys.platform=='darwin':self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle('白龙桌宠');self.setFixedSize(256,256)
        self.manifest=json.loads((ASSETS/'素材清单.json').read_text(encoding='utf-8'))
        self.variants=[v for v in self.manifest['variants'] if self.asset_path(v).is_file()]
        self.idles=[self.manifest['idle']]+self.manifest.get('additionalIdleAnimations',[])[:1]
        self.cache=OrderedDict();self.pinned_frames={};self.frames=[];self.current=None;self.mode='idle';self.index=0
        self.frame_size=min(512,max(256,round(256*max(s.devicePixelRatio() for s in QApplication.screens()))))
        self.frame_store=AnimationFrameStore() if sys.platform=='darwin' else None
        self.transition=None
        self.bubble=Bubble();self.generation=0;self.worker=None;self.quota_inflight=False;self.dragging=False;self.last_click=None
        self.chat=None
        self.task_active=False
        self.manual_hidden=False;self.fullscreen_hidden=False;self.hidden_since=None
        STATE.mkdir(parents=True,exist_ok=True)
        self.settings=QSettings(str(STATE/'preferences.ini'),QSettings.Format.IniFormat) if sys.platform=='darwin' else QSettings('BailongPet','DesktopPet')
        self.auto_hide_fullscreen=self.settings.value('autoHideFullscreen',True,type=bool)
        self.work_slots=self.manifest.get('workAnimations',[])[:6]
        self.click_timer=QTimer(self);self.click_timer.setTimerType(Qt.TimerType.PreciseTimer);self.click_timer.setSingleShot(True);self.click_timer.setInterval(250);self.click_timer.timeout.connect(self.single_click)
        self.bubble_timer=QTimer(self);self.bubble_timer.setSingleShot(True);self.bubble_timer.timeout.connect(self.dismiss_bubble)
        self.tick=QTimer(self);self.tick.setTimerType(Qt.TimerType.PreciseTimer);self.tick.setInterval(16);self.tick.timeout.connect(self.animate)
        area=QApplication.primaryScreen().availableGeometry()
        self.move(self.constrained_position(QPoint(area.right()-360,area.bottom()-340)))
        for screen in QApplication.screens():self.watch_screen(screen)
        QApplication.instance().screenAdded.connect(self.watch_screen)
        QApplication.instance().screenRemoved.connect(lambda screen:QTimer.singleShot(0,self.ensure_on_screen))
        self.idle()
        # On macOS, pin lightweight animation handles while frames share a bounded
        # cache. Other platforms keep the original preloading behavior.
        items=self.idles+self.variants+[v for v in self.work_slots if v and self.asset_path(v).is_file()]+[self.manifest[name] for name in ('dragAnimation','landingAnimation','quotaAnimation') if self.manifest.get(name)]
        items += [self.return_transition_item(v) for v in self.variants if v.get('returnTransition')]
        progress=None
        if sys.platform!='darwin' and QApplication.platformName()!='offscreen':
            progress=QProgressDialog('主人，等我整理好裙摆和小翅膀，马上就来…','',0,len(items))
            progress.setCancelButton(None);progress.setWindowTitle('白龙桌宠');progress.setMinimumDuration(0);progress.show()
        for i,item in enumerate(items):
            key=str(self.asset_path(item));self.pinned_frames[key]=self.load(item);self.cache.pop(key,None)
            if progress:progress.setValue(i+1);QApplication.processEvents()
        if progress:progress.close()
        self.transition=None
        self.started=time.monotonic();self.tick.start()
        self.setup_tray()
        from desktop_visibility import FullscreenDetector
        self.fullscreen_detector=FullscreenDetector()
        self.fullscreen_candidate=False;self.fullscreen_candidate_since=time.monotonic()
        self.visibility_timer=QTimer(self);self.visibility_timer.setInterval(500)
        self.visibility_timer.timeout.connect(self.check_fullscreen)
        if QApplication.platformName()!='offscreen':self.visibility_timer.start()
    def showEvent(self,event):
        super().showEvent(event)
        from desktop_visibility import configure_macos_window
        if QApplication.platformName()=='cocoa':configure_macos_window(int(self.winId()))
    def setup_tray(self):
        # Use the default idle's first frame, independent of the current action.
        icon=QIcon(self.pinned_frames[str(self.asset_path(self.idles[0]))][0])
        self.setWindowIcon(icon)
        self.tray=QSystemTrayIcon(icon,self);self.tray.setToolTip('GPT白龙娘桌宠')
        self.tray_menu=self.context_menu();self.tray.setContextMenu(self.tray_menu)
        self.tray_menu.aboutToShow.connect(self.refresh_tray_menu)
        self.tray.activated.connect(self.tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
    def refresh_tray_menu(self):
        # Rebuild through the same factory used by the pet's right-click menu.
        fresh=self.context_menu()
        self.tray_menu.clear()
        # Keep submenu/action owners alive until the next refresh.
        previous=getattr(self,'tray_menu_contents',None)
        self.tray_menu_contents=fresh
        for action in fresh.actions():self.tray_menu.addAction(action)
        if previous:previous.deleteLater()
    def tray_activated(self,reason):
        if reason==QSystemTrayIcon.ActivationReason.DoubleClick:self.set_manual_hidden(False)
    def desktop_hidden(self):
        return self.manual_hidden or self.fullscreen_hidden
    def dialogue_hidden(self):
        return self.desktop_hidden()
    def speech_hidden(self):
        return self.desktop_hidden() or (self.mode=='working' and self.current and self.current.get('id','').startswith('work'))
    def sync_dialogue_visibility(self):
        if self.speech_hidden() and not getattr(self.bubble,'is_task_progress',False) and self.bubble.isVisible():self.bubble.hide()
        if self.dialogue_hidden():
            if self.bubble.isVisible():self.bubble.hide()
            if self.chat and self.chat.composer.isVisible():self.chat.composer.hide()
        elif self.chat and self.chat.enabled:
            if not self.chat.composer.isVisible():
                self.chat.composer.show();self.chat.position()
    def set_auto_hide_fullscreen(self,enabled):
        self.auto_hide_fullscreen=enabled
        self.settings.setValue('autoHideFullscreen',enabled)
        if not enabled:self.fullscreen_hidden=False;self.apply_visibility()
        self.fullscreen_candidate=False;self.fullscreen_candidate_since=time.monotonic()
    def set_manual_hidden(self,hidden):
        if hidden and not self.tray.isVisible():
            self.say('主人，托盘暂时没准备好，我先留在这里陪你。');return
        self.manual_hidden=hidden;self.apply_visibility()
    def apply_visibility(self):
        if self.desktop_hidden():
            if self.hidden_since is None:self.hidden_since=time.monotonic()
            self.tick.stop();self.click_timer.stop();self.last_click=None;self.dragging=False
            self.hide();self.bubble.hide()
            if self.chat:self.chat.composer.hide()
        else:
            if self.hidden_since is not None:
                self.started+=time.monotonic()-self.hidden_since;self.hidden_since=None
            self.ensure_on_screen();self.show();self.tick.start()
            self.sync_dialogue_visibility()
        if hasattr(self,'tray'):
            state='已隐藏' if self.manual_hidden else ('全屏时自动隐藏' if self.fullscreen_hidden else '正在陪伴主人')
            self.tray.setToolTip('GPT白龙娘桌宠 · '+state)
    def check_fullscreen(self):
        if self.tray_menu.isVisible():return
        state=self.auto_hide_fullscreen and self.fullscreen_detector.active();now=time.monotonic()
        if state!=self.fullscreen_candidate:
            self.fullscreen_candidate=state;self.fullscreen_candidate_since=now
        # Hide promptly; wait longer before restoring to avoid focus-change flicker.
        if state!=self.fullscreen_hidden and now-self.fullscreen_candidate_since>=(.25 if state else .75):
            self.fullscreen_hidden=state;self.apply_visibility()
        if self.desktop_hidden():
            self.bubble.hide()
            if self.chat:self.chat.composer.hide()
        self.sync_dialogue_visibility()
    def constrained_position(self,position,pointer=None):
        screens=QApplication.screens()
        # Allow crossing monitors, but never use their bounding union: it can
        # contain empty gaps or permit half the pet to hang off a monitor.
        screen=QApplication.screenAt(pointer) if pointer is not None else None
        def constrain(area):
            if self.chat and self.chat.enabled:
                width=max(self.width(),self.chat.composer.width());shift=(width-self.width())//2
                size=QSize(width,self.height()+8+self.chat.composer.height())
                return clamp_position(position-QPoint(shift,0),size,area)+QPoint(shift,0)
            return clamp_position(position,self.size(),area)
        if screen:return constrain(screen.availableGeometry())
        candidates=[constrain(s.availableGeometry()) for s in screens]
        return min(candidates,key=lambda p:(p.x()-position.x())**2+(p.y()-position.y())**2) if candidates else position
    def watch_screen(self,screen):
        screen.availableGeometryChanged.connect(lambda area:self.ensure_on_screen())
        QTimer.singleShot(0,self.ensure_on_screen)
    def ensure_on_screen(self):
        position=self.constrained_position(self.pos())
        if position!=self.pos():
            self.move(position)
            if self.dragging:self.origin=self.pos();self.press_pos=QCursor.pos()
        if self.bubble.isVisible():self.position_bubble()
        if self.chat:self.chat.position()
    def moveEvent(self,event):
        super().moveEvent(event)
        if getattr(self,'chat',None):self.chat.position()
    def asset_path(self,item):
        # Optional playbackFile allows future formats without changing the manifest's video source.
        return ASSETS/(item.get('playbackFile') or item['file'].replace('.webm','.webp'))
    def load(self,item):
        path=self.asset_path(item);key=str(path)
        if key in self.pinned_frames:return self.pinned_frames[key]
        if key in self.cache: self.cache.move_to_end(key);return self.cache[key]
        if self.frame_store is not None:
            frames=LazyAnimationFrames(self.frame_store,path,self.frame_size)
            self.cache[key]=frames
            while len(self.cache)>2:self.cache.popitem(last=False)
            return frames
        frames=[]
        packed=ROOT/'app/cache'/f'{item["id"]}-hq.rgba.gz';metadata=packed.with_suffix('.json')
        if packed.is_file() and metadata.is_file():
            meta=json.loads(metadata.read_text(encoding='utf-8'));stat=path.stat()
            if meta['sourceSize']==stat.st_size and meta['sourceMtime']==stat.st_mtime_ns:
                raw=gzip.decompress(packed.read_bytes());stride=512*512*4
                if len(raw)==meta['frames']*stride:
                    for offset in range(0,len(raw),stride):
                        pixmap=QPixmap.fromImage(QImage(raw[offset:offset+stride],512,512,2048,QImage.Format.Format_RGBA8888).copy())
                        frames.append(pixmap.scaled(self.frame_size,self.frame_size,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation) if self.frame_size!=512 else pixmap)
        if frames:
            self.cache[key]=frames
            while len(self.cache)>2:self.cache.popitem(last=False)
            return frames
        with Image.open(path) as source:
            for i in range(source.n_frames):
                source.seek(i);im=source.convert('RGBA').resize((self.frame_size,self.frame_size),Image.Resampling.LANCZOS)
                raw=im.tobytes();qimage=QImage(raw,self.frame_size,self.frame_size,self.frame_size*4,QImage.Format.Format_RGBA8888).copy()
                frames.append(QPixmap.fromImage(qimage))
        if not frames: raise RuntimeError('动画没有可播放帧：'+str(path))
        self.cache[key]=frames
        while len(self.cache)>2:self.cache.popitem(last=False)
        return frames
    def play(self,item,mode):
        self.frames=self.load(item);self.current=item;self.mode=mode;self.index=0;self.started=time.monotonic();self.update_frame()
        if getattr(self,'hidden_since',None) is not None:self.hidden_since=self.started
        self.transition=None
        self.sync_dialogue_visibility()
    def idle(self):
        if self.task_active:
            work=self.regular_work_animations()
            previous=self.current.get('id') if self.current else None
            groups=[('working',work),('idle',self.idles)] if work else [('idle',self.idles)]
            candidates=[(mode,[v for v in pool if v['id']!=previous]) for mode,pool in groups]
            candidates=[g for g in candidates if g[1]]
            if not candidates:return
            mode,pool=random.choices(candidates,weights=[35 if mode=='working' else 65 for mode,pool in candidates])[0]
            self.last_task_group=mode
            self.play(random.choice(pool),mode)
            return
        item=random.choices(self.idles,weights=[4,1][:len(self.idles)])[0]
        self.play(item,'idle')
    def regular_work_animations(self):
        return [v for v in self.work_slots if v and v['id']!='work01' and self.asset_path(v).is_file()]
    def task_started(self):
        self.task_active=True
        self.last_task_group=None
        self.click_timer.stop();self.last_click=None
        work=[v for v in self.work_slots if v and self.asset_path(v).is_file()]
        opening=next((v for v in work if v['id']=='work01'),None)
        if opening:self.play(opening,'work-start')
        else:self.idle()
    def task_finished(self):
        self.task_active=False
        if self.mode in ('work-start','working','idle'):self.idle()
    def return_transition_item(self,item):
        transition=item['returnTransition']
        return {'id':'return-'+item['id'],'file':transition['file'],
                'durationMs':transition['durationMs'],'renderScale':1.0,'renderOffset':[0,0]}
    def update_frame(self):
        # Windows layered windows use per-pixel alpha. A binary mask would
        # dither the soft character edges and damage transparent rendering.
        self.update()
    def animate(self):
        duration=self.current.get('durationMs',4000)/1000
        elapsed=time.monotonic()-self.started
        if elapsed>=duration:
            if self.mode=='drag':self.play(self.manifest.get('dragAnimation') or self.idles[0],'drag')
            elif self.mode=='work-start' and self.task_active:
                work=self.regular_work_animations()
                if work:
                    self.last_task_group='working';self.play(random.choice(work),'working')
                else:self.idle()
            elif self.mode=='variant' and self.current.get('returnTransition'):
                self.play(self.return_transition_item(self.current),'return-idle')
            elif self.mode=='return-idle':self.play(self.idles[0],'idle')
            else:self.idle()
            return
        index=min(len(self.frames)-1,int(elapsed/duration*len(self.frames)))
        if self.transition:self.update()
        if index!=self.index:self.index=index;self.update_frame()
    def paintEvent(self,event):
        if self.frames:
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.draw_frame(painter,QRectF(self.rect()))
    def draw_frame(self,painter,canvas):
        scale=self.current.get('renderScale',1.0);offset=self.current.get('renderOffset',[0,0])
        width,height=canvas.width()*scale,canvas.height()*scale
        target=QRectF(canvas.x()+(canvas.width()-width)/2+canvas.width()*offset[0],canvas.y()+canvas.height()-height+canvas.height()*offset[1],width,height)
        frame=self.frames[self.index];painter.drawPixmap(target,frame,QRectF(frame.rect()))
    def snapshot_frame(self):
        pixmap=QPixmap(self.frame_size,self.frame_size);pixmap.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pixmap);self.draw_frame(painter,QRectF(pixmap.rect()));painter.end();return pixmap
    def position_bubble(self):
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        area=screen.availableGeometry();pet=self.frameGeometry()
        width,height=self.bubble.width(),self.bubble.height();gap=12
        if not getattr(self.bubble,'is_quota_result',False):
            x=max(area.left(),min(pet.center().x()-width//2,area.right()-width+1))
            y=pet.top()-height-gap
            if y<area.top():y=pet.bottom()+gap+1
            y=max(area.top(),min(y,area.bottom()-height+1))
            self.bubble.move(x,y);return
        # Prefer the sides; choose a screen-safe position with no character overlap.
        candidates=[(pet.right()+gap+1,pet.center().y()-height//2),
                    (pet.left()-width-gap,pet.center().y()-height//2),
                    (pet.center().x()-width//2,pet.top()-height-gap),
                    (pet.center().x()-width//2,pet.bottom()+gap+1)]
        positions=[]
        for x,y in candidates:
            x=max(area.left(),min(x,area.right()-width+1))
            y=max(area.top(),min(y,area.bottom()-height+1))
            overlap=pet.intersected(QRect(x,y,width,height))
            score=max(0,overlap.width())*max(0,overlap.height())
            if self.chat and self.chat.enabled:
                overlap=self.chat.composer.frameGeometry().intersected(QRect(x,y,width,height))
                score+=max(0,overlap.width())*max(0,overlap.height())
            positions.append((score,x,y))
        _,x,y=min(positions,key=lambda item:item[0]);self.bubble.move(x,y)
    def say(self,text,ms=4000):
        if self.speech_hidden():return
        self.bubble_timer.stop();self.bubble.message(text);self.position_bubble()
        if ms:self.bubble_timer.start(ms)
    def dismiss_bubble(self):
        self.bubble.hide()
        if self.mode=='quota':self.idle()
    def task_result(self,title,text,details):
        if self.speech_hidden():return
        self.generation+=1;self.bubble_timer.stop()
        self.bubble.task_result(title,text,details);self.position_bubble();self.bubble_timer.start(20000)
    def task_progress(self,title,text,details):
        if self.desktop_hidden():return
        self.bubble_timer.stop()
        if getattr(self.bubble,'is_task_progress',False) and self.bubble.isVisible():
            view=self.bubble.result_view;bar=view.verticalScrollBar()
            bottom=bar.value()>=bar.maximum()-8;old=bar.value()
            self.bubble.result_title.setText(title);view.setPlainText(text)
            bar.setValue(bar.maximum() if bottom else min(old,bar.maximum()))
        else:
            self.bubble.task_result(title,text,details);self.bubble.is_task_progress=True
        self.position_bubble();self.bubble_timer.start(12000)
    def task_completed(self,text,details):
        self.play_click_sound()
        celebration=next((v for v in self.variants if v['id']=='18'),None)
        if celebration:self.play(celebration,'task-celebration')
        # Play directly so the celebration's interaction line is never shown.
        self.task_result('主人，完成啦！',text,details)
    def chat_controller(self):
        if self.chat is None:
            from chat_ui import ChatController
            try:self.chat=ChatController(self)
            except Exception as error:
                self.say('唔，主人，对话模式暂时打不开啦：'+str(error),10000);return None
        return self.chat
    def toggle_chat(self):
        controller=self.chat_controller()
        if controller:controller.toggle()
        self.sync_dialogue_visibility()
    def open_history(self):
        controller=self.chat_controller()
        if controller:controller.open_history()
    def context_menu(self):
        menu=QMenu(self)
        action=menu.addAction('显示桌宠' if self.manual_hidden or self.fullscreen_hidden else '隐藏桌宠')
        action.triggered.connect(lambda checked=False:self.set_manual_hidden(not self.manual_hidden if not self.fullscreen_hidden else False))
        if self.fullscreen_hidden:
            menu.addAction('全屏结束后自动显示').setEnabled(False)
        menu.addSeparator()
        automatic=menu.addAction('全屏时自动隐藏');automatic.setCheckable(True)
        automatic.setChecked(self.auto_hide_fullscreen);automatic.toggled.connect(self.set_auto_hide_fullscreen)
        menu.addAction('关闭对话模式' if self.chat and self.chat.enabled else '打开对话模式',self.toggle_chat)
        menu.addAction('查看历史对话',self.open_history)
        menu.addSeparator()
        interaction=menu.addMenu('互动差分动画')
        for item in self.variants:
            action=interaction.addAction(item['id']+' · '+item['name'])
            action.triggered.connect(lambda checked=False,v=item:self.choose(v))
        work=menu.addMenu('工作差分动画')
        available=[item for item in self.work_slots if item and self.asset_path(item).is_file()]
        for item in available:
            action=work.addAction(item['id']+' · '+item['name'])
            action.triggered.connect(lambda checked=False,v=item:self.choose(v))
        if not available:work.addAction('暂无动作（已预留6个位置）').setEnabled(False)
        idle=menu.addMenu('待机差分动画')
        for index,item in enumerate(self.idles):
            name='默认待机' if index==0 else '待机动作02'
            action=idle.addAction(name);action.triggered.connect(lambda checked=False,v=item:self.preview_idle(v))
        menu.addSeparator();menu.addAction('退出桌宠',self.close)
        return menu
    def preview_idle(self,item):
        self.click_timer.stop();self.last_click=None;self.generation+=1;self.play(item,'idle')
    def play_click_sound(self):
        if sys.platform=='darwin':
            from PySide6.QtMultimedia import QSoundEffect
            if not hasattr(self,'click_sound'):
                self.click_sound=QSoundEffect(self)
                self.click_sound.setSource(QUrl.fromLocalFile(str(ROOT/'app/sounds/click.wav')))
                self.click_sound.setVolume(.35)
            self.click_sound.play()
        elif sys.platform=='win32':
            import winsound
            sound=ROOT/'app/sounds/click.wav'
            if sound.is_file():
                try:winsound.PlaySound(str(sound),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
                except RuntimeError:pass
    def choose(self,item):
        self.click_timer.stop();self.last_click=None;self.generation+=1
        try:self.play_click_sound();self.play(item,'variant');self.say(item.get('line',''),4000)
        except Exception as error:self.idle();self.say('唔，主人，这个动作暂时没能准备好：'+str(error))
    def single_click(self):
        self.last_click=None
        pool=self.interaction_animations()
        previous=self.current.get('id') if self.current else None
        available=[v for v in pool if v['id']!=previous] or pool
        if available:self.choose(random.choice(available))
    def interaction_animations(self):
        return self.variants+[v for v in self.work_slots if v and self.asset_path(v).is_file()]
    def quota(self):
        self.click_timer.stop();self.last_click=None;self.generation+=1;token=self.generation
        self.play_click_sound()
        self.play(self.manifest.get('quotaAnimation') or self.idles[0],'quota')
        self.say('让我看看额度还有多少。。。。。。',0)
        if self.quota_inflight:
            # Repeated requests share the in-flight read; delivery uses the newest generation.
            self.quota_generation=token;return
        self.quota_generation=token;self.quota_inflight=True;self.worker=QuotaWorker(self)
        self.worker.ready.connect(self.quota_ready);self.worker.failed.connect(self.quota_failed);self.worker.start()
    def quota_ready(self,windows):
        self.quota_inflight=False
        if self.speech_hidden():return
        if self.quota_generation!=self.generation:return
        self.bubble.quota(windows);self.position_bubble();self.bubble_timer.start(12000)
    def quota_failed(self,error):
        self.quota_inflight=False
        if self.quota_generation==self.generation:self.say('主人，我暂时没查到额度，过一会儿再看看好不好？\n'+error,8000)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:
            self.click_timer.stop();self.last_click=None
            menu=self.context_menu();menu.exec(event.globalPosition().toPoint());menu.deleteLater();return
        if event.button()==Qt.MouseButton.LeftButton:
            self.press_pos=event.globalPosition().toPoint();self.origin=self.pos();self.dragging=False
    def mouseDoubleClickEvent(self,event):
        # Qt may emit this before mousePressEvent for the second physical press.
        self.mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.MouseButton.LeftButton and hasattr(self,'press_pos'):
            delta=event.globalPosition().toPoint()-self.press_pos
            if delta.manhattanLength()>8 and not self.dragging:
                self.dragging=True;self.click_timer.stop();self.last_click=None;self.generation+=1
                self.bubble_timer.stop();self.bubble.hide()
                self.play(self.manifest.get('dragAnimation') or self.idles[0],'drag')
            if self.dragging:
                self.move(self.constrained_position(self.origin+delta,event.globalPosition().toPoint()))
                self.position_bubble()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        if self.dragging:
            self.dragging=False;self.last_click=None;self.click_timer.stop()
            landing=self.manifest.get('landingAnimation')
            if landing:self.play(landing,'landing')
            else:self.idle()
            return
        now=time.monotonic()
        if self.last_click is not None and now-self.last_click<=.25:self.quota()
        else:self.last_click=now;self.click_timer.start()
    def closeEvent(self,event):
        if self.chat and not self.chat.shutdown():
            event.ignore();QTimer.singleShot(500,self.close);return
        self.tick.stop();self.visibility_timer.stop();self.tray.hide();self.bubble.close()
        if self.frame_store:self.frame_store.close()
        if self.worker and self.worker.isRunning():self.worker.cancel.set();self.worker.wait(3000)
        QApplication.quit();event.accept()

def main():
    if '--autostart' in sys.argv:
        from autostart import main as monitor
        return monitor()
    if '--self-test' in sys.argv:
        from selftest import run
        return run(ROOT,STATE)
    app=QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if '--enable-autostart' in sys.argv or '--disable-autostart' in sys.argv:
        from autostart import enable_autostart,disable_autostart
        try:
            if '--enable-autostart' in sys.argv:
                enable_autostart();message='已开启：以后登录电脑时，助手会自动运行；打开客户端后启动桌宠。\n如要移动桌宠应用，请先关闭自动启动，移好后再开启。'
            else:disable_autostart();message='已关闭桌宠自动启动。'
            QMessageBox.information(None,'白龙桌宠',message);return 0
        except Exception as error:QMessageBox.critical(None,'设置失败',str(error));return 1
    socket=QLocalSocket();socket.connectToServer('bailong-desktop-pet-v1')
    if socket.waitForConnected(150):return 0
    QLocalServer.removeServer('bailong-desktop-pet-v1');server=QLocalServer();server.listen('bailong-desktop-pet-v1')
    try:
        pet=Pet();pet.show()
        def reveal_existing_pet():
            while server.hasPendingConnections():
                connection=server.nextPendingConnection()
                connection.disconnectFromServer();connection.deleteLater()
            screen=QApplication.primaryScreen()
            if screen:
                area=screen.availableGeometry()
                pet.move(clamp_position(QPoint(area.center().x()-pet.width()//2,area.center().y()-pet.height()//2),pet.size(),area))
            pet.set_manual_hidden(False)
            if pet.desktop_hidden():return
            pet.showNormal();pet.show();pet.raise_()
            if sys.platform=='win32':
                import ctypes
                ctypes.windll.user32.ShowWindow(int(pet.winId()),4)
        server.newConnection.connect(reveal_existing_pet)
        def record_startup():
            # pythonw can inherit a hidden startup state from a launcher.
            # Explicitly show this app's own window without stealing focus.
            native_visible=pet.isVisible()
            if sys.platform=='win32':
                import ctypes
                handle=int(pet.winId())
                ctypes.windll.user32.ShowWindow(handle,4)
                native_visible=bool(ctypes.windll.user32.IsWindowVisible(handle))
            STATE.mkdir(parents=True,exist_ok=True)
            native_status={}
            if QApplication.platformName()=='cocoa':
                from desktop_visibility import mac_window_status
                native_status=mac_window_status(int(pet.winId()))
                native_visible=native_status.get('isVisible',native_visible)
            (STATE/'运行状态.json').write_text(json.dumps({'version':VERSION,'pid':os.getpid(),'visible':pet.isVisible(),'nativeVisible':native_visible,'nativeWindow':native_status,'windowId':int(pet.winId()),'variants':len(pet.variants),'position':[pet.x(),pet.y()],'displaySize':[pet.width(),pet.height()],'frameSize':[self_size for self_size in (pet.frames[0].width(),pet.frames[0].height())]},ensure_ascii=False),encoding='utf-8')
        QTimer.singleShot(1000,record_startup)
        if '--preview' in sys.argv:
            QTimer.singleShot(500,lambda:pet.grab().save(str(STATE/'桌宠窗口预览.png')))
            QTimer.singleShot(900,app.quit)
    except Exception as error:QMessageBox.critical(None,'白龙桌宠启动失败',str(error));return 1
    return app.exec()

if __name__=='__main__':sys.exit(main())
