import os
import threading
import base64
from datetime import datetime
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

# إعدادات ديسكورد
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://fnoon.onrender.com/callback")
OAUTH2_URL = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"

# إعدادات جوجل و ImgBB
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://fnoon.onrender.com/google_callback")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

client = MongoClient(MONGO_URI)
db = client['fnoon_studio']
orders_collection = db['orders']
portfolio_collection = db['portfolio']

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f'✅ البوت {bot.user.name} جاهز ومربوط بالموقع وأوامر السلاش تعمل!')

@bot.tree.command(name="add_portfolio", description="إضافة تصميم لمعرض الأعمال في الموقع")
@app_commands.describe(title="اسم التصميم", category="نوع التصميم", image="ارفع صورة التصميم بجودتها الأصلية هنا")
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
        img_data = await image.read()
        b64_img = base64.b64encode(img_data).decode('utf-8')
        
        payload = {"key": IMGBB_API_KEY, "image": b64_img}
        res = requests.post("https://api.imgbb.com/1/upload", data=payload)
        res_data = res.json()
        
        if res.status_code == 200 and res_data.get("data"):
            permanent_url = res_data["data"]["url"]
            portfolio_collection.insert_one({
                "title": title, "category": category.name,
                "image_url": permanent_url, "date": datetime.now().strftime("%Y-%m-%d")
            })
            await interaction.followup.send(f"✅ تم رفع **{title}** لـ **{category.name}**!\nالرابط الدائم: {permanent_url}")
        else:
            await interaction.followup.send("❌ فشل الرفع لـ ImgBB. تأكد من إضافة مفتاح الـ API في Render.")
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ أثناء الرفع: {e}")

@bot.tree.command(name="accept", description="قبول طلب والبدء في العمل عليه")
async def accept_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS: return
    orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 1}})
    await interaction.response.send_message(f"✅ تم تحويل الطلب `#{order_id.upper()}` إلى جاري العمل!")

@bot.tree.command(name="complete", description="تحديد الطلب كمكتمل")
async def complete_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS: return
    orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 2}})
    await interaction.response.send_message(f"🎉 تم تحديد الطلب `#{order_id.upper()}` كـ مكتمل!")

async def send_admins_notification(user_name, phone, pkg, order_id, contact_discord_id):
    embed = discord.Embed(title="🚨 طلب تصميم جديد!", color=0xffffff) 
    embed.add_field(name="العميل", value=f"<@{contact_discord_id}> ({user_name})", inline=True)
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

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

# --- تسجيل دخول ديسكورد ---
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

# --- تسجيل دخول جوجل ---
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
        'avatar': user_data.get('picture', ''), 'provider': 'google'
    }
    return redirect(url_for('home'))

@app.route('/api/portfolio')
def get_portfolio(): return jsonify(list(portfolio_collection.find({}, {'_id': 0}).sort('_id', -1)))

@app.route('/api/checkout', methods=['POST'])
def checkout():
    if 'user' not in session: return jsonify({"success": False, "message": "سجل دخول أولاً!"})
    data = request.json
    contact_id = data.get('contact_discord_id')
    try: contact_id_int = int(contact_id)
    except ValueError: return jsonify({"success": False, "message": "أيدي الديسكورد يجب أن يحتوي على أرقام فقط!"})

    guild = bot.get_guild(GUILD_ID)
    if guild and not guild.get_member(contact_id_int):
        return jsonify({"success": False, "message": "هذا الحساب غير موجود في سيرفر فنون."})

    new_order = {
        "user_id": session['user']['id'], "contact_discord_id": contact_id, "username": session['user']['username'],
        "vodafone_number": data.get('vodafone_number'), "package_name": data.get('package_name'),
        "price": data.get('price'), "status": 0, "date": datetime.now().strftime("%Y-%m-%d")
    }
    order_id = orders_collection.insert_one(new_order).inserted_id
    short_id = str(order_id)[-6:].upper()
    orders_collection.update_one({"_id": order_id}, {"$set": {"short_id": short_id}})

    bot.loop.create_task(send_admins_notification(session['user']['username'], data.get('vodafone_number'), data.get('package_name'), short_id, contact_id))
    return jsonify({"success": True, "order_id": short_id})

@app.route('/api/my_orders')
def my_orders():
    if 'user' not in session: return jsonify([])
    return jsonify(list(orders_collection.find({"user_id": session['user']['id']}, {'_id': 0, 'short_id': 1, 'package_name': 1, 'status': 1})))

def run_bot(): bot.run(DISCORD_TOKEN)
if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
