// src/frontend/OrderBookForm.tsx
import { createOrderBook } from "../network/order_book_client";

export function OrderBookForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createOrderBook({ title: "new order_book" });
      }}
    >
      <input name="title" placeholder="OrderBook title" />
      <button type="submit">Save</button>
    </form>
  );
}
