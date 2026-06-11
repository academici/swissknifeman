---
name: database
bucket: php
version: 0.1.0
description: "Database migrations, models, and table naming. Activate when writing migrations, creating models, defining schema, foreign keys, or working in database/migrations/."
risk: write
persona: oss-dev
tags: [php, laravel, database]
requires: [laravel]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Database

## Модели и таблицы

В {{project_name}} модели используют PHP-атрибут `#[Table(name: '...')]` для явного указания таблицы:

```php
#[Table(name: 'tickets')]
final class Ticket extends Model { ... }
```

Благодаря этому `(new Ticket())->getTable()` всегда возвращает имя таблицы из модели — **не хардкод-строку**.

## Паттерн миграций: имена таблиц через Model

**Никогда не хардкодить имена таблиц строками в миграциях.** Всегда получать имя через `(new Model())->getTable()`.

### Почему

- Если таблица переименуется — исправляем только `#[Table]` в модели, миграции обновятся автоматически
- Нет расхождений между моделью и миграцией
- Рефакторинг безопаснее

### Шаблон миграции

```php
<?php

declare(strict_types=1);

use App\Models\Ticket\Ticket;
use App\Models\Meeting\MeetingAgendaItem;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create($this->table(), function (Blueprint $table): void {
            $table->id();

            // FK через getTable() — не строку
            $table->foreignId('meeting_agenda_item_id')
                ->nullable()
                ->index()
                ->constrained(table: (new MeetingAgendaItem())->getTable())
                ->nullOnDelete();

            $table->string('status', 50)->index();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists($this->table());
    }

    private function table(): string
    {
        return (new Ticket())->getTable();
    }
};
```

### Self-referencing FK

```php
// Таблица ссылается на себя (related_ticket_id → tickets.id)
$table->foreignId('related_ticket_id')
    ->nullable()
    ->index()
    ->constrained(table: $this->table())
    ->nullOnDelete();
```

### Миграции изменения таблицы (alter)

```php
public function up(): void
{
    Schema::table($this->table(), function (Blueprint $table): void {
        $table->unsignedBigInteger('owner_id')->nullable()->after('creator_id');
        $table->foreign('owner_id', 'tickets_owner_id_foreign')
            ->references('id')
            ->on((new User())->getTable());
    });
}

private function table(): string
{
    return (new Ticket())->getTable();
}
```

## Именование таблиц

Таблицы именуются во множественном числе. При необходимости группировки — короткие префиксы (`meeting_`, `ticket_`). Имя всегда задаётся в `#[Table(name: '...')]` на модели.

## Создание модели и миграции

```bash
php artisan make:model ModelName -m --no-interaction
```

Сразу добавить `#[Table(name: 'table_name')]` на созданную модель, затем писать миграцию через паттерн выше.

## Текущее состояние в {{project_name}}

Существующие миграции (до внедрения этого паттерна) используют хардкод-строки. **При написании новых миграций — всегда применять паттерн через `getTable()`**. При редактировании старых миграций — при удобном случае приводить к новому стилю.
