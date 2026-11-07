// src/network/device_client.ts
export type Device = { id: number; title: string };

type NewDevice = Omit<Device, "id">;

export async function listDevice(): Promise<Device[]> {
  const res = await fetch("/api/devices");
  return res.json();
}

export async function createDevice(payload: NewDevice): Promise<Device> {
  const res = await fetch("/api/devices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
