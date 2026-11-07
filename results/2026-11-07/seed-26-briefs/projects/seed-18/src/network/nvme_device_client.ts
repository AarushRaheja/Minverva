// src/network/nvme_device_client.ts
export type NvmeDevice = { id: number; title: string };

type NewNvmeDevice = Omit<NvmeDevice, "id">;

export async function listNvmeDevice(): Promise<NvmeDevice[]> {
  const res = await fetch("/api/nvme_devices");
  return res.json();
}

export async function createNvmeDevice(payload: NewNvmeDevice): Promise<NvmeDevice> {
  const res = await fetch("/api/nvme_devices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
