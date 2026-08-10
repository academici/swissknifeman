# Owner refinement — whole-P5 successor authorization — 2026-08-05

Владелец подтвердил, что это третий design-запуск вокруг P5.2, и отверг ещё одну локальную
правку одного item. Требование — смотреть вперёд и согласовать всю фазу P5 так, чтобы исполнение
одного пункта не разрушало Inputs, generation pins или acceptance следующих пунктов.

Владелец разрешил запинить только точную additive successor generation для
contract/runtime/provider/assurance, сохранив terminal G2 и всю P4 history. Поручение включает
финитный owner carrier для нового producer-item, phase-wide producer→consumer reconcile и
downstream P6 generation pin. Оно не разрешает:

- запускать P5.2/P5.3/P5.4 pilot или расходовать любой из 14 D105 admissions;
- переписывать/перегенерировать terminal P4/G2, P5.1 carriers или их frozen parent item IDs;
- обходить package SSOT, admission/security/provider refusal или provider parity;
- расширять successor за точные contract/package/provider/test/assurance/Unreleased paths,
  перечисленные в D108 и P5.5.

Критерий результата этого design-захода: P5.5 является одним явным producer'ом G2B; P5.2,
P5.3, P5.4 и P6 потребляют его именованные terminal outputs; ни один downstream item не
продолжает ссылаться на G2 как на business-capable runtime.

Поскольку frozen D105 carriers содержат `g2_package_digest`, successor не переписывает и не
игнорирует это поле. Новый контракт обязан трактовать его только как точный predecessor pin:
D105 digest равен immutable G2, D108 generation manifest связывает именно этот G2 с единственным
current G2B digest, а запускаемый package обязан совпасть с G2B. Любая другая пара digest'ов
отказывает до intent. D108 не продлевает D105 expiry и не создаёт дополнительный dispatch budget.
