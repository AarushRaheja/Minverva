// src/network/cep_task_client.ts
export type CepTask = { id: number; title: string };

type NewCepTask = Omit<CepTask, "id">;

export async function listCepTask(): Promise<CepTask[]> {
  const res = await fetch("/api/cep_tasks");
  return res.json();
}

export async function createCepTask(payload: NewCepTask): Promise<CepTask> {
  const res = await fetch("/api/cep_tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
