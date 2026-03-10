import os
import threading
import base64
from datetime import datetime, timedelta
import requests
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fnoon_super_secret_123")

# ==========================================
# إعدادات البيئة
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
LUCIFER_ID = int(os.getenv("LUCIFER_ID", "1234567890"))
SECOND_ADMIN_ID = 892133353757736960 
GUILD_ID = int(os.getenv("GUILD_ID", "1234567890"))
ADMINS = [LUCIFER_ID, SECOND_ADMIN_ID]

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://fnoon.onrender.com/callback")
OAUTH2_URL = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://fnoon.onrender.com/google_callback")

# تنظيف المفتاح من أي مسافات أو علامات تنصيص بالغلط من ريندر
raw_imgbb = os.getenv("IMGBB_API_KEY", "")
IMGBB_API_KEY = raw_imgbb.replace('"', '').replace("'", "").strip()

INSTAGRAM_CLIENT_ID = os.getenv("INSTAGRAM_CLIENT_ID")
INSTAGRAM_CLIENT_SECRET = os.getenv("INSTAGRAM_CLIENT_SECRET")
INSTAGRAM_REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI", "https://fnoon.onrender.com/instagram_callback")

client = MongoClient(MONGO_URI)
db = client['fnoon_studio']
orders_collection = db['orders']
portfolio_collection = db['portfolio']
messages_collection = db['messages'] 

def is_admin():
    if 'user' not in session: return False
    return int(session['user']['id']) in ADMINS

def get_egypt_time():
    return datetime.utcnow() + timedelta(hours=2)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f'✅ البوت {bot.user.name} جاهز ومربوط بالموقع!')

@bot.tree.command(name="add_portfolio", description="إضافة تصميم لمعرض الأعمال")
@app_commands.describe(title="اسم التصميم", category="نوع التصميم", image="ارفع الصورة")
@app_commands.choices(category=[
    app_commands.Choice(name="سيرفرات ديسكورد", value="ديسكورد"),
    app_commands.Choice(name="بوسترات", value="بوسترات"),
    app_commands.Choice(name="خلفيات", value="خلفيات"),
    app_commands.Choice(name="شعارات", value="شعارات"),
    app_commands.Choice(name="صور مصغرة (Thumbnail)", value="صور مصغره"),
    app_commands.Choice(name="سوشيال ميديا", value="سوشيال ميديا")
])
async def add_portfolio(interaction: discord.Interaction, title: str, category: app_commands.Choice[str], image: discord.Attachment):
    if interaction.user.id not in ADMINS:
        return await interaction.response.send_message("❌ ليس لديك صلاحية.", ephemeral=True)
    if not image.content_type or not image.content_type.startswith('image/'):
        return await interaction.response.send_message("❌ يرجى إرفاق صورة صالحة.", ephemeral=True)

    await interaction.response.defer(ephemeral=False)
    try:
        if not IMGBB_API_KEY:
            return await interaction.followup.send("❌ مفتاح ImgBB غير مضاف في السيرفر!")
        
        img_data = await image.read()
        b64_img = base64.b64encode(img_data).decode('utf-8')
        
        # إرسال المفتاح في الرابط لضمان القبول
        res = requests.post(f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}", data={"image": b64_img})
        res_data = res.json()
        if res.status_code == 200 and res_data.get("data"):
            portfolio_collection.insert_one({"title": title, "category": category.name, "image_url": res_data["data"]["url"], "date": get_egypt_time().strftime("%Y-%m-%d")})
            await interaction.followup.send(f"✅ تم رفع **{title}**!\nالرابط: {res_data['data']['url']}")
        else: 
            await interaction.followup.send(f"❌ فشل الرفع. السبب: {res_data.get('error', {}).get('message', 'مجهول')}")
    except Exception as e: await interaction.followup.send(f"❌ حدث خطأ: {e}")

@bot.tree.command(name="accept", description="قبول طلب والبدء في العمل عليه")
async def accept_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS: return
    orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 1}})
    await interaction.response.send_message(f"✅ تم تحويل الطلب `#{order_id.upper()}` إلى جاري العمل!")

@bot.tree.command(name="complete", description="تحديد الطلب كمكتمل وبدء عداد إغلاق الشات")
async def complete_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS: return
    completed_time = get_egypt_time().strftime("%Y-%m-%d %H:%M:%S")
    orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 2, "completed_at": completed_time}})
    await interaction.response.send_message(f"🎉 تم تحديد الطلب `#{order_id.upper()}` كـ مكتمل، وسيتم إغلاق الشات تلقائياً بعد 24 ساعة!")

@bot.tree.command(name="delete_order", description="حذف طلب من قاعدة البيانات نهائياً")
async def delete_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS: return
    result = orders_collection.delete_one({"short_id": order_id.upper()})
    if result.deleted_count > 0:
        messages_collection.delete_many({"order_id": order_id.upper()})
        await interaction.response.send_message(f"🗑️ تم حذف الطلب `#{order_id.upper()}` ورسائله نهائياً!")
    else:
        await interaction.response.send_message(f"❌ لم يتم العثور على الطلب `#{order_id.upper()}`.")

