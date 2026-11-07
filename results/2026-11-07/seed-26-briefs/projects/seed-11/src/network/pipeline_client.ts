// src/network/pipeline_client.ts
export type Pipeline = { id: number; title: string };

type NewPipeline = Omit<Pipeline, "id">;

export async function listPipeline(): Promise<Pipeline[]> {
  const res = await fetch("/api/pipelines");
  return res.json();
}

export async function createPipeline(payload: NewPipeline): Promise<Pipeline> {
  const res = await fetch("/api/pipelines", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
