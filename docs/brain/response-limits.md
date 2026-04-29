# Per-Brain Response Limits

`data/{brain_id}/config.json` can limit that brain's normal chat replies:

```json
{
  "response": {
    "max_tokens": 180,
    "max_sentences": 1
  }
}
```

- `max_tokens`: passed to the model request for this brain. Use `null` or remove it to keep the model default.
- `max_sentences`: trims the assistant reply after this many sentence endings. Use `null`, `0`, or remove it to disable sentence trimming.
