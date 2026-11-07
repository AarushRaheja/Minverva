// src/network/telemetry_client.ts
export type Telemetry = { id: number; title: string };

export type NewTelemetry = Omit<Telemetry, "id">;

export async function listTelemetry(): Promise<Telemetry[]> {
  const res = await fetch("/api/telemetry");
  return res.json();
}

export async function createTelemetry(payload: NewTelemetry): Promise<Telemetry> {
  const res = await fetch("/api/telemetry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
