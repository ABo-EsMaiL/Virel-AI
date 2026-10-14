# خطة Virel AI — واحدة واحدة

**المرحلة الحالية: 001 تأسيس المشروع. اللي بعدها: 002 نص في n8n.** التنفيذ للمراحل القادمة يبدأ بعد اتفاقنا على spec المرحلة. الجدول ترتيب عمل مقترح، مش تقرير ميزات اشتغلت.

## إمتى نقول مرحلة خلصت؟

الاختبارات القديمة تنجح، اختبارات المرحلة تنجح، والعميل الحقيقي يبعث ويرجع بالطريقة الطبيعية. نسجل إصدار العميل، اسم العملية، المدخل، الموديل الفعلي في UI، النتيجة وتاريخ التجربة. في n8n ما نحسبش Code node أو HTTP Request بديل على إنه توافق native.

| مرحلة / اسم branch المقترح | نعمل إيه؟ | إثبات القبول |
|---|---|---|
| `001-project-foundation` | اسم مستقل، ملفات مستخدمة، RTL، Spec Kit، Git، CI | ١٧ اختبار محلي + مراجعة نقل الملفات؛ CI البعيد بعد إنشاء repo |
| `002-n8n-text` | credential، models، Chat JSON، usage الطلب للنص، أخطاء صريحة، readiness وحماية تشخيص الخادم | native Generate a Chat Completion يرجع نص وusage بمصدر واضح؛ auth/busy/timeout/UI error يتشافوا صح |
| `003-history-sessions` | حفظ الأدوار والـhistory، fresh replay، جلسات isolated للـdelta، سجل usage للطلب والجلسة | طلبان مرتبطان يفتكروا صح؛ عميلان ما يشوفوش بعض؛ مفيش history مكرر ولا usage بيتحسب مرتين |
| `004-n8n-vision` | image-only وimage+text، URL/base64/binary حسب node، validation وحدود وتنظيف | native image analysis + حالة صورة فقط؛ مدخل غير صالح يرجع خطأ |
| `005-n8n-responses-pdf` | Responses JSON مضبوط، PDF مباشر/FileID، upload/list/delete اللازمة | native Model Response بنص وPDF؛ الرد يظهر في node، حذف الملفات يعمل |
| `006-n8n-audio-input` | voice/audio multipart وتفريغ وترجمة عند دعم UI والموديل | native Transcribe/Translate من binary معروف؛ الناتج والحجم والمدة صحيحين |
| `007-model-routing` | كتالوج قدرات حقيقي، تغيير UI مؤكد، اختيار مناسب لكل نوع | موديلان متاحان؛ يثبت الاسم بعد الاختيار؛ غير المتاح يترفض |
| `008-video-input` | رفع فيديو وتحليله مع حدود مدة/حجم | عميل طبيعي يعرض video input فعلًا؛ لو n8n node مفيهاش مدخل فيديو نسجل ده |
| `009-n8n-images` | توليد وتعديل صور وإرجاع ملفات حقيقية | native Generate/Edit Image؛ الملف صالح وممكن node بعدها تستخدمه |
| `010-n8n-audio-output` | توليد صوت بصيغة وملف مناسبين | native Generate Audio؛ تشغيل الملف والتحقق من الصيغة |
| `011-n8n-video-output` | توليد فيديو وjobs/polling/download حسب البروتوكول | native Generate Video؛ job ينتهي أو يفشل بوضوح، وملف قابل للتشغيل |
| `012-tools-agents` | tools، tool_choice، tool_calls IDs، tool results، إكمال الدورة | native n8n Agent يستدعي أداة ويرجع نتيجتها؛ مش كلام فيه JSON شبه tool call |
| `013-streaming` | live DOM deltas، SSE صحيح لكل adapter، cancel/timeout، أخطاء أثناء stream | النص يصل قبل نهاية التوليد، مفيش تكرار، والنهاية صحيحة؛ الرجوع لـJSON يظل شغال |
| `014-langchain` | استعمال ChatOpenAI أو integration طبيعي حسب البروتوكول | invoke، history، media/tools/stream المدعومين بلا adapter خاص في كود العميل |
| `015-langgraph` | نفس integration داخل graph/state/tool loop | تشغيل graph وتكملته وإلغاءه؛ حالته مستقلة عن شات browser |
| `016-codex` | استكمال Responses/events/tools اللي إصدار Codex يحتاجها | جلسة عميل حقيقي تقرأ ملف وتنفذ tool وتكمل بعد النتيجة |
| `017-claude-code` | Anthropic Messages adapter بما يحتاجه العميل | tool loop وhistory وstream في العميل الحقيقي؛ اختبار حدود استخدام موديل غير Claude |
| `018-other-clients` | VS Code، OpenCode، Hermes وغيرهم، واحد واحد | نسجل الإصدار ودعم custom endpoint والبروتوكول؛ نجاح عميل مش دليل على الباقي |

