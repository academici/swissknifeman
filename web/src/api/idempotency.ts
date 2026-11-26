import { useMutation } from "@tanstack/react-query";

export function newKey(): string {
  return `web-${crypto.randomUUID()}`;
}

interface Attempt<T> {
  readonly input: T;
  readonly key: string;
}

export function useIdempotentMutation<TInput, TOutput>(
  execute: (input: TInput, idempotencyKey: string) => Promise<TOutput>,
) {
  const mutation = useMutation({
    mutationFn: ({ input, key }: Attempt<TInput>) => execute(input, key),
    retry: false,
    networkMode: "always",
  });

  return {
    status: mutation.status,
    data: mutation.data,
    error: mutation.error,
    submit: (input: TInput) => mutation.mutate({ input, key: newKey() }),
    retry: () => {
      if (mutation.isError) mutation.mutate(mutation.variables);
    },
  };
}
