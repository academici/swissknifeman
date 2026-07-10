// Урезанный реальный прогон (P2.4 фикстура): взято из реального workflow-скрипта
// `p1-4-auth-security-review-wf_99bb5940-eb5.js` (loqum, P1.4), export const meta
// скопирован байт-в-байт; тело прогона (FILES/CONTEXT/steps) обрезано — парсер
// wf_status.parse_script_meta читает ТОЛЬКО блок `export const meta` регуляркой.
export const meta = {
  name: 'p1-4-auth-security-review',
  description: 'Adversarial security review of Loqum gateway auth chain (P1.4)',
  phases: [
    { title: 'Review', detail: '5 security-focused finder angles, opus/high' },
    { title: 'Verify', detail: 'adversarial refute pass per finding, opus/high' },
  ],
}
