# Laravel Actions

## Концепция

**Action** — единственная точка входа в use-case. Одна операция, одна транзакция.

- `final readonly class` (всегда)
- Один публичный `execute()` — принимает Command DTO, возвращает Domain object
- `DB::transaction()` оборачивает всю мутацию
- Не принимает `Illuminate\Http\Request`

## Нейминг

| Артефакт | Шаблон | Пример |
|:---|:---|:---|
| Action класс | `VerbNounAction` | `StoreAction`, `RegisteredAction`, `WrittenReplyAction` |
| Command DTO | `VerbNounCommand` | `StoreCommand`, `WrittenReplyCommand` |

## Расположение файлов

```
app/Actions/<Domain>/<Subprocess>/VerbNounAction.php
app/Dto/Actions/<Domain>/<Subprocess>/VerbNounCommand.php
```

Пример для ticket-домена:
```
app/Actions/Ticket/Common/StoreAction.php
app/Actions/Ticket/Question/WrittenReplyAction.php
app/Dto/Actions/Ticket/Common/StoreCommand.php
app/Dto/Actions/Ticket/Question/WrittenReplyCommand.php
```

## Шаблон Action

```php
<?php

declare(strict_types=1);

namespace App\Actions\Ticket\Common;

use App\Dto\Actions\Ticket\Common\StoreCommand;
use App\Models\Ticket\Ticket;
use App\Repositories\Ticket\TicketStoreRepository;
use App\Services\Ticket\NotificationService;
use Illuminate\Support\Facades\DB;

final readonly class StoreAction
{
    public function __construct(
        private TicketStoreRepository $storeRepository,
        private NotificationService $notificationService,
    ) {}

    public function execute(StoreCommand $command): Ticket
    {
        return DB::transaction(function () use ($command): Ticket {
            $ticket = $this->storeRepository->create(command: $command);

            $this->notificationService->notifyCreated(
                ticket: $ticket,
                user: $command->user,
            );

            return $ticket;
        });
    }
}
```

## Шаблон Command DTO

```php
<?php

declare(strict_types=1);

namespace App\Dto\Actions\Ticket\Common;

use App\Dto\Ticket\Form\Form;
use App\Models\User\User;

final readonly class StoreCommand
{
    public function __construct(
        public Form $form,
        public User $user,
        public bool $syncParticipants = true,
    ) {}

    public static function fromRequest(StoreRequest $request): self
    {
        return new self(
            form: Form::fromRequest(request: $request),
            user: $request->user(),
        );
    }
}
```

## Composite Action

Когда сценарий состоит из нескольких атомарных шагов — Action составляется из других Actions. **Не через Service-оркестратор.**

```php
final readonly class RegisterStoreAction
{
    public function __construct(
        private StoreAction $storeAction,
        private RegisteredAction $registeredAction,
    ) {}

    public function execute(RegisterStoreCommand $command): Ticket
    {
        return DB::transaction(function () use ($command): Ticket {
            $ticket = $this->storeAction->execute(command: $command->storeCommand);

            return $this->registeredAction->execute(
                command: new RegisteredCommand(ticket: $ticket, user: $command->user),
            );
        });
    }
}
```

## Правила транзакций

1. **Action** = единственная транзакционная граница use-case.
2. `Service`, `StateMachine`, `*StoreRepository` работают **внутри** уже открытой транзакции Action.
3. Доменные события — `ShouldDispatchAfterCommit` (публикуются после commit, не до).
4. Самостоятельная транзакция в Service — только для автономных integration/batch сценариев (не ticket use-case).

## Нарушения бизнес-правил

```php
// Бросать ValidationException, не abort()
throw ValidationException::withMessages([
    'status' => 'Переход из текущего статуса невозможен.',
]);
```

## Архитектурные guardrails (тесты)

Контрактные тесты защищают структуру Actions:
- Action класс должен быть `final`
- Один публичный метод `execute()`
- `execute()` не принимает `Request`
