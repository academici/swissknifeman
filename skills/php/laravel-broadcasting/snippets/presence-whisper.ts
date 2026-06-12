// Source: anonymized production Laravel project

// Presence-канал: список «кто онлайн» + whisper (клиент-клиент без сервера).
// Серверная авторизация presence-канала ОБЯЗАНА вернуть массив данных
// пользователя (см. channels.php), иначе here/joining не сработают.

interface Member {
    id: number;
    name: string;
}

const channel = window.Echo.join(`warehouse.${warehouseId}`)
    // Полный список участников при подключении.
    .here((members: Member[]) => {
        console.log('online:', members.map((m) => m.name));
    })
    // Кто-то присоединился.
    .joining((member: Member) => {
        console.log('joined:', member.name);
    })
    // Кто-то вышел.
    .leaving((member: Member) => {
        console.log('left:', member.name);
    })
    .error((error: unknown) => {
        console.error('presence auth failed', error);
    });

// --- Whisper: эфемерные события между клиентами ---
// Работает только на private/presence каналах, не проходит через Laravel —
// идеально для typing-индикаторов и позиций курсора.

// Отправка (например, по input-событию, с debounce):
channel.whisper('typing', {
    userId: currentUserId,
    name: currentUserName,
});

// Приём у остальных участников:
channel.listenForWhisper('typing', (e: { userId: number; name: string }) => {
    showTypingIndicator(e.name);
});

// Покинуть канал (например, при unmount компонента):
// window.Echo.leave(`warehouse.${warehouseId}`);
