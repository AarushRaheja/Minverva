// src/frontend/TransactionPage.tsx
import { AuthRequired } from "./AuthRequired";

export const route = "/transactions";

type Row = { id: number; title: string };

export function TransactionPage() {
  return (
    <AuthRequired />
  );
}
