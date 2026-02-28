import os
import threading
from datetime import datetime
import requests
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fnoon_premium_key_2026")

# ==========================================
# إعدادات البيئة
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
LUCIFER_ID = int(os.getenv("LUCIFER_ID", "0"))
SECOND_ADMIN_ID = 892133353757736960 
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
ADMINS = [LUCIFER_ID, SECOND_ADMIN_ID]

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
OAUTH2_URL = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"

# قاعدة البيانات
client = MongoClient(MONGO_URI)
db = client['fnoon_studio']
orders_collection = db['orders']
portfolio_collection = db['portfolio']

# ==========================================
# البوت وأوامر السلاش (Slash Commands)
# ==========================================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f'✅ {bot.user.name} جاهز لإدارة فنون ستوديو!')

# --- أمر إضافة تصميم للمعرض مع خيارات محدودة ---
@bot.tree.command(name="add_portfolio", description="إضافة تصميم لمعرض الأعمال في الموقع")
@app_commands.describe(title="اسم التصميم", category="نوع التصميم", image="ارفع الصورة هنا")
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
        return await interaction.response.send_message("❌ لا تملك صلاحية.", ephemeral=True)
    
    if not image.content_type.startswith('image/'):
        return await interaction.response.send_message("❌ يرجى رفع صورة فقط.", ephemeral=True)

    portfolio_collection.insert_one({
        "title": title,
        "category": category.name,
        "image_url": image.url, # الرابط الأصلي بجودة ديسكورد
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    await interaction.response.send_message(f"✅ تم إضافة **{title}** إلى قسم **{category.name}** بنجاح!")

# --- أوامر السلاش لإدارة الطلبات ---
@bot.tree.command(name="accept", description="بدء العمل على طلب")
async def accept_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS: return
    orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 1}})
    await interaction.response.send_message(f"🟠 تم تحديث الطلب `#{order_id.upper()}` إلى: جاري العمل.")

@bot.tree.command(name="complete", description="تحديد الطلب كمكتمل")
async def complete_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS: return
    orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 2}})
    await interaction.response.send_message(f"🟢 تم تحديث الطلب `#{order_id.upper()}` إلى: مكتمل.")

# ==========================================
# مسارات الموقع (Flask)
# ==========================================
@app.route('/')
def home(): return render_template('index.html', user=session.get('user'))

@app.route('/login')
def login(): return redirect(OAUTH2_URL)

@app.route('/logout')
def logout(): session.pop('user', None); return redirect(url_for('home'))

@app.route('/callback')
def callback():
    code = request.args.get('code')
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    r = requests.post('https://discord.com/api/oauth2/token', data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    token = r.json().get('access_token')
    user_data = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {token}'}).json()
    session['user'] = {'id': user_data['id'], 'username': user_data['username'], 'avatar': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"}
    return redirect(url_for('home'))

@app.route('/api/portfolio')
def get_portfolio():
    items = list(portfolio_collection.find({}, {'_id': 0}).sort('_id', -1))
    return jsonify(items)

@app.route('/api/checkout', methods=['POST'])
def checkout():
    if 'user' not in session: return jsonify({"success": False})
    data = request.json
    new_order = {
        "user_id": session['user']['id'], "contact_discord_id": data.get('contact_discord_id'),
        "username": session['user']['username'], "vodafone_number": data.get('vodafone_number'),
        "package_name": data.get('package_name'), "price": data.get('price'), "status": 0, "date": datetime.now().strftime("%Y-%m-%d")
    }
    order_id = orders_collection.insert_one(new_order).inserted_id
    short_id = str(order_id)[-6:].upper()
    orders_collection.update_one({"_id": order_id}, {"$set": {"short_id": short_id}})
    return jsonify({"success": True, "order_id": short_id})

@app.route('/api/my_orders')
def my_orders():
    if 'user' not in session: return jsonify([])
    return jsonify(list(orders_collection.find({"user_id": session['user']['id']}, {'_id': 0, 'short_id': 1, 'package_name': 1, 'status': 1})))

# لوحة التحكم السرية
@app.route('/admin')
def admin():
    if 'user' not in session or int(session['user']['id']) not in ADMINS: return redirect('/')
    return render_template('admin.html')

def run_bot(): bot.run(DISCORD_TOKEN)
if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
