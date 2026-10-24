"""Persian/English copy for performance findings."""
from __future__ import annotations

from .models import PerfIssue

_MESSAGES: dict[str, dict[str, tuple[str, str, str]]] = {
    "perf.lcp_slow": {
        "en": ("Largest Contentful Paint is {ms} ms",
               "LCP should be 2.5 s or less. It is the moment the main content is visible.",
               "Optimize the LCP image/text: preload it, serve a smaller WebP/AVIF version, remove render-blocking work."),
        "fa": ("Largest Contentful Paint برابر {ms} میلی‌ثانیه است",
               "LCP باید حداکثر ۲.۵ ثانیه باشد؛ یعنی زمانی که محتوای اصلی دیده می‌شود.",
               "تصویر/متن LCP را بهینه کنید: preload، نسخه کوچک‌تر WebP/AVIF و حذف کارهای مسدودکننده رندر."),
    },
    "perf.cls_high": {
        "en": ("Cumulative Layout Shift is {cls}",
               "CLS should be 0.1 or less. Content jumps annoy users and cause mis-clicks.",
               "Set width/height or aspect-ratio for images, reserve space for ads/embeds and avoid inserting content above existing content."),
        "fa": ("Cumulative Layout Shift برابر {cls} است",
               "CLS باید حداکثر ۰.۱ باشد. جابه‌جایی محتوا کاربر را اذیت می‌کند و باعث کلیک اشتباه می‌شود.",
               "برای تصاویر width/height یا aspect-ratio بگذارید، برای تبلیغ/امبد جا رزرو کنید و از درج محتوا بالای محتوای موجود خودداری کنید."),
    },
    "perf.tbt_high": {
        "en": ("Total Blocking Time is {ms} ms",
               "TBT above 200 ms means the main thread is busy and interactions feel delayed.",
               "Split long JavaScript tasks, defer non-critical scripts and reduce third-party tags."),
        "fa": ("Total Blocking Time برابر {ms} میلی‌ثانیه است",
               "TBT بالای ۲۰۰ میلی‌ثانیه یعنی رشته اصلی مشغول است و تعامل با صفحه کند حس می‌شود.",
               "تسک‌های طولانی JavaScript را تقسیم کنید، اسکریپت‌های غیرحیاتی را defer کنید و تگ‌های third-party را کم کنید."),
    },
    "perf.ttfb_slow": {
        "en": ("Time to First Byte is {ms} ms",
               "TTFB above 800 ms points to slow hosting, database or server-side caching.",
               "Use page caching, a CDN and optimize the backend/database; check the server's response time."),
        "fa": ("Time to First Byte برابر {ms} میلی‌ثانیه است",
               "TTFB بالای ۸۰۰ میلی‌ثانیه نشانه کندی هاست، دیتابیس یا کش سمت سرور است.",
               "از کش صفحه، CDN و بهینه‌سازی بک‌اند/دیتابیس استفاده کنید و زمان پاسخ سرور را بررسی کنید."),
    },
    "perf.fcp_slow": {
        "en": ("First Contentful Paint is {ms} ms",
               "FCP above 1.8 s means users stare at a blank screen for too long.",
               "Reduce render-blocking CSS/JS, preconnect to critical origins and improve server response."),
        "fa": ("First Contentful Paint برابر {ms} میلی‌ثانیه است",
               "FCP بالای ۱.۸ ثانیه یعنی کاربر مدت زیادی صفحه خالی می‌بیند.",
               "CSS/JS مسدودکننده رندر را کم کنید، به مبدأهای حیاتی preconnect بدهید و پاسخ سرور را بهتر کنید."),
    },
    "perf.inp_lab": {
        "en": ("Approximate lab INP is {ms} ms",
               "Real INP requires real user interactions. This is a synthetic keyboard interaction and only an indicator.",
               "Use TBT and long-task data as the primary lab signal; collect field data for real INP."),
        "fa": ("INP آزمایشگاهی تقریبی {ms} میلی‌ثانیه است",
               "INP واقعی به تعامل کاربر واقعی نیاز دارد. این عدد از یک تعامل شبیه‌سازی‌شده به‌دست آمده و فقط شاخص است.",
               "برای آزمایشگاه به TBT و long task تکیه کنید؛ برای INP واقعی داده فیلد جمع کنید."),
    },
    "perf.page_weight": {
        "en": ("Page transfers {mb} MB",
               "Heavy pages cost more bandwidth and take longer on mobile networks.",
               "Compress images, use WebP/AVIF, lazy-load offscreen media and remove unused libraries."),
        "fa": ("حجم صفحه {mb} مگابایت است",
               "صفحات سنگین پهنای باند بیشتری مصرف می‌کنند و روی شبکه موبایل دیرتر بارگذاری می‌شوند.",
               "تصاویر را فشرده و WebP/AVIF کنید، رسانه خارج از دید را lazy-load کنید و کتابخانه‌های بلااستفاده را حذف کنید."),
    },
    "perf.requests_high": {
        "en": ("{count} network requests",
               "Many requests add connection overhead and delay loading.",
               "Combine files, remove unused plugins/scripts and defer non-critical resources."),
        "fa": ("{count} درخواست شبکه",
               "درخواست‌های زیاد سربار اتصال ایجاد می‌کنند و بارگذاری را دیرتر می‌کنند.",
               "فایل‌ها را ادغام کنید، افزونه/اسکریپت بلااستفاده را حذف کنید و منابع غیرحیاتی را defer کنید."),
    },
    "perf.render_blocking": {
        "en": ("{count} render-blocking resources",
               "Stylesheets and synchronous scripts in the head delay the first paint.",
               "Inline critical CSS, defer non-critical scripts and load styles asynchronously where possible."),
        "fa": ("{count} منبع مسدودکننده رندر",
               "استایل‌ها و اسکریپت‌های همگام در head اولین رنگ‌آمیزی را عقب می‌اندازند.",
               "CSS حیاتی را inline کنید، اسکریپت‌های غیرحیاتی را defer کنید و استایل‌ها را در صورت امکان غیرهمگام بارگذاری کنید."),
    },
    "perf.third_party": {
        "en": ("{count} third-party domains",
               "Third-party scripts are a common source of main-thread work and privacy risk.",
               "Audit analytics, chat and marketing tags; remove unused ones and load the rest after the page is interactive."),
        "fa": ("{count} دامنه third-party",
               "اسکریپت‌های third-party معمولاً عامل اصلی کار رشته اصلی و ریسک حریم خصوصی هستند.",
               "تگ‌های آنالیتیکس، چت و بازاریابی را بررسی کنید؛ موارد بلااستفاده را حذف و بقیه را بعد از تعامل بارگذاری کنید."),
    },
    "perf.oversized_images": {
        "en": ("{count} oversized images",
               "Images are much larger than their displayed size, wasting bandwidth.",
               "Resize images to their rendered dimensions and generate responsive srcset variants."),
        "fa": ("{count} تصویر بیش از حد بزرگ",
               "تصاویر بسیار بزرگ‌تر از اندازه نمایش هستند و پهنای باند هدر می‌دهند.",
               "تصاویر را به اندازه واقعی نمایش تغییر اندازه دهید و نسخه‌های srcset بسازید."),
    },
    "perf.image_dimensions": {
        "en": ("{count} images without intrinsic dimensions",
               "Missing width/height can cause layout shifts while images load.",
               "Add width and height attributes or CSS aspect-ratio to every image."),
        "fa": ("{count} تصویر بدون ابعاد ذاتی",
               "نبود width/height می‌تواند هنگام بارگذاری تصویر باعث جابه‌جایی چیدمان شود.",
               "برای همه تصاویر width و height یا CSS aspect-ratio اضافه کنید."),
    },
    "perf.slow_resource": {
        "en": ("Slow resource: {url}",
               "This resource took {ms} ms and delays the page.",
               "Optimize or defer this request; check the server and compress the response."),
        "fa": ("منبع کند: {url}",
               "این منبع {ms} میلی‌ثانیه طول کشیده و صفحه را عقب می‌اندازد.",
               "این درخواست را بهینه یا defer کنید؛ سرور را بررسی و پاسخ را فشرده کنید."),
    },
    "perf.no_compression": {
        "en": ("{count} text resources are not compressed",
               "Uncompressed HTML/CSS/JS increases transfer size.",
               "Enable gzip or Brotli compression on the server."),
        "fa": ("{count} منبع متنی فشرده نشده‌اند",
               "HTML/CSS/JS بدون فشرده‌سازی حجم انتقال را زیاد می‌کند.",
               "فشرده‌سازی gzip یا Brotli را روی سرور فعال کنید."),
    },
    "perf.no_cache": {
        "en": ("{count} static resources have no cache policy",
               "Without cache headers, repeat visits download the same files again.",
               "Set long Cache-Control headers for versioned static assets."),
        "fa": ("{count} منبع استاتیک سیاست کش ندارند",
               "بدون هدرهای کش، بازدیدهای بعدی همان فایل‌ها را دوباره دانلود می‌کنند.",
               "برای فایل‌های استاتیک نسخه‌دار هدر Cache-Control طولانی تنظیم کنید."),
    },
}


def perf_text(issue: PerfIssue, lang: str = "fa") -> tuple[str, str, str]:
    entry = _MESSAGES.get(issue.code)
    if not entry:
        return issue.code, "", ""
    lang_key = "fa" if lang == "fa" else "en"
    title, detail, fix = entry.get(lang_key) or entry["en"]
    values = {k: v for k, v in issue.data.items() if isinstance(v, (str, int, float))}
    try:
        title = title.format(**values)
    except (KeyError, ValueError, IndexError):
        pass
    try:
        detail = detail.format(**values)
    except (KeyError, ValueError, IndexError):
        pass
    try:
        fix = fix.format(**values)
    except (KeyError, ValueError, IndexError):
        pass
    return title, detail, fix


def metric_label(code: str, lang: str = "fa") -> str:
    labels = {
        "lcp": ("LCP", "LCP"),
        "cls": ("CLS", "CLS"),
        "tbt": ("TBT", "TBT"),
        "inp": ("INP (lab)", "INP (آزمایشگاهی)"),
        "fcp": ("FCP", "FCP"),
        "ttfb": ("TTFB", "TTFB"),
    }
    pair = labels.get(code)
    if not pair:
        return code
    return pair[1] if lang == "fa" else pair[0]
