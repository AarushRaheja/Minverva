"""Modal compute for the design-intent and visual-rubric phases."""
from pathlib import Path

import modal

from modal_app import gpu_image, results, weights

app = modal.App('frontendslm-design-evaluation')
image = gpu_image.add_local_python_source('design', 'modal_app')


@app.function(image=image, gpu='L40S', cpu=2, memory=16384, volumes={'/models': weights, '/results': results},
              timeout=3600, retries=0, max_containers=1, scaledown_window=2)
def intent_batch(jobs: list[dict], preferences: dict, config: dict, run_id: str):
    from design.inference import interpret_intents
    weights.reload()
    results.reload()
    return interpret_intents(jobs, preferences, config, Path('/results') / run_id, results.commit)


@app.function(image=image, gpu='L40S', cpu=2, memory=16384, volumes={'/models': weights, '/results': results},
              timeout=3600, retries=0, max_containers=1, scaledown_window=2)
def visual_batch(jobs: list[dict], rubric: dict, preferences: dict, config: dict, run_id: str):
    from design.inference import assess_visuals
    weights.reload()
    results.reload()
    return assess_visuals(jobs, rubric, preferences, config, Path('/results') / run_id, results.commit)
