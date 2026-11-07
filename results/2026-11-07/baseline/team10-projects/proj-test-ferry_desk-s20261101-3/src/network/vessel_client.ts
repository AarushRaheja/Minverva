// src/network/vessel_client.ts
export type Vessel = { id: number; title: string };

type NewVessel = Omit<Vessel, "id">;

export async function listVessel(): Promise<Vessel[]> {
  const res = await fetch("/api/vessels");
  return res.json();
}

export async function createVessel(payload: NewVessel): Promise<Vessel> {
  const res = await fetch("/api/vessels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
