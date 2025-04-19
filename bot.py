import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)
import sqlite3
import datetime
import pandas as pd
import os
from flask import Flask
import threading

# تعريف حالات المحادثة
(
    MAIN_MENU,
    ADD_PRODUCT,
    ADD_DAMAGED,
    ENTER_BARCODE,
    ENTER_PRODUCT_DETAILS,
    ENTER_DAMAGE_DETAILS,
    ENTER_PRODUCT_NAME
) = range(7)

# إعداد Flask لربط المنفذ (مطلوب لـ Render)
app = Flask(__name__)
@app.route('/')
def home():
    return "البوت شغال على Render 🚀"

@app.route('/')
def health_check():
    return "Bot is running!", 200

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# لوحة مفاتيح الرجوع
BACK_KEYBOARD = ReplyKeyboardMarkup([["🔙 رجوع", "🏠 القائمة الرئيسية"]], resize_keyboard=True)

def init_db():
    """تهيئة قاعدة البيانات"""
    conn = None
    try:
        conn = sqlite3.connect('inventory.db')
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS products
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      barcode TEXT UNIQUE,
                      name TEXT,
                      expiry_date TEXT,
                      quantity INTEGER,
                      added_date TEXT,
                      user_id INTEGER)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS damaged_products
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      barcode TEXT,
                      name TEXT,
                      quantity INTEGER,
                      damage_reason TEXT,
                      report_date TEXT,
                      user_id INTEGER)''')
        
        conn.commit()
    except Exception as e:
        logger.error(f"خطأ في تهيئة قاعدة البيانات: {e}")
        raise
    finally:
        if conn:
            conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء المحادثة وإعادة التعيين"""
    context.user_data.clear()
    
    keyboard = [
        ["➕ إضافة صنف جديد", "🗑️ إضافة صنف تالف"],
        ["📋 عرض الأصناف", "📦 عرض التالف"],
        ["📤 تصدير البيانات"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🏪 مرحباً بك في نظام إدارة المخزون\n\nاختر الإجراء المطلوب:",
        reply_markup=reply_markup
    )
    return MAIN_MENU

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة القائمة الرئيسية"""
    text = update.message.text
    
    if text == "🏠 القائمة الرئيسية":
        return await start(update, context)
        
    if text == "➕ إضافة صنف جديد":
        context.user_data.clear()
        context.user_data['is_damaged'] = False
        await update.message.reply_text(
            "📦 الرجاء إدخال الباركود (أرقام فقط):",
            reply_markup=BACK_KEYBOARD
        )
        return ENTER_BARCODE
        
    elif text == "🗑️ إضافة صنف تالف":
        context.user_data.clear()
        context.user_data['is_damaged'] = True
        await update.message.reply_text(
            "🗑️ الرجاء إدخال الباركود للصنف التالف:",
            reply_markup=BACK_KEYBOARD
        )
        return ADD_DAMAGED
        
    elif text == "📋 عرض الأصناف":
        return await view_products(update, context)
        
    elif text == "📦 عرض التالف":
        return await view_damaged_products(update, context)
        
    elif text == "📤 تصدير البيانات":
        return await export_data(update, context)
        
    elif text == "🔙 رجوع":
        return await start(update, context)

async def handle_barcode_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال الباركود"""
    text = update.message.text.strip()
    is_damaged = context.user_data.get('is_damaged', False)
    
    logger.info(f"handle_barcode_input - user_data: {context.user_data}")
    
    if text in ["🔙 رجوع", "🏠 القائمة الرئيسية"]:
        await start(update, context)
        return MAIN_MENU
    
    if not text.isdigit():
        await update.message.reply_text("❌ الباركود يجب أن يحتوي على أرقام فقط!", reply_markup=BACK_KEYBOARD)
        return ADD_DAMAGED if is_damaged else ENTER_BARCODE
    
    context.user_data['barcode'] = text
    
    if is_damaged:
        try:
            conn = sqlite3.connect('inventory.db')
            c = conn.cursor()
            c.execute("SELECT name, quantity FROM products WHERE barcode=?", (text,))
            product = c.fetchone()
            
            if product:
                context.user_data['product_name'] = product[0]
                context.user_data['current_quantity'] = product[1]  # حفظ الكمية الحالية للمنتج
                
                keyboard = [
                    ["1", "2", "5"],
                    ["10", "20", "50"],
                    ["إدخال كمية أخرى", "🔙 رجوع"]
                ]
                await update.message.reply_text(
                    f"🧮 اختر كمية التالف (الكمية المتاحة: {product[1]}):",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                return ENTER_DAMAGE_DETAILS
            else:
                await update.message.reply_text(
                    "📝 هذا الباركود غير مسجل. الرجاء إدخال اسم الصنف التالف:",
                    reply_markup=BACK_KEYBOARD
                )
                return ENTER_PRODUCT_NAME
        except Exception as e:
            logger.error(f"Error checking product: {e}")
            await update.message.reply_text(
                "❌ حدث خطأ أثناء التحقق من المنتج!",
                reply_markup=BACK_KEYBOARD
            )
            return ADD_DAMAGED
        finally:
            conn.close()
    else:
        keyboard = [
            ["اليوم", "غداً"],
            ["أسبوع", "شهر"],
            ["إدخال تاريخ يدوياً", "🔙 رجوع"]
        ]
        await update.message.reply_text(
            "📅 اختر تاريخ الانتهاء:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return ENTER_PRODUCT_DETAILS

async def handle_expiry_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال تاريخ الانتهاء"""
    text = update.message.text
    
    logger.info(f"handle_expiry_date - user_data: {context.user_data}")
    
    if text == "🔙 رجوع":
        await update.message.reply_text(
            "📦 الرجاء إدخال الباركود (أرقام فقط):",
            reply_markup=BACK_KEYBOARD
        )
        return ENTER_BARCODE
    
    if text == "🏠 القائمة الرئيسية":
        await start(update, context)
        return MAIN_MENU
    
    if text in ["اليوم", "غداً", "أسبوع", "شهر"]:
        date_map = {
            "اليوم": 0,
            "غداً": 1,
            "أسبوع": 7,
            "شهر": 30
        }
        expiry_date = (datetime.datetime.now() + datetime.timedelta(days=date_map[text])).strftime("%Y-%m-%d")
        context.user_data['expiry_date'] = expiry_date
    elif text == "إدخال تاريخ يدوياً":
        await update.message.reply_text(
            "📅 الرجاء إدخال تاريخ الانتهاء (YYYY-MM-DD):",
            reply_markup=BACK_KEYBOARD
        )
        return ENTER_PRODUCT_DETAILS
    else:
        try:
            datetime.datetime.strptime(text, "%Y-%m-%d")
            context.user_data['expiry_date'] = text
        except ValueError:
            await update.message.reply_text("❌ تنسيق التاريخ غير صحيح! استخدم YYYY-MM-DD", reply_markup=BACK_KEYBOARD)
            return ENTER_PRODUCT_DETAILS
    
    keyboard = [
        ["1", "5", "10"],
        ["20", "50", "100"],
        ["إدخال كمية أخرى", "🔙 رجوع"]
    ]
    await update.message.reply_text(
        "🧮 اختر الكمية:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ENTER_PRODUCT_DETAILS

async def handle_quantity_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال الكمية مع تحسينات للأصناف التالفة"""
    text = update.message.text
    is_damaged = context.user_data.get('is_damaged', False)
    
    logger.info(f"handle_quantity_input - user_data: {context.user_data}")
    
    if text == "🔙 رجوع":
        if is_damaged:
            if 'product_name' in context.user_data:
                await update.message.reply_text(
                    "🗑️ الرجاء إدخال الباركود للصنف التالف:",
                    reply_markup=BACK_KEYBOARD
                )
                return ADD_DAMAGED
            else:
                await update.message.reply_text(
                    "📝 الرجاء إدخال اسم الصنف التالف:",
                    reply_markup=BACK_KEYBOARD
                )
                return ENTER_PRODUCT_NAME
        else:
            keyboard = [
                ["اليوم", "غداً"],
                ["أسبوع", "شهر"],
                ["إدخال تاريخ يدوياً", "🔙 رجوع"]
            ]
            await update.message.reply_text(
                "📅 اختر تاريخ الانتهاء:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return ENTER_PRODUCT_DETAILS
    
    if text == "🏠 القائمة الرئيسية":
        await start(update, context)
        return MAIN_MENU
    
    if text == "إدخال كمية أخرى":
        await update.message.reply_text(
            "🧮 الرجاء إدخال الكمية:",
            reply_markup=BACK_KEYBOARD
        )
        return ENTER_DAMAGE_DETAILS if is_damaged else ENTER_PRODUCT_DETAILS
    
    try:
        quantity = int(text)
        
        # تحسينات خاصة بالأصناف التالفة
        if is_damaged:
            current_quantity = context.user_data.get('current_quantity', float('inf'))
            if quantity <= 0:
                await update.message.reply_text("❌ الكمية يجب أن تكون أكبر من الصفر!", reply_markup=BACK_KEYBOARD)
                return ENTER_DAMAGE_DETAILS
            if quantity > current_quantity:
                await update.message.reply_text(
                    f"❌ الكمية المدخلة ({quantity}) أكبر من الكمية المتاحة ({current_quantity})!",
                    reply_markup=BACK_KEYBOARD
                )
                return ENTER_DAMAGE_DETAILS
        
        context.user_data['quantity'] = quantity
        logger.info(f"تم حفظ الكمية: {quantity} - user_data الآن: {context.user_data}")
        
        if is_damaged:
            keyboard = [
                ["انتهت صلاحيته", "تلف أثناء التخزين"],
                ["تلف أثناء النقل", "عيب تصنيع"],
                ["إدخال سبب آخر", "🔙 رجوع"]
            ]
            await update.message.reply_text(
                "📝 اختر سبب التلف:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return ENTER_DAMAGE_DETAILS
        else:
            await update.message.reply_text(
                "📝 الرجاء إدخال اسم المنتج:",
                reply_markup=BACK_KEYBOARD
            )
            return ENTER_PRODUCT_NAME
            
    except ValueError:
        await update.message.reply_text("❌ الكمية يجب أن تكون رقماً صحيحاً!", reply_markup=BACK_KEYBOARD)
        return ENTER_DAMAGE_DETAILS if is_damaged else ENTER_PRODUCT_DETAILS

async def save_product_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حفظ بيانات المنتج في قاعدة البيانات"""
    text = update.message.text.strip()
    is_damaged = context.user_data.get('is_damaged', False)
    
    logger.info(f"save_product_data - user_data: {context.user_data}")
    
    if text == "🔙 رجوع":
        keyboard = [
            ["1", "5", "10"],
            ["20", "50", "100"],
            ["إدخال كمية أخرى", "🔙 رجوع"]
        ]
        await update.message.reply_text(
            "🧮 اختر الكمية:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return ENTER_PRODUCT_DETAILS

    if text == "🏠 القائمة الرئيسية":
        await start(update, context)
        return MAIN_MENU

    # التحقق من الأصناف التالفة
    if is_damaged:
        # أول مرة: حفظ الاسم فقط
        if 'product_name' not in context.user_data:
            context.user_data['product_name'] = text
            await update.message.reply_text(
                "🧮 الرجاء إدخال الكمية التالفة:",
                reply_markup=ReplyKeyboardMarkup([["1", "2", "5", "10"], ["🔙 رجوع"]], resize_keyboard=True)
            )
            return ENTER_DAMAGE_DETAILS

        # ثاني مرة: حفظ الكمية
        if 'quantity' not in context.user_data:
            try:
                quantity = int(text)
                if quantity <= 0:
                    raise ValueError
                context.user_data['quantity'] = quantity
                keyboard = [
                    ["انتهت صلاحيته", "تلف أثناء التخزين"],
                    ["تلف أثناء النقل", "عيب تصنيع"],
                    ["إدخال سبب آخر", "🔙 رجوع"]
                ]
                await update.message.reply_text(
                    "📝 اختر سبب التلف:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                return ENTER_DAMAGE_DETAILS
            except ValueError:
                await update.message.reply_text(
                    "❌ الكمية يجب أن تكون رقمًا صحيحًا!",
                    reply_markup=ReplyKeyboardMarkup([["🔙 رجوع"]], resize_keyboard=True)
                )
                return ENTER_DAMAGE_DETAILS

        # إذا الكمية والاسم موجودين → احفظ المنتج التالف
        return await save_damaged_product(update, context, text)

    # الحالة العادية (منتج جديد)
    required_fields = ['barcode', 'expiry_date', 'quantity']
    missing_fields = [field for field in required_fields if field not in context.user_data]

    if missing_fields:
        logger.error(f"حقول مطلوبة ناقصة: {missing_fields} - البيانات الحالية: {context.user_data}")
        await update.message.reply_text(
            "❌ فشل في حفظ البيانات، يرجى البدء من جديد",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
        return MAIN_MENU

    return await save_new_product(update, context, text)

async def save_new_product(update: Update, context: ContextTypes.DEFAULT_TYPE, product_name: str):
    """حفظ المنتج الجديد في قاعدة البيانات"""
    barcode = context.user_data['barcode']
    expiry_date = context.user_data['expiry_date']
    quantity = context.user_data['quantity']
    
    logger.info(f"حفظ منتج جديد - الباركود: {barcode}, الكمية: {quantity}")
    
    try:
        conn = sqlite3.connect('inventory.db')
        c = conn.cursor()
        c.execute('''INSERT INTO products 
                    (barcode, name, expiry_date, quantity, added_date, user_id)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (barcode, product_name, expiry_date, quantity, 
                  datetime.datetime.now().strftime("%Y-%m-%d"), update.message.from_user.id))
        conn.commit()
        
        await update.message.reply_text(
            f"✅ تمت إضافة المنتج بنجاح!\n\n"
            f"الاسم: {product_name}\n"
            f"الباركود: {barcode}\n"
            f"الكمية: {quantity}\n"
            f"تاريخ الانتهاء: {expiry_date}",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "❌ هذا الباركود مسجل مسبقاً!",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"Error saving product: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء حفظ البيانات!",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    finally:
        conn.close()
    
    await start(update, context)
    return MAIN_MENU

async def save_damaged_product(update: Update, context: ContextTypes.DEFAULT_TYPE, damage_reason: str):
    """حفظ الصنف التالف مع تحسينات شاملة"""
    logger.info(f"بدء save_damaged_product - user_data: {context.user_data}")
    
    # التحقق من وجود جميع الحقول المطلوبة
    required_fields = ['barcode', 'quantity']
    missing_fields = [field for field in required_fields if field not in context.user_data]
    
    if missing_fields:
        error_msg = f"حقول مطلوبة ناقصة: {missing_fields} - البيانات الحالية: {context.user_data}"
        logger.error(error_msg)
        await update.message.reply_text(
            "❌ فشل في حفظ البيانات، يرجى البدء من جديد",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
        return MAIN_MENU
    
    try:
        barcode = context.user_data['barcode']
        quantity = context.user_data['quantity']
        product_name = context.user_data.get('product_name', 'غير معروف')
        
        logger.info(f"حفظ صنف تالف - الباركود: {barcode}, الكمية: {quantity}, السبب: {damage_reason}")
        
        conn = sqlite3.connect('inventory.db')
        c = conn.cursor()
        
        # إدخال البيانات في جدول التالف
        c.execute('''INSERT INTO damaged_products 
                    (barcode, name, quantity, damage_reason, report_date, user_id)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                (barcode, product_name, quantity, damage_reason, 
                 datetime.datetime.now().strftime("%Y-%m-%d"), update.message.from_user.id))
        
        # تحديث المخزون إذا كان المنتج موجوداً
        if 'current_quantity' in context.user_data:
            new_quantity = context.user_data['current_quantity'] - quantity
            if new_quantity < 0:
                new_quantity = 0
            c.execute("UPDATE products SET quantity = ? WHERE barcode=?", 
                     (new_quantity, barcode))
        
        conn.commit()
        
        await update.message.reply_text(
            f"✅ تم تسجيل التالف بنجاح!\n\n"
            f"الباركود: {barcode}\n"
            f"الاسم: {product_name}\n"
            f"الكمية التالفة: {quantity}\n"
            f"السبب: {damage_reason}",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"خطأ في حفظ الصنف التالف: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ غير متوقع أثناء حفظ البيانات!",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    finally:
        conn.close()
    
    await start(update, context)
    return MAIN_MENU

async def view_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الأصناف"""
    try:
        conn = sqlite3.connect('inventory.db')
        c = conn.cursor()
        c.execute("SELECT barcode, name, expiry_date, quantity FROM products ORDER BY expiry_date")
        products = c.fetchall()
        
        if not products:
            await update.message.reply_text(
                "📭 لا توجد أصناف مسجلة بعد",
                reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
            )
            return
        
        for i in range(0, len(products), 10):
            chunk = products[i:i+10]
            text = "📋 قائمة الأصناف:\n\n"
            for product in chunk:
                barcode, name, expiry, quantity = product
                text += (
                    f"🏷️ الباركود: {barcode}\n"
                    f"📌 الاسم: {name}\n"
                    f"📅 تاريخ الانتهاء: {expiry}\n"
                    f"🧮 الكمية: {quantity}\n"
                    f"────────────────────\n"
                )
            
            await update.message.reply_text(
                text,
                reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
            )
    except Exception as e:
        logger.error(f"Error viewing products: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء جلب البيانات!",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    finally:
        conn.close()
    
    await start(update, context)
    return MAIN_MENU

async def view_damaged_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الأصناف التالفة"""
    try:
        conn = sqlite3.connect('inventory.db')
        c = conn.cursor()
        c.execute("SELECT barcode, name, quantity, damage_reason, report_date FROM damaged_products ORDER BY report_date DESC")
        damaged = c.fetchall()
        
        if not damaged:
            await update.message.reply_text(
                "📭 لا توجد أصناف تالفة مسجلة",
                reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
            )
            return
        
        for i in range(0, len(damaged), 10):
            chunk = damaged[i:i+10]
            text = "🗑️ قائمة الأصناف التالفة:\n\n"
            for item in chunk:
                barcode, name, quantity, reason, date = item
                text += (
                    f"🏷️ الباركود: {barcode}\n"
                    f"📌 الاسم: {name}\n"
                    f"🧮 الكمية التالفة: {quantity}\n"
                    f"📝 السبب: {reason}\n"
                    f"📅 تاريخ الإبلاغ: {date}\n"
                    f"────────────────────\n"
                )
            
            await update.message.reply_text(
                text,
                reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
            )
    except Exception as e:
        logger.error(f"Error viewing damaged products: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء جلب البيانات!",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    finally:
        conn.close()
    
    await start(update, context)
    return MAIN_MENU

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصدير البيانات إلى ملف Excel"""
    try:
        import openpyxl
    except ImportError:
        import subprocess
        subprocess.run(["pip", "install", "openpyxl"])
        import openpyxl
    
    conn = None
    try:
        conn = sqlite3.connect('inventory.db')
        products_df = pd.read_sql_query("SELECT * FROM products", conn)
        damaged_df = pd.read_sql_query("SELECT * FROM damaged_products", conn)
        
        if products_df.empty and damaged_df.empty:
            await update.message.reply_text(
                "📭 لا توجد بيانات لتصديرها",
                reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
            )
            return
        
        filename = f"inventory_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            if not products_df.empty:
                products_df.to_excel(writer, sheet_name='المنتجات', index=False)
            if not damaged_df.empty:
                damaged_df.to_excel(writer, sheet_name='التالف', index=False)
        
        with open(filename, 'rb') as file:
            await update.message.reply_document(
                document=file,
                caption="📤 تم تصدير بيانات المخزون بنجاح",
                reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
            )
            
        os.remove(filename)
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء التصدير!",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    finally:
        if conn:
            conn.close()
    
    await start(update, context)
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء العملية الحالية"""
    await update.message.reply_text(
        "تم إلغاء العملية",
        reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
    )
    return MAIN_MENU

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأخطاء العامة"""
    logger.error(msg="حدث خطأ غير متوقع", exc_info=context.error)
    
    if update and hasattr(update, 'message'):
        logger.error(f"الرسالة التي تسببت في الخطأ: {update.message.text}")
        logger.error(f"user_data: {context.user_data if hasattr(context, 'user_data') else 'N/A'}")
        
        await update.message.reply_text(
            "❌ حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى",
            reply_markup=ReplyKeyboardMarkup([["🏠 القائمة الرئيسية"]], resize_keyboard=True)
        )
    
    context.user_data.clear()

def run_flask_app():
    """تشغيل تطبيق Flask في منفذ منفصل"""
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    if os.path.exists("inventory.db"):
        os.remove("inventory.db")
    
    init_db()
    
    # تشغيل Flask في thread منفصل
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    
    # إنشاء تطبيق التليجرام
    application = Application.builder().token(os.environ.get('TOKEN')).build()
    
    # إعداد معالجات المحادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)],
            ENTER_BARCODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_barcode_input)],
            ADD_DAMAGED: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_barcode_input)],
            ENTER_PRODUCT_DETAILS: [
                MessageHandler(filters.Regex("^(اليوم|غداً|أسبوع|شهر|إدخال تاريخ يدوياً|🔙 رجوع|🏠 القائمة الرئيسية)$"), handle_expiry_date),
                MessageHandler(filters.Regex("^(\d+|إدخال كمية أخرى|🔙 رجوع|🏠 القائمة الرئيسية)$"), handle_quantity_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expiry_date)
            ],
            ENTER_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_product_data)],
            ENTER_DAMAGE_DETAILS: [
                MessageHandler(filters.Regex("^(\d+|إدخال كمية أخرى|🔙 رجوع|🏠 القائمة الرئيسية)$"), handle_quantity_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_product_data)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    logger.info("✅ البوت يعمل!")
    application.run_polling()

if __name__ == '__main__':
    main()