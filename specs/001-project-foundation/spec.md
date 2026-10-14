<div class="rtl-doc" dir="rtl" lang="ar" style="direction: rtl; text-align: right;">

# Feature Specification: تأسيس Virel

**Feature Branch**: <code dir="ltr" style="unicode-bidi: isolate;">001-project-foundation</code> | **Created**: 2026-10-14 | **Status**: Implemented locally; remote verification pending

**Input**: تنظيم نسخة AI Studio كبراند مستقل، نقل المستخدم فقط، RTL، خطة تدريجية وSpec Kit وGit. الاسم المعتمد Virel، والفولدر مستقل؛ Google session الأصلية تفضل مكانها.

## User Scenarios & Testing

### US1 — نسخة مستقلة قابلة للتشغيل (P1)
كمطور أقدر أشتغل في Virel بدون اعتماد على source الفولدر القديم.

**Acceptance**: Given الكود المنقول، When نستورد app ونشغّل الاختبارات، Then imports تشير لـvirel والـ١٧ اختبار تنجح. Given مسار تشغيل مختلف، Then env/profile/session مرتبطة بجذر Virel. Given repo، Then بيانات Google وenv الحقيقي غير tracked.

### US2 — الوصول للملف وقراءة الشرح (P1)
كمطور عربي أقدر أوصل لملف المهمة وأقرأ نص عربي/English من غير قلب الاتجاه.

**Acceptance**: README يربط الخطة والخريطة والأمثلة والتقرير؛ كل ملف source له مسؤولية مسجلة؛ RTL ظاهر والكود LTR في HTML-enabled Markdown preview. الروابط الداخلية سليمة.

### US3 — مراحل محفوظة وميّزات صادقة (P2)
كمطور أقدر أعرف الخطوة التالية ومتى تعتبر ناجحة.

**Acceptance**: official Spec Kit وGit extension موجودين، constitution مكتوبة، stage001 في branch مستقل ثم merge/tag محليين، roadmap تحدد native acceptance. GitHub push وCI البعيد يتوقفوا على استلام URL repo، مش بيتوصفوا مكتملين.

## Requirements

- **FR-001**: نقل source المستخدم والاختبارات والتشغيل فقط؛ حفظ LICENSE الأصلي وعدم نسخ private runtime.
- **FR-002**: rebrand الحزمة والإعدادات والمسارات والـDocker والاختبارات إلى Virel مع حفظ سلوك browser الموروث.
- **FR-003**: runtime في فولدر متجاهل؛ تحميل env/profile من جذر المشروع؛ login والخادم على نفس profile/session.
- **FR-004**: docs عربية RTL، code LTR، خريطة ومسار طلب وأمثلة وتقرير حذف وحدود وخطة قصيرة.
- **FR-005**: تهيئة Spec Kit من الأدوات الرسمية، constitution، branch وسجل محلي وCI workflow.
- **FR-006**: إثبات محلي وعدم ادعاء Google/n8n/Codex حي أو تنفيذ المراحل القادمة.

## Success Criteria

- **SC-001**: الـ١٦ اختبار موروث + اختبار المسارات الجديد ينجح من المشروع الجديد؛ لا Google requests في الاختبارات.
- **SC-002**: لا private files tracked ولا imports قديمة في source/tests/launchers.
- **SC-003**: preview RTL وLTR للكود يُراجع بصريًا؛ headings/tables/code محفوظة.
- **SC-004**: feature artifacts بلا template placeholders وروابط التوثيق الداخلية صحيحة؛ Git main وfeature/tag محفوظين.

## Edge Cases and Scope

غياب GitHub URL يمنع الرفع واختبارات Actions البعيدة فقط. بروفايل جديد يحتاج manual Google login؛ نقل القديم تلقائيًا خارج النطاق. viewer اللي يمنع HTML مش هدف إثبات RTL. HTTP/SSE/history/model defects الموروثة موثقة، وتصليحها في مراحلها؛ ولا ملف feature مستقبلي يتخلق فاضي. تغيير UI الحقيقي أو ترقيات provider مش ضمن المرحلة دي.

</div>
