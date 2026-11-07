// src/network/belay_check_client.ts
export type BelayCheck = { id: number; title: string };

type NewBelayCheck = Omit<BelayCheck, "id">;

export async function listBelayCheck(): Promise<BelayCheck[]> {
  const res = await fetch("/api/belay_checks");
  return res.json();
}

export async function createBelayCheck(payload: NewBelayCheck): Promise<BelayCheck> {
  const res = await fetch("/api/belay_checks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
