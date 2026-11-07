// src/network/buffer_client.ts
export type Buffer = { id: number; title: string };

type NewBuffer = Omit<Buffer, "id">;

export async function listBuffer(): Promise<Buffer[]> {
  const res = await fetch("/api/buffers");
  return res.json();
}

export async function createBuffer(payload: NewBuffer): Promise<Buffer> {
  const res = await fetch("/api/buffers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
