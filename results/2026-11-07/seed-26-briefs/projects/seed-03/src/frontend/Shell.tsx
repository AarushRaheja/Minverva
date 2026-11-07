// src/frontend/Shell.tsx
import { EventInvoicePage } from "./EventInvoicePage";
import { TransactionPage } from "./TransactionPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/event_invoices">EventInvoice</a><br />
        <a href="/transactions">Transaction</a><br />
      </nav>
      <main>
        <EventInvoicePage />
        <TransactionPage />
      </main>
    </div>
  );
}
