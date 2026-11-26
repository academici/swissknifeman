const hiddenCharacters = /[\p{Cc}\p{Bidi_Control}]/gu;

export function escapeText(value: string): string {
  return value.replace(hiddenCharacters, (character) =>
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}
