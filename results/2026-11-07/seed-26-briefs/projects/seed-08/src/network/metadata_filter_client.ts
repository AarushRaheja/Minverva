// src/network/metadata_filter_client.ts
export type MetadataFilter = { id: number; title: string };

type NewMetadataFilter = Omit<MetadataFilter, "id">;

export async function listMetadataFilter(): Promise<MetadataFilter[]> {
  const res = await fetch("/api/metadata_filters");
  return res.json();
}

export async function createMetadataFilter(payload: NewMetadataFilter): Promise<MetadataFilter> {
  const res = await fetch("/api/metadata_filters", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
