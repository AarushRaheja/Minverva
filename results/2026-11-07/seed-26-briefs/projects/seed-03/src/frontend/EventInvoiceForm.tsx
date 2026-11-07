// src/frontend/EventInvoiceForm.tsx
import { createEventInvoice } from "../network/event_invoice_client";

export function EventInvoiceForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createEventInvoice({ title: "new event_invoice" });
      }}
    >
      <input name="title" placeholder="EventInvoiceForm title" />
      <button type="submit">Save</button>
    </form>
  );
}
