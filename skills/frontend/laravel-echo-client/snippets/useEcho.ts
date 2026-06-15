// Source: anonymized production project
//
// Vue 3 composable: подписка на private-канал Laravel Echo с детерминированной
// отпиской в onUnmounted. Внизу — вариант для presence-канала и ref-count-обёртка
// для каналов, которые слушают несколько компонентов сразу.
//
// Backend объявляет broadcastAs(), напр. 'order.updated' -> на фронте слушаем
// '.order.updated' (с ведущей точкой). Имена каналов/событий — нейтральные.

import { onUnmounted, ref, type Ref } from "vue";

type OrderUpdatedPayload = { order_id: number };

/**
 * Подписка на private-канал заказа. Возвращает реактивные данные realtime.
 * Если Echo выключен (guest / disabled) — деградирует в no-op, не падает.
 */
export function useOrderRealtime(orderId: number): { lastUpdatedAt: Ref<number | null> } {
  const lastUpdatedAt = ref<number | null>(null);

  // Гард: Echo может быть не инициализирован (guest, broadcasting disabled).
  if (!window.echo || !orderId) {
    return { lastUpdatedAt };
  }

  const channelName = `order.${orderId}`;
  const channel = window.echo.private(channelName);

  // Именованный handler — иначе его нельзя точечно снять через stopListening.
  const onUpdated = (payload: OrderUpdatedPayload): void => {
    if (payload.order_id === orderId) {
      lastUpdatedAt.value = Date.now();
    }
  };

  // broadcastAs-имя слушаем с ведущей точкой.
  channel.listen(".order.updated", onUpdated);

  onUnmounted(() => {
    channel.stopListening(".order.updated", onUpdated);
    window.echo.leave(channelName);
  });

  return { lastUpdatedAt };
}

// --- Presence-канал: те же правила + список участников ---------------------

type PresenceUser = { id: number; name: string };

export function usePresenceRoom(roomId: number): { members: Ref<PresenceUser[]> } {
  const members = ref<PresenceUser[]>([]);

  if (!window.echo || !roomId) {
    return { members };
  }

  const channelName = `room.${roomId}`;

  window.echo
    .join(channelName)
    .here((users: PresenceUser[]) => {
      members.value = users;
    })
    .joining((user: PresenceUser) => {
      members.value.push(user);
    })
    .leaving((user: PresenceUser) => {
      members.value = members.value.filter((m) => m.id !== user.id);
    });

  onUnmounted(() => {
    window.echo.leave(channelName);
  });

  return { members };
}

// --- Ref-count для разделяемого канала -------------------------------------
//
// Если один канал слушают несколько компонентов одновременно, реальный leave()
// делаем только когда последний подписчик ушёл — иначе размонтирование одного
// компонента оборвёт realtime у остальных. acquire() возвращает dispose.

const sharedRefs = new Map<string, number>();
const sharedCleanups = new Map<string, () => void>();

export function acquireSharedChannel(
  channelName: string,
  eventName: string,
  handler: (payload: unknown) => void,
): () => void {
  if (!window.echo) {
    return () => {};
  }

  const next = (sharedRefs.get(channelName) ?? 0) + 1;
  sharedRefs.set(channelName, next);

  if (next === 1) {
    const channel = window.echo.private(channelName);
    channel.listen(eventName, handler);

    sharedCleanups.set(channelName, () => {
      channel.stopListening(eventName, handler);
      window.echo.leave(channelName);
    });
  }

  return (): void => {
    const count = (sharedRefs.get(channelName) ?? 1) - 1;

    if (count <= 0) {
      sharedCleanups.get(channelName)?.();
      sharedCleanups.delete(channelName);
      sharedRefs.delete(channelName);
    } else {
      sharedRefs.set(channelName, count);
    }
  };
}
