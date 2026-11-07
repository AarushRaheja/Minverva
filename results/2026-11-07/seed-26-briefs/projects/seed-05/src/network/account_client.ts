// src/network/account_client.ts
export type Account = { id: number; title: string };

type NewAccount = Omit<Account, "id">;

export async function listAccount(): Promise<Account[]> {
  const res = await fetch("/api/accounts");
  return res.json();
}

export async function createAccount(payload: NewAccount): Promise<Account> {
  const res = await fetch("/api/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
