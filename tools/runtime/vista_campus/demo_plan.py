"""Chinese demo storyboard tied to the actions actually dispatched and recorded."""
import math
import time
from Xlib import X, XK
from Xlib.ext import xtest

ROOMS=[
 ('entry','玄關',(1130,-240,86,90),['exit_door','shoe_bench']),
 ('living','客廳',(620,-180,86,-145),['sofa','coffee_table','television','floor_lamp']),
 ('kitchen','廚房與餐廳',(1430,-790,86,-135),['dining_table','stove','fridge']),
 ('bedroom','臥室',(470,-890,406,-150),['bed','nightstand','wardrobe_0','wardrobe_1','wardrobe_2','wardrobe_3']),
 ('office','書房',(820,-840,406,-90),['desk','rolling_chair','computer','cabinet','cabinet_right','ladder']),
 ('bathroom','浴室與洗衣間',(1248,-870,406,-90),['bathtub','toilet','basin_faucet','washer','laundry_basket']),
]

def record_rooms(r):
    def setup(target,pos,event=None):
        r.reset(event);r.fixture(target,pos)
    for chapter,title,pos,entities in ROOMS:
        def prep(p=pos):r.reset();r.pose(p,pitch=-8)
        def tour():
            r.cue('第一人稱探索室內空間');r.key('w',hold=.6);time.sleep(1.5)
            r.cue('Tab 切換第三人稱，查看人物與空間比例');r.key('Tab');time.sleep(2.4)
        r.shot(chapter+'-overview',chapter,title+'｜空間導覽',prep,tour,entities)

    doors=[
      ('exit_door','entry','玄關大門',(30,326,86,90)),
      ('living_door','entry','客廳門',(-235,205,86,-90)),
      ('kitchen_door','entry','廚房門',(95,215,86,-115)),
      ('bedroom_door','bedroom','臥室門',(-238,-204,86,-90)),
      ('office_door','office','書房門',(238,-192,86,-90)),
      ('bathroom_door','bathroom','浴室門',(20,-489,86,180)),
      ('fridge','kitchen','冰箱門',(223,148,86,-90)),
      ('cabinet','office','收納櫃左門',(220,-318,86,-25)),
      ('cabinet_right','office','收納櫃右門',(350,-318,86,-150)),
      ('bedside_drawer','bedroom','床頭抽屜',(-300,-276,86,-135)),
    ]+ [('wardrobe_'+str(i),'bedroom','衣櫃 '+str(i+1),(-488+i*60,-110,86,100)) for i in range(4)]
    for target,chapter,label,pos in doors:
        def cycle(t=target,l=label):
            initial=next(e for e in r.h.state()['entities'] if e['short_id']==t)['state']['open']
            for action in (['close','articulation.open'] if initial else ['articulation.open','close']):
                r.act('look_at',t,label='看向'+l)
                r.act(action,t,label=('打開' if action=='articulation.open' else '關上')+l)
        r.shot(target+'-cycle',chapter,label+'｜開啟與關閉',lambda t=target,p=pos:setup(t,p),cycle,[target])

    for target,chapter,label,pos in [
      ('shoe_bench','entry','換鞋凳',(72,299,86,0)),('sofa','living','沙發',(-415,130,86,-90)),
      ('bed','bedroom','床邊',(-325,-258,86,180)),('rolling_chair','office','辦公椅',(550,-200,86,180))]:
        def seated(t=target,l=label):
            r.act('sit_down',t,label='坐上'+l);r.key('Tab');time.sleep(1)
            r.act('seated_idle',t,label='維持坐姿，檢視身體與座面的接觸');time.sleep(1)
            r.act('stand_up',t,label='從'+l+'起身')
        r.shot(target+'-seat',chapter,label+'｜坐下、停留與起身',lambda t=target,p=pos:setup(t,p),seated,[target])

    for target,chapter,label,pos in [
      ('keys','living','鑰匙',(-443,243,86,-90)),('slipper','living','拖鞋',(-207,260,86,-90)),
      ('phone','bedroom','手機',(-306,-290,86,-150)),('pot','kitchen','鍋子',(380,102,86,-90))]:
        def pickup(t=target,l=label):
            r.act('inspect',t,label='檢視'+l);r.act('pick_up',t,label='伸手拿起'+l)
            time.sleep(1.2);r.act('carry',t,label='保持握持'+l)
            r.key('Tab');time.sleep(1.3);r.key('Tab')
            r.act('drop',t,label='鬆手放下'+l)
        r.shot(target+'-pickup',chapter,label+'｜拿取、握持與放手',lambda t=target,p=pos:setup(t,p),pickup,[target])

    for target,chapter,label,pos,event in [
      ('television','living','電視',(-403,305,86,90),None),
      ('floor_lamp','living','立燈',(-575,3,86,90),None),
      ('computer','office','電腦',(553,-180,86,0),None),
      ('stove','kitchen','爐具',(390,120,86,-90),'mmg_001'),
      ('faucet','bathroom','浴缸水龍頭',(-8,-604,86,-150),None),
      ('basin_faucet','bathroom','洗手台水龍頭',(66,-515,86,0),None)]:
        def toggle(t=target,l=label):
            initial=next(e for e in r.h.state()['entities'] if e['short_id']==t)['state']['active']
            for action in (['turn_off','turn_on','turn_off'] if initial else ['turn_on','turn_off']):
                r.act(action,t,label=('啟動' if action=='turn_on' else '關閉')+l);time.sleep(1)
            if t in ('television','computer','floor_lamp'):
                r.act('press_button',t,label='按下'+l+'按鈕');r.act('use',t,label='使用控制，再次切換狀態')
            if t in ('stove','faucet','basin_faucet'):
                r.act('appliance.toggle_rotary',t,label='轉動'+l+'控制旋鈕');r.act('turn_off',t,label='關閉'+l)
        r.shot(target+'-control',chapter,label+'｜控制與狀態變化',lambda t=target,p=pos,e=event:setup(t,p,e),toggle,[target])

    def cup():
        r.act('pick_up','coffee_cup',label='拿起餐桌上的杯子');time.sleep(1.5)
        r.act('place','coffee_cup',label='把杯子放回桌面')
    def cup_setup():
        setup('coffee_cup',(391,317,86,180));r.console('EmbodiedCamera -60 180')
    r.shot('cup-place','kitchen','杯子｜拿取與桌面放置',cup_setup,cup,['coffee_cup','dining_table'])

    def liquids():
        r.act('pick_up','water_jug',label='拿起水壺');time.sleep(1.3)
        r.act('look_at','coffee_cup',label='對準杯口')
        receipt=r.act('pour','water_jug','coffee_cup',label='傾斜水壺，向杯子倒水')
        r.evidence('pour_transfers_100_ml',receipt.get('transferred_ml')==100,receipt)
        r.cue('杯子到達容量上限，本次轉移 100 mL');time.sleep(2)
        r.act('spill','water_jug',label='傾倒剩餘液體，展示潑灑狀態');time.sleep(2)
    r.shot('pour-spill','kitchen','倒水與潑灑｜液體互動原型',lambda:setup('water_jug',(393,310,86,-160)),liquids,['water_jug','coffee_cup','spill_marker'])

    def gear():
        r.act('pick_up','backpack',label='拿起背包');time.sleep(1.3)
        r.act('equip','backpack',label='把背包背上肩膀');r.key('Tab');time.sleep(2.3)
        r.act('unequip','backpack',label='卸下背包，回到手持狀態')
    r.shot('backpack-gear','bedroom','背包｜拿取、穿戴與卸下',lambda:setup('backpack',(-235,-70,86,90)),gear,['backpack'])

    def ladder():
        r.act('contact.brace','ladder',label='扶住梯子扶手')
        r.act('step_up','ladder',label='踏上梯子，登上平台');r.key('Tab');time.sleep(2)
        r.act('step_down','ladder',label='逐步下梯，回到地板')
    r.shot('ladder-climb','office','梯子｜扶握、上梯與下梯',lambda:setup('ladder',(284,-224,86,-90)),ladder,['ladder'])
    def box():
        r.act('step_up','ladder',label='登上梯子接近高處物品')
        r.act('look_at','cardboard_box',label='看向高櫃上的紙箱')
        r.act('pick_up','cardboard_box',label='用雙手取下高處紙箱');r.key('Tab');time.sleep(2.5)
    r.shot('ladder-box','office','高處取物｜使用梯子與雙手拿箱',lambda:setup('ladder',(284,-224,86,-90)),box,['ladder','cardboard_box'])
    for action,pos,label in [('push',(550,-200,86,180),'向前推動辦公椅'),('pull_drag',(470,-140,86,-65),'把辦公椅拉向身前')]:
        r.shot('chair-'+action,'office','椅子｜推拉移動',lambda p=pos:setup('rolling_chair',p),
               lambda a=action,l=label:r.act(a,'rolling_chair',label=l),['rolling_chair'])
    def basket():
        r.act('articulation.open','laundry_basket',label='掀開洗衣籃')
        r.act('storage.remove','clothes','laundry_basket',label='從籃中拿出衣物')
        r.act('storage.insert','clothes','laundry_basket',label='把衣物收回洗衣籃')
        r.act('storage.remove','clothes','laundry_basket',label='再次拿出衣物')
        r.act('insert','clothes','laundry_basket',label='使用收納動作放回衣物')
        r.act('look_at','laundry_basket',label='看向籃蓋');r.act('close','laundry_basket',label='闔上洗衣籃')
    r.shot('basket-storage','bathroom','衣物｜取出與收納',lambda:setup('laundry_basket',(40,-590,86,-20)),basket,['laundry_basket','clothes'])
    def washer():
        r.act('articulation.open','washer_door',label='打開洗衣機門')
        r.act('unload','clothes','washer_door',label='取出已放入的衣物')
        r.act('load','clothes','washer_door',label='把衣物放回洗衣槽')
        r.act('look_at','washer_door',label='看向機門');r.act('close','washer_door',label='關好洗衣機門')
        r.act('look_at','washer',label='看向啟動按鈕');r.act('turn_on','washer',label='按下啟動，開始洗衣');time.sleep(2)
        r.act('turn_off','washer',label='停止洗衣機')
    r.shot('washer-load','bathroom','洗衣｜開門、取放衣物與啟停',lambda:setup('washer_door',(20,-670,86,-30),'mmg_070'),washer,['washer_door','washer','clothes'])
    r.shot('toilet-button','bathroom','馬桶｜按壓沖水控制',lambda:setup('toilet',(-80,-475,86,-135)),
           lambda:r.act('press_button','toilet',label='按下沖水按鈕'),['toilet'])


