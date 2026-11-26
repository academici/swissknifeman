const unsafeCharacters = /[\p{Cc}\u200e\u200f\u202a-\u202e\u2066-\u2069\\]/u;

export interface SafeDestination {
  href: string;
  origin: string | null;
}

export function sanitizeLink(value: string): SafeDestination | null {
  if (!value || /\s/u.test(value) || unsafeCharacters.test(value)) return null;

  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return null;
  }
  if (unsafeCharacters.test(decoded)) return null;

  if (value.startsWith("/")) {
    return decoded.startsWith("//") ? null : { href: value, origin: null };
  }
  if (!/^https?:\/\/[^/]/iu.test(value)) return null;

  try {
    const url = new URL(value);
    if (url.username || url.password) return null;
    return { href: url.href, origin: url.origin };
  } catch {
    return null;
  }
}
