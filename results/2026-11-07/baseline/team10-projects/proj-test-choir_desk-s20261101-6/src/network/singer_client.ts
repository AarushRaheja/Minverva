// src/network/singer_client.ts
export type Singer = { id: number; title: string };

type NewSinger = Omit<Singer, "id">;

export async function listSinger(): Promise<Singer[]> {
  const res = await fetch("/api/singers");
  return res.json();
}

export async function createSinger(payload: NewSinger): Promise<Singer> {
  const res = await fetch("/api/singers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
