// src/network/bucket_client.ts
export type Bucket = { id: number; title: string };

type NewBucket = Omit<Bucket, "id">;

export async function listBucket(): Promise<Bucket[]> {
  const res = await fetch("/api/buckets");
  return res.json();
}

export async function createBucket(payload: NewBucket): Promise<Bucket> {
  const res = await fetch("/api/buckets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
