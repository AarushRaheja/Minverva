// src/frontend/Shell.tsx
import { VideoPage } from "./VideoPage";
import { InputPredictionPage } from "./InputPredictionPage";

export function Shell() {
  return (
    <div>
      <nav>
        <a href="/videos">Video</a><br />
        <a href="/input_predictions">InputPrediction</a><br />
      </nav>
      <main>
        <VideoPage />
        <InputPredictionPage />
      </main>
    </div>
  );
}
