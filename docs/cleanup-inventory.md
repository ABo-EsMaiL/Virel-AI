# سجل الملفات المحذوفة من النسخة السابقة

القائمة دي تخص تنظيف النسخة القديمة قبل تأسيس Virel AI؛ مش ملفات اتمسحت من Virel AI بعد تأسيسه. المجموع ١٣١ ملف و٢٣٬٧٨٦٬٦٦٣ بايت.

| الحاجة | العدد | الدليل/السبب |
|---|---:|---|
| `pow_solver.py` | 1 | خاص بتحديات ChatGPT؛ مفيش caller/import، وإشارة Docker كانت COPY فقط |
| `stealth.min.js` | 1 | الحقن اتشال سابقًا من start، ومفيش قراءة تانية للملف |
| `test_webdriver.py`, `test_webdriver2.py` | 2 | تجارب موقع bot.sannysoft.com، بتشغّل browser عند import، لا تختبر gateway |
| `test_vision_manual.py` | 1 | مسار صيدلية خارجي وPDF شخصي ومفتاح ثابت؛ اتعوض باختبار base64 وHTTP مستقل |
| `powershell.cmd` | 1 | wrapper غير مرتبط بتشغيل المشروع |
| فيديو `Google AI Studio - Chromium 2026-09-23 12-57-27.mp4` | 1 | تسجيل شاشة، لا يقرأه أي جزء من التطبيق |
| `debug_screen.png`, `debug_state.png`, `debug_stuck.png`, `scratch_studio_tools.png` | 4 | نواتج وصور تشخيص، مش inputs؛ debug_state قد يُنشأ تاني |
| `temp_uploads/upload_*.webp` | 117 | نواتج صور requests قديمة؛ لا يوجد خادم HTTP محلي يعمل وقت الحذف؛ أصلها محفوظ بالأرشيف |
| `__pycache__/app.cpython-312.pyc`, `app.cpython-313.pyc` | 2 | نواتج Python، تعاد تلقائيًا |
| `.github/FUNDING.yml` | 1 | تمويل المشروع الأصلي، مش workflow أو إعداد تشغيل |

المجموع 131. حذف مجلدات فارغة أو bytecode مولد أثناء الاختبارات مش محسوب كملفات أصلية إضافية. المجلدات runtime مثل temp_uploads و__pycache__ طبيعي تظهر تاني.
