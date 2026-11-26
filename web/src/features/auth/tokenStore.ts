const tokenKey = "skm.token";

export const tokenStore = {
  get(): string | null {
    return sessionStorage.getItem(tokenKey);
  },

  set(token: string): void {
    sessionStorage.setItem(tokenKey, token);
  },

  clear(): void {
    sessionStorage.removeItem(tokenKey);
  },

  ingestFragment(): string | null {
    const { hash, pathname, search } = window.location;
    if (hash.startsWith("#token=")) {
      try {
        const token = new URLSearchParams(hash.slice(1)).get("token");
        if (token) tokenStore.set(token);
      } finally {
        history.replaceState(null, "", pathname + search);
      }
    }
    return tokenStore.get();
  },
};
