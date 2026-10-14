# حساب التوكنز والـusage

**ده عقد مستهدف للمراحل القادمة، مش counter اتنفّذ بالفعل.** حاليًا Responses بيستخدم عدد الكلمات، وChat مش بيرجع usage. عدد الكلمات مش token count؛ هنصلح ده في المرحلة 002.

## المطلوب

| المستوى | نسجل إيه؟ |
|---|---|
| كل request | request ID، model الفعلي، input/output/total، تفاصيل التفكير وcache إن متاحة، المصدر والدقة، الحالة |
| كل محاولة browser | attempt ID مرتبط بالطلب؛ retry ممكن يستهلك حتى لو العميل ما استلمش رد |
| كل session/chat | session ID منفصل عن تبويب browser، عدد الطلبات، مجموع usage المرصود، الأجزاء المقدرة/المجهولة |
| context الحالي | حجمه الحالي منفصل عن مجموع استهلاك الطلبات؛ مش نفس الرقم |

السجل يحفظ counts ومعرفات وحالة، مش نصوص محادثات أو ملفات أو cookies، ومكانه private runtime. عزل القراءة مرتبط بعزل الجلسات. مش هنضيف database/service جديدة قبل ما spec المرحلة تحدد أصغر تخزين يفي بالمطلوب.

## الرقم ييجي منين؟

1. نختبر رقم خاص **بنفس الطلب** توفره UI أو استجابة التوليد اللي المتصفح استقبلها. مراقبة استجابة المتصفح لا تعني إرسال طلب جديد لـGoogle API. لا Google key ولا SDK مطلوبين بسبب العدّ.
2. لو الرقم يمثل حجم context فقط، ما نسميهوش استهلاك request. نخلي correlation والتوقيت والموديل واضحين، ومش ننسب رقم شات قديم لطلب جديد.
3. لو المصدر ناقص، أي تقدير له طريقة معلنة مرتبطة بالموديل، وأي جزء غير قابل للقياس يبقى unknown. tokenizer خاص بـOpenAI مش دليل على عدد Gemini. النص وحده ما يثبتش توكنز الصورة/الصوت/الفيديو أو التفكير المخفي.

الحقول اللي اتقرت فعلًا تتسجل reported؛ المقدرة estimated؛ غير المعروفة unknown. mixed request يفضل فيه مصدر لكل جزء، ومجموع الجلسة يوضح الناقص. مش بنكتب صفر على إنه مقاس لما الحقيقة إن المعلومة غايبة. الشكل المناسب لـnull/omission/estimated في البروتوكول يتحدد مع اختبار الـSDK وn8n، وإشارة الدقة تبقى واضحة خارج حقول usage القياسية لو العميل بيحتاج ده.

في Google API فيه usage metadata للمدخل والمخرج والتفكير وcache، لكن ده **مش إثبات** إن واجهة AI Studio هتكشفها لنا؛ هنفحصها وقت التجربة. [توثيق Google](https://ai.google.dev/gemini-api/docs/generate-content/tokens). وفي OpenAI الـoutput usage يشمل توكنز قد لا تظهر في النص؛ قراءة النص وحده مش قياس مكافئ. [OpenAI Docs](https://developers.openai.com/api/docs/guides/token-counting).

## الشكل الطبيعي للعميل

Chat Completions: `usage.prompt_tokens` و`usage.completion_tokens` و`usage.total_tokens`. Responses: `usage.input_tokens` و`usage.output_tokens` و`usage.total_tokens`. التفاصيل تتسمى حسب البروتوكول، ونختبر mapping بدون جمع cached/thinking مرتين. نبقي رقم المصدر ومصدره متاحين داخليًا عند اختلاف المعاني بين البروتوكولات؛ أسماء حقول OpenAI لا تحول موديل Gemini إلى موديل OpenAI.

في stream، بعض البروتوكولات بتبعث usage في الحدث النهائي أو عند طلبه؛ نطابق عقد كل واحد. لو العميل فصل قبل النهاية، usage known/partial/unknown وحالة canceled منفصلين؛ ما نعدّش deltas كأنها requests ولا نفترض الاستهلاك صفر.

## الجلسات والـhistory

لو client بيبعث history كاملة في كل request، السياق ده يدخل في قياس الطلب الفعلي كل مرة؛ جمع الاستهلاك عبر الطلبات صحيح. **حجم context الحالي** مش مجموع التاريخ ولا مجموع الاستهلاك. لو browser chat ثابت، نحسب السياق الفعلي اللي اتولد عليه الرد، ونمنع duplication عند إدخال history. لو retry حصل بعد توليد، نسجله كمحاولة مستقلة؛ ما نكرر نفس attempt بسبب قراءة stream أكتر من مرة. Google billing/quota balance شيء منفصل عن telemetry Virel AI؛ ما ندّعيش معرفته من عداداتنا.

## اختبارات القبول

- عربي، إنجليزي، كود وhistory: لا استعمال split كـtoken count.
- مصدر صحيح لنفس الطلب، ثم غياب/تأخر/اختلاف المصدر؛ ما نرجعش عداد الطلب السابق.
- JSON وstream لنفس fixture، final usage بلا تكرار؛ cancel/failure/retry محفوظين بحالتهم.
- جلستان مستقلتان؛ مجموع الجلسة معلوم مقابل مقدر/مجهول، وcontext منفصل.
- media/tools/thinking/cache كل واحد لما مرحلته تتنفذ؛ مفيش أرقام وهمية لإعلان توافق كامل.
