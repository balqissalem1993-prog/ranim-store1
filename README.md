# متجر رنيم — Ranim Store 🌸

نظام متجر متكامل مبني بـ Flask + Supabase

## الرفع على Render

كل البيانات (Supabase وغيرها) موجودة بالفعل داخل الكود — لا تحتاج إضافة أي إعدادات.

1. ارفع المجلد كاملاً على GitHub (بنفس الهيكل: `app.py`, `requirements.txt`, `Procfile`, ومجلد `templates/`)
2. اذهب إلى [render.com](https://render.com) وأنشئ **New Web Service**
3. اربطه بـ GitHub repo
4. **Start Command**: `gunicorn app:app`
5. اضغط Deploy ✅

## الروابط
- واجهة الزبون: `https://your-app.onrender.com/`
- واجهة الإدارة: `https://your-app.onrender.com/admin`

