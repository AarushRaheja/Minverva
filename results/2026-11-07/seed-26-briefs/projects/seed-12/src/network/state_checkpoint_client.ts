// src/network/state_checkpoint_client.ts
export type StateCheckpoint = { id: number; title: string };

export type NewStateCheckpoint = Omit<StateCheckpoint, "id">;

export async function listStateCheckpoint(): Promise<StateCheckpoint[]> {
  const res = await fetch("/api/state_checkcases");
  return res.json();
}

export async function createStateCheckpoint(payload: NewStateCheckpoint): Promise<StateCheckpoint> {
  const res = await fetch("/api/state_checkcases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
