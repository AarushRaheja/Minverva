// src/frontend/FeatureForm.tsx
import { createFeature } from "../network/feature_client";

export function FeatureForm() {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        createFeature({ title: "new feature" });
      }}
    >
      <input name="title" placeholder="Feature title" />
      <button type="submit">Save</button>
    </form>
  );
}
