from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
import requests
import os
from datetime import datetime

app = Flask(__name__)

# المتغيرات السرية (هنحطها في إعدادات Render لاحقاً عشان الأمان)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# الاتصال بقاعدة البيانات (MongoDB)
try:
    client = MongoClient(MONGO_URI)
    db = client['fnoon_studio']
    orders_collection = db['orders']
except Exception as e:
    print("Database connection error:", e)

@app.route('/')
def home():
    # استدعاء الواجهة الزجاجية
    return render_template('index.html')

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    discord_user = data.get('discord_user')
    vodafone_number = data.get('vodafone_number')
    package_name = data.get('package_name')
    price = data.get('price')

    # 1. تسجيل الطلب في قاعدة البيانات (حالة 0 تعني Pending)
    new_order = {
        "discord_user": discord_user,
        "vodafone_number": vodafone_number,
        "package_name": package_name,
        "price": price,
        "status": 0, 
        "order_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        order_id = orders_collection.insert_one(new_order).inserted_id
        short_id = str(order_id)[-6:].upper() # رقم طلب مختصر للعميل
    except:
        short_id = "ERR-DB"

    # 2. إرسال إشعار فوري لـ لوسيفر على الديسكورد عبر Webhook
    if DISCORD_WEBHOOK_URL:
        discord_message = {
            "content": "🚨 **طلب تصميم جديد يا لوسيفر!** 🚨",
            "embeds": [{
                "title": "تفاصيل الطلب الجديد",
                "color": 12845619, 
                "fields": [
                    {"name": "العميل (يوزر ديسكورد)", "value": discord_user, "inline": True},
                    {"name": "رقم الكاش المحول منه", "value": vodafone_number, "inline": True},
                    {"name": "الباقة المطلوبة", "value": f"{package_name} ({price} ج.م)", "inline": False},
                    {"name": "رقم الطلب", "value": f"#{short_id}", "inline": False}
                ],
                "footer": {"text": "Fnoon Studio Order System"}
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=discord_message)

    # 3. الرد على الموقع لإظهار الإيصال
    return jsonify({
        "success": True,
        "order_id": short_id,
        "message": "تم استلام الطلب بنجاح"
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
