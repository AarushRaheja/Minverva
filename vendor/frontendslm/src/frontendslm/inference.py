"""Untouched-model inference adapters; imported inside GPU functions only."""
import json
import time
from pathlib import Path

from frontendslm.evidence import (
    compact_evidence,
    critic_output_schema,
    effective_verdict,
    validate_measured_critique,
)
from frontendslm.generation import component_manifest, split_thinking_tokens
from frontendslm.io import parse_json_response, sha256, write_json
from frontendslm.prompts import CRITIC_INSTRUCTIONS, architect_messages
from frontendslm.repair import (
    SourcePatch,
    UnitPatch,
    apply_source_patch,
    apply_unit_patch,
    component_repair_messages,
    repair_messages,
    unit_patch_schema,
    unit_repair_messages,
)
from frontendslm.schemas import Critique, validate_critique_references
from frontendslm.thinking import AfterThinkingLogitsProcessor, critic_decoding_parameters


def architect_decoding_parameters(*, repairing=False, patching=False, repair_decoding='greedy', output_mode='component'):
    if output_mode == 'thinking':
        if patching or repair_decoding != 'thinking-recommended':
            raise ValueError('Thinking output requires component generation and thinking-recommended decoding')
        # A declared resource bound for the development experiment; lower than
        # the vendor's 32,768 recommendation. Truncation stays a failed attempt.
        return {'max_new_tokens': 16384, 'do_sample': True,
                'temperature': 0.6, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0}
    if output_mode != 'component':
        raise ValueError('Unknown Architect output mode')
    if repair_decoding not in {'greedy', 'qwen-recommended'}:
        raise ValueError('Unknown repair decoding profile')
    if patching and repair_decoding != 'greedy':
        raise ValueError('Sampling profile is only supported for component repairs')
    parameters = {'max_new_tokens': 6144, 'do_sample': not repairing}
    if not repairing:
        parameters.update(temperature=0.2, top_p=0.9, repetition_penalty=1.05)
    elif not patching:
        parameters['repetition_penalty'] = 1.05
        if repair_decoding == 'qwen-recommended':
            parameters.update(do_sample=True, temperature=0.7, top_p=0.8, top_k=20, min_p=0.0)
    return parameters


def runtime_metadata(model, tokenizer, config):
    import subprocess

    import torch
    import transformers
    return {
        **config, "torch": torch.__version__, "transformers": transformers.__version__,
        "gpu": torch.cuda.get_device_name(), "cuda": torch.version.cuda,
        "chat_template_sha256": sha256(str(tokenizer.chat_template).encode()),
        "chat_template": tokenizer.chat_template,
        "model_config": model.config.to_dict(),
        "packages": subprocess.check_output(["python", "-m", "pip", "freeze"], text=True).splitlines(),
    }