def record_body(r):
    labels={'idle':'自然站立','walk':'步行','jog':'慢跑','sprint':'快跑','turn_in_place':'原地轉身','crouch':'蹲下',
            'pause':'停下動作','stumble':'踉蹌','slip':'滑倒','fall':'跌倒','impact':'碰撞反應','recover':'恢復站姿'}
    for name,label in labels.items():
        def prep():r.reset();r.fixture('exit_door',(0,100,86,-90),third=True)
        def move(n=name,l=label):
            r.act(n,label=l+'｜動作原型展示');time.sleep(.7)
            if n in ('slip','fall','impact'):r.act('recover',label='從跌倒／受撞狀態恢復')
        r.shot('body-'+name,'body','人物動作｜'+label,prep,move)


def record_events(r):
    # Terminal conditions are observed from native receipts, never invented by captions.
    events=[('mmg_001','出門前關閉爐具','stove',(390,120,86,-90),'turn_off'),
            ('mmg_013','移走走道上的拖鞋','slipper',(-207,260,86,-90),'pick_up'),
            ('mmg_021','關閉持續放水的浴缸水龍頭','faucet',(-8,-604,86,-150),'turn_off'),
            ('mmg_040','高處取物前檢視梯子','ladder',(284,-224,86,-90),'inspect'),
            ('mmg_070','啟動已裝好衣物的洗衣機','washer',(22,-723,86,0),'turn_on')]
    for event,title,target,pos,action in events:
        def prep(e=event,t=target,p=pos):r.reset(e);r.fixture(t,p)
        def run(t=target,a=action):
            r.act(a,t,label='執行當前事件所需的操作')
            r.evidence('native_event_succeeded',r.h.state()['event_status']=='succeeded',r.h.state()['event_id'])
            r.cue('事件目標已完成｜腳本操作示例，非模型實驗結果');time.sleep(2.2)
        r.shot('event-'+event,'events','VISTA 事件｜'+title,prep,run,[target])
    for event,title,target,pos,route in [
      ('mmg_044','帶上客廳鑰匙','keys',(-443,243,86,-90),[(520,-270),(810,-270)]),
      ('mmg_045','帶上臥室手機','phone',(-306,-290,86,-150),[(450,-1030),(470,-900),(470,-740),(1260,-730),(1410,-710),(1410,-50),(1230,-50),(1230,-190)])]:
        def prep(e=event,t=target,p=pos):r.reset(e);r.fixture(t,p)
        def pickup(t=target):
            r.act('pick_up',t,label='拿起'+('鑰匙' if t=='keys' else '手機'));time.sleep(1.3)
        r.shot('event-'+event+'-pickup','events','VISTA 事件｜'+title+'：拿取物品',prep,pickup,[target])
        def route_setup(e=event,t=target,p=pos):
            current=r.h.state()
            if current['event_id']!=e or current['held_id']!=r.h.target(t):
                r.reset(e);r.fixture(t,p)
                receipt=r.h.action('pick_up',t);assert receipt['status']=='succeeded';time.sleep(1.7)
                r.current['setup_receipts']=[receipt]
            # An explicit camera cut between takes leaves item ownership and
            # world position intact, then shows the actual route at eye level.
            r.console('EmbodiedCamera -10 '+str(r.state()['camera_yaw']))
            r.current['camera_cut_only']=True
        def run(t=target,points=route):
            r.cue('攜帶物品沿實際路徑前往玄關')
            for x,y in points:walk_to(r,x,y)
            r.evidence('native_event_succeeded',r.h.state()['event_status']=='succeeded',r.h.state()['event_id'])
            r.cue('已帶著物品抵達玄關｜事件目標完成');time.sleep(2)
        r.shot('event-'+event,'events','VISTA 事件｜'+title,route_setup,run,[target])
    def wrong_prep():r.reset('mmg_001');r.fixture('exit_door',(30,326,86,90))
    def wrong():
        r.act('articulation.open','exit_door',label='示範錯誤順序：爐具未關，先開門離開')
        r.evidence('native_event_failed',r.h.state()['event_status']=='failed',r.h.state()['event_id'])
        r.cue('事件判定失敗｜可用來研究規劃順序與介入時機');time.sleep(2)
    r.shot('event-wrong-order','events','VISTA 事件｜錯誤順序的結果',wrong_prep,wrong,['exit_door'])


