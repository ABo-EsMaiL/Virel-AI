# Implementation Plan: تأسيس Virel AI

**Branch**: `001-project-foundation` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

## Summary
نسخة مستقلة في Virel AI، نفس Python/FastAPI/Playwright مع حدود modules الموجودة، rebrand ومسارات runtime، official Spec Kit، docs RTL وCI صغير. مصدر runtime الموروث هو النسخة المنظفة، وما نزودش ميزات provider هنا.

## Technical Context
Python 3.12، FastAPI وPydantic وslowapi وPlaywright، unittest وhttpx للاختبارات. Windows للتجربة المحلية؛ Linux CI مُجهّز ولم يُجرّب عن بعد. متصفح واحد/worker واحد. التخزين profile وmetadata/uploads محلية؛ مفيش DB جديدة أو Google SDK. نسخ dependencies زي النسخة المنظفة.

## Constitution Check
حدود source واضحة؛ native acceptance مستقبلية ومش منسوبة للاختبارات الحالية؛ عيوب history/errors/input الموروثة استثناء baseline موثق للمرحلة الأولى فقط. خصوصية runtime محفوظة؛ docs RTL؛ لا تنفيذ تلقائي للـroadmap.

## Project Structure
`app.py` و`get_session.py` نقطتي تشغيل، `virel/` application وroutes، `tests/` checks، `docs/` مرجع، `tasks/` roadmap، `specs/001-project-foundation/` spec/plan/tasks/evidence، `.specify/` و`.agents/` أدوات رسمية، `runtime/` private ignored.

## Implementation Sequence
1. inventory الملفات الفعالة → نسخ لVirel من غير env/profile.
2. تغيير imports/config/health/Docker/tests، تجميع runtime ومسارات ثابتة بالنسبة لجذر المشروع.
3. إعداد Spec Kit الرسمي والـconstitution؛ Git bootstrap ثم feature branch.
4. توثيق RTL والخريطة والعقود والـroadmap، GitHub checks للـ١٧ اختبار.
5. اختبارات ومراجعة doc links/preview/source/ignore، evidence ثم commit/merge/tag محليًا.

## Validation and Delivery
تشغيل الـ١٧ اختبار بعد نقل المصدر. تحقق path config من cwd مختلف بدون تشغيل Google. MarkdownIt HTML render ثم isolated Chromium preview. فحص diff وGit tracked secrets/old names. لا اختبار Google حي/داخل Docker/Actions remote. يتسجل المطلوب المتبقي بدل اختلاق نجاح.

## Complexity Tracking
مفيش abstraction جديدة أو empty feature modules. browser.py الكبير يفضل زي ما هو في التأسيس؛ تقسيمه يتبع حاجة feature واختباراتها. أدوات Spec Kit متعددة الملفات upstream محتفظين بيها علشان شغله الرسمي، مش بقايا ChatGPT.
