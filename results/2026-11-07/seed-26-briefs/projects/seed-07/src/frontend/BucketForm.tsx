// src/frontend/BucketForm.tsx
import { createBucket } from "../network/bucket_client";

export function BucketForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createBucket({ title: "new bucket" });
      }}
    >
      <input name="title" placeholder="Bucket title" />
      <button type="submit">Save</button>
    </form>
  );
}
