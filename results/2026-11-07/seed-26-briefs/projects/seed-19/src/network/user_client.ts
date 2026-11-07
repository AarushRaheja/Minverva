// src/network/user_client.ts
export type User = { id: number; title: string };

type NewUser = Omit<User, "id">;

export async function listUser(): Promise<User[]> {
  const res = await fetch("/api/users");
  return res.json();
}

export async function createUser(payload: NewUser): Promise<User> {
  const res = await fetch("/api/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
