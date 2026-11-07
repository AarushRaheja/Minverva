// src/frontend/SingerForm.tsx
import { createSinger } from "../network/singer_client";

export function SingerForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createSinger({ title: "new singer" });
      }}
    >
      <input name="title" placeholder="Singer title" />
      <button type="submit">Save</button>
    </form>
  );
}
