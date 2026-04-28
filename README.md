# smalllocalLLMs

Live model catalog for the **Youme** iOS app — a list of small local LLMs that can run on iPhone via [MLX Swift](https://github.com/ml-explore/mlx-swift).

The Youme app fetches `models.json` from this repo on every cold launch (with a one-hour cooldown) and uses it as the catalog shown in **Settings → Choose model**. The bundled in-app catalog is a fallback for offline first launches.

## Editing the catalog

`models.json` is the source of truth. To add or update a model, edit it and push to `main`. App users will pick up the change on their next cold launch.

### Schema

```json
{
  "schemaVersion": 1,
  "models": [
    {
      "id": "mlx-community/Qwen2.5-3B-Instruct-4bit",
      "displayName": "Qwen 2.5 3B",
      "family": "Qwen",
      "paramCount": "3B",
      "contextWindow": "32K",
      "releaseDate": "Sep 2024",
      "bestFor": "Strongest general model.",
      "approxSizeBytes": 1800000000,
      "minRamGB": 7.5,
      "licenseLabel": "Apache 2.0"
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | The HuggingFace repo identifier — must point at an MLX-compatible 4-bit quant. Used as the cache key and for `MLXLLM.ModelConfiguration(id:)`. |
| `displayName` | string | What users see in the picker. |
| `family` | string | Used to group rows in the picker. Conventionally: `"Qwen"`, `"Llama"`, `"Phi"`, `"SmolLM"`. |
| `paramCount` | string | Display-only. Free-form, e.g. `"3B"`, `"1.5B"`, `"360M"`. |
| `contextWindow` | string | Display-only, e.g. `"32K"`, `"128K"`. |
| `releaseDate` | string | Display-only, e.g. `"Sep 2024"`. Not parsed. |
| `bestFor` | string | One short sentence shown under the model name. |
| `approxSizeBytes` | integer | Pre-download size estimate, in bytes. |
| `minRamGB` | number | Minimum device RAM for the model to fit. The picker computes compatibility from this against device physical memory. |
| `licenseLabel` | string | Short license name shown in the meta line, e.g. `"Apache 2.0"`, `"MIT"`. |

### Schema versioning

`schemaVersion` is a top-level integer. The app currently understands `1`. If a future schema change breaks back-compat, bump to `2`; older app builds will ignore the manifest and fall back to whatever version they bundled, which is fine.

### Validation rules (enforced by the app)

A manifest is rejected (and the app falls back to its previous cache or the bundled catalog) if any of these fail:

- `schemaVersion` is missing or not equal to `1`.
- `models` is missing, not an array, or empty.
- Any entry is missing a required field.
- Any string field is empty.
- Any `id` is duplicated.
- The JSON itself doesn't parse.

### Adding a new model

1. Find an MLX-compatible 4-bit quant on HuggingFace (`mlx-community/<family>-<size>-Instruct-4bit` is the usual pattern).
2. Verify it loads with the MLX-Swift `LLMModelFactory`.
3. Add an entry to the `models` array. Keep `family` consistent with existing values so it groups under the right header.
4. Commit + push to `main`. App users get the new entry on their next cold launch.

### Removing a model

Remove the entry from `models.json`. App users who previously selected that model will fall back to whatever `ModelCatalog.recommended(...)` returns for their device on the next launch.

## License

The contents of this repo (the manifest itself, this README) are released under the MIT license. Each model listed in `models.json` retains its own license — see the `licenseLabel` field for each entry.
