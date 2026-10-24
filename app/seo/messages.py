"""Human-readable SEO issue copy. Rules stay pure; this module owns the wording."""
from __future__ import annotations

from .models import Issue

CATEGORY_NAMES = {
    "technical": ("Technical & indexability", "فنی و ایندکس‌پذیری"),
    "meta": ("Meta & social", "متا و شبکه‌های اجتماعی"),
    "content": ("Content", "محتوا"),
    "media": ("Images", "تصاویر"),
    "links": ("Links", "لینک‌ها"),
    "structured": ("Structured data", "داده ساختاریافته"),
    "mobile": ("Mobile", "موبایل"),
    "site": ("Site-wide", "کل سایت"),
    "performance": ("Performance", "عملکرد"),
}

SEVERITY_NAMES = {
    "critical": ("Critical", "بحرانی"),
    "high": ("High", "زیاد"),
    "medium": ("Medium", "متوسط"),
    "low": ("Low", "کم"),
    "info": ("Info", "اطلاعات"),
}

_MESSAGES: dict[str, dict[str, tuple[str, str, str]]] = {
    "technical.https": {
        "en": ("Page is not served over HTTPS",
               "Google treats HTTPS as a ranking signal and browsers warn visitors about insecure pages.",
               "Install an SSL certificate and redirect all HTTP requests to HTTPS."),
        "fa": ("صفحه روی HTTPS سرو نمی‌شود",
               "HTTPS یکی از سیگنال‌های رتبه‌بندی است و مرورگرها به بازدیدکننده هشدار ناامن نشان می‌دهند.",
               "گواهی SSL نصب کنید و همه درخواست‌های HTTP را به HTTPS ریدایرکت کنید."),
    },
    "technical.status": {
        "en": ("Page returns HTTP {status}",
               "Search engines cannot index a page that does not return a successful response.",
               "Fix the server error or restore the page, then request indexing again."),
        "fa": ("صفحه کد HTTP {status} برمی‌گرداند",
               "موتورهای جستجو صفحه‌ای را که پاسخ موفق ندارد ایندکس نمی‌کنند.",
               "خطای سرور را رفع یا صفحه را بازگردانی کنید و سپس دوباره درخواست ایندکس بدهید."),
    },
    "technical.redirect": {
        "en": ("URL redirects to another address",
               "Every redirect adds latency and can dilute link signals.",
               "Link to the final URL directly and update internal links."),
        "fa": ("آدرس به نشانی دیگری ریدایرکت می‌شود",
               "هر ریدایرکت تأخیر اضافه می‌کند و می‌تواند سیگنال لینک را تضعیف کند.",
               "مستقیماً به آدرس نهایی لینک بدهید و لینک‌های داخلی را به‌روزرسانی کنید."),
    },
    "technical.noindex": {
        "en": ("Page is blocked from indexing",
               "The page asks search engines not to index it (meta robots / X-Robots-Tag).",
               "Remove noindex/none when this page should appear in search results."),
        "fa": ("صفحه از ایندکس شدن منع شده است",
               "صفحه به موتورهای جستجو می‌گوید آن را ایندکس نکنند (meta robots / X-Robots-Tag).",
               "اگر این صفحه باید در نتایج جستجو دیده شود، noindex/none را حذف کنید."),
    },
    "technical.canonical_missing": {
        "en": ("Canonical URL is missing",
               "Without a canonical, duplicate URLs may compete with each other.",
               "Add a self-referencing <link rel=\"canonical\"> to the page head."),
        "fa": ("آدرس canonical وجود ندارد",
               "بدون canonical، آدرس‌های تکراری ممکن است با هم رقابت کنند.",
               "یک <link rel=\"canonical\"> خودارجاع به head صفحه اضافه کنید."),
    },
    "technical.canonical_mismatch": {
        "en": ("Canonical points to a different URL",
               "The canonical tells search engines to index {canonical} instead of {final_url}.",
               "Use a self-referencing canonical, or make sure the target page is the intended version."),
        "fa": ("canonical به آدرس دیگری اشاره می‌کند",
               "canonical به موتور جستجو می‌گوید {canonical} را جای {final_url} ایندکس کند.",
               "از canonical خودارجاع استفاده کنید یا مطمئن شوید صفحه مقصد همان نسخه اصلی است."),
    },
    "technical.viewport_missing": {
        "en": ("Mobile viewport meta tag is missing",
               "Without a viewport tag, mobile browsers show a zoomed-out desktop layout.",
               "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">."),
        "fa": ("تگ viewport موبایل وجود ندارد",
               "بدون viewport، مرورگر موبایل صفحه را کوچک‌نمایی‌شده و شبیه دسکتاپ نشان می‌دهد.",
               "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> را اضافه کنید."),
    },
    "technical.lang_missing": {
        "en": ("Page language is not declared",
               "The html lang attribute helps search engines and screen readers understand the language.",
               "Add the correct lang attribute, for example <html lang=\"fa\">."),
        "fa": ("زبان صفحه اعلام نشده است",
               "ویژگی lang به موتور جستجو و صفحه‌خوان کمک می‌کند زبان را تشخیص دهند.",
               "ویژگی lang درست را اضافه کنید، مثلاً <html lang=\"fa\">."),
    },
    "technical.charset_missing": {
        "en": ("Character encoding is not declared",
               "A missing charset can cause garbled Persian or Arabic characters.",
               "Declare <meta charset=\"utf-8\"> early in the head."),
        "fa": ("کدگذاری کاراکترها اعلام نشده است",
               "نبود charset می‌تواند باعث نمایش نامناسب حروف فارسی یا عربی شود.",
               "<meta charset=\"utf-8\"> را ابتدای head قرار دهید."),
    },
    "technical.sitemap_missing": {
        "en": ("No XML sitemap was found",
               "A sitemap helps search engines discover new and updated pages.",
               "Publish a sitemap and list it in robots.txt."),
        "fa": ("نقشه سایت XML پیدا نشد",
               "sitemap به موتور جستجو کمک می‌کند صفحات جدید و به‌روزرسانی‌شده را کشف کند.",
               "یک sitemap منتشر کنید و آدرس آن را در robots.txt بنویسید."),
    },
    "technical.robots_disallow": {
        "en": ("robots.txt blocks this page",
               "The site's robots.txt disallows this URL for the tester's user agent.",
               "If the page should rank, remove the Disallow rule; otherwise this may be intentional."),
        "fa": ("robots.txt این صفحه را مسدود می‌کند",
               "robots.txt سایت این آدرس را برای user agent تستر ممنوع کرده است.",
               "اگر صفحه باید رتبه بگیرد قاعده Disallow را بردارید؛ در غیر این صورت ممکن است عمدی باشد."),
    },
    "technical.mixed_content": {
        "en": ("{count} insecure HTTP resources on an HTTPS page",
               "Mixed content is blocked by browsers and weakens trust and security.",
               "Serve every image, script and stylesheet over HTTPS."),
        "fa": ("{count} منبع HTTP ناامن در صفحه HTTPS",
               "محتوای ترکیبی را مرورگرها مسدود می‌کنند و به امنیت و اعتماد آسیب می‌زند.",
               "همه تصاویر، اسکریپت‌ها و استایل‌ها را با HTTPS سرو کنید."),
    },
    "meta.title_missing": {
        "en": ("Title tag is missing",
               "The title is one of the strongest on-page relevance signals and is shown in search results.",
               "Add a unique, descriptive <title> to the page."),
        "fa": ("تگ عنوان وجود ندارد",
               "عنوان یکی از قوی‌ترین سیگنال‌های مرتبط‌بودن صفحه و متن نمایش‌داده‌شده در نتایج جستجوست.",
               "یک <title> یکتا و توصیفی به صفحه اضافه کنید."),
    },
    "meta.title_length": {
        "en": ("Title is {length} characters",
               "Titles are usually truncated around 60 characters in search results.",
               "Keep the title between 30 and 60 characters and put the main keyword first."),
        "fa": ("طول عنوان {length} کاراکتر است",
               "عنوان در نتایج جستجو معمولاً حدود ۶۰ کاراکتر کوتاه می‌شود.",
               "عنوان را بین ۳۰ تا ۶۰ کاراکتر نگه دارید و کلمه کلیدی اصلی را ابتدا بیاورید."),
    },
    "meta.description_missing": {
        "en": ("Meta description is missing",
               "Search engines often use the description as the snippet under the title.",
               "Write a compelling 70–155 character description for this page."),
        "fa": ("توضیحات متا وجود ندارد",
               "موتورهای جستجو معمولاً از توضیحات متا به‌عنوان متن زیر عنوان استفاده می‌کنند.",
               "یک توضیح جذاب بین ۷۰ تا ۱۵۵ کاراکتر برای این صفحه بنویسید."),
    },
    "meta.description_length": {
        "en": ("Meta description is {length} characters",
               "Descriptions outside the usual range are truncated or ignored.",
               "Keep the description between 70 and 155 characters."),
        "fa": ("طول توضیحات متا {length} کاراکتر است",
               "توضیحات خارج از بازه معمول کوتاه یا نادیده گرفته می‌شود.",
               "توضیحات را بین ۷۰ تا ۱۵۵ کاراکتر نگه دارید."),
    },
    "meta.og_missing": {
        "en": ("Open Graph tags are incomplete",
               "Missing: {missing}. Open Graph controls how the page looks when shared.",
               "Add og:title, og:description and og:image to the page head."),
        "fa": ("تگ‌های Open Graph کامل نیستند",
               "موارد گمشده: {missing}. Open Graph ظاهر صفحه هنگام اشتراک‌گذاری را کنترل می‌کند.",
               "og:title، og:description و og:image را به head اضافه کنید."),
    },
    "meta.twitter_missing": {
        "en": ("Twitter Card tags are missing",
               "Twitter/X may show a plain link instead of a rich preview.",
               "Add twitter:card, twitter:title and twitter:description."),
        "fa": ("تگ‌های Twitter Card وجود ندارند",
               "توییتر/X ممکن است به‌جای پیش‌نمایش غنی، فقط لینک ساده نشان دهد.",
               "twitter:card، twitter:title و twitter:description را اضافه کنید."),
    },
    "content.h1_missing": {
        "en": ("H1 heading is missing",
               "The H1 gives the page a clear main topic for users and search engines.",
               "Add one descriptive H1 that matches the page intent."),
        "fa": ("هدینگ H1 وجود ندارد",
               "H1 موضوع اصلی صفحه را برای کاربر و موتور جستجو روشن می‌کند.",
               "یک H1 توصیفی و متناسب با هدف صفحه اضافه کنید."),
    },
    "content.h1_multiple": {
        "en": ("Page has {count} H1 headings",
               "Multiple H1s can blur the main topic; use one H1 and H2s for sections.",
               "Keep a single H1 and demote the others to H2."),
        "fa": ("صفحه {count} هدینگ H1 دارد",
               "تعداد زیاد H1 موضوع اصلی را مبهم می‌کند؛ یک H1 و برای بخش‌ها H2 استفاده کنید.",
               "یک H1 نگه دارید و بقیه را به H2 تغییر دهید."),
    },
    "content.thin": {
        "en": ("Thin content ({words} words)",
               "Pages with very little unique text rarely satisfy search intent.",
               "Add useful details, examples, specifications or FAQs (aim for 300+ words where appropriate)."),
        "fa": ("محتوای کم‌مایه ({words} کلمه)",
               "صفحاتی با متن یکتای بسیار کم معمولاً نیاز جستجوگر را برآورده نمی‌کنند.",
               "جزئیات مفید، مثال، مشخصات یا پرسش‌های متداول اضافه کنید (در صورت نیاز ۳۰۰ کلمه یا بیشتر)."),
    },
    "content.keyword_missing": {
        "en": ("Focus keyword \"{keyword}\" is missing from the content",
               "The page does not mention the keyword you are targeting.",
               "Mention the keyword naturally in the intro and at least one heading."),
        "fa": ("کلمه کلیدی هدف «{keyword}» در محتوا نیست",
               "صفحه کلمه کلیدی هدف شما را ذکر نمی‌کند.",
               "کلمه کلیدی را به‌صورت طبیعی در مقدمه و حداقل یک هدینگ بیاورید."),
    },
    "content.title_keyword_missing": {
        "en": ("Focus keyword is missing from the title",
               "The title is a strong relevance signal but does not contain the target keyword.",
               "Place the keyword near the beginning of the title without stuffing."),
        "fa": ("کلمه کلیدی هدف در عنوان نیست",
               "عنوان سیگنال مهمی است اما کلمه کلیدی هدف را ندارد.",
               "کلمه کلیدی را بدون تکرار مصنوعی نزدیک ابتدای عنوان قرار دهید."),
    },
    "content.description_keyword_missing": {
        "en": ("Focus keyword is missing from the meta description",
               "The description can reinforce relevance and improve click-through rate.",
               "Include the keyword naturally in the meta description."),
        "fa": ("کلمه کلیدی هدف در توضیحات متا نیست",
               "توضیحات متا می‌تواند مرتبط‌بودن را تقویت و نرخ کلیک را بهتر کند.",
               "کلمه کلیدی را به‌صورت طبیعی در توضیحات متا بیاورید."),
    },
    "content.keyword_density_high": {
        "en": ("Keyword density is {density}%",
               "Repeating the keyword too often looks like keyword stuffing.",
               "Use synonyms and natural phrasing; keep density below about 3–4%."),
        "fa": ("چگالی کلمه کلیدی {density}٪ است",
               "تکرار بیش از حد کلمه کلیدی شبیه keyword stuffing است.",
               "از مترادف و جمله‌بندی طبیعی استفاده کنید؛ چگالی را زیر حدود ۳ تا ۴ درصد نگه دارید."),
    },
    "media.alt_missing": {
        "en": ("{count} of {total} images have no alt text",
               "Alt text makes images accessible and gives search engines context.",
               "Describe each meaningful image in its alt attribute; mark decorative images with alt=\"\"."),
        "fa": ("{count} از {total} تصویر متن جایگزین ندارند",
               "متن جایگزین تصاویر را قابل‌دسترس و برای موتور جستجو معنادار می‌کند.",
               "برای هر تصویر معنادار alt توصیفی بنویسید؛ تصاویر تزئینی را alt=\"\" بگذارید."),
    },
    "media.dimensions_missing": {
        "en": ("{count} images have no width/height attributes",
               "Missing dimensions can cause layout shifts while images load.",
               "Add intrinsic width and height attributes (or CSS aspect-ratio)."),
        "fa": ("{count} تصویر ویژگی width/height ندارند",
               "نبود ابعاد می‌تواند هنگام بارگذاری تصاویر باعث جابه‌جایی چیدمان (CLS) شود.",
               "ابعاد واقعی width و height (یا CSS aspect-ratio) را اضافه کنید."),
    },
    "media.lazy_missing": {
        "en": ("{count} below-the-fold images are not lazy-loaded",
               "Loading offscreen images eagerly wastes bandwidth and delays important content.",
               "Add loading=\"lazy\" to images that are not visible initially."),
        "fa": ("{count} تصویر پایین صفحه lazy-load نیستند",
               "بارگذاری زودهنگام تصاویر خارج از دید، پهنای باند را هدر می‌دهد و محتوای مهم را دیرتر نشان می‌دهد.",
               "برای تصاویری که در ابتدا دیده نمی‌شوند loading=\"lazy\" اضافه کنید."),
    },
    "links.internal_low": {
        "en": ("Only {count} internal links on the page",
               "Internal links spread authority and help crawlers discover related pages.",
               "Link to relevant products, categories or articles with descriptive anchors."),
        "fa": ("فقط {count} لینک داخلی در صفحه وجود دارد",
               "لینک‌های داخلی اعتبار را پخش می‌کنند و به خزنده‌ها در کشف صفحات مرتبط کمک می‌کنند.",
               "با متن لنگر توصیفی به محصولات، دسته‌ها یا مقالات مرتبط لینک بدهید."),
    },
    "links.broken": {
        "en": ("{count} broken links detected",
               "Broken links frustrate visitors and waste crawl budget.",
               "Fix or remove the links listed in the evidence."),
        "fa": ("{count} لینک شکسته پیدا شد",
               "لینک‌های شکسته کاربر را ناامید می‌کنند و بودجه خزش را هدر می‌دهند.",
               "لینک‌های فهرست‌شده در شواهد را اصلاح یا حذف کنید."),
    },
    "links.redirect": {
        "en": ("{count} links point to redirecting URLs",
               "Linking to redirects adds an extra hop for users and crawlers.",
               "Update the links to point to the final destination."),
        "fa": ("{count} لینک به آدرس‌های ریدایرکت‌شده اشاره می‌کنند",
               "لینک به ریدایرکت برای کاربر و خزنده یک مرحله اضافه ایجاد می‌کند.",
               "لینک‌ها را به مقصد نهایی به‌روزرسانی کنید."),
    },
    "links.generic_anchor": {
        "en": ("{count} links use generic anchor text",
               "Anchors such as \"click here\" tell search engines nothing about the target.",
               "Use descriptive anchor text that reflects the destination."),
        "fa": ("{count} لینک از متن لنگر عمومی استفاده می‌کنند",
               "لنگرهایی مثل «اینجا کلیک کنید» هیچ اطلاعاتی درباره مقصد به موتور جستجو نمی‌دهند.",
               "از متن لنگر توصیفی متناسب با مقصد استفاده کنید."),
    },
    "structured.missing": {
        "en": ("No JSON-LD structured data found",
               "Structured data helps search engines understand products, articles and breadcrumbs.",
               "Add JSON-LD for the page type (Product, Article, BreadcrumbList)."),
        "fa": ("داده ساختاریافته JSON-LD پیدا نشد",
               "داده ساختاریافته به موتور جستجو در فهم محصول، مقاله و مسیر صفحه کمک می‌کند.",
               "برای نوع صفحه (Product، Article، BreadcrumbList) JSON-LD اضافه کنید."),
    },
    "structured.invalid": {
        "en": ("Invalid JSON-LD block",
               "Search engines cannot parse structured data with invalid JSON.",
               "Validate the JSON-LD syntax and fix the reported error."),
        "fa": ("بلوک JSON-LD نامعتبر است",
               "موتور جستجو نمی‌تواند داده ساختاریافته با JSON نامعتبر را بخواند.",
               "سینتکس JSON-LD را اعتبارسنجی و خطای گزارش‌شده را اصلاح کنید."),
    },
    "structured.product_offer": {
        "en": ("Product schema has no offer or price",
               "Product rich results require offer/price information.",
               "Add an Offer with price, priceCurrency and availability."),
        "fa": ("اسکیمای محصول فیلد offer یا قیمت ندارد",
               "نتایج غنی محصول به اطلاعات offer/price نیاز دارند.",
               "یک Offer با price، priceCurrency و availability اضافه کنید."),
    },
    "structured.article_headline": {
        "en": ("Article schema has no headline",
               "Article rich results need a headline and author information.",
               "Add headline, author and datePublished to the Article schema."),
        "fa": ("اسکیمای مقاله فیلد headline ندارد",
               "نتایج غنی مقاله به headline و اطلاعات نویسنده نیاز دارند.",
               "headline، author و datePublished را به اسکیمای Article اضافه کنید."),
    },
    "mobile.overflow": {
        "en": ("Page scrolls horizontally on mobile",
               "Horizontal overflow makes the page harder to read and use.",
               "Fix elements wider than the viewport; use max-width: 100% for media."),
        "fa": ("صفحه در موبایل به‌صورت افقی اسکرول می‌شود",
               "سرریز افقی خواندن و استفاده از صفحه را سخت می‌کند.",
               "عناصر پهن‌تر از viewport را اصلاح کنید؛ برای رسانه‌ها max-width: 100% بگذارید."),
    },
    "mobile.small_text": {
        "en": ("{count} text elements are smaller than 12px",
               "Small text is difficult to read on phones and can hurt user experience.",
               "Increase body and caption font sizes for mobile."),
        "fa": ("{count} عنصر متنی کوچک‌تر از ۱۲ پیکسل هستند",
               "متن کوچک روی موبایل سخت خوانده می‌شود و تجربه کاربری را ضعیف می‌کند.",
               "اندازه فونت متن اصلی و توضیحات را برای موبایل بزرگ‌تر کنید."),
    },
    "mobile.small_taps": {
        "en": ("{count} tap targets are smaller than 48px",
               "Small buttons and links are hard to tap accurately.",
               "Increase the hit area of buttons and links to at least 48×48px."),
        "fa": ("{count} هدف لمسی کوچک‌تر از ۴۸ پیکسل هستند",
               "دکمه‌ها و لینک‌های کوچک به‌سختی لمس می‌شوند.",
               "ناحیه لمس دکمه‌ها و لینک‌ها را حداقل ۴۸×۴۸ پیکسل کنید."),
    },
    "site.duplicate_titles": {
        "en": ("{count} pages share duplicate titles",
               "Duplicate titles make it hard for search engines to distinguish pages.",
               "Give every page a unique title."),
        "fa": ("{count} صفحه عنوان تکراری دارند",
               "عنوان تکراری تشخیص صفحات را برای موتور جستجو سخت می‌کند.",
               "برای هر صفحه عنوان یکتا بنویسید."),
    },
    "site.duplicate_descriptions": {
        "en": ("{count} pages share duplicate meta descriptions",
               "Duplicate descriptions reduce snippet quality and relevance.",
               "Write a unique description for each page."),
        "fa": ("{count} صفحه توضیحات متای تکراری دارند",
               "توضیحات تکراری کیفیت و مرتبط‌بودن اسنیپت را کم می‌کند.",
               "برای هر صفحه توضیحات یکتا بنویسید."),
    },
}


def issue_text(issue: Issue, lang: str = "fa") -> tuple[str, str, str]:
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


def category_label(category: str, lang: str = "fa") -> str:
    pair = CATEGORY_NAMES.get(category)
    if not pair:
        return category
    return pair[1] if lang == "fa" else pair[0]


def severity_label(severity: str, lang: str = "fa") -> str:
    pair = SEVERITY_NAMES.get(severity)
    if not pair:
        return severity
    return pair[1] if lang == "fa" else pair[0]
