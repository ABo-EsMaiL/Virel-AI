<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# خطة Virel — واحدة واحدة

**المرحلة الحالية: 001 تأسيس المشروع. اللي بعدها: 002 نص في n8n.** التنفيذ للمراحل القادمة يبدأ بعد اتفاقنا على spec المرحلة. الجدول ترتيب عمل مقترح، مش تقرير ميزات اشتغلت.

## إمتى نقول مرحلة خلصت؟

الاختبارات القديمة تنجح، اختبارات المرحلة تنجح، والعميل الحقيقي يبعث ويرجع بالطريقة الطبيعية. نسجل إصدار العميل، اسم العملية، المدخل، الموديل الفعلي في UI، النتيجة وتاريخ التجربة. في n8n ما نحسبش Code node أو HTTP Request بديل على إنه توافق native.

| مرحلة / اسم branch المقترح | نعمل إيه؟ | إثبات القبول |
|---|---|---|
| <code dir="ltr" style="unicode-bidi: isolate;">001-project-foundation</code> | اسم مستقل، ملفات مستخدمة، RTL، Spec Kit، Git، CI | ١٧ اختبار محلي + مراجعة نقل الملفات؛ CI البعيد بعد إنشاء repo |
| <code dir="ltr" style="unicode-bidi: isolate;">002-n8n-text</code> | credential، models، Chat JSON، أخطاء صريحة، readiness وحماية تشخيص الخادم | native Generate a Chat Completion يرجع نص؛ auth/busy/timeout/UI error يتشافوا صح |
| <code dir="ltr" style="unicode-bidi: isolate;">003-history-sessions</code> | حفظ الأدوار والـhistory، fresh replay، جلسات isolated للـdelta | طلبان مرتبطان يفتكروا صح؛ عميلان ما يشوفوش بعض؛ مفيش history مكرر |
| <code dir="ltr" style="unicode-bidi: isolate;">004-n8n-vision</code> | image-only وimage+text، URL/base64/binary حسب node، validation وحدود وتنظيف | native image analysis + حالة صورة فقط؛ مدخل غير صالح يرجع خطأ |
| <code dir="ltr" style="unicode-bidi: isolate;">005-n8n-responses-pdf</code> | Responses JSON مضبوط، PDF مباشر/FileID، upload/list/delete اللازمة | native Model Response بنص وPDF؛ الرد يظهر في node، حذف الملفات يعمل |
| <code dir="ltr" style="unicode-bidi: isolate;">006-n8n-audio-input</code> | voice/audio multipart وتفريغ وترجمة عند دعم UI والموديل | native Transcribe/Translate من binary معروف؛ الناتج والحجم والمدة صحيحين |
| <code dir="ltr" style="unicode-bidi: isolate;">007-model-routing</code> | كتالوج قدرات حقيقي، تغيير UI مؤكد، اختيار مناسب لكل نوع | موديلان متاحان؛ يثبت الاسم بعد الاختيار؛ غير المتاح يترفض |
| <code dir="ltr" style="unicode-bidi: isolate;">008-video-input</code> | رفع فيديو وتحليله مع حدود مدة/حجم | عميل طبيعي يعرض video input فعلًا؛ لو n8n node مفيهاش مدخل فيديو نسجل ده |
| <code dir="ltr" style="unicode-bidi: isolate;">009-n8n-images</code> | توليد وتعديل صور وإرجاع ملفات حقيقية | native Generate/Edit Image؛ الملف صالح وممكن node بعدها تستخدمه |
| <code dir="ltr" style="unicode-bidi: isolate;">010-n8n-audio-output</code> | توليد صوت بصيغة وملف مناسبين | native Generate Audio؛ تشغيل الملف والتحقق من الصيغة |
| <code dir="ltr" style="unicode-bidi: isolate;">011-n8n-video-output</code> | توليد فيديو وjobs/polling/download حسب البروتوكول | native Generate Video؛ job ينتهي أو يفشل بوضوح، وملف قابل للتشغيل |
| <code dir="ltr" style="unicode-bidi: isolate;">012-tools-agents</code> | tools، tool_choice، tool_calls IDs، tool results، إكمال الدورة | native n8n Agent يستدعي أداة ويرجع نتيجتها؛ مش كلام فيه JSON شبه tool call |
| <code dir="ltr" style="unicode-bidi: isolate;">013-streaming</code> | live DOM deltas، SSE صحيح لكل adapter، cancel/timeout، أخطاء أثناء stream | النص يصل قبل نهاية التوليد، مفيش تكرار، والنهاية صحيحة؛ الرجوع لـJSON يظل شغال |
| <code dir="ltr" style="unicode-bidi: isolate;">014-langchain</code> | استعمال ChatOpenAI أو integration طبيعي حسب البروتوكول | invoke، history، media/tools/stream المدعومين بلا adapter خاص في كود العميل |
| <code dir="ltr" style="unicode-bidi: isolate;">015-langgraph</code> | نفس integration داخل graph/state/tool loop | تشغيل graph وتكملته وإلغاءه؛ حالته مستقلة عن شات browser |
| <code dir="ltr" style="unicode-bidi: isolate;">016-codex</code> | استكمال Responses/events/tools اللي إصدار Codex يحتاجها | جلسة عميل حقيقي تقرأ ملف وتنفذ tool وتكمل بعد النتيجة |
| <code dir="ltr" style="unicode-bidi: isolate;">017-claude-code</code> | Anthropic Messages adapter بما يحتاجه العميل | tool loop وhistory وstream في العميل الحقيقي؛ اختبار حدود استخدام موديل غير Claude |
| <code dir="ltr" style="unicode-bidi: isolate;">018-other-clients</code> | VS Code، OpenCode، Hermes وغيرهم، واحد واحد | نسجل الإصدار ودعم custom endpoint والبروتوكول؛ نجاح عميل مش دليل على الباقي |

