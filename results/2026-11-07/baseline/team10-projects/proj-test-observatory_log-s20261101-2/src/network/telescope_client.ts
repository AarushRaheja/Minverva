// src/network/telescope_client.ts
export type Telescope = { id: number; title: string };

type NewTelescope = Omit<Telescope, "id">;

export async function listTelescope(): Promise<Telescope[]> {
  const res = await fetch("/api/telescopes");
  return res.json();
}

export async function createTelescope(payload: NewTelescope): Promise<Telescope> {
  const res = await fetch("/api/telescopes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
