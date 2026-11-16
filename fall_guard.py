# -*- coding: utf-8 -*-
"""小辣椒本地安全守护。摄像头仅在本机处理，不通过 HTTP 输出视频。"""
import os, time, threading, collections

class FallGuard:
    def __init__(self):
        self.lock=threading.RLock(); self.running=False; self.status='未启动'; self.error=''
        self.events=collections.deque(maxlen=100); self.seq=0; self.worker=None
        self.stop_flag=threading.Event(); self.pending=None; self.last_alarm=0
        self.model_path=os.getenv('XLJ_FALL_MODEL','yolov8n-pose.pt')
        self.camera_index=int(os.getenv('XLJ_FALL_CAMERA','0'))
        self.confirm_seconds=2.0; self.cooldown=45
    def snapshot(self):
        with self.lock:
            return {'running':self.running,'status':self.status,'error':self.error,'pending':dict(self.pending) if self.pending else None,'events':list(self.events)[:30]}
    def _event(self,kind,message):
        self.seq+=1; event={'id':self.seq,'kind':kind,'message':message,'time':time.time()}
        self.events.appendleft(event); return event
    def start(self):
        with self.lock:
            if self.running:return self.snapshot()
            self.stop_flag.clear(); self.running=True; self.status='启动中'; self.error=''
            self.worker=threading.Thread(target=self._run,daemon=True); self.worker.start()
        return self.snapshot()
    def stop(self):
        self.stop_flag.set()
        with self.lock:
            self.status='正在停止'; return {'ok':True}
    def acknowledge(self,action):
        with self.lock:
            if not self.pending: raise ValueError('当前没有待处理的疑似跌倒事件')
            if action not in ('safe','help'):raise ValueError('无效操作')
            event=self.pending;self.pending=None
            self._event('help' if action=='help' else 'cancel', '老人请求帮助' if action=='help' else '已确认安全，取消本次警报')
            return {'ok':True,'event_id':event['id'],'action':action}
    def _alarm(self):
        with self.lock:
            if self.pending or time.time()-self.last_alarm<self.cooldown:return
            event=self._event('suspected','检测到疑似跌倒，请确认是否需要帮助')
            self.pending=event;self.last_alarm=time.time()
    def _run(self):
        cap=None
        try:
            import cv2
            from ultralytics import YOLO
            model=YOLO(self.model_path)
            cap=cv2.VideoCapture(self.camera_index,cv2.CAP_DSHOW if os.name=='nt' else cv2.CAP_ANY)
            if not cap.isOpened():raise RuntimeError('无法打开摄像头，请检查是否被视频通话或其他程序占用')
            with self.lock:self.status='监测中（实验性识别）'
            suspected_since=None
            while not self.stop_flag.is_set():
                ok,frame=cap.read()
                if not ok:time.sleep(.2);continue
                # 实验性启发式：关键点躯干近水平 + 人体框宽高比；不是经过临床验证的跌倒模型。
                results=model.predict(frame,verbose=False,conf=.45,imgsz=640)
                suspect=False
                for r in results:
                    if r.boxes is None or r.keypoints is None:continue
                    boxes=r.boxes.xyxy.cpu().numpy(); pts=r.keypoints.xy.cpu().numpy()
                    for box,kp in zip(boxes,pts):
                        if len(kp)<13:continue
                        x1,y1,x2,y2=box; w=x2-x1;h=y2-y1
                        shoulders=(kp[5]+kp[6])/2; hips=(kp[11]+kp[12])/2
                        if min(*shoulders,*hips)<=0:continue
                        dx=abs(float(shoulders[0]-hips[0]));dy=abs(float(shoulders[1]-hips[1]))
                        if w>h*1.15 and dx>dy*1.15:suspect=True;break
                    if suspect:break
                now=time.monotonic()
                if suspect:
                    if suspected_since is None:suspected_since=now
                    elif now-suspected_since>=self.confirm_seconds:self._alarm()
                else:suspected_since=None
                time.sleep(.08)
        except Exception as e:
            with self.lock:self.error=str(e);self.status='启动失败'
        finally:
            if cap is not None:cap.release()
            with self.lock:
                self.running=False
                if not self.error:self.status='已停止'

GUARD=FallGuard()
