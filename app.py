import sqlite3
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title='旅伴 Go｜毕业旅行拼团规划', page_icon='🧳', layout='wide')
DB = Path(__file__).with_name('travel_go.db')
DESTINATIONS = {
    '重庆': ['解放碑与八一好吃街', '洪崖洞夜景', '李子坝轻轨', '磁器口古镇', '长江索道', '南山观景'],
    '成都': ['宽窄巷子', '成都大熊猫繁育研究基地', '人民公园', '锦里古街', '武侯祠', '东郊记忆'],
    '大理': ['洱海生态廊道', '大理古城', '喜洲古镇', '双廊古镇', '苍山', '崇圣寺三塔'],
    '杭州': ['西湖', '灵隐寺', '西溪湿地', '河坊街', '良渚古城遗址公园', '京杭大运河'],
    '南京': ['中山陵', '夫子庙', '玄武湖', '南京博物院', '老门东', '明孝陵'],
    '厦门': ['鼓浪屿', '环岛路', '沙坡尾', '南普陀寺', '植物园', '集美学村'],
}
PREFERENCES = ['美食', '自然风光', '城市漫步', '历史文化', '拍照打卡', '休闲放松']

def connect():
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def init_db():
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, destination TEXT NOT NULL,
            start_date TEXT NOT NULL, days INTEGER NOT NULL,
            budget REAL NOT NULL, capacity INTEGER NOT NULL,
            preference TEXT NOT NULL, organizer TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            name TEXT NOT NULL, UNIQUE(trip_id, name)
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            description TEXT NOT NULL, amount REAL NOT NULL CHECK(amount > 0),
            payer TEXT NOT NULL
        );
        ''')

@st.cache_data(ttl=10)
def get_trips():
    with connect() as con:
        return [dict(x) for x in con.execute('''SELECT t.*,
          (SELECT COUNT(*) FROM members m WHERE m.trip_id=t.id) AS joined
          FROM trips t ORDER BY t.id DESC''').fetchall()]

def get_members(trip_id):
    with connect() as con:
        return [x['name'] for x in con.execute('SELECT name FROM members WHERE trip_id=? ORDER BY id', (trip_id,))]

def create_trip(title, dest, start, days, budget, capacity, preference, organizer):
    with connect() as con:
        cur = con.execute('''INSERT INTO trips(title,destination,start_date,days,budget,capacity,preference,organizer)
            VALUES(?,?,?,?,?,?,?,?)''', (title, dest, start.isoformat(), days, budget, capacity, preference, organizer))
        con.execute('INSERT INTO members(trip_id,name) VALUES(?,?)', (cur.lastrowid, organizer))
    get_trips.clear()

def join_trip(trip_id, name):
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        trip = con.execute('SELECT capacity FROM trips WHERE id=?', (trip_id,)).fetchone()
        if not trip:
            return '旅行团不存在'
        count = con.execute('SELECT COUNT(*) AS n FROM members WHERE trip_id=?', (trip_id,)).fetchone()['n']
        if count >= trip['capacity']:
            return '旅行团已满员'
        try:
            con.execute('INSERT INTO members(trip_id,name) VALUES(?,?)', (trip_id, name))
        except sqlite3.IntegrityError:
            return '该昵称已经在团内，请换一个昵称'
    get_trips.clear()
    return None

def score_trip(t, dest, earliest, latest, budget, pref):
    trip_start = date.fromisoformat(t['start_date'])
    trip_end = trip_start + timedelta(days=t['days'] - 1)
    # 目的地40分，日期重合25分，预算接近20分，偏好一致15分
    s = 40 if t['destination'] == dest else 0
    overlap = max(0, (min(trip_end, latest) - max(trip_start, earliest)).days + 1)
    s += 25 * overlap / t['days']
    s += 20 * max(0, 1 - abs(t['budget'] - budget) / max(budget, 1))
    s += 15 if t['preference'] == pref else 0
    return round(s, 1)

def plan(destination, days, pref):
    places = DESTINATIONS[destination]
    if pref == '历史文化':
        places = sorted(places, key=lambda p: any(k in p for k in ['古', '寺', '陵', '博物', '祠']), reverse=True)
    elif pref == '自然风光':
        places = sorted(places, key=lambda p: any(k in p for k in ['湖', '山', '海', '湿地', '环岛']), reverse=True)
    result = []
    for i in range(days):
        a = places[(2*i) % len(places)]
        b = places[(2*i+1) % len(places)]
        result.append({'天数': f'Day {i+1}', '上午': a, '下午': b, '晚上': '自由活动 / 当地美食'})
    return pd.DataFrame(result)

def settle(members, expenses):
    if not members:
        return [], []
    total = round(sum(float(e['amount']) for e in expenses), 2)
    share = total / len(members)
    paid = {m: 0.0 for m in members}
    for e in expenses:
        if e['payer'] in paid:
            paid[e['payer']] += float(e['amount'])
    # 整数分结算，避免浮点误差
    cents_total = round(total * 100)
    base, extra = divmod(cents_total, len(members))
    balances = {}
    for i, m in enumerate(members):
        balances[m] = round(paid[m]*100) - base - (1 if i < extra else 0)
    debtors = [[m, -v] for m, v in balances.items() if v < 0]
    creditors = [[m, v] for m, v in balances.items() if v > 0]
    transfers = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i][1], creditors[j][1])
        transfers.append({'付款人': debtors[i][0], '收款人': creditors[j][0], '金额(元)': amount/100})
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] == 0: i += 1
        if creditors[j][1] == 0: j += 1
    overview = [{'成员': m, '已垫付(元)': round(paid[m],2), '应承担(元)': (base+(1 if i < extra else 0))/100,
                 '净余额(元)': round(balances[m]/100,2)} for i,m in enumerate(members)]
    return overview, transfers

init_db()
st.title('🧳 旅伴 Go｜毕业旅行拼团规划')
st.caption('从组队到行程、从预算到AA结算，一站式规划毕业旅行。演示版不涉及真实支付或票务预订。')
page = st.sidebar.radio('功能导航', ['🏠 拼团大厅', '➕ 创建旅行团', '✨ 智能匹配', '🗺️ 行程规划', '💰 AA费用管理'])
trips = get_trips()

if page == '🏠 拼团大厅':
    c1,c2,c3 = st.columns(3)
    c1.metric('旅行团数量',len(trips))
    c2.metric('已报名人次',sum(t['joined'] for t in trips))
    c3.metric('可加入旅行团',sum(t['joined'] < t['capacity'] for t in trips))
    keyword = st.text_input('搜索目的地或团名', placeholder='例如：重庆')
    matches = [t for t in trips if keyword.strip().lower() in (t['destination']+' '+t['title']).lower()]
    if not matches: st.info('暂无符合条件的旅行团，可先创建一个！')
    for t in matches:
        with st.expander(f"{t['title']}｜{t['destination']}｜{t['joined']}/{t['capacity']}人", expanded=False):
            st.write(f"出发：{t['start_date']}　时长：{t['days']}天　参考人均预算：¥{t['budget']:.0f}　偏好：{t['preference']}")
            st.write('成员：' + '、'.join(get_members(t['id'])))
            with st.form(f"join_{t['id']}"):
                name = st.text_input('你的昵称（演示用）', key=f"name_{t['id']}")
                submitted = st.form_submit_button('加入旅行团', disabled=t['joined']>=t['capacity'])
                if submitted:
                    if not name.strip(): st.error('请输入昵称')
                    else:
                        error = join_trip(t['id'], name.strip())
                        if error: st.error(error)
                        else: st.success('报名成功！'); st.rerun()

elif page == '➕ 创建旅行团':
    with st.form('create'):
        title = st.text_input('旅行团名称', placeholder='例如：重庆毕业美食之旅')
        dest = st.selectbox('目的地', list(DESTINATIONS))
        start = st.date_input('出发日期', min_value=date.today(), value=date.today()+timedelta(days=14))
        days = st.number_input('旅行天数', 1, 15, 4)
        budget = st.number_input('参考人均预算（元）', 100, 50000, 2000, 100)
        capacity = st.number_input('人数上限', 2, 50, 6)
        pref = st.selectbox('旅行偏好', PREFERENCES)
        organizer = st.text_input('发起人昵称')
        if st.form_submit_button('发布旅行团', type='primary'):
            if not title.strip() or not organizer.strip(): st.error('请填写团名和发起人昵称')
            else:
                create_trip(title.strip(), dest, start, days, budget, capacity, pref, organizer.strip())
                st.success('旅行团创建成功！请前往拼团大厅查看。')

elif page == '✨ 智能匹配':
    st.write('匹配分数：目的地40分、日期重合25分、预算接近20分、偏好一致15分。')
    c1,c2 = st.columns(2)
    with c1:
        dest = st.selectbox('想去哪里',list(DESTINATIONS))
        earliest = st.date_input('最早出发日期',date.today())
        budget = st.number_input('期望人均预算（元）',100,50000,2000,100)
    with c2:
        latest = st.date_input('最晚旅行结束日期',date.today()+timedelta(days=30))
        pref = st.selectbox('偏好',PREFERENCES)
    if earliest > latest: st.error('最晚日期不能早于最早日期')
    else:
        available = [t for t in trips if t['joined'] < t['capacity'] and date.fromisoformat(t['start_date']) >= date.today()]
        ranked = sorted([(score_trip(t,dest,earliest,latest,budget,pref),t) for t in available],reverse=True,key=lambda x:x[0])
        if not ranked: st.info('暂无可加入的旅行团')
        for score,t in ranked[:10]:
            st.write(f"**{t['title']}**｜{t['destination']}｜匹配度 **{score}/100**｜¥{t['budget']:.0f}｜{t['start_date']}｜{t['joined']}/{t['capacity']}人")

elif page == '🗺️ 行程规划':
    c1,c2,c3 = st.columns(3)
    dest = c1.selectbox('目的地',list(DESTINATIONS))
    days = c2.slider('旅行天数',1,10,4)
    pref = c3.selectbox('偏好',PREFERENCES)
    itinerary = plan(dest,days,pref)
    st.dataframe(itinerary, use_container_width=True, hide_index=True)
    st.download_button('下载行程 CSV',itinerary.to_csv(index=False).encode('utf-8-sig'),file_name='毕业旅行行程.csv',mime='text/csv')
    st.info('行程为规则生成的参考方案，未校验景点营业时间、距离、交通及门票，请出行前自行确认。')

elif page == '💰 AA费用管理':
    if not trips: st.info('请先创建旅行团')
    else:
        selected = st.selectbox('选择旅行团', trips, format_func=lambda t:f"#{t['id']} {t['title']}")
        tid = selected['id']
        members = get_members(tid)
        with st.form('expense'):
            description = st.text_input('费用项目',placeholder='例如：酒店住宿')
            amount = st.number_input('金额（元）',min_value=0.01,value=100.0,step=1.0)
            payer = st.selectbox('垫付人',members)
            if st.form_submit_button('添加费用'):
                if not description.strip(): st.error('请输入费用项目')
                else:
                    with connect() as con:
                        con.execute('INSERT INTO expenses(trip_id,description,amount,payer) VALUES(?,?,?,?)',(tid,description.strip(),amount,payer))
                    st.success('费用已记录'); st.rerun()
        with connect() as con:
            expenses = [dict(e) for e in con.execute('SELECT * FROM expenses WHERE trip_id=? ORDER BY id DESC',(tid,))]
        st.subheader('费用明细')
        st.dataframe(pd.DataFrame(expenses)[['description','amount','payer']] if expenses else pd.DataFrame(columns=['description','amount','payer']),hide_index=True,use_container_width=True)
        st.metric('总费用',f"¥{sum(e['amount'] for e in expenses):.2f}")
        overview, transfers = settle(members,expenses)
        st.subheader('成员分摊')
        st.dataframe(pd.DataFrame(overview),hide_index=True,use_container_width=True)
        st.subheader('建议转账方案')
        if transfers: st.dataframe(pd.DataFrame(transfers),hide_index=True,use_container_width=True)
        else: st.success('目前没有待结算转账')

st.divider()
st.caption('注意：此版本使用昵称演示，无登录认证；公共部署时数据对所有访客可见，勿填写真实隐私信息。SQLite 在部分云平台可能重启丢失，不适合正式生产使用。')