def walk_to(r,x,y):
    trace=[];stalled=0
    for _ in range(100):
        before=r.h.state();px,py,pz=before['player_cm'];distance=math.hypot(x-px,y-py)
        if distance<15:
            r.evidence('physical_route_'+str(x)+'_'+str(y),True,trace);return
        yaw=math.degrees(math.atan2(y-py,x-px));current=r.state()['camera_yaw']
        # Actual relative mouse events turn the view; no console/teleport while carrying.
        delta=(yaw-current+180)%360-180
        if abs(delta)>2:
            mouse_turn(r,delta)
            continue
        r.key('w',hold=min(.6,max(.07,(distance-6)/100)),settle=.1)
        after=r.h.state();assert before['held_id']==after['held_id']
        trace.append(dict(player_cm=after['player_cm'],held_id=after['held_id'],clock_s=after['clock_s']))
        stalled=stalled+1 if math.dist(before['player_cm'][:2],after['player_cm'][:2])<1 else 0
        assert stalled<4,'Physical walking route blocked'
    raise AssertionError('Walking route did not finish')


def mouse_turn(r,degrees):
    # Closed-loop mouse yaw; sensitivity is measured from the actual camera.
    scale=getattr(r,'mouse_degrees_per_pixel',.08)
    for _ in range(35):
        before=r.state()['camera_yaw']
        if abs(degrees)<1.2:return
        pixels=round(max(-80,min(80,degrees/scale)))
        r.window();xtest.fake_input(r.d,X.MotionNotify,x=pixels,y=0,detail=1);r.d.sync();time.sleep(.28)
        after=r.state()['camera_yaw'];moved=(after-before+180)%360-180
        if abs(moved)>.05 and pixels and moved/pixels>0:
            scale=moved/pixels;r.mouse_degrees_per_pixel=scale
        degrees-=moved
    assert abs(degrees)<3,'Mouse turn did not converge'


