<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# الطلب شكله إيه؟ والملفات تيجي إزاي؟

أمثلة JSON دي لشرح اللي node/SDK بيبعته؛ مش مطلوب منك تعمل Code node. أي مثال مكتوب عليه «مستهدف» **لسه مش شغال في Virel**. رابط baseURL للعميل على نفس الجهاز <code dir="ltr" style="unicode-bidi: isolate;">http://localhost:8001/v1</code>، وAuthorization هو <code dir="ltr" style="unicode-bidi: isolate;">Bearer &lt;VIREL_API_KEY&gt;</code>.

## الموجود حاليًا: Chat نص

<div dir="ltr" style="direction: ltr; text-align: left;">

```json
{"model":"<available-ui-model>","messages":[{"role":"user","content":"قول أهلاً بالمصري"}],"stream":false}
```

</div>

يروح POST <code dir="ltr" style="unicode-bidi: isolate;">/v1/chat/completions</code>. الرد النصي موجود في <code dir="ltr" style="unicode-bidi: isolate;">choices[0].message.content</code>. <code dir="ltr" style="unicode-bidi: isolate;">stream:true</code> يطلب SSE؛ ده موجود محليًا لكنه محتاج اختبار حي. اختيار موديل هنا لازم يبقى موجود فعلًا في UI؛ الكتالوج الحالي ثابت.

## الصور: تحويل موجود، native acceptance لسه

<div dir="ltr" style="direction: ltr; text-align: left;">

```json
{"model":"<vision-ui-model>","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,<bytes>"}},{"type":"text","text":"إيه اللي في الصورة؟"}]}],"stream":false}
```

</div>

صورة بس: نشيل جزء text. image preparation موجود في Chat، لكن صورة-only وURL والحدود لسه مش certified من node حقيقية. المسارات المحلية في image_url سلوك موروث هنقفله عند trust boundary؛ ما تستخدمهاش كحل لنقل ملفات من n8n.

## PDF: مستهدف في المرحلة 005

الطريق الطبيعي: node بتنتج binary زي <code dir="ltr" style="unicode-bidi: isolate;">data</code> → <code dir="ltr" style="unicode-bidi: isolate;">OpenAI / Text / Generate a Model Response</code> → Messages من نوع **File** واختيار binary. أو <code dir="ltr" style="unicode-bidi: isolate;">OpenAI / File / Upload a File</code> ثم تمرير FileID في رسالة File. المصدر والعملية حسب إصدار n8n اللي هنجربه. راجع [Text operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/text-operations/) و[File operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/file-operations/).

رفع ملف عادة multipart فيه <code dir="ltr" style="unicode-bidi: isolate;">file</code> و<code dir="ltr" style="unicode-bidi: isolate;">purpose</code> على <code dir="ltr" style="unicode-bidi: isolate;">/v1/files</code>؛ يرجع file ID. بعدها Model Response يبعته كده:

<div dir="ltr" style="direction: ltr; text-align: left;">

```json
{"model":"<pdf-ui-model>","input":[{"role":"user","content":[{"type":"input_file","file_id":"file_example"},{"type":"input_text","text":"لخّص الملف"}]}],"stream":false}
```

</div>

دي عقود هننفذها ونطابقها مع الطلب الفعلي من node؛ <code dir="ltr" style="unicode-bidi: isolate;">/v1/files</code> وinput_file **مش منفذين دلوقتي**. رفع الملفات وعمرها وحذفها جزء من المرحلة، مش تحويل PDF لنص داخل Code node.

## باقي الوسائط

| اللي هتبعته/تستلمه | طريقة العميل الطبيعية المستهدفة | حالة Virel |
|---|---|---|
| صورة من binary/URL | OpenAI Image / Analyze Image، أو رسالة Image في Model Response | تجهيز Chat موجود؛ التوافق لسه |
| صوت/voice كمدخل | Audio / Transcribe أو Translate؛ multipart file | غير منفذ |
| فيديو للتحليل | عملية/SDK يعرض video input؛ نثبت وجود مدخل طبيعي أولًا | غير منفذ |
| توليد/تعديل صورة | Image / Generate أو Edit؛ ملف ناتج | غير منفذ |
| توليد صوت | Audio / Generate Audio؛ binary ناتج | غير منفذ |
| توليد فيديو | Video / Generate Video؛ job ثم ملف | غير منفذ |
| استدعاء function | model يرجع tool_calls، **العميل** ينفذ الأداة ويرسل tool result | غير منفذ |

بحث Google في AI Studio مش tool calling لقراءة ملفات جهاز Codex؛ الأداة عند العميل هي اللي تقرأ/تنفذ. ما نحولش كلام الموديل لاستدعاء أداة ونعتبره موثوق من غير validation وعقد صحيح.

## لو n8n جوه Docker

<code dir="ltr" style="unicode-bidi: isolate;">localhost</code> جوه container يشير للـcontainer نفسه. على Docker Desktop خلي baseURL <code dir="ltr" style="unicode-bidi: isolate;">http://host.docker.internal:8001/v1</code> لو Virel على الجهاز؛ لو الخدمتين في نفس شبكة Compose استخدم اسم خدمة Virel. هنثبت credential URL الفعلي في تجربة المرحلة 002.

</div>