def generate_architect(cases, baselines, config, output: Path, checkpoint):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(config["model"], revision=config["revision"], local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(config["model"], revision=config["revision"],
        dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa", local_files_only=True)
    model.eval()
    write_json(output / "architect_runtime.json", runtime_metadata(model, tokenizer, config))
    output_mode = config.get('output_mode', 'component')
    end_thinking_id = tokenizer.convert_tokens_to_ids('</think>') if output_mode == 'thinking' else None
    if output_mode == 'thinking' and tokenizer.convert_ids_to_tokens(end_thinking_id) != '</think>':
        raise ValueError('Thinking tokenizer does not expose the expected final-answer boundary')
    import xgrammar as xgr
    from xgrammar.contrib.hf import LogitsProcessor
    compiler = xgr.GrammarCompiler(xgr.TokenizerInfo.from_huggingface(tokenizer, vocab_size=model.config.vocab_size))
    patch_grammar = compiler.compile_json_schema(SourcePatch.model_json_schema())
    rows = []
    for baseline in baselines:
        for case in cases:
            if case.get("repair_baseline") and case["repair_baseline"] != baseline:
                continue
            path = output / baseline / case["id"] / "generation.json"
            if path.exists():
                rows.append(json.loads(path.read_text()))
                continue
            if time.monotonic() - started > 3300:
                raise TimeoutError("Architect phase reached its 55-minute compute bound; resume saved rows")
            set_seed(42)
            repairing = bool(case.get('repair_context'))
            patching = repairing and case.get('repair_strategy') == 'line'
            catalog = (case.get('repair_context') or {}).get('source_catalog') or {}
            unit_patching = bool(repairing and case.get('repair_strategy') == 'units' and
                                 catalog.get('nodes') and not catalog.get('diagnostics'))
            messages = (unit_repair_messages(case) if unit_patching else repair_messages(case) if patching
                        else component_repair_messages(case)) if repairing else architect_messages(case, baseline)
            inputs = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors="pt").to(model.device)
            torch.cuda.reset_peak_memory_stats()
            begin = time.monotonic()
            with torch.inference_mode():
                parameters = architect_decoding_parameters(repairing=repairing, patching=patching or unit_patching,
                    repair_decoding=case.get('repair_decoding', 'greedy'), output_mode=output_mode)
                if patching:
                    parameters['logits_processor'] = [LogitsProcessor(patch_grammar)]
                elif unit_patching:
                    parameters['logits_processor'] = [LogitsProcessor(compiler.compile_json_schema(unit_patch_schema(catalog)))]
                tokens = model.generate(**inputs, **parameters, pad_token_id=tokenizer.eos_token_id)
            torch.cuda.synchronize()
            elapsed = time.monotonic() - begin
            generated = tokens[0, inputs.input_ids.shape[1]:]
            raw = tokenizer.decode(generated, skip_special_tokens=True)
            row = {"case_id": case["id"], "baseline": baseline, "model": config, "seed": 42,
                "generation_parameters": {k: v for k, v in parameters.items() if k != 'logits_processor'},
                "prompt_sha256": sha256(json.dumps(messages, sort_keys=True).encode()), "messages": messages,
                "input_tokens": inputs.input_ids.shape[1], "output_tokens": len(generated), "seconds": elapsed,
                "tokens_per_second": len(generated) / elapsed,
                "peak_gpu_gib": torch.cuda.max_memory_allocated() / 2**30,
                "output_protocol": "thinking-component-v8" if output_mode == 'thinking' else "source-unit-patch-v7.1" if unit_patching else "line-patch-v5" if patching else "component-repair-v6" if repairing else "component-v2", "model_generated_files": ["src/App.tsx"],
                "host_supplied_files": ["src/index.css"], "planning_metadata": "host placeholder; not model-generated",
                "repair_decoding": case.get('repair_decoding', 'greedy') if repairing else None,
                "repair_strategy_fallback": 'No valid source units; complete-component repair' if repairing and case.get('repair_strategy') == 'units' and not unit_patching else None,
                "truncated": len(generated) >= parameters['max_new_tokens'], "raw": raw, "manifest": None, "error": None}
            try:
                if repairing:
                    source = case['repair_context']['previous_source']
                    row['repair_base_source'] = source
                    row['source_before_sha256'] = sha256(source.encode())
                if patching or unit_patching:
                    row['generation_parameters']['structured_decoding'] = 'xgrammar==0.2.8'
                    if row['truncated']:
                        raise ValueError('Patch exhausted its token budget')
                    patch = (UnitPatch if unit_patching else SourcePatch).model_validate(parse_json_response(raw))
                    row['patch'] = patch.model_dump()
                    manifest = apply_unit_patch(source, patch, catalog) if unit_patching else apply_source_patch(source, patch)
                    if unit_patching:
                        row['source_catalog'] = catalog
                    row['source_after_sha256'] = sha256(manifest.files['src/App.tsx'].encode())
                else:
                    final_answer = raw
                    if output_mode == 'thinking':
                        reasoning_ids, answer_ids = split_thinking_tokens(generated.tolist(), end_thinking_id)
                        final_answer = tokenizer.decode(answer_ids, skip_special_tokens=True)
                        row.update(reasoning_text=tokenizer.decode(reasoning_ids, skip_special_tokens=True),
                                   final_answer=final_answer, thinking_end_token_id=end_thinking_id,
                                   reasoning_output_tokens=len(reasoning_ids), answer_output_tokens=len(answer_ids))
                    manifest = component_manifest(final_answer, truncated=row["truncated"])
                    if repairing:
                        row['source_after_sha256'] = sha256(manifest.files['src/App.tsx'].encode())
                row["manifest"] = manifest.model_dump()
                for name, content in manifest.files.items():
                    target = path.parent / "source" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
            except (ValueError, TypeError) as error:
                row["error"] = str(error)
            write_json(path, row)
            checkpoint()
            rows.append(row)
            print(json.dumps({"stage": "architect", "baseline": baseline, "case": case["id"],
                "valid": row["manifest"] is not None, "tokens": len(generated), "seconds": round(elapsed, 2)}), flush=True)
    return rows


def generate_critiques(cases, baselines, config, output: Path, checkpoint):
    import torch
    import xgrammar as xgr
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, set_seed
    from xgrammar.contrib.hf import LogitsProcessor

    from frontendslm.prompts import CONTENT_REVIEW_INSTRUCTIONS
    started = time.monotonic()
    processor = AutoProcessor.from_pretrained(config["model"], revision=config["revision"], local_files_only=True)
    # Explicit pixel bounds keep visual token cost predictable, preserving separate views.
    processor.image_processor.size = {"shortest_edge": 65536, "longest_edge": 1048576}
    model = Qwen3VLForConditionalGeneration.from_pretrained(config["model"], revision=config["revision"],
        dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa", local_files_only=True)
    model.eval()
    write_json(output / "critic_runtime.json", runtime_metadata(model, processor.tokenizer, config))
    tokenizer_info = xgr.TokenizerInfo.from_huggingface(processor.tokenizer,
        vocab_size=model.config.text_config.vocab_size)
    compiler = xgr.GrammarCompiler(tokenizer_info)
    output_mode = config.get('output_mode', 'json')
    parameters = critic_decoding_parameters(output_mode)
    end_thinking_id = processor.tokenizer.convert_tokens_to_ids('</think>') if output_mode == 'thinking' else None
    if output_mode == 'thinking' and processor.tokenizer.convert_ids_to_tokens(end_thinking_id) != '</think>':
        raise ValueError('Thinking Critic tokenizer lacks the expected final-answer boundary')
    results = []
    for baseline in baselines:
        for case in cases:
            case_dir = output / baseline / case["id"]
            path = case_dir / "critique.json"
            if path.exists():
                results.append(json.loads(path.read_text()))
                continue
            evidence_path = case_dir / "render/evidence.json"
            if not evidence_path.exists():
                continue
            if time.monotonic() - started > 3300:
                raise TimeoutError("Critic phase reached its 55-minute compute bound")
            evidence = json.loads(evidence_path.read_text())
            content = []
            images = []
            for view in ("desktop", "mobile"):
                if view in evidence.get("screenshots", {}):
                    image_path = case_dir / "render" / evidence["screenshots"][view]
                    images.append(Image.open(image_path).convert("RGB"))
                    content += [{"type": "text", "text": f"Screenshot reference: {view}"}, {"type": "image", "image": images[-1]}]
            explicit_review = config.get('explicit_content_review', False)
            compact = compact_evidence(evidence, case["tests"], explicit_content_review=explicit_review)
            decode_schema = critic_output_schema(compact)
            grammar = compiler.compile_json_schema(decode_schema)
            payload = {"specification": case["spec"], "evidence": compact, "output_schema": decode_schema}
            content.append({"type": "text", "text": json.dumps(payload, ensure_ascii=False)})
            instructions = CRITIC_INSTRUCTIONS + ('\n' + CONTENT_REVIEW_INSTRUCTIONS if explicit_review else '')
            input_contract = {'instructions': instructions, 'payload': payload,
                'image_sha256': {v: sha256((case_dir / 'render' / evidence['screenshots'][v]).read_bytes())
                                 for v in ('desktop', 'mobile') if v in evidence.get('screenshots', {})}}
            write_json(case_dir / 'critic_input.json', input_contract)
            messages = [{"role": "system", "content": instructions}, {"role": "user", "content": content}]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=images or None, return_tensors="pt", padding=True).to(model.device)
            set_seed(42)
            torch.cuda.reset_peak_memory_stats()
            begin = time.monotonic()
            grammar_processor = LogitsProcessor(grammar)
            if output_mode == 'thinking':
                grammar_processor = AfterThinkingLogitsProcessor(grammar_processor,
                    prompt_length=inputs.input_ids.shape[1], end_thinking_id=end_thinking_id)
            with torch.inference_mode():
                tokens = model.generate(**inputs, **parameters, logits_processor=[grammar_processor])
            torch.cuda.synchronize()
            elapsed = time.monotonic() - begin
            generated = tokens[0, inputs.input_ids.shape[1]:]
            raw = processor.decode(generated, skip_special_tokens=True)
            result = {"case_id": case["id"], "baseline": baseline, "model": config, "raw": raw,
                "schema_valid": False, "critique": None, "reference_checks": [], "error": None,
                "measured_checks": compact["measured_checks"], "measurement_validation": None,
                "measurement_enforcement": "schema-required issues and verdict; not independent model detection",
                "evidence_sha256": sha256(evidence_path.read_bytes()),
                "input_contract_sha256": sha256(json.dumps(input_contract, sort_keys=True).encode()),
                "seconds": elapsed, "input_tokens": inputs.input_ids.shape[1], "output_tokens": len(generated),
                "peak_gpu_gib": torch.cuda.max_memory_allocated() / 2**30,
                "generation_parameters": {**parameters, "seed": 42,
                    "structured_decoding": "xgrammar==0.2.8", "output_schema": decode_schema,
                    "constraint_phase": "after_thinking" if output_mode == 'thinking' else 'whole_answer'},
                "output_protocol": "thinking-critic-v1" if output_mode == 'thinking' else 'constrained-critic',
                "truncated": len(generated) >= parameters['max_new_tokens'],
                "images": [v for v in ("desktop", "mobile") if v in evidence.get("screenshots", {})],
                "image_processor": processor.image_processor.to_dict(), "prompt": text,
                "human_grounding_precision": None, "human_grounding_recall": None}
            critique = None
            try:
                final_answer = raw
                if output_mode == 'thinking':
                    reasoning_ids, answer_ids = split_thinking_tokens(generated.tolist(), end_thinking_id)
                    final_answer = processor.decode(answer_ids, skip_special_tokens=True)
                    result.update(reasoning_text=processor.decode(reasoning_ids, skip_special_tokens=True),
                                  final_answer=final_answer, thinking_end_token_id=end_thinking_id,
                                  reasoning_output_tokens=len(reasoning_ids), answer_output_tokens=len(answer_ids))
                if result['truncated']:
                    raise ValueError('Critic exhausted its token budget; partial verdicts are not accepted')
                critique = Critique.model_validate(parse_json_response(final_answer))
                result.update(schema_valid=True, critique=critique.model_dump(),
                    reference_checks=validate_critique_references(critique, compact),
                    measurement_validation=validate_measured_critique(critique, compact))
            except (ValueError, TypeError) as error:
                result["error"] = str(error)
            result["effective_verdict"] = effective_verdict(critique, compact["measured_checks"],
                                                           result["measurement_validation"])
            write_json(path, result)
            checkpoint()
            results.append(result)
            print(json.dumps({"stage": "critic", "baseline": baseline, "case": case["id"],
                "valid": result["schema_valid"], "seconds": round(elapsed, 2)}), flush=True)
    # Processor settings contain Pillow IntEnums. Return only JSON primitives so
    # the local coordinator does not need GPU/image-processing dependencies.
    return json.loads(json.dumps(results))
