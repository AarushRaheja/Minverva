// src/network/manuscript_client.ts
export type Manuscript = { id: number; title: string };

type NewManuscript = Omit<Manuscript, "id">;

export async function listManuscript(): Promise<Manuscript[]> {
  const res = await fetch("/api/manuscripts");
  return res.json();
}

export async function createManuscript(payload: NewManuscript): Promise<Manuscript> {
  const res = await fetch("/api/manuscripts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
