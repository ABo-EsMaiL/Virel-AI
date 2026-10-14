# الطلب شكله إيه؟ والملفات تيجي إزاي؟

أمثلة JSON دي لشرح اللي node/SDK بيبعته؛ مش مطلوب منك تعمل Code node. أي مثال مكتوب عليه «مستهدف» **لسه مش شغال في Virel AI**. رابط baseURL للعميل على نفس الجهاز `http://localhost:8001/v1`، وAuthorization هو `Bearer <VIREL_API_KEY>`.

## الموجود حاليًا: Chat نص

```json
{"model":"<available-ui-model>","messages":[{"role":"user","content":"قول أهلاً بالمصري"}],"stream":false}
```

يروح POST `/v1/chat/completions`. الرد النصي موجود في `choices[0].message.content`. `stream:true` يطلب SSE؛ ده موجود محليًا لكنه محتاج اختبار حي. اختيار موديل هنا لازم يبقى موجود فعلًا في UI؛ الكتالوج الحالي ثابت.

## الصور: تحويل موجود، native acceptance لسه

```json
{"model":"<vision-ui-model>","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,<bytes>"}},{"type":"text","text":"إيه اللي في الصورة؟"}]}],"stream":false}
```

صورة بس: نشيل جزء text. image preparation موجود في Chat، لكن صورة-only وURL والحدود لسه مش certified من node حقيقية. المسارات المحلية في image_url سلوك موروث هنقفله عند trust boundary؛ ما تستخدمهاش كحل لنقل ملفات من n8n.

## PDF: مستهدف في المرحلة 005

الطريق الطبيعي: node بتنتج binary زي `data` → `OpenAI / Text / Generate a Model Response` → Messages من نوع **File** واختيار binary. أو `OpenAI / File / Upload a File` ثم تمرير FileID في رسالة File. المصدر والعملية حسب إصدار n8n اللي هنجربه. راجع [Text operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/text-operations/) و[File operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/file-operations/).

رفع ملف عادة multipart فيه `file` و`purpose` على `/v1/files`؛ يرجع file ID. بعدها Model Response يبعته كده:

```json
{"model":"<pdf-ui-model>","input":[{"role":"user","content":[{"type":"input_file","file_id":"file_example"},{"type":"input_text","text":"لخّص الملف"}]}],"stream":false}
```

دي عقود هننفذها ونطابقها مع الطلب الفعلي من node؛ `/v1/files` وinput_file **مش منفذين دلوقتي**. رفع الملفات وعمرها وحذفها جزء من المرحلة، مش تحويل PDF لنص داخل Code node.

## باقي الوسائط

| اللي هتبعته/تستلمه | طريقة العميل الطبيعية المستهدفة | حالة Virel AI |
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

`localhost` جوه container يشير للـcontainer نفسه. على Docker Desktop خلي baseURL `http://host.docker.internal:8001/v1` لو Virel AI على الجهاز؛ لو الخدمتين في نفس شبكة Compose استخدم اسم خدمة Virel. هنثبت credential URL الفعلي في تجربة المرحلة 002.
