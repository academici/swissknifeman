// Golden shared primitives

export type Uuid = string & { readonly __brand: "Uuid" };
export type IsoDateTime = string & { readonly __brand: "IsoDateTime" };
