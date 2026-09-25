# V2Ray Deploy-Site Config Collector

ابزار جمع‌آوری کانفیگ‌های رایگان V2Ray / Xray که روی سرویس‌های رایگان هاستینگ (Railway, Vercel, Netlify, Cloudflare Pages و ...) قرار دارند.

این پروژه دو بخش دارد:

1. **نسخه گرافیکی (GUI)** برای استفاده دستی
2. **نسخه خودکار** که هر ۲۴ ساعت یک‌بار کانفیگ‌ها را جمع‌آوری و منتشر می‌کند

---

## لینک سابسکریپشن خودکار
https://raw.githubusercontent.com/alirezauser67-coder/collector-UI/main/configs.txt


- هر روز ساعت ۱۰ صبح UTC (حدود ۱۳:۳۰ ایران) به‌روزرسانی می‌شود
- فقط کانفیگ‌هایی که دامنه آن‌ها متعلق به سرویس‌های رایگان است نگه داشته می‌شوند

---

## فایل‌های پروژه

| فایل | توضیح |
|------|------|
| `collector_ui.py` | نسخه گرافیکی (Tkinter) |
| `scripts/collect.py` | اسکریپت خودکار جمع‌آوری |
| `sources.txt` | لیست منابع کانفیگ |
| `configs.txt` | خروجی نهایی سابسکریپشن |
| `.github/workflows/build.yml` | اجرای خودکار روزانه |

---

## نیازمندی‌ها

- Python **3.10** یا بالاتر
- Tkinter (همراه نصب Python رسمی ویندوز موجود است)
- اتصال به اینترنت

```bash
pip install -r requirements.txt