لو عميل محتاج streaming بدري ننقل المرحلة 013 قبل تكامله. توليد الوسائط يتوقف على اللي **واجهة الحساب والموديل المختار** بيوفروه فعلًا؛ مفيش switch يخلق ميزة غير موجودة. Embeddings/moderation/conversations وأي عمليات إضافية ما تتوصفش مدعومة إلا بعد تنفيذ واختبار مستقل. n8n ملهاش شهادة «كل nodes» لمجرد نجاح النص.

## حساب usage من أول المراحل

[سياسة usage](../docs/usage.md) جزء من قبول المشروع. المرحلة 002 تبدأ عدّ الطلب للنص؛ 003 تربطه بالجلسة؛ كل مرحلة media/tools توسع الحساب لمدخلاتها، و013 تضيف usage النهائي في stream حسب عقد العميل. نفضّل أرقام المصدر الفعلية ونعلن أي تقدير أو نقص؛ ما نستخدمش عدد الكلمات كأنه توكنز.

## هنستخدم الشاتين إمتى؟

| العميل بيبعت إيه؟ | وضع المتصفح المستهدف |
|---|---|
| history كاملة كل request، زي عملاء agents كتير | شات جديد لكل request، وإرسال history مرة واحدة بأدوارها |
| آخر رسالة بس وعايز server يحتفظ بالسياق | شات ثابت **خاص بالجلسة** مع session ID/reset وسياسة انتهاء |
| طلب مستقل | شات جديد |

الوضع الحالي `CLEAR_CHAT_ON_REQUEST=false` تبويب واحد مشترك؛ مش نظام sessions ولا اختيار مناسب لعدة عملاء. شات جديد يمنع تراكم/تكرار السياق في المتصفح، لكنه مش بيصغّر history المرسلة ولا يلغي حدود Google.

## دورة كل مرحلة

1. نكتب spec صغيرة فيها اللي داخل المرحلة واللي خارجها وحالات القبول.
2. Spec Kit Git extension ينشئ branch واحد بالرقم التالي. نحفظ spec/plan/tasks في `specs/<branch>/`.
3. تنفيذ واختبارات محلية ثم تجربة node/client حقيقي. نضيف evidence بالحالات الفاشلة والناجحة.
4. مراجعة diff، PR على GitHub، checks ناجحة، ثم merge في main وtag للنسخة.
5. نبدأ اللي بعدها. التأسيس اترفع على [Virel-AI](https://github.com/ABo-EsMaiL/Virel-AI)، وchecks التأسيس نجحت على GitHub. أي تحديث له evidence وإصدار واضح.

قوالب العمل من [Spec Kit الرسمي](https://github.com/github/spec-kit). native PDF وأنواع رسائل Model Response موثقة في [n8n Text operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/text-operations/). Codex له متطلبات Responses نختبرها في [إعدادات Codex](https://learn.chatgpt.com/docs/config-file/config-reference)، وClaude Code له [متطلبات gateway](https://code.claude.com/docs/en/llm-gateway-protocol)؛ تشابه JSON لوحده مش اختبار توافق.
