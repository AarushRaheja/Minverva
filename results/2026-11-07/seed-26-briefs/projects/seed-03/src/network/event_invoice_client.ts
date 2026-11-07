// src/network/event_invoice_client.ts
export type EventInvoice = { id: number; title: string };

type NewEventInvoice = Omit<EventInvoice, "id">;

export async function listEventInvoice(): Promise<EventInvoice[]> {
  const res = await fetch("/api/event_invoices");
  return res.json();
}

export async function createEventInvoice(payload: NewEventInvoice): Promise<EventInvoice> {
  const res = await fetch("/api/event_invoices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}
