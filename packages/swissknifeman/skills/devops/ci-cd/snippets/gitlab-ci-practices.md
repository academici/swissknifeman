# GitLab CI/CD Best Practices

Этот документ описывает стандарты и лучшие практики по написанию `.gitlab-ci.yml` пайплайнов для проектов.

## Основные Принципы

1.  **Скорость:** Пайплайн должен проходить максимально быстро. Используйте кэширование зависимостей и Docker образов.
2.  **Надежность:** Тесты и линтеры должны выполняться изолированно и не зависеть от состояния окружения.
3.  **Безопасность:** Секреты и пароли должны храниться только в GitLab CI/CD Variables (желательно с флагами `Masked` и `Protected`), никогда в коде.

## Структура Пайплайна (Stages)

Стандартное разделение стадий:
```yaml
stages:
  - lint
  - test
  - build
  - deploy
```

## Правила (Rules) вместо Only/Except

Используйте `rules` для контроля запуска джобов. Это современный и более гибкий механизм по сравнению с устаревшими `only` и `except`.

```yaml
.standard_rules:
  rules:
    # Запускать при Merge Request
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    # Запускать на дефолтной ветке (main/master)
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
```

## Кэширование (Caching)

Кэшируйте папки с зависимостями (например, `vendor/` для PHP, `node_modules/` для Node.js, `.venv/` для Python), чтобы ускорить сборку.
Ключ кэша лучше привязывать к файлу блокировки (`composer.lock`, `package-lock.json`, `poetry.lock`).

```yaml
cache:
  key:
    files:
      - composer.lock
  paths:
    - vendor/
```

## Docker in Docker (dind)

Для сборки Docker-образов внутри GitLab CI используйте сервис `docker:dind`.
Старайтесь использовать `docker buildx` с кэшированием слоев (`--cache-from` и `--cache-to`).

```yaml
build_image:
  stage: build
  image: docker:24.0.5
  services:
    - docker:24.0.5-dind
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build --pull -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
```

## Оптимизация и Трюки

-   **Interruptible:** Устанавливайте `interruptible: true` для стадий `lint` и `test`. Если разработчик запушит новый коммит до того, как закончится пайплайн старого, старый пайплайн будет отменен, что сэкономит ресурсы раннеров.
-   **Needs:** Используйте ключевое слово `needs`, чтобы строить Directed Acyclic Graphs (DAG). Это позволяет джобам начинаться сразу после завершения нужных предыдущих джобов, не дожидаясь окончания всей стадии.

```yaml
test_backend:
  stage: test
  needs: ["lint_backend"]
  script:
    - vendor/bin/phpunit
```
