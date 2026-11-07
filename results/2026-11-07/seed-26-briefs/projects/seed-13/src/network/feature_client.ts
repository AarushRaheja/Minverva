// src/network/feature_client.ts
export type Feature = { id: number; title: string };

type NewFeature = Omit<Feature, "id">;

export async function listFeature(): Promise<Feature[]> {
  const res = await fetch("/api/features");
  return res.json();
}

export async function createFeature(payload: NewFeature): Promise<Feature> {
  const res = await fetch("/api/features", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
