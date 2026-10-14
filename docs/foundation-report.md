<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# تقرير التأسيس والتنضيف

تاريخ التأسيس: 2026-10-14. Virel نسخة مستقلة مشتقة من نسخة AI Studio المنظّفة؛ مش clone أعمى لكل فولدر المشروع القديم.

## اللي اتنقل

الكود الفعّال بس: app، get_session، حزمة التشغيل والـroutes، ١٧ اختبار، requirements، Docker، قالب env، ignore rules، وLICENSE بنفس نسبته الأصلية. اتغيّر اسم حزمة <code dir="ltr" style="unicode-bidi: isolate;">msemax</code> لـ<code dir="ltr" style="unicode-bidi: isolate;">virel</code> في imports والاختبارات وDocker، واسم gateway وإصدار البداية لـ<code dir="ltr" style="unicode-bidi: isolate;">0.1.0</code>.

الإعدادات الجديدة: <code dir="ltr" style="unicode-bidi: isolate;">VIREL_API_KEY</code>، <code dir="ltr" style="unicode-bidi: isolate;">VIREL_RATE_LIMIT</code>، <code dir="ltr" style="unicode-bidi: isolate;">VIREL_MAX_CONCURRENT</code>. <code dir="ltr" style="unicode-bidi: isolate;">.env</code> يتقرأ من جذر Virel، وprofile النسبي يتفسر من جذر المشروع، مش cwd. profile وsession/uploads اتجمعوا في <code dir="ltr" style="unicode-bidi: isolate;">runtime/</code>. إعداد تسجيل الدخول والخادم بيشيروا لنفس profile ونفس metadata.

## اللي ما اتنقلش

بيانات Google وcookies، <code dir="ltr" style="unicode-bidi: isolate;">.env</code> الحقيقي، uploads القديمة، فيديو/صور/سجلات الفحص، ملفات cache وبيئات Python، اسم حزمة ChatGPT القديم، scripts تشغيل تعتمد على مسارات جهاز بعينه، والوثائق المكررة. <code dir="ltr" style="unicode-bidi: isolate;">__pycache__</code> اللي الاختبارات بتعمله تلقائيًا متجاهَل، مش source.

في تنظيف النسخة السابقة اتشال ١٣١ ملف بحوالي ٢٣٫٨ MB؛ [قائمة الحذف وأسبابه](cleanup-inventory.md) محفوظة كسجل تاريخي. النسخة الأصلية وجلسة دخولها موجودين في مكانهم. نسخة ما قبل التنظيف محفوظة خارج repo، وفيها بيانات خاصة؛ ما ترفعهاش مع المشروع.

## اللي اتجرّب

١٦ اختبار موروث + اختبار جديد لمسارات التشغيل من cwd مختلف = ١٧ اختبار محلي: Bearer/بدون مفتاح، رفض جسم ناقص، Chat JSON وSSE، headers، busy 429، Responses وalias وSSE الحالي، Completions القديم، health/models، تحويل رسائل وصور base64، تطابق profile بين login والخادم، وقراءة الرد/fallback داخل Chromium معزول. نماذج الردود في الاختبارات ثابتة، مش Gemini حي.

## حدود النسخة الحالية اللي لازم ما تتخبّاش

| الحد | نعالجه فين؟ |
|---|---|
| خطأ browser ممكن يتحول لـHTTP 200 أو رد فاضي؛ readiness ضعيف | 002 |
| debug/shutdown من غير حماية مناسبة، وصلاحيات CORS واسعة | 002 قبل أي إتاحة خارج localhost |
| Chat بيتجاهل assistant history وبيغيّر نصوص بأنماط قديمة | 003 |
| clear=false تبويب مشترك؛ sessions مش منفذة | 003 |
| صور من URL/مسار محلي من غير حدود وثقة مناسبة | 004 |
| Responses جزئي، ملفات PDF مش مدعومة، token usage مش محسوب بدقة | 005 وما تحتاجه مراحل العملاء |
| أسماء models ثابتة؛ بعض المسارات مش بتوصل model للمتصفح | 007 |
| لا أدوات عميل أصلية ولا توليد صوت/صورة/فيديو | مراحل الوسائط والأدوات |
| شكل SSE الحالي مش كفاية لضمان Codex أو أي عميل | 013 و016 |

مشروع بالشكل ده يسمح نبني adapters ونضيف القدرات تدريجيًا. حدود السياق والسرعة وتغير UI وقدرات الموديل/الحساب موجودة مهما نظّمنا الكود؛ وعد «كل عميل وكل ميزة 100%» محتاج مصفوفة تجارب فعلية، وممكن عميل أصلًا ما يسمحش بـcustom endpoint.

## شكل Git عند تسليم التأسيس

main لتأسيس الأدوات، branch <code dir="ltr" style="unicode-bidi: isolate;">001-project-foundation</code> لنقل المصدر والتوثيق والتحقق، ثم merge محلي وtag <code dir="ltr" style="unicode-bidi: isolate;">v0.1.0</code>. المرحلة 002 لسه ما اتنفذتش. GitHub remote وchecks البعيدة وbranch protection لسه مستنيين repo. نرفع source والوثائق؛ runtime والأسرار متجاهَلة.

</div>