def record_campus(r):
    def select(identifier,clean=True,reload=False):
        assert not r.recording
        item=next(s for s in r.scenes if s['id']==identifier)
        r.console('HomeObserve 0')
        if r.state()['map']!=item['map'] or reload:
            r.key('Escape');index=r.scenes.index(item)
            r.click(400+(index%2)*735,312+(index//2)*145)
            r.wait(lambda s:s['map']==item['map'] and s['body_ready'] and s['menu']==0,120);time.sleep(5)
        if clean:r.console('HomeObserve 1')

    def ui_setup():select('campus',False)
    def ui():
        r.cue('Esc 開啟場景選單，滑鼠點選要探索的空間');r.key('Escape');time.sleep(3)
        r.click(400,312)
        home=next(s for s in r.scenes if s['id']=='home')
        r.wait(lambda s:s['map']==home['map'] and s['body_ready'] and s['menu']==0,120);time.sleep(3)
        r.cue('Q 顯示目前可用的動作，也可選擇房間與研究活動');r.key('q');time.sleep(4)
        r.key('Escape');r.cue('Tab 切換第一／第三人稱');r.key('Tab');time.sleep(2);r.key('Tab')
        r.cue('再開啟 Esc 選單，一鍵返回校園');r.key('Escape');r.click(1135,312)
        campus=next(s for s in r.scenes if s['id']=='campus')
        r.wait(lambda s:s['map']==campus['map'] and s['body_ready'] and s['menu']==0,120);time.sleep(3)
        r.evidence('mouse_scene_switch_home_campus',True)
    r.shot('controls-menu','controls','操作介面｜房間、活動與戶外切換',ui_setup,ui)

    for scene,name,pos,pitch,title in [
      ('campus','campus-plaza',(-400,-2200,108,-90),3,'光復校區｜廣場與步行空間'),
      ('campus','campus-brick',(-3300,-2900,108,-90),17,'校園建築｜磚牆、窗框與百葉'),
      ('campus','campus-library',(0,-6000,108,-90),20,'校園遠景｜建築與植栽配置'),
      ('gate','gate-front',(0,1650,108,90),8,'北門街區｜人行道與路口'),
      ('daxue','daxue-arcade',(-700,-950,108,-85),16,'大學路｜騎樓步行空間'),
      ('daxue','daxue-frontage',(400,950,108,90),18,'街屋立面｜冷氣格柵、欄杆與排水管')]:
        def prep(s=scene,p=pos,pi=pitch):select(s);r.pose(p,pitch=pi)
        def tour(t=title):
            r.cue(t+'（近似重建）');time.sleep(2)
            trace=r.key('d',hold=1.4,sample=True);time.sleep(2)
            r.evidence('native_moving_camera',len(trace)>5,trace)
        r.shot(name,'campus',title,prep,tour)
    def locomotion_setup():select('campus');r.pose((-400,-1800,108,-90),third=True)
    def locomotion():
        r.cue('WASD 步行，第三人稱觀察人物步態');r.key('w',hold=1.2)
        r.cue('Space 跳躍並落回地面');r.key('space');time.sleep(2)
        r.cue('按住 Shift 加快移動');r.window()
        code=r.d.keysym_to_keycode(XK.string_to_keysym('Shift_L'));xtest.fake_input(r.d,X.KeyPress,code);r.d.sync()
        try:r.key('w',hold=1.2)
        finally:xtest.fake_input(r.d,X.KeyRelease,code);r.d.sync()
        r.key('Tab');time.sleep(1)
    r.shot('campus-locomotion','campus','校園探索｜步行、快走與跳躍',locomotion_setup,locomotion)
    def portrait_setup():
        select('gate');r.pose((500,-1700,108,0),third=True)
        r.console('EmbodiedCamera -8 180');r.console('fov 48')
    def portrait():
        r.cue('人物近景：髮束、皮膚、黑色上衣與工裝細節');time.sleep(5)
    r.shot('avatar-detail','campus','人物造型｜皮膚、髮型與衣料',portrait_setup,portrait)
    if not r.a.only or 'avatar-detail' in r.a.only:r.console('fov 78')

    for kind,x,y,chapter,label in [('car_player',1250,-1380,'car','汽車'),('scooter_player',200,-1370,'scooter','機車')]:
        def prep(k=kind,px=x,py=y):
            select('gate',reload=True);r.pose((px,py,108,90),third=True)
            r.wait(lambda s:s['nearby']==k)
        def ride(k=kind,l=label):
            r.cue('E '+('開車門並坐入駕駛座' if k=='car_player' else '跨上機車並坐穩'))
            r.key('e',settle=.1);entry=[]
            while r.state()['ride_phase']!='riding':entry.append(r.state());time.sleep(.1)
            r.evidence('animated_entry',len(entry)>3,entry);time.sleep(1)
            r.cue('Tab 切換第一人稱，體驗'+('駕駛視野' if k=='car_player' else '機車騎乘視野'))
            r.key('Tab');time.sleep(3)
            r.cue('W 加速；A／D 轉向');r.key('w',hold=1.1)
            steering=r.key('d',hold=.55,sample=True);r.key('Tab');time.sleep(.3)
            r.evidence('physical_vehicle_motion',any(abs(next(v for v in s['vehicles'] if v['id']==k)['speed_cm_s'])>20 for s in steering),steering)
            r.cue('Space 煞車，等車輛完全停穩');r.key('space',hold=1.5)
            r.wait(lambda s:abs(next(v for v in s['vehicles'] if v['id']==k)['speed_cm_s'])<2)
            r.cue('E '+('打開車門並下車' if k=='car_player' else '落腳、起身並下車'));r.key('e',settle=.1)
            r.wait(lambda s:not s['riding'],12);time.sleep(1.5)
            r.evidence('animated_dismount',not r.state()['riding'])
        r.shot(chapter+'-ride',chapter,label+'｜上下車、第一人稱、行駛與煞停',prep,ride)
        def grip_setup(k=kind,px=x,py=y):
            select('gate',reload=True);r.pose((px,py,108,90));r.wait(lambda s:s['nearby']==k)
            r.key('e');r.wait(lambda s:s['ride_phase']=='riding')
            r.console('EmbodiedView 0');r.console('EmbodiedCamera -14 0');time.sleep(1)
        def grip(k=kind):
            r.cue('第一人稱近看'+('雙手握方向盤' if k=='car_player' else '雙手握住機車把手'));time.sleep(2.5)
            r.cue('轉向時手部跟隨'+('方向盤' if k=='car_player' else '車把'));r.key('w',hold=.8)
            trace=r.key('d',hold=.5,sample=True)
            r.evidence('hands_follow_steering',all(max(s['hand_l_error_cm'],s['hand_r_error_cm'])<8 for s in trace),trace)
            r.cue('煞停後安全下車');r.key('space',hold=1.5);r.key('e');r.wait(lambda s:not s['riding'],12)
        r.shot(chapter+'-grip',chapter,label+'｜第一人稱手部與轉向',grip_setup,grip)

    def road_setup():
        select('gate',reload=True);r.pose((1250,-1380,108,90),third=True)
        r.wait(lambda s:s['nearby']=='car_player')
    def road():
        r.cue('坐入駕駛座');r.key('e');r.wait(lambda s:s['ride_phase']=='riding')
        r.cue('轉向駛出停車位置，進入道路');r.window()
        steer=r.d.keysym_to_keycode(XK.string_to_keysym('d'));forward=r.d.keysym_to_keycode(XK.string_to_keysym('w'))
        xtest.fake_input(r.d,X.KeyPress,steer);xtest.fake_input(r.d,X.KeyPress,forward);r.d.sync()
        trace=[];turning=True;end=time.monotonic()+8
        try:
            while time.monotonic()<end:
                s=r.state();trace.append(s);v=next(v for v in s['vehicles'] if v['id']=='car_player')
                if turning and v['yaw']>=80:
                    xtest.fake_input(r.d,X.KeyRelease,steer);r.d.sync();turning=False
                if v['position_cm'][1]>-450:break
                time.sleep(.1)
        finally:
            xtest.fake_input(r.d,X.KeyRelease,steer);xtest.fake_input(r.d,X.KeyRelease,forward);r.d.sync()
        r.evidence('drives_onto_road',next(v for v in r.state()['vehicles'] if v['id']=='car_player')['position_cm'][1]>-500,trace)
        r.cue('Space 煞停；S 倒車調整位置');r.key('space',hold=1.3);reverse=r.key('s',hold=.7,sample=True);r.key('space',hold=1.3)
        r.evidence('reverses_with_input',any(next(v for v in s['vehicles'] if v['id']=='car_player')['speed_cm_s']< -10 for s in reverse),reverse)
        r.cue('停穩後下車');r.key('e');r.wait(lambda s:not s['riding'],12)
    r.shot('car-road','car','汽車上路｜駛出停車位與倒車',road_setup,road)
    def obstacle():
        r.cue('車輛接觸前方障礙物時停止前進');r.key('e');r.wait(lambda s:s['ride_phase']=='riding')
        trace=r.key('w',hold=4.2,sample=True);v=next(v for v in r.state()['vehicles'] if v['id']=='car_player')
        r.evidence('obstacle_stops_vehicle',v['contacts']>0 and abs(v['speed_cm_s'])<2,trace)
        time.sleep(2);r.key('e');r.wait(lambda s:not s['riding'],12)
    r.shot('car-obstacle','car','車輛碰撞｜障礙物接觸與停止',road_setup,obstacle)

    def traffic_setup():select('gate',reload=True);r.pose((0,-780,108,90),pitch=-3)
    def traffic():
        r.cue('行人先在人行道等候，觀察車流與號誌');before=r.state();trace=[]
        end=time.monotonic()+12
        while time.monotonic()<end:trace.append(r.state());time.sleep(.1)
        moving=any(math.dist(trace[0]['vehicles'][i]['position_cm'],trace[-1]['vehicles'][i]['position_cm'])>100 for i in range(len(trace[0]['vehicles'])) if trace[0]['vehicles'][i]['traffic'])
        r.evidence('ambient_traffic_moves',moving,trace)
    r.shot('traffic-wait','crossing','路口｜號誌與持續行駛的車流',traffic_setup,traffic)
    def cross_setup():
        select('gate',reload=True);r.pose((0,-780,108,90),pitch=-3)
        r.wait(lambda s:14.8<=s['clock_s']%32<15.5,40)
    def cross():
        r.cue('等待行人綠燈');r.wait(lambda s:18.05<=s['clock_s']%32<18.8,40)
        before=r.state();r.cue('綠燈亮起，沿斑馬線走到對面');trace=r.key('w',hold=9.3,sample=True,settle=.5)
        after=r.state();r.evidence('completed_green_crossing',after['crossings']==before['crossings']+1 and after['red_entries']==before['red_entries'],trace)
        r.cue('已抵達對側人行道，完成一次綠燈通行');r.key('Tab');time.sleep(2)
    r.shot('crossing-green','crossing','行人過馬路｜等待、通行與抵達',cross_setup,cross)

    def guard_setup():
        select('gate',False,reload=True);r.pose((1250,-1380,108,90),third=True);r.wait(lambda s:s['nearby']=='car_player')
    def guards():
        r.cue('上車後啟動車輛');r.key('e');r.wait(lambda s:s['ride_phase']=='riding');r.key('w',hold=1.1)
        r.cue('行進時按 E：系統要求先煞停');r.key('e');r.evidence('moving_exit_rejected',r.state()['riding']=='car_player');time.sleep(1)
        r.cue('Q 開啟操作選單，車輛自動煞停');r.key('q');r.wait(lambda s:abs(next(v for v in s['vehicles'] if v['id']=='car_player')['speed_cm_s'])<2)
        time.sleep(2);r.key('Escape');r.evidence('menu_brakes_vehicle',True)
    r.shot('car-safety','car','操作保護｜行進中禁止下車、選單煞停',guard_setup,guards)
