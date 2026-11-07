// src/network/domain_client.ts
export type Domain = { id: number; title: string };

type NewDomain = Omit<Domain, "id">;

export async function listDomain(): Promise<Domain[]> {
  const res = await fetch("/api/domains");
  return res.json();
}

export async function createDomain(payload: NewDomain): Promise<Domain> {
  const res = await fetch("/api/domains", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
