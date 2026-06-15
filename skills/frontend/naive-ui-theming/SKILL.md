---
name: naive-ui-theming
bucket: frontend
version: 0.1.0
description: "Глобальная тема Naive UI: GlobalThemeOverrides (common + Button/Card/Form/Input/Tag/Tabs…), NConfigProvider в точке входа, тёмная тема naive (darkTheme), связь токенов с Tailwind/CSS-переменными. Активировать при правке config/naive-ui.ts, темы Naive, themeOverrides, NConfigProvider, primaryColor/borderRadius, dark mode под Naive UI."
risk: write
persona: oss-dev
tags: [naive-ui, vue, theming, design-tokens, dark-mode, tailwind, frontend]
requires: []
produces_for: []
outputs: []
snippets: [naive-theme.ts, app.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Naive UI theming

## Контекст

Централизованная настройка внешнего вида Naive UI через **один** объект
`GlobalThemeOverrides`, подключённый в корневой `NConfigProvider`. Цель —
чтобы все кнопки, карточки, формы, инпуты, табы и теги выглядели единообразно
из одного источника правды, а не правились инлайн-стилями по компонентам.

**Когда активировать:**

- Правка или создание `resources/js/config/naive-ui.ts` (или иного модуля темы
  Naive), объекта `themeOverrides` / `GlobalThemeOverrides`.
- Изменение `primaryColor`, `borderRadius`, `fontFamily`, высот компонентов,
  цветов состояний (success/info/warning/error) глобально.
- Настройка пер-компонентных переопределений (`Button`, `Card`, `Form`,
  `Input`, `Tag`, `Tabs`, `Timeline` и т.д.).
- Подключение/правка `NConfigProvider` в точке входа приложения
  (`app.ts`/`main.ts`), порядка провайдеров (modal/message/dialog).
- Включение тёмной темы Naive (`darkTheme`) или связки темы с
  Tailwind/CSS-переменными.

**Не про это:** утилитарные классы и дизайн-токены Tailwind как таковые — в
`frontend/tailwind-conventions`; организация `resources/js/` по слоям — в
`frontend/inertia-vue`. Naive UI — **не** часть Laravel Boost, upstream не нужен.

## Модель темизации Naive UI

Три уровня, от глобального к точечному — выбирай минимально достаточный:

| Уровень | Механизм | Когда |
|:---|:---|:---|
| Глобальный | `themeOverrides` в `NConfigProvider` | дефолты всего приложения (этот скилл) |
| Поддерево | вложенный `NConfigProvider` со своими `themeOverrides` | отдельная зона (например, тёмный сайдбар) |
| Точечный | проп `:theme-overrides` на конкретном компоненте | разовое отклонение одного компонента |

`GlobalThemeOverrides` = `{ common, <ИмяКомпонента>: {...} }`:

- **`common`** — токены, наследуемые всеми компонентами: `primaryColor` (+`Hover`
  /`Pressed`/`Suppl`), `successColor`/`infoColor`/`warningColor`/`errorColor`,
  `fontFamily`, `fontSizeMedium`/`Large`, `heightMedium`, `borderRadius`,
  `borderColor`, `textColorBase`, `bodyColor`. Менять `common` — самый дешёвый
  способ перекрасить всё приложение.
- **Пер-компонент** — ключ = PascalCase-имя без `N` (`Button`, `Card`, `Form`,
  `Input`, `Tag`, `Tabs`). Значения = переменные темы именно этого компонента.
  Имена переменных смотри в `src/<component>/styles/light.ts` пакета `naive-ui`
  или в таблице «Theme Variables» на странице компонента в доках.

## Алгоритм

1. **Один модуль темы.** Держи тему в одном файле, например
   `resources/js/config/naive-ui.ts`, и экспортируй типизированную константу:

   ```ts
   import type { GlobalThemeOverrides } from 'naive-ui';
   export const theme: GlobalThemeOverrides = { common: { /* ... */ } };
   ```

   Тип `GlobalThemeOverrides` обязателен — он даёт автодополнение имён
   переменных и ловит опечатки на этапе сборки.

2. **Сначала `common`, потом компоненты.** Сложи бренд-токены в `common`
   (палитра, шрифт, радиус, базовые высоты). Пер-компонентные блоки добавляй
   только когда `common` недостаточно — не дублируй то, что уже наследуется.

3. **Не хардкодь цвета по месту.** Все бренд-цвета — в `common`/пер-компонент;
   в `.vue` не пиши `style="color:#..."`. Повторяющийся цвет = токен в теме
   (или CSS-переменная, см. п. 7).

4. **Подключи в корневом `NConfigProvider`.** В точке входа оберни приложение в
   `NConfigProvider` с `:theme-overrides="theme"`. Порядок провайдеров снаружи
   внутрь: `NConfigProvider` → `NModalProvider`/`NDialogProvider` →
   `NMessageProvider` → `App`. Провайдеры сообщений/модалок должны быть **внутри**
   config-provider, иначе их всплывающие узлы не получат тему.

5. **Локаль рядом с темой.** `NConfigProvider` принимает `locale`/`dateLocale`
   (`ruRU`, `dateRuRU` из `naive-ui`) — настраивай их там же, где `themeOverrides`,
   это единая точка глобальной конфигурации UI-кита.

6. **Тёмная тема — `darkTheme`.** Импортируй `darkTheme` из `naive-ui` и
   передавай его в `:theme` провайдера, когда приложение в тёмном режиме
   (`:theme="isDark ? darkTheme : null"`). `null` = встроенная светлая тема.
   `themeOverrides` применяется поверх обеих — держи в нём цвета, валидные для
   светлой и тёмной (или вынеси тёмные переопределения в отдельный объект и
   подставляй его при `isDark`).

7. **Связка с Tailwind/CSS-переменными (один источник правды).** Чтобы Naive и
   Tailwind не разъезжались по цветам:

   - Объяви бренд-палитру как CSS-переменные на `:root` (и переопредели их под
     `.dark`), а в Tailwind-конфиге сошлись на них
     (`colors.primary: 'var(--color-primary)'`).
   - В `GlobalThemeOverrides` подставляй те же переменные:
     `primaryColor: 'var(--color-primary)'`. Тогда переключение `.dark` на
     `<html>` меняет и Tailwind-классы, и тему Naive одновременно.
   - Тёмный режим обычно завязан на класс `.dark` у `documentElement`
     (Tailwind-конвенция); тот же флаг используй, чтобы выбрать `darkTheme`
     для Naive (см. п. 6) — один переключатель на оба слоя.

8. **Единицы и консистентность.** Размеры — строки с единицами (`'14px'`,
   `'40px'`, `'8px'`), цвета — hex/rgb/`var(...)`, числовые веса (`fontWeight`) —
   числа или строки согласно типу переменной. Не смешивай `px` и `rem` для
   одного семейства размеров без причины.

## Частые пер-компонентные переменные (шпаргалка)

| Компонент | Типичные переменные |
|:---|:---|
| `Button` | `heightMedium`, `paddingMedium`, `fontSizeMedium`, `fontWeight`, `textColorPrimary`, `textColorHoverPrimary` |
| `Card` | `paddingMedium`, `paddingSmall`, `borderRadius`, `titleFontSizeMedium`, `fontSizeMedium` |
| `Form` | `labelTextColor`, `labelFontSizeTopMedium`, `feedbackFontSizeMedium`, `feedbackHeightMedium`, `blankHeightMedium` |
| `Input` | `border`, `borderHover`, `borderFocus`, `color`, `placeholderColor`, `borderRadius` |
| `Tag` | `borderRadius`, `fontSizeMedium`, `heightMedium`, `padding`, `fontWeightStrong` |
| `Tabs` | `tabFontSizeMedium`, `tabTextColorActiveLine`, `barColor`, `tabGapMediumLine`, `panePaddingMedium` |

Точные имена и суффиксы размеров (`Small`/`Medium`/`Large`) различаются по
компонентам — сверяйся с таблицей Theme Variables компонента, не угадывай.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Завести/расширить объект темы (`common` + пер-компонент) | `snippets/naive-theme.ts` |
| Подключить тему, локаль, dark mode и провайдеры в точке входа | `snippets/app.ts` |

## Чеклист качества

- [ ] Тема — один типизированный `GlobalThemeOverrides` в одном модуле (`config/naive-ui.ts`).
- [ ] Бренд-токены (палитра, шрифт, радиус) живут в `common`, пер-компонент — только сверх необходимого.
- [ ] В `.vue` нет хардкод-цветов/инлайн-стилей, дублирующих токены темы.
- [ ] `NConfigProvider` обёрнут вокруг провайдеров message/modal/dialog (они внутри него), `themeOverrides` и `locale` заданы там.
- [ ] Тёмный режим использует `darkTheme` Naive, завязанный на тот же флаг `.dark`, что и Tailwind.
- [ ] Если палитра общая с Tailwind — единый источник правды через CSS-переменные (`var(--color-*)`), а не два списка цветов.
- [ ] Размеры — строки с единицами; имена переменных сверены по таблице Theme Variables компонента.

## Ссылки

- https://www.naiveui.com/en-US/os-theme/docs/customize-theme
- https://www.naiveui.com/en-US/os-theme/docs/theme — общая модель тем и `darkTheme`
- Переменные компонента: `node_modules/naive-ui/es/<component>/styles/light.ts`
- Связанные скиллы: `frontend/tailwind-conventions`, `frontend/inertia-vue`, `frontend/vue-composition-api`
