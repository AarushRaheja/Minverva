// src/network/table_town_client.ts
export type TableTown = { id: number; title: string };

type NewTableTown = Omit<TableTown, "id">;

export async function listTableTown(): Promise<TableTown[]> {
  const res = await fetch("/api/table_towns");
  return res.json();
}

export async function createTableTown(payload: NewTableTown): Promise<TableTown> {
  const res = await fetch("/api/table_towns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
