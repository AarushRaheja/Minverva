// src/network/entry_client.ts
export type Entry = { id: number; title: string };

export async function listEntry(): Promise<Entry[]> {
  const res = await fetch("/api/entities");
  return res.json();
}

export async function createEntry(payload: NewEntry): Promise<Entry> {
  const res = await fetch("/api/entities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
