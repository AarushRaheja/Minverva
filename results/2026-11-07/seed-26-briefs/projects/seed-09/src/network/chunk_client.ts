// src/network/chunk_client.ts
export type Chunk = { id: number; title: string };

type NewChunk = Omit<Chunk, "id">;

export async function listChunk(): Promise<Chunk[]> {
  const res = await fetch("/api/chunks");
  return res.json();
}

export async function createChunk(payload: NewChunk): Promise<Chunk> {
  const res = await fetch("/api/chunks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
