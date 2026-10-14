<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# Virel — ڤيريل

**Visual Interface Relay**: وسيط يستقبل طلب HTTP، ينفّذه في واجهة AI Studio عن طريق Chromium، ويرجع الرد للبرنامج اللي طلبه.

## تبدأ تقرأ منين؟

| محتاج إيه؟ | افتح |
|---|---|
| المراحل وترتيب الشغل | [الخطة](tasks/plan.md) |
| مكان كل حاجة ورحلة الطلب | [خريطة المشروع](docs/architecture.md) |
| شكل الطلبات وإرسال ملفات من n8n | [المدخلات](docs/client-inputs.md) |
| اللي اتنقل واتشال وحدود النسخة الحالية | [تقرير التأسيس](docs/foundation-report.md) |
| المهمة الحالية | [المهام](tasks/todo.md) |
| قواعد أي agent | [AGENTS.md](AGENTS.md) |

## التشغيل على Windows

من فولدر Virel وبـPython 3.12:

<div dir="ltr" style="direction: ltr; text-align: left;">

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

</div>

عدّل <code dir="ltr" style="unicode-bidi: isolate;">.env</code>: اختار مفتاح خاص في <code dir="ltr" style="unicode-bidi: isolate;">VIREL_API_KEY</code>، وراجع الموديل اللي حسابك بيوفره. أسماء الموديلات الموروثة مش إثبات إن الموديل متاح. بعد كده:

<div dir="ltr" style="direction: ltr; text-align: left;">

```powershell
python get_session.py
python app.py
```

</div>

أول أمر بيفتح تسجيل دخول Google يدويًا في بروفايل Virel الجديد. اقفل متصفح الإعداد قبل تشغيل الخادم. بروفايل النسخة القديمة موجود في مكانه؛ ما نقلناش بيانات دخولك.

العنوان المحلي <code dir="ltr" style="unicode-bidi: isolate;">http://localhost:8001/v1</code>، والفحص <code dir="ltr" style="unicode-bidi: isolate;">http://localhost:8001/health</code>. المفتاح ده للـgateway عندك، مش مفتاح Google. سيبه فاضي هيلغي مصادقة مسارات التوليد.

## التحقق

<div dir="ltr" style="direction: ltr; text-align: left;">

```powershell
python -m unittest discover -s tests -v
```

</div>

فيه ١٧ اختبار محلي للـHTTP والتحويل وقراءة DOM من Chromium معزول. ده مش شهادة توافق مع n8n أو Google الحقيقي. شغّل process واحد وworker واحد؛ فيه تبويب متصفح واحد مشترك.

## Spec Kit وGit

المشروع مهيّأ من [Spec Kit الرسمي](https://github.com/github/spec-kit)، CLI إصدار <code dir="ltr" style="unicode-bidi: isolate;">1.2.0</code>، تكامل Codex وPowerShell، وإضافة Git إصدار <code dir="ltr" style="unicode-bidi: isolate;">1.0.1</code>. قواعد المشروع في [.specify/memory/constitution.md](.specify/memory/constitution.md)، ومستندات مرحلة التأسيس في [specs/001-project-foundation](specs/001-project-foundation/spec.md).

افتح Virel كمشروع مستقل في Codex علشان تعليماته ومهاراته المحلية تتقرأ. استخدم <code dir="ltr" style="unicode-bidi: isolate;">$speckit-specify</code> ثم <code dir="ltr" style="unicode-bidi: isolate;">$speckit-plan</code> ثم <code dir="ltr" style="unicode-bidi: isolate;">$speckit-tasks</code> لكل مرحلة؛ التنفيذ بـ<code dir="ltr" style="unicode-bidi: isolate;">$speckit-implement</code> بعد اتفاقنا على نطاقها. استخدام مهارة واحدة ما يأذنّش بتنفيذ باقي المراحل تلقائيًا.

العربي متغلف بـ<code dir="ltr" style="unicode-bidi: isolate;">dir=&quot;rtl&quot;</code>، والكود اتجاهه يسار ليمين، ومعاه إعداد VS Code للـMarkdown. الـviewer محتاج يسمح بعرض HTML. أدوات Spec Kit الأصلية بالإنجليزي زي ما نزلت.

</div>
