<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# Verification: تأسيس Virel

تاريخ التحقق: 2026-10-14. النتائج دي محلية؛ GitHub remote لسه مش موجود.

| التحقق | النتيجة |
|---|---|
| unittest من Virel | 17/17 PASS: 16 اختبار نقل + اختبار مسارات جديد |
| path regression | اختبار جديد يشغل import من cwd مؤقت مختلف ويحفظ profile/session/uploads تحت جذر Virel |
| mutation check | عكس شرط profile-relative خلّى الاختبار يفشل؛ source اتردّ واتشغلت المجموعة ونجحت |
| source carryover review | فرق مصدر النسخة القديمة بعد rebrand محصور في config وsession path وhealth وتشخيص profile؛ browser generation logic زي ما هو |
| Python syntax | AST parse لكل الملفات المنقولة نجح |
| Markdown | 11 مستند عربي: headings/tables/code fences/RTL والروابط الداخلية صحيحة؛ evidence دي المستند رقم 12 |
| Chromium preview | README والخطة والمدخلات اتعرضوا في browser معزول؛ اتجاه النص RTL والكود LTR، واتراجعت screenshots بصريًا |
| Git privacy | .env وruntime وfeature.json متجاهَلة؛ source ما فيهش مفاتيح Google أو imports قديمة |
| Spec Kit | CLI 1.2.0، Codex/PowerShell، Git extension 1.0.1، official branch/spec/plan/tasks scripts نجحت |
| Google/n8n/عملاء agents | لم يُجرّبوا حي؛ خارج تأسيس المشروع |
| Docker وGitHub Actions | ملفات التشغيل/CI جاهزة؛ لم تُشغّل بيئة container أو CI بعيد |

## Review result

تغيير bootstrap بيحسن ملكية الملفات والتوثيق من غير تغيير توليد المتصفح. أصل الـLICENSE محفوظ. المفتاح اتغير اسمه عمدًا؛ لازم إعداد .env جديد أو ضبط VIREL_API_KEY في environment. Google profile قديم لم ينتقل. العيوب الموروثة مسجلة في تقرير التأسيس وخطة المراحل؛ التأسيس مش إقرار بأنها اتصلحت.

## Local delivery

commit المصدر ثم commit التوثيق والتحقق على branch المرحلة 001، وبعدها merge محلي في main وtag v0.1.0. GitHub push/CI/branch protection متبقّيين لحد URL repo. أي نجاح بعيد يتسجل لاحقًا في متابعة المشروع.

</div>
