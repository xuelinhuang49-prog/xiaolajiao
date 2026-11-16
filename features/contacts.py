# -*- coding: utf-8 -*-
"""联系人通讯录：新增 / 查看 / 删除 / 查找，持久化到 contacts.json。

配合前端「给 XX 打视频」使用；默认预置几位常用联系人（儿子/女儿/孙子/孙女/村医）。
"""
import json
import os
import re
import threading

DEFAULT_CONTACTS = [
    {'name': '小辣椒', 'photo': 'xiaolajiao.png', 'emoji': '🌶️'},
    {'name': '儿子', 'photo': 'son.jpg', 'emoji': '👨'},
    {'name': '女儿', 'photo': '', 'emoji': '👧'},
    {'name': '孙子', 'photo': '', 'emoji': '👦'},
    {'name': '孙女', 'photo': '', 'emoji': '👧'},
    {'name': '村医', 'photo': '', 'emoji': '👨‍⚕️'},
]


class ContactsStore:
    """联系人仓库（线程安全，持久化到 JSON 文件）。"""

    def __init__(self, path):
        self.path = path
        self._items = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        self._items = data
                except Exception:
                    self._items = []
            if not self._items:
                self._items = [dict(c) for c in DEFAULT_CONTACTS]
                self._save_locked()

    def _save_locked(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def list(self):
        with self._lock:
            return [dict(c) for c in self._items]

    def find(self, name):
        with self._lock:
            for c in self._items:
                if c['name'] == name:
                    return dict(c)
            return None

    def add(self, name):
        with self._lock:
            if any(c['name'] == name for c in self._items):
                return False
            self._items.append({'name': name, 'photo': '', 'emoji': '👤'})
            self._save_locked()
            return True

    def remove(self, name):
        with self._lock:
            before = len(self._items)
            self._items = [c for c in self._items if c['name'] != name]
            if len(self._items) != before:
                self._save_locked()
                return True
            return False


class ContactsTask:
    """一次“管理通讯录”的对话（新增/查看/删除，名字没听清时追问）。"""

    def __init__(self, store):
        self.store = store
        self.pending = None  # 'add' 或 'del'：上一轮问了名字，这一轮等名字

    def handle(self, text):
        text = (text or '').strip()

        # 查看通讯录
        if (re.search(r'(查看|看看|有哪些|几个|列表|都啥|都有啥)', text)
                and re.search(r'(通讯录|联系人)', text)) \
                or text in ('通讯录', '联系人', '查看联系人', '我的通讯录', '通讯录里都有谁'):
            return self._list_result()

        # 上一轮问了名字，这一轮报名字
        if self.pending == 'add':
            name = self._clean_name(text)
            if name:
                return self._add_result(name)
            return self._result('没听清名字，您再说一遍好吗？比如「小明」。', active=True)
        if self.pending == 'del':
            name = self._clean_name(text)
            if name:
                return self._remove_result(name)
            return self._result('没听清名字，您再说一遍好吗？', active=True)

        # 删除
        if re.search(r'(删掉|删除|删了|去掉|移除)', text):
            name = self._extract_name(text)
            if name:
                return self._remove_result(name)
            self.pending = 'del'
            return self._result('删哪位联系人呀？告诉我名字，比如「小明」。', active=True)

        # 新增
        if re.search(r'(存进|存到|加进|加|新增|添加|记录|存一下)', text) \
                and re.search(r'(通讯录|联系人)', text):
            name = self._extract_name(text)
            if name:
                return self._add_result(name)
            self.pending = 'add'
            return self._result('好的，存谁呀？告诉我名字，比如「小明」。', active=True)

        return self._result('您可以说「把小明存进通讯录」「查看通讯录」或「删除联系人小明」。', active=False)

    def _extract_name(self, text):
        # 去掉动作词、助词和“通讯录/联系人”，剩下的连续字符就是名字
        t = re.sub(r'(名叫|叫做|存进|存到|加进|加到|加入|新增|添加|记录|存一下|'
                   r'删掉|删除|删了|去掉|移除|通讯录|联系人|把|给|叫|的|里|中|到|入)', '', text)
        t = re.sub(r'[，。,.！!？?、\s~～]', '', t)
        m = re.search(r'[一-龥A-Za-z0-9]{1,8}', t)
        if m:
            return self._clean_name(m.group(0))
        return None

    def _clean_name(self, s):
        s = re.sub(r'[，。,.！!？?、\s~～]', '', s or '')
        s = re.sub(r'^(名叫|叫做|叫|把|给|的|存进|存到|加进|新增|添加|删除|删掉|删了|移除|去掉|联系人|通讯录)', '', s)
        s = re.sub(r'(吧|呀|啊|哦|嗯|一下|的)$', '', s)
        return s.strip()

    def _add_result(self, name):
        if not self.store.add(name):
            self.pending = None
            return self._result('「' + name + '」已经在通讯录里啦。', active=False)
        self.pending = None
        return self._result(
            '好嘞，把「' + name + '」存进通讯录了。想打视频就说「给' + name + '打视频」。',
            active=False, done=True)

    def _remove_result(self, name):
        if self.store.remove(name):
            self.pending = None
            return self._result('好的，把「' + name + '」从通讯录删掉了。', active=False)
        self.pending = None
        return self._result('通讯录里没有「' + name + '」哦，您可以说「查看通讯录」看看。', active=False)

    def _list_result(self):
        items = self.store.list()
        if not items:
            return self._result('通讯录还是空的。您可以说「把小明存进通讯录」。', active=False)
        names = '、'.join(c['name'] for c in items)
        return self._result(
            '您通讯录里有 ' + str(len(items)) + ' 位联系人：' + names + '。想打视频就说「给谁打视频」。',
            active=False)

    def _result(self, reply, active=False, done=False):
        return {'reply': reply, 'active': active, 'done': done, 'contacts': self.store.list()}
