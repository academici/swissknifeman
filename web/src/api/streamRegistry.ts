const closers = new Set<() => void>();

export function trackSubscription(subscription: { close(): void }): { close(): void } {
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    closers.delete(close);
    subscription.close();
  };
  closers.add(close);
  return { close };
}

export function closeAllStreams(): void {
  for (const close of [...closers]) close();
}
