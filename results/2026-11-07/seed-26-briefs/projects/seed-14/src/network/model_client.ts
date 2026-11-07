// src/network/model_client.ts
export type Model = { id: number; title: string };

type NewModel = Omit<Model, "id">;

export async function listModel(): Promise<Model[]> {
  const res = await fetch("/api/models");
  return res.json();
}

export async function createModel(payload: NewModel): Promise<Model> {
  const res = await fetch("/api/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
