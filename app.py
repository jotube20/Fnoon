import os
import threading
from datetime import datetime
import requests
import discord
from discord.ext import commands
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fnoon_super_secret_123")

# ==========================================
# إعدادات البيئة (Render Environment Variables)
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
LUCIFER_ID = int(os.getenv("LUCIFER_ID", "1234567890")) # الـ ID بتاعك
GUILD_ID = int(os.getenv("GUILD_ID", "1234567890")) # ID سيرفر فنون

# إعدادات تسجيل الدخول (Discord OAuth2)
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://YOUR_RENDER_URL.onrender.com/callback")
OAUTH2_URL = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"

# قاعدة البيانات
client = MongoClient(MONGO_URI)
db = client['fnoon_studio']
orders_collection = db['orders']

# ==========================================
# إعدادات ديسكورد بوت
# ==========================================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ البوت {bot.user.name} جاهز ومربوط بالموقع!')

async def send_lucifer_notification(user_name, phone, pkg, order_id):
    lucifer = await bot.fetch_user(LUCIFER_ID)
    embed = discord.Embed(title="🚨 طلب تصميم جديد!", color=0xc300ff)
    embed.add_field(name="العميل", value=user_name, inline=True)
    embed.add_field(name="رقم الكاش", value=phone, inline=True)
    embed.add_field(name="الباقة", value=pkg, inline=False)
    embed.add_field(name="رقم الإيصال", value=f"#{order_id}", inline=False)
    embed.set_footer(text="يجب التأكد من تحويل المبلغ على 01004811745")
    await lucifer.send(embed=embed)

async def create_ticket(user_id, topic):
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(int(user_id))
    if not member: return False
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    ticket_channel = await guild.create_text_channel(name=f'ticket-{member.name}', overwrites=overwrites)
    await ticket_channel.send(f"أهلاً بك {member.mention}، لوسيفر (`946m`) سيكون معك قريباً.\n**المشكلة:** {topic}")
    return True

# ==========================================
# مسارات الموقع (Web Routes)
# ==========================================

@app.route('/')
def home():
    return render_template('index.html', user=session.get('user'))

# تسجيل الدخول
@app.route('/login')
def login():
    return redirect(OAUTH2_URL)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/callback')
def callback():
    code = request.args.get('code')
    data = {
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
    token = r.json().get('access_token')
    
    user_r = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {token}'})
    user_data = user_r.json()
    
    session['user'] = {
        'id': user_data['id'],
        'username': user_data['username'],
        'avatar': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"
    }
    return redirect(url_for('home'))

# الدفع وإنشاء الطلب
@app.route('/api/checkout', methods=['POST'])
def checkout():
    if 'user' not in session:
        return jsonify({"success": False, "message": "يجب تسجيل الدخول أولاً!"})
        
    data = request.json
    new_order = {
        "user_id": session['user']['id'],
        "username": session['user']['username'],
        "vodafone_number": data.get('vodafone_number'),
        "package_name": data.get('package_name'),
        "price": data.get('price'),
        "status": 0, # 0=Pending, 1=Working, 2=Completed
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    order_id = orders_collection.insert_one(new_order).inserted_id
    short_id = str(order_id)[-6:].upper()

    bot.loop.create_task(send_lucifer_notification(session['user']['username'], data.get('vodafone_number'), data.get('package_name'), short_id))
    return jsonify({"success": True, "order_id": short_id})

# جلب طلبات العميل للـ Progress Bar
@app.route('/api/my_orders')
def my_orders():
    if 'user' not in session: return jsonify([])
    orders = list(orders_collection.find({"user_id": session['user']['id']}, {'_id': 0}))
    return jsonify(orders)

# التذاكر
@app.route('/api/support', methods=['POST'])
def support():
    if 'user' not in session: return jsonify({"success": False})
    topic = request.json.get('topic')
    bot.loop.create_task(create_ticket(session['user']['id'], topic))
    return jsonify({"success": True})

def run_bot():
    if DISCORD_TOKEN: bot.run(DISCORD_TOKEN)

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
