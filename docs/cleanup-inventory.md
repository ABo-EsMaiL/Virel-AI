<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# سجل الملفات المحذوفة من النسخة السابقة

القائمة دي تخص تنظيف النسخة القديمة قبل تأسيس Virel؛ مش ملفات اتمسحت من Virel بعد تأسيسه. المجموع ١٣١ ملف و٢٣٬٧٨٦٬٦٦٣ بايت.

| الحاجة | العدد | الدليل/السبب |
|---|---:|---|
| <code dir="ltr" style="unicode-bidi: isolate;">pow_solver.py</code> | 1 | خاص بتحديات ChatGPT؛ مفيش caller/import، وإشارة Docker كانت COPY فقط |
| <code dir="ltr" style="unicode-bidi: isolate;">stealth.min.js</code> | 1 | الحقن اتشال سابقًا من start، ومفيش قراءة تانية للملف |
| <code dir="ltr" style="unicode-bidi: isolate;">test_webdriver.py</code>, <code dir="ltr" style="unicode-bidi: isolate;">test_webdriver2.py</code> | 2 | تجارب موقع bot.sannysoft.com، بتشغّل browser عند import، لا تختبر gateway |
| <code dir="ltr" style="unicode-bidi: isolate;">test_vision_manual.py</code> | 1 | مسار صيدلية خارجي وPDF شخصي ومفتاح ثابت؛ اتعوض باختبار base64 وHTTP مستقل |
| <code dir="ltr" style="unicode-bidi: isolate;">powershell.cmd</code> | 1 | wrapper غير مرتبط بتشغيل المشروع |
| فيديو <code dir="ltr" style="unicode-bidi: isolate;">Google AI Studio - Chromium 2026-09-23 12-57-27.mp4</code> | 1 | تسجيل شاشة، لا يقرأه أي جزء من التطبيق |
| <code dir="ltr" style="unicode-bidi: isolate;">debug_screen.png</code>, <code dir="ltr" style="unicode-bidi: isolate;">debug_state.png</code>, <code dir="ltr" style="unicode-bidi: isolate;">debug_stuck.png</code>, <code dir="ltr" style="unicode-bidi: isolate;">scratch_studio_tools.png</code> | 4 | نواتج وصور تشخيص، مش inputs؛ debug_state قد يُنشأ تاني |
| <code dir="ltr" style="unicode-bidi: isolate;">temp_uploads/upload_*.webp</code> | 117 | نواتج صور requests قديمة؛ لا يوجد خادم HTTP محلي يعمل وقت الحذف؛ أصلها محفوظ بالأرشيف |
| <code dir="ltr" style="unicode-bidi: isolate;">__pycache__/app.cpython-312.pyc</code>, <code dir="ltr" style="unicode-bidi: isolate;">app.cpython-313.pyc</code> | 2 | نواتج Python، تعاد تلقائيًا |
| <code dir="ltr" style="unicode-bidi: isolate;">.github/FUNDING.yml</code> | 1 | تمويل المشروع الأصلي، مش workflow أو إعداد تشغيل |

المجموع 131. حذف مجلدات فارغة أو bytecode مولد أثناء الاختبارات مش محسوب كملفات أصلية إضافية. المجلدات runtime مثل temp_uploads و__pycache__ طبيعي تظهر تاني.

</div>
