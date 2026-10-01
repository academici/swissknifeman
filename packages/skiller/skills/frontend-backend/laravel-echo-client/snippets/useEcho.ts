// Source: anonymized production project
//
// Vue 3 composable: subscription to private-channel Laravel Echo with deterministic
// unsubscribe to onUnmounted. Below is an option for presence-channel and ref-count-wrapper
// for channels that listen to multiple components at once.
//
// Backend announces broadcastAs(), e.g. 'order.updated' -> at the front listening
// '.order.updated' (with leading dot). Channel names/events are neutral.

import { onUnmounted, ref, type Ref } from "vue";

type OrderUpdatedPayload = { order_id: number };

/**
 * Subscribe to private-order channel. Returns reactive data realtime.
 * If Echo disabled (guest / disabled) — degrades into no-op, does not crash.
 */
export function useOrderRealtime(orderId: number): { lastUpdatedAt: Ref<number | null> } {
  const lastUpdatedAt = ref<number | null>(null);

  // Guard: Echo may not be initialized (guest, broadcasting disabled).
  if (!window.echo || !orderId) {
    return { lastUpdatedAt };
  }

  const channelName = `order.${orderId}`;
  const channel = window.echo.private(channelName);

  // Named handler — otherwise it cannot be removed pointwise through stopListening.
  const onUpdated = (payload: OrderUpdatedPayload): void => {
    if (payload.order_id === orderId) {
      lastUpdatedAt.value = Date.now();
    }
  };

  // broadcastAs-name we listen with a leading dot.
  channel.listen(".order.updated", onUpdated);

  onUnmounted(() => {
    channel.stopListening(".order.updated", onUpdated);
    window.echo.leave(channelName);
  });

  return { lastUpdatedAt };
}

// --- Presence-channel: same rules + list of participants ---------------------

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

// --- Ref-count for shared channel -------------------------------------
//
// If several components listen to one channel at the same time, the real leave()
// do only when the last subscriber has left - otherwise unmounting one
// component will break realtime for the rest. acquire() returns dispose.

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
