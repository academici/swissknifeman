> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: vueuse-functions
description: Apply VueUse composables where appropriate to build concise, maintainable Vue.js / Nuxt features.
license: MIT
metadata:
    author: SerKo <https://github.com/serkodev>
    version: "1.0"
compatibility: Requires Vue 3 (or above) or Nuxt 3 (or above) project
---

# Функции VueUse

Этот скилл — руководство по принятию решений и реализации для composable-функций VueUse в проектах Vue.js / Nuxt. Он сопоставляет требования с наиболее подходящей функцией VueUse, применяет корректный паттерн использования и отдаёт предпочтение решениям на основе composable-функций перед самописным кодом — чтобы реализации были лаконичными, поддерживаемыми и производительными.

## Когда применять

- Применяй этот скилл всякий раз, когда помогаешь пользователю в разработке на Vue.js / Nuxt.
- Сначала всегда проверяй, может ли функция VueUse реализовать требование.
- Отдавай предпочтение composable-функциям VueUse перед самописным кодом — ради читаемости, поддерживаемости и производительности.
- Сопоставляй требования с наиболее подходящей функцией VueUse и следуй правилу вызова этой функции.
- Сверяйся с полем `Invocation` в таблице функций ниже. Например:
  - `AUTO`: использовать автоматически, когда применимо.
  - `EXTERNAL`: использовать только если пользователь уже установил требуемую внешнюю зависимость; иначе пересмотри решение и предлагай установку только если она действительно нужна.
  - `EXPLICIT_ONLY`: использовать только по явному запросу пользователя.
  > *ПРИМЕЧАНИЕ* Инструкции пользователя в промте или в `AGENTS.md` могут переопределить дефолтное правило `Invocation` функции.

## Функции

