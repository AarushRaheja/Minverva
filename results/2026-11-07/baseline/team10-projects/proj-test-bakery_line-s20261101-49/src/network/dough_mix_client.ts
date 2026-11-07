// src/network/dough_mix_client.ts
export type DoughMix = { id: number; title: string };

type NewDoughMix = Omit<DoughMix, "id">;

export async function listDoughMix(): Promise<DoughMix[]> {
  const res = await fetch("/api/dough_mixes");
  return res.json();
}

export async function createDoughMix(payload: NewDoughMix): Promise<DoughMix> {
  const res = await fetch("/api/dough_mixes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
