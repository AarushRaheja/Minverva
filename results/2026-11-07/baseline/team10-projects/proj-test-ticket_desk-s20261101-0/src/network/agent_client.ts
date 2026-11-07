// src/network/agent_client.ts
export type Agent = { id: number; title: string };

type NewAgent = Omit<Agent, "id">;

export async function listAgent(): Promise<Agent[]> {
  const res = await fetch("/api/agents");
  return res.json();
}

export async function createAgent(payload: NewAgent): Promise<Agent> {
  const res = await fetch("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