Все перечисленные ниже функции — часть библиотеки [VueUse](https://vueuse.org/); каждый раздел группирует функции по их назначению.

ВАЖНО: каждая запись о функции включает краткое `Description` (описание) и подробный `Reference` (справочник). При использовании любой функции всегда сверяйся с соответствующим документом в `./references` для деталей использования (Usage) и объявлений типов (Type Declarations).

### State (Состояние)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`createGlobalState`](references/createGlobalState.md) | Хранить состояния в глобальной области видимости для переиспользования между экземплярами Vue | AUTO |
| [`createInjectionState`](references/createInjectionState.md) | Создать глобальное состояние, которое можно внедрять (inject) в компоненты | AUTO |
| [`createSharedComposable`](references/createSharedComposable.md) | Сделать composable-функцию пригодной к использованию с несколькими экземплярами Vue | AUTO |
| [`injectLocal`](references/injectLocal.md) | Расширенный `inject` с возможностью вызвать `provideLocal`, чтобы предоставить значение в том же компоненте | AUTO |
| [`provideLocal`](references/provideLocal.md) | Расширенный `provide` с возможностью вызвать `injectLocal`, чтобы получить значение в том же компоненте | AUTO |
| [`useAsyncState`](references/useAsyncState.md) | Реактивное асинхронное состояние | AUTO |
| [`useDebouncedRefHistory`](references/useDebouncedRefHistory.md) | Сокращение для `useRefHistory` с debounce-фильтром | AUTO |
| [`useLastChanged`](references/useLastChanged.md) | Записывает временную метку последнего изменения | AUTO |
| [`useLocalStorage`](references/useLocalStorage.md) | Реактивный [LocalStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage) | AUTO |
| [`useManualRefHistory`](references/useManualRefHistory.md) | Вручную отслеживать историю изменений ref, когда вызывающий код вызывает `commit()` | AUTO |
| [`useRefHistory`](references/useRefHistory.md) | Отслеживать историю изменений ref | AUTO |
| [`useSessionStorage`](references/useSessionStorage.md) | Реактивный [SessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage) | AUTO |
| [`useStorage`](references/useStorage.md) | Создать реактивный ref, через который можно читать и изменять [LocalStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage) или [SessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage) | AUTO |
| [`useStorageAsync`](references/useStorageAsync.md) | Реактивный Storage с поддержкой async | AUTO |
| [`useThrottledRefHistory`](references/useThrottledRefHistory.md) | Сокращение для `useRefHistory` с throttle-фильтром | AUTO |

### Elements (Элементы)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useActiveElement`](references/useActiveElement.md) | Реактивный `document.activeElement` | AUTO |
| [`useDocumentVisibility`](references/useDocumentVisibility.md) | Реактивно отслеживать [`document.visibilityState`](https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilityState) | AUTO |
| [`useDraggable`](references/useDraggable.md) | Сделать элементы перетаскиваемыми | AUTO |
| [`useDropZone`](references/useDropZone.md) | Создать зону, куда можно сбрасывать файлы | AUTO |
| [`useElementBounding`](references/useElementBounding.md) | Реактивный [bounding box](https://developer.mozilla.org/en-US/docs/Web/API/Element/getBoundingClientRect) HTML-элемента | AUTO |
| [`useElementSize`](references/useElementSize.md) | Реактивный размер HTML-элемента | AUTO |
| [`useElementVisibility`](references/useElementVisibility.md) | Отслеживает видимость элемента в пределах вьюпорта | AUTO |
| [`useIntersectionObserver`](references/useIntersectionObserver.md) | Определяет видимость целевого элемента | AUTO |
| [`useMouseInElement`](references/useMouseInElement.md) | Реактивная позиция мыши относительно элемента | AUTO |
| [`useMutationObserver`](references/useMutationObserver.md) | Следить за изменениями, вносимыми в DOM-дерево | AUTO |
| [`useParentElement`](references/useParentElement.md) | Получить родительский элемент заданного элемента | AUTO |
| [`useResizeObserver`](references/useResizeObserver.md) | Сообщает об изменениях размеров содержимого элемента или его border-box | AUTO |
| [`useWindowFocus`](references/useWindowFocus.md) | Реактивно отслеживать фокус окна через события `window.onfocus` и `window.onblur` | AUTO |
| [`useWindowScroll`](references/useWindowScroll.md) | Реактивная прокрутка окна | AUTO |
| [`useWindowSize`](references/useWindowSize.md) | Реактивный размер окна | AUTO |

### Browser (Браузер)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useBluetooth`](references/useBluetooth.md) | Реактивный [Web Bluetooth API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Bluetooth_API) | AUTO |
| [`useBreakpoints`](references/useBreakpoints.md) | Реактивные брейкпоинты вьюпорта | AUTO |
| [`useBroadcastChannel`](references/useBroadcastChannel.md) | Реактивный [BroadcastChannel API](https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel) | AUTO |
| [`useBrowserLocation`](references/useBrowserLocation.md) | Реактивный browser location | AUTO |
| [`useClipboard`](references/useClipboard.md) | Реактивный [Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API) | AUTO |
| [`useClipboardItems`](references/useClipboardItems.md) | Реактивный [Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API) | AUTO |
| [`useColorMode`](references/useColorMode.md) | Реактивный цветовой режим (тёмный / светлый / кастомные) с автоматическим сохранением данных | AUTO |
| [`useCssSupports`](references/useCssSupports.md) | SSR-совместимый и реактивный [`CSS.supports`](https://developer.mozilla.org/docs/Web/API/CSS/supports_static) | AUTO |
| [`useCssVar`](references/useCssVar.md) | Управлять CSS-переменными | AUTO |
| [`useDark`](references/useDark.md) | Реактивный тёмный режим с автоматическим сохранением данных | AUTO |
| [`useEventListener`](references/useEventListener.md) | Использовать EventListener легко и просто | AUTO |
| [`useEyeDropper`](references/useEyeDropper.md) | Реактивный [EyeDropper API](https://developer.mozilla.org/en-US/docs/Web/API/EyeDropper_API) | AUTO |
| [`useFavicon`](references/useFavicon.md) | Реактивный favicon | AUTO |
| [`useFileDialog`](references/useFileDialog.md) | Открыть диалог выбора файлов легко и просто | AUTO |
| [`useFileSystemAccess`](references/useFileSystemAccess.md) | Создавать, читать и записывать локальные файлы через [FileSystemAccessAPI](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API) | AUTO |
| [`useFullscreen`](references/useFullscreen.md) | Реактивный [Fullscreen API](https://developer.mozilla.org/en-US/docs/Web/API/Fullscreen_API) | AUTO |
| [`useGamepad`](references/useGamepad.md) | Предоставляет реактивные привязки для [Gamepad API](https://developer.mozilla.org/en-US/docs/Web/API/Gamepad_API) | AUTO |
| [`useImage`](references/useImage.md) | Реактивная загрузка изображения в браузере | AUTO |
| [`useMediaControls`](references/useMediaControls.md) | Реактивные элементы управления медиа для элементов `audio` и `video` | AUTO |
| [`useMediaQuery`](references/useMediaQuery.md) | Реактивный [Media Query](https://developer.mozilla.org/en-US/docs/Web/CSS/Media_Queries/Testing_media_queries) | AUTO |
| [`useMemory`](references/useMemory.md) | Реактивная информация о памяти (Memory Info) | AUTO |
| [`useObjectUrl`](references/useObjectUrl.md) | Реактивный URL, представляющий объект | AUTO |
| [`usePerformanceObserver`](references/usePerformanceObserver.md) | Наблюдать за метриками производительности | AUTO |
| [`usePermission`](references/usePermission.md) | Реактивный [Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API) | AUTO |
| [`usePreferredColorScheme`](references/usePreferredColorScheme.md) | Реактивный media-запрос [prefers-color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme) | AUTO |
| [`usePreferredContrast`](references/usePreferredContrast.md) | Реактивный media-запрос [prefers-contrast](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-contrast) | AUTO |
| [`usePreferredDark`](references/usePreferredDark.md) | Реактивное предпочтение тёмной темы | AUTO |
| [`usePreferredLanguages`](references/usePreferredLanguages.md) | Реактивные [Navigator Languages](https://developer.mozilla.org/en-US/docs/Web/API/NavigatorLanguage/languages) | AUTO |
| [`usePreferredReducedMotion`](references/usePreferredReducedMotion.md) | Реактивный media-запрос [prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) | AUTO |
| [`usePreferredReducedTransparency`](references/usePreferredReducedTransparency.md) | Реактивный media-запрос [prefers-reduced-transparency](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-transparency) | AUTO |
| [`useScreenOrientation`](references/useScreenOrientation.md) | Реактивный [Screen Orientation API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Orientation_API) | AUTO |
| [`useScreenSafeArea`](references/useScreenSafeArea.md) | Реактивный `env(safe-area-inset-*)` | AUTO |
| [`useScriptTag`](references/useScriptTag.md) | Создаёт тег script | AUTO |
| [`useShare`](references/useShare.md) | Реактивный [Web Share API](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share) | AUTO |
| [`useSSRWidth`](references/useSSRWidth.md) | Используется для задания глобальной ширины вьюпорта, которая будет применяться при рендеринге SSR-компонентов, зависящих от ширины вьюпорта, таких как [`useMediaQuery`](../useMediaQuery/index.md) или [`useBreakpoints`](../useBreakpoints/index.md) | AUTO |
| [`useStyleTag`](references/useStyleTag.md) | Внедрить реактивный элемент `style` в head | AUTO |
| [`useTextareaAutosize`](references/useTextareaAutosize.md) | Автоматически обновлять высоту textarea в зависимости от содержимого | AUTO |
| [`useTextDirection`](references/useTextDirection.md) | Реактивный [dir](https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/dir) (направление текста) элемента | AUTO |
| [`useTitle`](references/useTitle.md) | Реактивный заголовок документа | AUTO |
| [`useUrlSearchParams`](references/useUrlSearchParams.md) | Реактивные [URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams) | AUTO |
| [`useVibrate`](references/useVibrate.md) | Реактивный [Vibration API](https://developer.mozilla.org/en-US/docs/Web/API/Vibration_API) | AUTO |
| [`useWakeLock`](references/useWakeLock.md) | Реактивный [Screen Wake Lock API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API) | AUTO |
| [`useWebNotification`](references/useWebNotification.md) | Реактивный [Notification](https://developer.mozilla.org/en-US/docs/Web/API/notification) | AUTO |
| [`useWebWorker`](references/useWebWorker.md) | Простая регистрация и коммуникация [Web Workers](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Using_web_workers) | AUTO |
| [`useWebWorkerFn`](references/useWebWorkerFn.md) | Запускать ресурсоёмкие функции без блокировки UI | AUTO |

### Sensors (Сенсоры)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`onClickOutside`](references/onClickOutside.md) | Слушать клики за пределами элемента | AUTO |
| [`onElementRemoval`](references/onElementRemoval.md) | Срабатывает, когда элемент или любой содержащий его элемент удаляется из DOM | AUTO |
| [`onKeyStroke`](references/onKeyStroke.md) | Слушать нажатия клавиш клавиатуры | AUTO |
| [`onLongPress`](references/onLongPress.md) | Слушать долгое нажатие на элемент | AUTO |
| [`onStartTyping`](references/onStartTyping.md) | Срабатывает, когда пользователь начинает печатать на нередактируемых элементах | AUTO |
| [`useBattery`](references/useBattery.md) | Реактивный [Battery Status API](https://developer.mozilla.org/en-US/docs/Web/API/Battery_Status_API) | AUTO |
| [`useDeviceMotion`](references/useDeviceMotion.md) | Реактивный [DeviceMotionEvent](https://developer.mozilla.org/en-US/docs/Web/API/DeviceMotionEvent) | AUTO |
| [`useDeviceOrientation`](references/useDeviceOrientation.md) | Реактивный [DeviceOrientationEvent](https://developer.mozilla.org/en-US/docs/Web/API/DeviceOrientationEvent) | AUTO |
| [`useDevicePixelRatio`](references/useDevicePixelRatio.md) | Реактивно отслеживать [`window.devicePixelRatio`](https://developer.mozilla.org/docs/Web/API/Window/devicePixelRatio) | AUTO |
| [`useDevicesList`](references/useDevicesList.md) | Реактивный [enumerateDevices](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices) — перечень доступных устройств ввода/вывода | AUTO |
| [`useDisplayMedia`](references/useDisplayMedia.md) | Реактивный стриминг [`mediaDevices.getDisplayMedia`](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia) | AUTO |
| [`useElementByPoint`](references/useElementByPoint.md) | Реактивный элемент по точке | AUTO |
| [`useElementHover`](references/useElementHover.md) | Реактивное состояние наведения (hover) на элемент | AUTO |
| [`useFocus`](references/useFocus.md) | Реактивная утилита для отслеживания или установки состояния фокуса DOM-элемента | AUTO |
| [`useFocusWithin`](references/useFocusWithin.md) | Реактивная утилита для отслеживания, есть ли фокус на элементе или на одном из его потомков | AUTO |
| [`useFps`](references/useFps.md) | Реактивный FPS (кадры в секунду) | AUTO |
| [`useGeolocation`](references/useGeolocation.md) | Реактивный [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API) | AUTO |
| [`useIdle`](references/useIdle.md) | Отслеживает, бездействует ли пользователь | AUTO |
| [`useInfiniteScroll`](references/useInfiniteScroll.md) | Бесконечная прокрутка элемента | AUTO |
| [`useKeyModifier`](references/useKeyModifier.md) | Реактивное [состояние модификатора (Modifier State)](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/getModifierState) | AUTO |
| [`useMagicKeys`](references/useMagicKeys.md) | Реактивное состояние нажатых клавиш | AUTO |
| [`useMouse`](references/useMouse.md) | Реактивная позиция мыши | AUTO |
| [`useMousePressed`](references/useMousePressed.md) | Реактивное состояние нажатия мыши | AUTO |
| [`useNavigatorLanguage`](references/useNavigatorLanguage.md) | Реактивный [navigator.language](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/language) | AUTO |
| [`useNetwork`](references/useNetwork.md) | Реактивный [сетевой статус (Network status)](https://developer.mozilla.org/en-US/docs/Web/API/Network_Information_API) | AUTO |
| [`useOnline`](references/useOnline.md) | Реактивное состояние онлайн | AUTO |
| [`usePageLeave`](references/usePageLeave.md) | Реактивное состояние, показывающее, покидает ли мышь страницу | AUTO |
| [`useParallax`](references/useParallax.md) | Легко создать эффект параллакса | AUTO |
| [`usePointer`](references/usePointer.md) | Реактивное [состояние указателя (pointer state)](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events) | AUTO |
| [`usePointerLock`](references/usePointerLock.md) | Реактивный [pointer lock](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_Lock_API) | AUTO |
| [`usePointerSwipe`](references/usePointerSwipe.md) | Реактивное определение свайпа на основе [PointerEvents](https://developer.mozilla.org/en-US/docs/Web/API/PointerEvent) | AUTO |
| [`useScroll`](references/useScroll.md) | Реактивная позиция и состояние прокрутки | AUTO |
| [`useScrollLock`](references/useScrollLock.md) | Заблокировать прокрутку элемента | AUTO |
| [`useSpeechRecognition`](references/useSpeechRecognition.md) | Реактивный [SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition) | AUTO |
| [`useSpeechSynthesis`](references/useSpeechSynthesis.md) | Реактивный [SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis) | AUTO |
| [`useSwipe`](references/useSwipe.md) | Реактивное определение свайпа на основе [`TouchEvents`](https://developer.mozilla.org/en-US/docs/Web/API/TouchEvent) | AUTO |
| [`useTextSelection`](references/useTextSelection.md) | Реактивно отслеживать выделение текста пользователем на основе [`Window.getSelection`](https://developer.mozilla.org/en-US/docs/Web/API/Window/getSelection) | AUTO |
| [`useUserMedia`](references/useUserMedia.md) | Реактивный стриминг [`mediaDevices.getUserMedia`](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) | AUTO |

### Network (Сеть)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useEventSource`](references/useEventSource.md) | Экземпляр [EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource) или [Server-Sent-Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) открывает постоянное соединение с HTTP-сервером | AUTO |
| [`useFetch`](references/useFetch.md) | Реактивный [Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API), даёт возможность прерывать (abort) запросы | AUTO |
| [`useWebSocket`](references/useWebSocket.md) | Реактивный [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket)-клиент | AUTO |

### Animation (Анимация)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useAnimate`](references/useAnimate.md) | Реактивный [Web Animations API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API) | AUTO |
| [`useInterval`](references/useInterval.md) | Реактивный счётчик, увеличивающийся на каждом интервале | AUTO |
| [`useIntervalFn`](references/useIntervalFn.md) | Обёртка для `setInterval` с управлением | AUTO |
| [`useNow`](references/useNow.md) | Реактивный текущий экземпляр Date | AUTO |
| [`useRafFn`](references/useRafFn.md) | Вызывать функцию на каждом `requestAnimationFrame` | AUTO |
| [`useTimeout`](references/useTimeout.md) | Реактивное значение, которое становится `true` по истечении заданного времени | AUTO |
| [`useTimeoutFn`](references/useTimeoutFn.md) | Обёртка для `setTimeout` с управлением | AUTO |
| [`useTimestamp`](references/useTimestamp.md) | Реактивная текущая временная метка | AUTO |
| [`useTransition`](references/useTransition.md) | Переход между значениями | AUTO |

### Component (Компонент)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`computedInject`](references/computedInject.md) | Сочетает `computed` и `inject` | AUTO |
| [`createReusableTemplate`](references/createReusableTemplate.md) | Определить и переиспользовать шаблон в пределах области видимости компонента | AUTO |
| [`createTemplatePromise`](references/createTemplatePromise.md) | Шаблон как Promise | AUTO |
| [`templateRef`](references/templateRef.md) | Сокращение для привязки ref к элементу шаблона | AUTO |
| [`tryOnBeforeMount`](references/tryOnBeforeMount.md) | Безопасный `onBeforeMount` | AUTO |
| [`tryOnBeforeUnmount`](references/tryOnBeforeUnmount.md) | Безопасный `onBeforeUnmount` | AUTO |
| [`tryOnMounted`](references/tryOnMounted.md) | Безопасный `onMounted` | AUTO |
| [`tryOnScopeDispose`](references/tryOnScopeDispose.md) | Безопасный `onScopeDispose` | AUTO |
| [`tryOnUnmounted`](references/tryOnUnmounted.md) | Безопасный `onUnmounted` | AUTO |
| [`unrefElement`](references/unrefElement.md) | Извлекает нижележащий DOM-элемент из Vue ref или экземпляра компонента | AUTO |
| [`useCurrentElement`](references/useCurrentElement.md) | Получить DOM-элемент текущего компонента как ref | AUTO |
| [`useMounted`](references/useMounted.md) | Состояние «смонтирован» (mounted) в виде ref | AUTO |
| [`useTemplateRefsList`](references/useTemplateRefsList.md) | Сокращение для привязки ref'ов к элементам шаблона и компонентам внутри `v-for` | AUTO |
| [`useVirtualList`](references/useVirtualList.md) | Легко создавать виртуальные списки | AUTO |
| [`useVModel`](references/useVModel.md) | Сокращение для привязки v-model | AUTO |
| [`useVModels`](references/useVModels.md) | Сокращение для привязки v-model к пропсам | AUTO |

### Watch (Наблюдение)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`until`](references/until.md) | Одноразовое наблюдение за изменениями в виде Promise | AUTO |
| [`watchArray`](references/watchArray.md) | Наблюдать за массивом с добавлениями и удалениями | AUTO |
| [`watchAtMost`](references/watchAtMost.md) | `watch` с ограничением числа срабатываний | AUTO |
| [`watchDebounced`](references/watchDebounced.md) | Debounce-watch | AUTO |
| [`watchDeep`](references/watchDeep.md) | Сокращение для наблюдения за значением с `{deep: true}` | AUTO |
| [`watchIgnorable`](references/watchIgnorable.md) | Игнорируемый watch | AUTO |
| [`watchImmediate`](references/watchImmediate.md) | Сокращение для наблюдения за значением с `{immediate: true}` | AUTO |
| [`watchOnce`](references/watchOnce.md) | Сокращение для наблюдения за значением с `{ once: true }` | AUTO |
| [`watchPausable`](references/watchPausable.md) | Приостанавливаемый (pausable) watch | AUTO |
| [`watchThrottled`](references/watchThrottled.md) | Throttle-watch | AUTO |
| [`watchTriggerable`](references/watchTriggerable.md) | Watch, который можно запустить вручную | AUTO |
| [`watchWithFilter`](references/watchWithFilter.md) | `watch` с дополнительным контролем через EventFilter | AUTO |
| [`whenever`](references/whenever.md) | Сокращение для наблюдения за значением на истинность (truthy) | AUTO |

### Reactivity (Реактивность)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`computedAsync`](references/computedAsync.md) | Computed для асинхронных функций | AUTO |
| [`computedEager`](references/computedEager.md) | Жадный (eager) computed без ленивого вычисления | AUTO |
| [`computedWithControl`](references/computedWithControl.md) | Явно определить зависимости computed | AUTO |
| [`createRef`](references/createRef.md) | Возвращает `deepRef` или `shallowRef` в зависимости от параметра `deep` | AUTO |
| [`extendRef`](references/extendRef.md) | Добавить дополнительные атрибуты к Ref | AUTO |
| [`reactify`](references/reactify.md) | Преобразует обычные функции в реактивные | AUTO |
| [`reactifyObject`](references/reactifyObject.md) | Применить `reactify` к объекту | AUTO |
| [`reactiveComputed`](references/reactiveComputed.md) | Computed реактивный объект | AUTO |
| [`reactiveOmit`](references/reactiveOmit.md) | Реактивно исключить поля из реактивного объекта | AUTO |
| [`reactivePick`](references/reactivePick.md) | Реактивно выбрать поля из реактивного объекта | AUTO |
| [`refAutoReset`](references/refAutoReset.md) | Ref, который будет сброшен к значению по умолчанию через некоторое время | AUTO |
| [`refDebounced`](references/refDebounced.md) | Debounce выполнения значения ref | AUTO |
| [`refDefault`](references/refDefault.md) | Применить значение по умолчанию к ref | AUTO |
| [`refManualReset`](references/refManualReset.md) | Создать ref с возможностью ручного сброса | AUTO |
| [`refThrottled`](references/refThrottled.md) | Throttle изменения значения ref | AUTO |
| [`refWithControl`](references/refWithControl.md) | Тонкий контроль над ref и его реактивностью | AUTO |
| [`syncRef`](references/syncRef.md) | Двусторонняя синхронизация ref'ов | AUTO |
| [`syncRefs`](references/syncRefs.md) | Держать целевые ref'ы в синхронизации с исходным ref | AUTO |
| [`toReactive`](references/toReactive.md) | Преобразует ref в reactive | AUTO |
| [`toRef`](references/toRef.md) | Нормализует value/ref/getter в `ref` или `computed` | EXPLICIT_ONLY |
| [`toRefs`](references/toRefs.md) | Расширенный [`toRefs`](https://vuejs.org/api/reactivity-utilities.html#torefs), который также принимает ref'ы объекта | AUTO |

### Array (Массивы)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useArrayDifference`](references/useArrayDifference.md) | Реактивно получить разность двух массивов | AUTO |
| [`useArrayEvery`](references/useArrayEvery.md) | Реактивный `Array.every` | AUTO |
| [`useArrayFilter`](references/useArrayFilter.md) | Реактивный `Array.filter` | AUTO |
| [`useArrayFind`](references/useArrayFind.md) | Реактивный `Array.find` | AUTO |
| [`useArrayFindIndex`](references/useArrayFindIndex.md) | Реактивный `Array.findIndex` | AUTO |
| [`useArrayFindLast`](references/useArrayFindLast.md) | Реактивный `Array.findLast` | AUTO |
| [`useArrayIncludes`](references/useArrayIncludes.md) | Реактивный `Array.includes` | AUTO |
| [`useArrayJoin`](references/useArrayJoin.md) | Реактивный `Array.join` | AUTO |
| [`useArrayMap`](references/useArrayMap.md) | Реактивный `Array.map` | AUTO |
| [`useArrayReduce`](references/useArrayReduce.md) | Реактивный `Array.reduce` | AUTO |
| [`useArraySome`](references/useArraySome.md) | Реактивный `Array.some` | AUTO |
| [`useArrayUnique`](references/useArrayUnique.md) | Реактивный уникальный массив | AUTO |
| [`useSorted`](references/useSorted.md) | Реактивная сортировка массива | AUTO |

### Time (Время)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useCountdown`](references/useCountdown.md) | Реактивный таймер обратного отсчёта в секундах | AUTO |
| [`useDateFormat`](references/useDateFormat.md) | Получить отформатированную дату согласно строке токенов | AUTO |
| [`useTimeAgo`](references/useTimeAgo.md) | Реактивный «time ago» (сколько времени назад) | AUTO |
| [`useTimeAgoIntl`](references/useTimeAgoIntl.md) | Реактивный «time ago» с поддержкой i18n | AUTO |

### Utilities (Утилиты)

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`createEventHook`](references/createEventHook.md) | Утилита для создания event-хуков | AUTO |
| [`createUnrefFn`](references/createUnrefFn.md) | Сделать обычную функцию принимающей ref и сырые значения в качестве аргументов | AUTO |
| [`get`](references/get.md) | Сокращение для доступа к `ref.value` | EXPLICIT_ONLY |
| [`isDefined`](references/isDefined.md) | Type guard для Ref, проверяющий на non-nullish (не null/undefined) | AUTO |
| [`makeDestructurable`](references/makeDestructurable.md) | Сделать изоморфно деструктурируемым одновременно как объект и как массив | AUTO |
| [`set`](references/set.md) | Сокращение для `ref.value = x` | EXPLICIT_ONLY |
| [`useAsyncQueue`](references/useAsyncQueue.md) | Выполняет каждую асинхронную задачу последовательно и передаёт результат текущей задачи следующей | AUTO |
| [`useBase64`](references/useBase64.md) | Реактивное преобразование в base64 | AUTO |
| [`useCached`](references/useCached.md) | Кэшировать ref с кастомным компаратором | AUTO |
| [`useCloned`](references/useCloned.md) | Реактивный клон ref | AUTO |
| [`useConfirmDialog`](references/useConfirmDialog.md) | Создаёт event-хуки для поддержки модальных окон и цепочек диалогов подтверждения | AUTO |
| [`useCounter`](references/useCounter.md) | Базовый счётчик с вспомогательными функциями | AUTO |
| [`useCycleList`](references/useCycleList.md) | Циклически перебирать список элементов | AUTO |
| [`useDebounceFn`](references/useDebounceFn.md) | Debounce выполнения функции | AUTO |
| [`useEventBus`](references/useEventBus.md) | Базовая шина событий (event bus) | AUTO |
| [`useMemoize`](references/useMemoize.md) | Кэшировать результаты функций в зависимости от аргументов и держать кэш реактивным | AUTO |
| [`useOffsetPagination`](references/useOffsetPagination.md) | Реактивная offset-пагинация | AUTO |
| [`usePrevious`](references/usePrevious.md) | Хранит предыдущее значение ref | AUTO |
| [`useStepper`](references/useStepper.md) | Предоставляет помощники для построения многошагового интерфейса-визарда | AUTO |
| [`useSupported`](references/useSupported.md) | SSR-совместимый `isSupported` | AUTO |
| [`useThrottleFn`](references/useThrottleFn.md) | Throttle выполнения функции | AUTO |
| [`useTimeoutPoll`](references/useTimeoutPoll.md) | Использовать таймаут для опроса (polling) чего-либо | AUTO |
| [`useToggle`](references/useToggle.md) | Булев переключатель с вспомогательными функциями | AUTO |
| [`useToNumber`](references/useToNumber.md) | Реактивно конвертировать строковый ref в число | AUTO |
| [`useToString`](references/useToString.md) | Реактивно конвертировать ref в строку | AUTO |

### @Electron

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useIpcRenderer`](references/useIpcRenderer.md) | Предоставляет [ipcRenderer](https://www.electronjs.org/docs/api/ipc-renderer) и все его API с реактивностью Vue | EXTERNAL |
| [`useIpcRendererInvoke`](references/useIpcRendererInvoke.md) | Реактивный результат [ipcRenderer.invoke API](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererinvokechannel-args) | EXTERNAL |
| [`useIpcRendererOn`](references/useIpcRendererOn.md) | Использовать [ipcRenderer.on](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendereronchannel-listener) легко и просто, с автоматическим [ipcRenderer.removeListener](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererremovelistenerchannel-listener) при размонтировании | EXTERNAL |
| [`useZoomFactor`](references/useZoomFactor.md) | Реактивный коэффициент масштаба (zoom factor) [WebFrame](https://www.electronjs.org/docs/api/web-frame#webframe) | EXTERNAL |
| [`useZoomLevel`](references/useZoomLevel.md) | Реактивный уровень масштаба (zoom level) [WebFrame](https://www.electronjs.org/docs/api/web-frame#webframe) | EXTERNAL |

### @Firebase

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useAuth`](references/useAuth.md) | Реактивная привязка к [Firebase Auth](https://firebase.google.com/docs/auth) | EXTERNAL |
| [`useFirestore`](references/useFirestore.md) | Реактивная привязка к [Firestore](https://firebase.google.com/docs/firestore) | EXTERNAL |
| [`useRTDB`](references/useRTDB.md) | Реактивная привязка к [Firebase Realtime Database](https://firebase.google.com/docs/database) | EXTERNAL |

### @Head

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`createHead`](https://github.com/vueuse/head#api) | Создать экземпляр менеджера head. | EXTERNAL |
| [`useHead`](https://github.com/vueuse/head#api) | Реактивно обновлять meta-теги head. | EXTERNAL |

### @Integrations

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useAsyncValidator`](references/useAsyncValidator.md) | Обёртка для [`async-validator`](https://github.com/yiminghe/async-validator) | EXTERNAL |
| [`useAxios`](references/useAxios.md) | Обёртка для [`axios`](https://github.com/axios/axios) | EXTERNAL |
| [`useChangeCase`](references/useChangeCase.md) | Реактивная обёртка для [`change-case`](https://github.com/blakeembrey/change-case) | EXTERNAL |
| [`useCookies`](references/useCookies.md) | Обёртка для [`universal-cookie`](https://www.npmjs.com/package/universal-cookie) | EXTERNAL |
| [`useDrauu`](references/useDrauu.md) | Реактивный экземпляр для [drauu](https://github.com/antfu/drauu) | EXTERNAL |
| [`useFocusTrap`](references/useFocusTrap.md) | Реактивная обёртка для [`focus-trap`](https://github.com/focus-trap/focus-trap) | EXTERNAL |
| [`useFuse`](references/useFuse.md) | Легко реализовать нечёткий (fuzzy) поиск через composable с [Fuse.js](https://github.com/krisk/fuse) | EXTERNAL |
| [`useIDBKeyval`](references/useIDBKeyval.md) | Обёртка для [`idb-keyval`](https://www.npmjs.com/package/idb-keyval) | EXTERNAL |
| [`useJwt`](references/useJwt.md) | Обёртка для [`jwt-decode`](https://github.com/auth0/jwt-decode) | EXTERNAL |
| [`useNProgress`](references/useNProgress.md) | Реактивная обёртка для [`nprogress`](https://github.com/rstacruz/nprogress) | EXTERNAL |
| [`useQRCode`](references/useQRCode.md) | Обёртка для [`qrcode`](https://github.com/soldair/node-qrcode) | EXTERNAL |
| [`useSortable`](references/useSortable.md) | Обёртка для [`sortable`](https://github.com/SortableJS/Sortable) | EXTERNAL |

### @Math

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`createGenericProjection`](references/createGenericProjection.md) | Обобщённая версия `createProjection` | EXTERNAL |
| [`createProjection`](references/createProjection.md) | Реактивная числовая проекция из одной области значений в другую | EXTERNAL |
| [`logicAnd`](references/logicAnd.md) | Условие `AND` для ref'ов | EXTERNAL |
| [`logicNot`](references/logicNot.md) | Условие `NOT` для ref | EXTERNAL |
| [`logicOr`](references/logicOr.md) | Условия `OR` для ref'ов | EXTERNAL |
| [`useAbs`](references/useAbs.md) | Реактивный `Math.abs` | EXTERNAL |
| [`useAverage`](references/useAverage.md) | Получить среднее массива реактивно | EXTERNAL |
| [`useCeil`](references/useCeil.md) | Реактивный `Math.ceil` | EXTERNAL |
| [`useClamp`](references/useClamp.md) | Реактивно зажать (clamp) значение между двумя другими значениями | EXTERNAL |
| [`useFloor`](references/useFloor.md) | Реактивный `Math.floor` | EXTERNAL |
| [`useMath`](references/useMath.md) | Реактивные методы `Math` | EXTERNAL |
| [`useMax`](references/useMax.md) | Реактивный `Math.max` | EXTERNAL |
| [`useMin`](references/useMin.md) | Реактивный `Math.min` | EXTERNAL |
| [`usePrecision`](references/usePrecision.md) | Реактивно задать точность числа | EXTERNAL |
| [`useProjection`](references/useProjection.md) | Реактивная числовая проекция из одной области значений в другую | EXTERNAL |
| [`useRound`](references/useRound.md) | Реактивный `Math.round` | EXTERNAL |
| [`useSum`](references/useSum.md) | Получить сумму массива реактивно | EXTERNAL |
| [`useTrunc`](references/useTrunc.md) | Реактивный `Math.trunc` | EXTERNAL |

### @Motion

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useElementStyle`](https://motion.vueuse.org/api/use-element-style) | Синхронизировать реактивный объект с CSS-стилями целевого элемента | EXTERNAL |
| [`useElementTransform`](https://motion.vueuse.org/api/use-element-transform) | Синхронизировать реактивный объект с CSS transform целевого элемента. | EXTERNAL |
| [`useMotion`](https://motion.vueuse.org/api/use-motion) | Приводит ваши компоненты в движение. | EXTERNAL |
| [`useMotionProperties`](https://motion.vueuse.org/api/use-motion-properties) | Доступ к свойствам движения (Motion Properties) для целевого элемента. | EXTERNAL |
| [`useMotionVariants`](https://motion.vueuse.org/api/use-motion-variants) | Управление состоянием и выбором вариантов (Variants). | EXTERNAL |
| [`useSpring`](https://motion.vueuse.org/api/use-spring) | Пружинные (spring) анимации. | EXTERNAL |

### @Router

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useRouteHash`](references/useRouteHash.md) | Сокращение для реактивного `route.hash` | EXTERNAL |
| [`useRouteParams`](references/useRouteParams.md) | Сокращение для реактивного `route.params` | EXTERNAL |
| [`useRouteQuery`](references/useRouteQuery.md) | Сокращение для реактивного `route.query` | EXTERNAL |

### @RxJS

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`from`](references/from.md) | Обёртки вокруг [`from()`](https://rxjs.dev/api/index/function/from) и [`fromEvent()`](https://rxjs.dev/api/index/function/fromEvent) из RxJS, чтобы они могли принимать `ref`'ы | EXTERNAL |
| [`toObserver`](references/toObserver.md) | Удобная функция для преобразования `ref` в RxJS [Observer](https://rxjs.dev/guide/observer) | EXTERNAL |
| [`useExtractedObservable`](references/useExtractedObservable.md) | Использовать RxJS [`Observable`](https://rxjs.dev/guide/observable), извлечённый из одной или нескольких composable-функций | EXTERNAL |
| [`useObservable`](references/useObservable.md) | Использовать RxJS [`Observable`](https://rxjs.dev/guide/observable) | EXTERNAL |
| [`useSubject`](references/useSubject.md) | Привязать RxJS [`Subject`](https://rxjs.dev/guide/subject) к `ref` и распространять изменения значений в обе стороны | EXTERNAL |
| [`useSubscription`](references/useSubscription.md) | Использовать RxJS [`Subscription`](https://rxjs.dev/guide/subscription), не беспокоясь об отписке от неё и об утечках памяти | EXTERNAL |
| [`watchExtractedObservable`](references/watchExtractedObservable.md) | Наблюдать за значениями RxJS [`Observable`](https://rxjs.dev/guide/observable), извлечённого из одной или нескольких composable-функций | EXTERNAL |

### @SchemaOrg

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`createSchemaOrg`](https://vue-schema-org.netlify.app/api/core/create-schema-org.html) | Создать экземпляр менеджера schema.org. | EXTERNAL |
| [`useSchemaOrg`](https://vue-schema-org.netlify.app/api/core/use-schema-org.html) | Реактивно обновлять schema.org. | EXTERNAL |

### @Sound

| Функция | Описание | Invocation |
|----------|-------------|------------|
| [`useSound`](https://github.com/vueuse/sound#examples) | Реактивно воспроизводить звуковые эффекты. | EXTERNAL |
