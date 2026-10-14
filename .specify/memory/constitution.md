<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# Virel Constitution

## Core Principles

### I. Native Client Acceptance
ميزة توافق ما تعتبرش كاملة إلا لما node/SDK/agent طبيعي يستخدمها بدون glue مخصص عند العميل. نجاح HTTP mock شرط محلي، مش إثبات توافق حي. نسجل إصدار العميل والعملية والموديل والمدخل والنتيجة.

### II. Incremental Delivery Without Regressions
مرحلة واحدة متفق عليها، branch واحد، وspec وplan وtasks واختبارات قبول. الاختبارات القديمة لازم تفضل ناجحة؛ ممنوع تخفيض الاختبارات أو تغيير العقد علشان نخبي failure. التصليح المكسّر للعقد يتوثق ويتختبر.

### III. Clear Boundaries and Truthful Capabilities
بروتوكولات HTTP منفصلة عن تحويل المدخلات وعن أفعال browser. كل feature في مكان معروف؛ مفيش scaffolding فاضي للمستقبل. أي قدرة أو موديل لازم تكون متاحة فعلًا في الواجهة؛ الخطأ يرجع كخطأ، مش نجاح وهمي أو تبديل صامت.

### IV. Explicit History and Isolation
history كاملة تتنفذ في fresh chat مرة واحدة بأدوارها؛ delta-only يستخدم جلسة خاصة بمعرف واضح. مفيش تبويب سياق مشترك بين العملاء ولا history مزدوجة. clear=false الموروث مش تنفيذ للمبدأ ده لحد مرحلة sessions.

### V. Private Runtime and Readable Documentation
جلسة Google والأسرار والملفات المحلية خارج Git وDocker context. مدخلات الملفات والروابط تخضع للحدود والتحقق قبل إتاحة قدراتها. الشرح العربي قصير وواضح RTL؛ هوية Virel مستقلة مع حفظ LICENSE الأصلي.

## Scope and Constraints

الهدف gateway متعدد البروتوكولات والقدرات، يبدأ AI Studio. حدود UI/حساب Google والموديل تتوثق؛ لا ندّعي تجاوز quotas أو دعم كل عميل بلا تجربة. مرحلة التأسيس تحفظ سلوك browser الموروث وتوثق عيوبه؛ القيود الأمنية والعقود الناقصة تتصلح في مراحلها قبل إعلان القدرة آمنة أو متوافقة.

## Development Workflow

Spec Kit الرسمي: specify → plan → tasks → implement → converge → tests → native client evidence → review → merge/tag. كل مرحلة لها <code dir="ltr" style="unicode-bidi: isolate;">specs/&lt;feature&gt;/</code>. لا يبدأ تنفيذ roadmap كاملة بمجرد كتابة constitution أو plan. main يحتفظ بآخر مرحلة مستقرة؛ GitHub checks وbranch protection يتفعلوا لما repo تبقى موجودة.

## Governance

القواعد دي تسجيل لمتطلبات المستخدم في تأسيس Virel. أي تغيير جوهري فيها يتشرح للمستخدم ويتوثق بإصدار وتاريخ، مع مراجعة أثره على specs والاختبارات والوثائق. principles الحالية معيار قبول للمراحل القادمة؛ الحالات الموروثة المخالفة مسجلة في تقرير التأسيس، مش اتصلحت لمجرد كتابة القواعد.

**Version**: 1.0.0 | **Ratified**: 2026-10-14 | **Last Amended**: 2026-10-14

</div>
