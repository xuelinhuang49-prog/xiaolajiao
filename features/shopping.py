# -*- coding: utf-8 -*-
"""购物业务：商品/数量解析 + 下单确认状态机。

“我想买东西”若没识别出具体商品，会先追问“买什么”，而不是把“东西”当商品名。
状态机：ask_item → ask_quantity → confirm → done / cancelled。
"""
import re

from features.task_manager import (
    ASK_ITEM, ASK_QUANTITY, CONFIRM, DONE, CANCELLED,
    is_affirm, is_negate,
)

# 商品价目（演示用模拟价，单位：元）
PRICE = {
    '鸡蛋': '12', '大米': '30', '米': '30', '面': '15', '油': '45',
    '降压药': '28', '药': '28', '菜': '15', '水果': '20', '牛奶': '35',
    '盐': '3', '酱油': '8', '醋': '6', '糖': '8', '肉': '25',
    '猪肉': '30', '牛肉': '45', '鸡肉': '25', '鱼': '28', '虾': '40',
    '苹果': '10', '香蕉': '8', '橘子': '8', '梨': '8', '葡萄': '15',
    '西瓜': '12', '白菜': '6', '萝卜': '5', '土豆': '6', '西红柿': '8',
    '黄瓜': '8', '茄子': '8', '豆腐': '8', '面包': '15', '饼干': '12',
    '酸奶': '20', '纸巾': '18', '洗衣粉': '15', '肥皂': '8', '牙膏': '15',
    '感冒药': '22',
}

# 泛指词：只出现这些说明老人还没说出具体要买什么
_GENERIC_ITEMS = {'东西', '这个', '那个', '啥', '什么', '吃的', '用的', '一点', '点儿', '点'}

_QUANTITY_RE = re.compile(
    r'([零一二两三四五六七八九十百几]|\d+)\s*'
    r'(斤|公斤|千克|克|两|盒|包|瓶|袋|箱|个|份|双|只|条|桶|提|打|件)')


def price_of(item):
    p = PRICE.get(item)
    return ('约 ' + p + ' 元') if p else '价格待确认'


def extract_item(text):
    """从话里提取商品名。

    返回：
      - 具体商品名（在价目表内）
      - ''    泛指词/空串（“东西”“这个”等，老人还没说出具体要买什么）
      - None  识别出了字面词但不在价目表里（疑似误识别，如“期待”），按“没听懂”处理
    """
    item = (text or '')
    item = re.sub(r'(帮我|给我|我要|我想|想|要|麻烦|请|您)', '', item)
    item = re.sub(r'(买点|买些|来点|来些|买|下单|订购)', '', item)
    item = _QUANTITY_RE.sub('', item)
    item = re.sub(r'[，。,.！!？?、\s~～]', '', item)
    if item in _GENERIC_ITEMS:
        return ''
    if item and item not in PRICE:
        return None
    return item


def extract_quantity(text):
    m = _QUANTITY_RE.search(text or '')
    return m.group(0) if m else ''


class ShoppingTask:
    """一次购物会话的状态机。"""

    def __init__(self):
        self.stage = ASK_ITEM
        self.item = ''
        self.quantity = ''

    def handle(self, text):
        text = (text or '').strip()

        # 任意阶段都可以取消
        if is_negate(text):
            self.stage = CANCELLED
            return self._result('好的，那不买了，需要时再叫我。')

        if self.stage == ASK_ITEM:
            item = extract_item(text)
            qty = extract_quantity(text)
            if item:
                self.item = item
                self.quantity = qty
                if qty:
                    self.stage = CONFIRM
                    return self._confirm()
                self.stage = ASK_QUANTITY
                return self._result('您想买多少' + item + '？')
            # 没识别到商品 → 继续追问，绝不把“东西”/误识别词当商品
            if item is None:
                # 听成了不在价目表里的乱词（如“期待”）→ 反问澄清，不把错词带入回复
                return self._result('奶奶，我没听懂，您是要买什么东西呀？比如苹果、鸡蛋、降压药都行。')
            return self._result('您想买点什么呀？比如苹果、鸡蛋、降压药都行。')

        if self.stage == ASK_QUANTITY:
            item = extract_item(text)
            if item and item != self.item:
                self.item = item          # 老人这句可能又说了新商品
            qty = extract_quantity(text)
            if qty:
                self.quantity = qty
                self.stage = CONFIRM
                return self._confirm()
            return self._result('您想买多少' + self.item + '？比如两斤、一盒都行。')

        if self.stage == CONFIRM:
            if is_affirm(text):
                self.stage = DONE
                return self._result(
                    '已为您模拟下单：' + self.item + ' × ' + self.quantity
                    + '。这是演示环境，未接入真实支付，订单仅作记录。',
                    show=True, buttons='none',
                    status='✅ 模拟下单成功（演示，未接真实支付）', done=True)
            # 没听清是/否，再确认一次
            return self._confirm()

        # 已结束的会话收到新话 → 视为一次新的购买意图
        item = extract_item(text)
        qty = extract_quantity(text)
        self.item = item
        self.quantity = qty
        if not item:
            self.stage = ASK_ITEM
            return self._result('您想买点什么呀？比如苹果、鸡蛋、降压药都行。')
        if not qty:
            self.stage = ASK_QUANTITY
            return self._result('您想买多少' + item + '？')
        self.stage = CONFIRM
        return self._confirm()

    def _confirm(self):
        status = price_of(self.item) + ' · 请确认订单'
        reply = self.item + ' × ' + self.quantity + '，' + price_of(self.item) + '，确认下单吗？'
        return self._result(reply, show=True, buttons='confirm_cancel', status=status)

    def _result(self, reply, show=False, buttons='none', status='', done=False):
        active = self.stage not in (DONE, CANCELLED)
        ui = {
            'show': show,
            'item': self.item,
            'quantity': self.quantity,
            'price': price_of(self.item) if self.item else '',
            'status': status or reply,
            'buttons': buttons,
        }
        return {'reply': reply, 'ui': ui, 'stage': self.stage, 'active': active, 'done': done}
