// src/frontend/Shell.tsx
import { OrderBookPage } from "./OrderBookPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/order_books">OrderBook</a><br />
      </nav>
      <main>
        <OrderBookPage />
      </main>
    </div>
  );
}