async def send_admins_notification(user_name, phone, pkg, order_id, contact_id, contact_method):
    embed = discord.Embed(title="🚨 طلب تصميم جديد!", color=0xffffff) 
    if contact_method == 'instagram': contact_info = f"انستجرام: {contact_id} ({user_name})"
    elif contact_method == 'gmail': contact_info = f"جيميل: {contact_id} ({user_name})"
    else: contact_info = f"<@{contact_id}> ({user_name})"

    embed.add_field(name="العميل (للتواصل)", value=contact_info, inline=False)
    embed.add_field(name="رقم الكاش", value=phone, inline=True)
    embed.add_field(name="الباقة", value=pkg, inline=False)
    embed.add_field(name="رقم الإيصال", value=f"#{order_id}", inline=False)
    for admin_id in ADMINS:
        try:
            admin_user = await bot.fetch_user(admin_id)
            if admin_user: await admin_user.send(embed=embed)
        except Exception: pass

# ==========================================
# مسارات الموقع
# ==========================================
@app.route('/')
def home(): return render_template('index.html', user=session.get('user'))

@app.route('/admin_chat')
def admin_chat():
    if not is_admin(): return redirect(url_for('home'))
    orders = list(orders_collection.find().sort('_id', -1))
    return render_template('admin_chat.html', user=session['user'], orders=orders)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/login/discord')