لو عميل محتاج streaming بدري ننقل المرحلة 013 قبل تكامله. توليد الوسائط يتوقف على اللي **واجهة الحساب والموديل المختار** بيوفروه فعلًا؛ مفيش switch يخلق ميزة غير موجودة. Embeddings/moderation/conversations وأي عمليات إضافية ما تتوصفش مدعومة إلا بعد تنفيذ واختبار مستقل. n8n ملهاش شهادة «كل nodes» لمجرد نجاح النص.

## هنستخدم الشاتين إمتى؟

| العميل بيبعت إيه؟ | وضع المتصفح المستهدف |
|---|---|
| history كاملة كل request، زي عملاء agents كتير | شات جديد لكل request، وإرسال history مرة واحدة بأدوارها |
| آخر رسالة بس وعايز server يحتفظ بالسياق | شات ثابت **خاص بالجلسة** مع session ID/reset وسياسة انتهاء |
| طلب مستقل | شات جديد |

الوضع الحالي <code dir="ltr" style="unicode-bidi: isolate;">CLEAR_CHAT_ON_REQUEST=false</code> تبويب واحد مشترك؛ مش نظام sessions ولا اختيار مناسب لعدة عملاء. شات جديد يمنع تراكم/تكرار السياق في المتصفح، لكنه مش بيصغّر history المرسلة ولا يلغي حدود Google.

## دورة كل مرحلة

1. نكتب spec صغيرة فيها اللي داخل المرحلة واللي خارجها وحالات القبول.
2. Spec Kit Git extension ينشئ branch واحد بالرقم التالي. نحفظ spec/plan/tasks في <code dir="ltr" style="unicode-bidi: isolate;">specs/&lt;branch&gt;/</code>.
3. تنفيذ واختبارات محلية ثم تجربة node/client حقيقي. نضيف evidence بالحالات الفاشلة والناجحة.
4. مراجعة diff، PR على GitHub، checks ناجحة، ثم merge في main وtag للنسخة.
5. نبدأ اللي بعدها. قبل وجود repo، commits وmerge محليين فقط؛ مفيش push اتعمل.

قوالب العمل من [Spec Kit الرسمي](https://github.com/github/spec-kit). native PDF وأنواع رسائل Model Response موثقة في [n8n Text operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/text-operations/). Codex له متطلبات Responses نختبرها في [إعدادات Codex](https://learn.chatgpt.com/docs/config-file/config-reference)، وClaude Code له [متطلبات gateway](https://code.claude.com/docs/en/llm-gateway-protocol)؛ تشابه JSON لوحده مش اختبار توافق.

</div>
