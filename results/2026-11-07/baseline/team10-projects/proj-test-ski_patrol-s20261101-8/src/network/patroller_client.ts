// src/network/patroller_client.ts
export type Patroller = { id: number; title: string };

type NewPatroller = Omit<Patroller, "id">;

export async function listPatroller(): Promise<Patroller[]> {
  const res = await fetch("/api/patrollers");
  return res.json();
}

export async function createPatroller(payload: NewPatroller): Promise<Patroller> {
  const res = await fetch("/api/patrollers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
