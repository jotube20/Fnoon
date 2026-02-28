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

# إعدادات تسجيل الدخول
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://fnoon.onrender.com/callback")
OAUTH2_URL = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"

# قاعدة البيانات
client = MongoClient(MONGO_URI)
db = client['fnoon_studio']
orders_collection = db['orders']

# ==========================================
# إعدادات البوت والـ Slash Commands
# ==========================================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    # مزامنة أوامر السلاش مع سيرفرك عشان تظهر فوراً
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f'✅ البوت {bot.user.name} جاهز ومربوط بالموقع وأوامر السلاش تعمل!')

# --- أوامر السلاش للإدارة ---
@bot.tree.command(name="accept", description="قبول طلب والبدء في العمل عليه")
@app_commands.describe(order_id="رقم الإيصال (مثال: A1B2C3)")
async def accept_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS:
        return await interaction.response.send_message("❌ ليس لديك صلاحية لاستخدام هذا الأمر.", ephemeral=True)
    
    result = orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 1}})
    if result.modified_count > 0:
        await interaction.response.send_message(f"✅ تم تحويل الطلب `#{order_id.upper()}` إلى **جاري العمل** بنجاح!")
    else:
        await interaction.response.send_message(f"⚠️ لم يتم العثور على طلب برقم `#{order_id}` أو أنه قيد العمل بالفعل.", ephemeral=True)

@bot.tree.command(name="complete", description="تحديد الطلب كمكتمل")
@app_commands.describe(order_id="رقم الإيصال (مثال: A1B2C3)")
async def complete_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS:
        return await interaction.response.send_message("❌ ليس لديك صلاحية لاستخدام هذا الأمر.", ephemeral=True)
    
    result = orders_collection.update_one({"short_id": order_id.upper()}, {"$set": {"status": 2}})
    if result.modified_count > 0:
        await interaction.response.send_message(f"🎉 تم تحديد الطلب `#{order_id.upper()}` كـ **مكتمل** بنجاح!")
    else:
        await interaction.response.send_message(f"⚠️ لم يتم العثور على طلب برقم `#{order_id}`.", ephemeral=True)

@bot.tree.command(name="delete", description="حذف طلب من النظام")
@app_commands.describe(order_id="رقم الإيصال (مثال: A1B2C3)")
async def delete_order(interaction: discord.Interaction, order_id: str):
    if interaction.user.id not in ADMINS:
        return await interaction.response.send_message("❌ ليس لديك صلاحية لاستخدام هذا الأمر.", ephemeral=True)
    
    result = orders_collection.delete_one({"short_id": order_id.upper()})
    if result.deleted_count > 0:
        await interaction.response.send_message(f"🗑️ تم حذف الطلب `#{order_id.upper()}` نهائياً.")
    else:
        await interaction.response.send_message(f"⚠️ لم يتم العثور على طلب برقم `#{order_id}`.", ephemeral=True)

# إرسال إشعار للمديرين
async def send_admins_notification(user_name, phone, pkg, order_id, contact_discord_id):
    embed = discord.Embed(title="🚨 طلب تصميم جديد!", color=0xffffff) 
    embed.add_field(name="العميل", value=f"<@{contact_discord_id}> ({user_name})", inline=True)
    embed.add_field(name="رقم الكاش", value=phone, inline=True)
    embed.add_field(name="الباقة", value=pkg, inline=False)
    embed.add_field(name="رقم الإيصال", value=f"#{order_id}", inline=False)
    embed.set_footer(text="Fnoon Studio | تحويل على 01004811745")
    
    for admin_id in ADMINS:
        try:
            admin_user = await bot.fetch_user(admin_id)
            if admin_user:
                await admin_user.send(embed=embed)
        except Exception as e:
            print(f"Could not send to admin {admin_id}: {e}")

# ==========================================
# مسارات الموقع
# ==========================================
@app.route('/')
def home():
    return render_template('index.html', user=session.get('user'))

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
    if not code: return redirect(url_for('home'))
    
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
    token = r.json().get('access_token')
    
    if not token: return redirect(url_for('home'))

    user_r = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {token}'})
    user_data = user_r.json()
    
    session['user'] = {
        'id': user_data['id'],
        'username': user_data['username'],
        'avatar': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"
    }
    return redirect(url_for('home'))

@app.route('/api/checkout', methods=['POST'])
def checkout():
    if 'user' not in session: return jsonify({"success": False, "message": "يجب تسجيل الدخول أولاً!"})
    data = request.json
    contact_id = data.get('contact_discord_id')
    
    try: contact_id_int = int(contact_id)
    except ValueError: return jsonify({"success": False, "message": "أيدي الديسكورد يجب أن يحتوي على أرقام فقط!"})

    guild = bot.get_guild(GUILD_ID)
    if guild:
        member = guild.get_member(contact_id_int)
        if not member: return jsonify({"success": False, "message": "هذا الحساب غير موجود في سيرفر فنون."})

    new_order = {
        "user_id": session['user']['id'],
        "contact_discord_id": contact_id,
        "username": session['user']['username'],
        "vodafone_number": data.get('vodafone_number'),
        "package_name": data.get('package_name'),
        "price": data.get('price'),
        "status": 0,
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    
    order_id = orders_collection.insert_one(new_order).inserted_id
    short_id = str(order_id)[-6:].upper()
    # تحديث الطلب لحفظ الرقم القصير عشان السلاش كوماند
    orders_collection.update_one({"_id": order_id}, {"$set": {"short_id": short_id}})

    bot.loop.create_task(send_admins_notification(session['user']['username'], data.get('vodafone_number'), data.get('package_name'), short_id, contact_id))
    return jsonify({"success": True, "order_id": short_id})

@app.route('/api/my_orders')
def my_orders():
    if 'user' not in session: return jsonify([])
    orders = list(orders_collection.find({"user_id": session['user']['id']}, {'_id': 0, 'short_id': 1, 'package_name': 1, 'status': 1}))
    return jsonify(orders)

# ==========================================
# 🛡️ مسارات لوحة تحكم الإدارة (السرية) 🛡️
# ==========================================
@app.route('/admin')
def admin_panel():
    if 'user' not in session or int(session['user']['id']) not in ADMINS:
        return redirect(url_for('home')) # طرد أي حد مش أدمن
    return render_template('admin.html', user=session.get('user'))

@app.route('/api/admin/orders')
def api_admin_orders():
    if 'user' not in session or int(session['user']['id']) not in ADMINS:
        return jsonify([])
    orders = list(orders_collection.find().sort('_id', -1))
    for o in orders: o['_id'] = str(o['_id'])
    return jsonify(orders)

@app.route('/api/admin/update', methods=['POST'])
def api_admin_update():
    if 'user' not in session or int(session['user']['id']) not in ADMINS:
        return jsonify({"success": False})
    
    data = request.json
    short_id = data.get('short_id')
    action = data.get('action') # 1 (جاري العمل), 2 (مكتمل), -1 (حذف)
    
    if action == -1:
        orders_collection.delete_one({"short_id": short_id})
    else:
        orders_collection.update_one({"short_id": short_id}, {"$set": {"status": int(action)}})
        
    return jsonify({"success": True})

def run_bot():
    if DISCORD_TOKEN: bot.run(DISCORD_TOKEN)

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