def login_discord(): return redirect(OAUTH2_URL)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return redirect(url_for('home'))
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    r = requests.post('https://discord.com/api/oauth2/token', data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    token = r.json().get('access_token')
    if not token: return redirect(url_for('home'))
    user_data = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {token}'}).json()
    session['user'] = {
        'id': user_data['id'], 'username': user_data['username'],
        'avatar': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png", 'provider': 'discord'
    }
    return redirect(url_for('home'))

@app.route('/login/google')
def login_google():
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&response_type=code&scope=openid%20email%20profile"
    return redirect(auth_url)

@app.route('/google_callback')
def google_callback():
    code = request.args.get('code')
    if not code: return redirect(url_for('home'))
    token_url = "https://oauth2.googleapis.com/token"
    data = { "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "code": code, "grant_type": "authorization_code", "redirect_uri": GOOGLE_REDIRECT_URI }
    r = requests.post(token_url, data=data)
    access_token = r.json().get("access_token")
    if not access_token: return redirect(url_for('home'))
    user_data = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"}).json()
    session['user'] = {
        'id': user_data['id'], 'username': user_data.get('name', 'Google User'),
        'email': user_data.get('email', ''), 'avatar': user_data.get('picture', ''), 'provider': 'google'
    }
    return redirect(url_for('home'))

@app.route('/login/instagram')
def login_instagram():
    auth_url = f"https://api.instagram.com/oauth/authorize?client_id={INSTAGRAM_CLIENT_ID}&redirect_uri={INSTAGRAM_REDIRECT_URI}&scope=user_profile&response_type=code"
    return redirect(auth_url)

@app.route('/instagram_callback')
def instagram_callback():
    code = request.args.get('code')
    if not code: return redirect(url_for('home'))
    token_url = "https://api.instagram.com/oauth/access_token"
    data = { "client_id": INSTAGRAM_CLIENT_ID, "client_secret": INSTAGRAM_CLIENT_SECRET, "grant_type": "authorization_code", "redirect_uri": INSTAGRAM_REDIRECT_URI, "code": code }
    r = requests.post(token_url, data=data)
    res_data = r.json()
    access_token = res_data.get("access_token")
    user_id = res_data.get("user_id")
    if not access_token: return redirect(url_for('home'))
    
    user_info_url = f"https://graph.instagram.com/{user_id}?fields=id,username&access_token={access_token}"
    user_info = requests.get(user_info_url).json()
    session['user'] = {
        'id': user_info.get('id'), 'username': user_info.get('username', 'Instagram User'),
        'avatar': 'https://upload.wikimedia.org/wikipedia/commons/e/e7/Instagram_logo_2016.svg', 'provider': 'instagram'
    }
    return redirect(url_for('home'))

# ==========================================
# APIs الشات والطلبات
# ==========================================

@app.route('/api/chat/<order_id>', methods=['GET'])
def get_chat(order_id):
    if 'user' not in session: return jsonify([])
    order = orders_collection.find_one({"short_id": order_id})
    if not order: return jsonify([])
    
    if order['user_id'] != session['user']['id'] and not is_admin(): 
        return jsonify([])
    
    messages = list(messages_collection.find({"order_id": order_id}, {'_id': 0}).sort('raw_time', 1))
    
    chat_closed = False
    if order.get('status') == 2 and order.get('completed_at'):
        completed_at = datetime.strptime(order['completed_at'], "%Y-%m-%d %H:%M:%S")
        if (get_egypt_time() - completed_at).total_seconds() > 86400:
            chat_closed = True

    return jsonify({
        "messages": messages, 
        "chat_closed": chat_closed,
        "status": order.get('status'),
        "contact_id": order.get('contact_discord_id'),
        "contact_method": order.get('contact_method')
    })

@app.route('/api/chat/<order_id>', methods=['POST'])
def send_message(order_id):
    if 'user' not in session: return jsonify({"success": False, "message": "غير مصرح لك"})
    order = orders_collection.find_one({"short_id": order_id})
    if not order: return jsonify({"success": False, "message": "الطلب غير موجود"})
    
    is_adm = is_admin()
    if order['user_id'] != session['user']['id'] and not is_adm: 
        return jsonify({"success": False, "message": "غير مصرح لك"})
    
    if order.get('status') == 2 and order.get('completed_at'):
        completed_at = datetime.strptime(order['completed_at'], "%Y-%m-%d %H:%M:%S")
        if (get_egypt_time() - completed_at).total_seconds() > 86400:
            return jsonify({"success": False, "message": "تم إغلاق المحادثة لانتهاء الطلب."})

    data = request.json
    text = data.get('text', '').strip()
    image_base64 = data.get('image_base64', '') 
    image_url = ""

    if image_base64:
        if not IMGBB_API_KEY:
            return jsonify({"success": False, "message": "عذراً، لم يتم إعداد مفتاح الصور في السيرفر."})
        try:
            # إرسال المفتاح في الرابط لضمان القبول
            res = requests.post(f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}", data={"image": image_base64})
            res_data = res.json()
            if res.status_code == 200 and res_data.get("data"):
                image_url = res_data["data"]["url"]
            else:
                error_msg = res_data.get("error", {}).get("message", "خطأ غير معروف")
                return jsonify({"success": False, "message": f"رفض ImgBB الصورة: {error_msg}"})
        except Exception as e:
            return jsonify({"success": False, "message": "حدث خطأ أثناء الاتصال بسيرفر الصور."})
    
    if not text and not image_url: return jsonify({"success": False})

    egypt_time = get_egypt_time()
    msg = {
        "order_id": order_id,
        "sender_id": session['user']['id'],
        "sender_name": session['user']['username'],
        "is_admin": is_adm,
        "text": text,
        "image_url": image_url,
        "time_display": egypt_time.strftime("%I:%M %p"), 
        "raw_time": egypt_time.strftime("%Y-%m-%d %H:%M:%S")
    }
    messages_collection.insert_one(msg)
    return jsonify({"success": True})

@app.route('/api/portfolio')
def get_portfolio(): return jsonify(list(portfolio_collection.find({}, {'_id': 0}).sort('_id', -1)))

@app.route('/api/checkout', methods=['POST'])
def checkout():
    if 'user' not in session: return jsonify({"success": False, "message": "سجل دخول أولاً!"})
    
    active_order = orders_collection.find_one({"user_id": session['user']['id'], "status": {"$in": [0, 1]}})
    if active_order: return jsonify({"success": False, "message": "عذراً، لديك طلب قيد التنفيذ بالفعل! يرجى الانتظار حتى يكتمل."})

    data = request.json
    contact_id = data.get('contact_discord_id')
    contact_method = data.get('contact_method', 'discord')
    
    if contact_method == 'discord':
        try: contact_id_int = int(contact_id)
        except ValueError: return jsonify({"success": False, "message": "أيدي الديسكورد يجب أن يحتوي على أرقام فقط!"})
        guild = bot.get_guild(GUILD_ID)
        if guild and not guild.get_member(contact_id_int):
            return jsonify({"success": False, "message": "هذا الحساب غير موجود في سيرفر فنون."})

    new_order = {
        "user_id": session['user']['id'], "contact_discord_id": contact_id, "contact_method": contact_method,
        "username": session['user']['username'], "vodafone_number": data.get('vodafone_number'), 
        "package_name": data.get('package_name'), "price": data.get('price'), 
        "status": 0, "date": get_egypt_time().strftime("%Y-%m-%d")
    }
    order_id = orders_collection.insert_one(new_order).inserted_id
    short_id = str(order_id)[-6:].upper()
    orders_collection.update_one({"_id": order_id}, {"$set": {"short_id": short_id}})

    bot.loop.create_task(send_admins_notification(session['user']['username'], data.get('vodafone_number'), data.get('package_name'), short_id, contact_id, contact_method))
    return jsonify({"success": True, "order_id": short_id})

@app.route('/api/my_orders')
def my_orders():
    if 'user' not in session: return jsonify([])
    return jsonify(list(orders_collection.find({"user_id": session['user']['id']}, {'_id': 0, 'short_id': 1, 'package_name': 1, 'status': 1})))

def run_bot(): bot.run(DISCORD_TOKEN)
if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
