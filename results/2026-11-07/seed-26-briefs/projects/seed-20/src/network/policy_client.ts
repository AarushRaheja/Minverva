// src/network/policy_client.ts
export type Policy = { id: number; title: string };

type NewPolicy = Omit<Policy, "id">;

export async function listPolicy(): Promise<Policy[]> {
  const res = await fetch("/api/policys");
  return res.json();
}

export async function createPolicy(payload: NewPolicy): Promise<Policy> {
  const res = await fetch("/api/policys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
