// src/network/vintage_client.ts
export type Vintage = { id: number; title: string };

type NewVintage = Omit<Vintage, "id">;

export async function listVintage(): Promise<Vintage[]> {
  const res = await fetch("/api/vintages");
  return res.json();
}

export async function createVintage(payload: NewVintage): Promise<Vintage> {
  const res = await fetch("/api/vintages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
